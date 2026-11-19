"""문항별 해설 생성 (Claude Message Batches API, 50% 할인).

사용법:
  python pipeline/explain.py submit [--limit N]   # 해설 없는 문항을 배치로 제출
  python pipeline/explain.py collect              # 끝난 배치 결과를 받아 저장
  python pipeline/explain.py run                  # collect → submit → 끝날 때까지 대기 → collect

결과: web/public/data/explanations/{paperId}.json  →  {"<no>": {...}}
인증: 로컬은 ANTHROPIC_API_KEY, CI 는 Workload Identity Federation(.github/workflows/update.yml 참고).
"""
from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

import anthropic
import fitz
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"
EXPL = DATA / "explanations"
STATE = ROOT / "data" / "explain_state.json"
# API 로 자동 해설을 붙일 시험 (web/src/exams.json 의 autoExplain)
AUTO_EXPLAIN = {e["id"] for e in json.loads((ROOT / "web" / "src" / "exams.json").read_text())["exams"] if e.get("autoExplain")}
MODEL = "claude-opus-5-5"
CIRCLED = "①②③④⑤"

SYSTEM = """당신은 PSAT(공직적격성평가) 전문 강사입니다. 수험생이 스스로 채점한 뒤 읽는 해설을 씁니다.
- 공식 정답이 주어집니다. 정답을 바꾸거나 의심하지 말고, 그 정답이 왜 맞는지 근거를 보여주세요.
- 문제 이미지와 추출 텍스트를 함께 봅니다. 표·그래프 수치는 이미지를 우선합니다.
- 해설은 한국어로, 실제 시험장에서 쓸 수 있는 빠른 풀이 순서를 먼저 제시하고 계산·근거를 구체적으로 보여주세요.
- 선택지별 판단은 각 선택지가 왜 옳은지/틀린지 한두 문장으로 씁니다. <보기> 문제라면 ㄱ·ㄴ·ㄷ·ㄹ 각각의 판단을 explanation 안에 포함하세요.
- 수식은 일반 텍스트로(예: 120÷4=30). 마크다운은 굵게(**)와 목록(-)만 씁니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "key_point": {"type": "string", "description": "이 문제의 핵심 한 줄 (40자 이내)"},
        "explanation": {"type": "string", "description": "풀이 과정 해설"},
        "choices": {"type": "array", "items": {"type": "string"}, "description": "①~⑤ 각 선택지 판단 근거, 5개"},
        "tip": {"type": "string", "description": "시간 단축 요령 또는 함정 (없으면 빈 문자열)"},
    },
    "required": ["key_point", "explanation", "choices", "tip"],
    "additionalProperties": False,
}


def render_regions(pdf: fitz.Document, regions: list[dict]) -> list[str]:
    out = []
    for r in regions:
        page = pdf[r["page"]]
        pix = page.get_pixmap(clip=fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"]), dpi=150)
        out.append(base64.standard_b64encode(pix.tobytes("png")).decode())
    return out


def build_request(paper: dict, q: dict, pdf: fitz.Document) -> dict:
    content = []
    regions = (q.get("shared", {}).get("regions") or []) + q["regions"]
    for b64 in render_regions(pdf, regions):
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})
    ans = q["answer"]
    ans_txt = "모든 선택지 정답 처리" if len(ans) == 5 else ", ".join(CIRCLED[a - 1] for a in ans)
    text = (
        f"[{paper['year']}년 {'/'.join(paper['exams'])} PSAT {paper['subject']}영역 {q['no']}번]\n"
        f"공식 정답: {ans_txt}\n\n"
        + (f"[공통 지문 텍스트]\n{q['shared']['text']}\n\n" if q.get("shared") else "")
        + f"[문항 텍스트(PDF 추출, 표 구조가 깨져 있을 수 있음)]\n{q['text']}"
    )
    content.append({"type": "text", "text": text})
    return MessageCreateParamsNonStreaming(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"batches": [], "pending": []}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def existing(pid: str) -> dict:
    f = EXPL / f"{pid}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def submit(client: anthropic.Anthropic, limit: int | None) -> None:
    st = load_state()
    pending = set(st["pending"])
    reqs = []
    for f in sorted((DATA / "papers").glob("*.json")):
        paper = json.loads(f.read_text())
        if not paper.get("answersFinal", True):
            continue  # 정답 확정 후에 해설 생성
        if paper.get("exam", "psat") not in AUTO_EXPLAIN:
            continue  # API 자동 해설은 exams.json 에서 autoExplain 을 켠 시험만 (나머지는 단계별로 승인 후 진행)
        done = existing(paper["id"])
        pdf = None
        for q in paper["questions"]:
            cid = f"{paper['id']}__{q['no']}"
            if str(q["no"]) in done or cid in pending:
                continue
            pdf = pdf or fitz.open(DATA / "pdf" / f"{paper.get('pdf', paper['id'])}.pdf")
            reqs.append(Request(custom_id=cid, params=build_request(paper, q, pdf)))
            if limit and len(reqs) >= limit:
                break
        if limit and len(reqs) >= limit:
            break
    if not reqs:
        print("해설할 새 문항 없음")
        return
    # 배치 하나당 256MB 제한 → 1000건씩 나눠 제출
    for i in range(0, len(reqs), 1000):
        chunk = reqs[i : i + 1000]
        b = client.messages.batches.create(requests=chunk)
        st["batches"].append(b.id)
        st["pending"] += [r["custom_id"] for r in chunk]
        save_state(st)
        print(f"submitted {b.id}: {len(chunk)}건")


def collect(client: anthropic.Anthropic) -> bool:
    """끝난 배치를 반영. 아직 진행 중인 배치가 있으면 False."""
    st = load_state()
    remaining, all_done = [], True
    updates: dict[str, dict] = {}
    retry = []
    for bid in st["batches"]:
        b = client.messages.batches.retrieve(bid)
        if b.processing_status != "ended":
            remaining.append(bid)
            all_done = False
            continue
        for res in client.messages.batches.results(bid):
            pid, no = res.custom_id.rsplit("__", 1)
            if res.result.type == "succeeded":
                msg = res.result.message
                if msg.stop_reason != "end_turn":
                    retry.append(res.custom_id)
                    continue
                text = next((blk.text for blk in msg.content if blk.type == "text"), "")
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    retry.append(res.custom_id)
                    continue
                data["model"] = msg.model
                updates.setdefault(pid, {})[no] = data
            else:
                retry.append(res.custom_id)
        print(f"collected {bid}")
    EXPL.mkdir(parents=True, exist_ok=True)
    for pid, items in updates.items():
        cur = existing(pid)
        cur.update(items)
        (EXPL / f"{pid}.json").write_text(json.dumps(cur, ensure_ascii=False))
    done_ids = {f"{pid}__{no}" for pid, items in updates.items() for no in items}
    st["pending"] = [c for c in st["pending"] if c not in done_ids and c not in retry]
    st["batches"] = remaining
    save_state(st)
    n = sum(len(v) for v in updates.values())
    print(f"saved {n}건, 재시도 대상 {len(retry)}건 (다음 submit 때 다시 제출)")
    return all_done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["submit", "collect", "run"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    client = anthropic.Anthropic()
    if a.cmd == "submit":
        submit(client, a.limit)
    elif a.cmd == "collect":
        collect(client)
    else:
        collect(client)
        submit(client, a.limit)
        while not collect(client):
            time.sleep(120)


if __name__ == "__main__":
    main()
