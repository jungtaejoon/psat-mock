"""문항별 해설 생성 (Claude Message Batches API, 50% 할인).

사용법:
  python pipeline/explain.py submit [--limit N]   # 해설 없는 문항을 배치로 제출 (autoExplain 시험만)
  python pipeline/explain.py submit --queue --limit N  # 모든 시험에서 우선순위(expl_agent queue) 순으로 N문항
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

import sys

import anthropic
import fitz
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
DATA = ROOT / "web" / "public" / "data"
EXPL = DATA / "explanations"
STATE = ROOT / "data" / "explain_state.json"
# API 로 자동 해설을 붙일 시험 (web/src/exams.json 의 autoExplain)
AUTO_EXPLAIN = {e["id"] for e in json.loads((ROOT / "web" / "src" / "exams.json").read_text())["exams"] if e.get("autoExplain")}
MODEL = "claude-opus-5-5"
CIRCLED = "①②③④⑤"

# 배치 요금 (Opus 5.5, 50% 할인): 입력 $2 / 출력 $10 per MTok
PRICE_IN, PRICE_OUT = 2.0, 10.0

SYSTEM_GENERAL = """당신은 한국 공무원·국가자격시험 전문 강사입니다. 수험생이 스스로 채점한 뒤 읽는 해설을 씁니다.
- 공식 정답이 주어집니다. 정답을 바꾸거나 의심하지 말고, 그 정답이 왜 맞는지 근거(개념·법령 조문·판례·계산)를 구체적으로 보여주세요. 출제 이후 법령이 바뀌어 지금 기준과 다르면 "출제 당시 법령 기준 정답이며, 현재는 …"처럼 짧게 밝히되 사실을 지어내지 마세요.
- 문제 이미지와 글자 텍스트를 함께 봅니다. 그림·표 수치는 이미지를 우선합니다.
- 해설(explanation)은 한국어로 3~8문장. 「보기」/ㄱㄴㄷㄹ 문제는 각 항목의 옳고 그름을 모두 판단합니다. 영어 문제는 지문의 논리를 한국어로 설명하고 핵심 문장을 번역합니다.
- choices 에는 선택지마다 그 선택지가 왜 맞는지/틀린지 한두 문장씩, 선택지 수와 정확히 같은 개수로 씁니다.
- 과목의 법령·교과서 용어를 정확히 쓰고, 확실하지 않은 조문 번호는 적지 마세요. 정확성이 길이보다 중요합니다.
- 수식은 일반 텍스트로(예: 120÷4=30). 마크다운은 굵게(**)와 목록(-)만 씁니다."""

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
        "choices": {"type": "array", "items": {"type": "string"}, "description": "각 선택지 판단 근거, 선택지 수만큼"},
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


def nchoices(paper: dict, q: dict) -> int:
    return len(q.get("choices") or []) or paper.get("choices") or 4


def build_request(paper: dict, q: dict, pdf: fitz.Document, text_map: dict | None = None) -> dict:
    content = []
    regions = (q.get("shared", {}).get("regions") or []) + q["regions"]
    for b64 in render_regions(pdf, regions):
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})
    ans = q["answer"]
    nch = nchoices(paper, q)
    ans_txt = "모든 선택지 정답 처리" if len(ans) >= nch else ", ".join(CIRCLED[a - 1] for a in ans)
    if paper.get("exam", "psat") != "psat":
        from expl_agent import plain

        t = (text_map or {}).get(str(q["no"]))
        body = (plain(t["stem"]) + "\n" + "\n".join(f"{CIRCLED[i]} {plain(c)}" for i, c in enumerate(t.get("choices") or []))
                if t else (q.get("text") or "(텍스트 없음 — 이미지를 보세요)"))
        text = (f"[{paper['year']}년 {' / '.join(paper['exams'])} {paper['subject']} {q['no']}번, 선택지 {nch}개]\n"
                f"공식 정답: {ans_txt}\n\n[문항 텍스트]\n{body}")
        content.append({"type": "text", "text": text})
        return MessageCreateParamsNonStreaming(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_GENERAL,
            thinking={"type": "adaptive"},
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": content}],
        )
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


def api_id(cid: str) -> str:
    """배치 custom_id 는 영문·숫자·_- 64자까지만 → 문제지 id(한글 포함)를 해시로 바꾼다. 원래 id 는 상태 파일 ids 에 둔다"""
    import hashlib

    return "q" + hashlib.sha1(cid.encode()).hexdigest()[:40]


def load_state() -> dict:
    st = json.loads(STATE.read_text()) if STATE.exists() else {"batches": [], "pending": []}
    st.setdefault("ids", {})
    return st


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def existing(pid: str) -> dict:
    f = EXPL / f"{pid}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def queue_ids() -> list[str]:
    """expl_agent 와 같은 우선순위(공무원 공통과목 → 수요 큰 시험 → 최신 연도)로 해설이 빠진 문제지 id"""
    import contextlib
    import io

    import expl_agent

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        expl_agent.queue(100000)
    return buf.getvalue().split()


def submit(client: anthropic.Anthropic, limit: int | None, use_queue: bool = False) -> None:
    st = load_state()
    pending = set(st["pending"])
    reqs = []
    if use_queue:
        files = [DATA / "papers" / f"{pid}.json" for pid in queue_ids()]
    else:
        files = sorted((DATA / "papers").glob("*.json"))
    for f in files:
        paper = json.loads(f.read_text())
        if not paper.get("answersFinal", True):
            continue  # 정답 확정 후에 해설 생성
        if not use_queue and paper.get("exam", "psat") not in AUTO_EXPLAIN:
            continue  # 정기 실행은 exams.json 에서 autoExplain 을 켠 시험만 (나머지는 --queue 로 한도를 정해 돌린다)
        done = existing(paper["id"])
        tf = DATA / "text" / f"{paper['id']}.json"
        text_map = json.loads(tf.read_text()) if tf.exists() else {}
        pdf = None
        for q in paper["questions"]:
            cid = f"{paper['id']}__{q['no']}"
            if str(q["no"]) in done or cid in pending:
                continue
            pdf = pdf or fitz.open(DATA / "pdf" / f"{paper.get('pdf', paper['id'])}.pdf")
            reqs.append(Request(custom_id=api_id(cid), params=build_request(paper, q, pdf, text_map)))
            st["ids"][api_id(cid)] = cid
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
        st["pending"] += [st["ids"][r["custom_id"]] for r in chunk]
        save_state(st)
        print(f"submitted {b.id}: {len(chunk)}건")


_CH: dict[str, dict] = {}


def paper_choices(pid: str, no: str) -> int:
    if pid not in _CH:
        f = DATA / "papers" / f"{pid}.json"
        _CH[pid] = {str(q["no"]): nchoices(p, q) for p in [json.loads(f.read_text())] for q in p["questions"]} if f.exists() else {}
    return _CH[pid].get(str(no), 0)


def collect(client: anthropic.Anthropic) -> bool:
    """끝난 배치를 반영. 아직 진행 중인 배치가 있으면 False."""
    st = load_state()
    remaining, all_done = [], True
    updates: dict[str, dict] = {}
    retry = []
    usage = st.setdefault("usage", {"input": 0, "output": 0, "count": 0})
    for bid in st["batches"]:
        b = client.messages.batches.retrieve(bid)
        if b.processing_status != "ended":
            remaining.append(bid)
            all_done = False
            continue
        for res in client.messages.batches.results(bid):
            cid = st["ids"].pop(res.custom_id, res.custom_id)
            pid, no = cid.rsplit("__", 1)
            if res.result.type == "succeeded":
                msg = res.result.message
                u = msg.usage
                usage["input"] += (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
                usage["output"] += u.output_tokens or 0
                usage["count"] += 1
                if msg.stop_reason != "end_turn":
                    retry.append(cid)
                    continue
                text = next((blk.text for blk in msg.content if blk.type == "text"), "")
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    retry.append(cid)
                    continue
                if paper_choices(pid, no) and len(data.get("choices") or []) not in (0, paper_choices(pid, no)):
                    retry.append(cid)
                    continue
                data["model"] = msg.model
                updates.setdefault(pid, {})[no] = data
            else:
                retry.append(cid)
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
    if usage["count"]:
        cost = usage["input"] / 1e6 * PRICE_IN + usage["output"] / 1e6 * PRICE_OUT
        print(f"누적 API 사용: {usage['count']}건, 입력 {usage['input']:,} / 출력 {usage['output']:,} 토큰, "
              f"약 ${cost:.2f} (문항당 ${cost / usage['count']:.3f})")
    return all_done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["submit", "collect", "run"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--queue", action="store_true", help="모든 시험에서 우선순위 순으로 (--limit 와 함께)")
    a = ap.parse_args()
    client = anthropic.Anthropic()
    if a.cmd == "submit":
        submit(client, a.limit, a.queue)
    elif a.cmd == "collect":
        collect(client)
    else:
        collect(client)
        submit(client, a.limit, a.queue)
        while not collect(client):
            time.sleep(120)


if __name__ == "__main__":
    main()
