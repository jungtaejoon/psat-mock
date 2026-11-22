"""Claude Code 에이전트가 직접 해설을 쓰도록 돕는 도구 (API 배치 대신 구독 사용량으로 해설 작성).

  python pipeline/expl_agent.py queue [--n N]          # 해설이 빠진 문제지 id 를 우선순위대로 출력
  python pipeline/expl_agent.py prep <paperId> <dir>   # 에이전트가 읽을 문항 묶음(md + 그림 png)을 dir 에 만든다
  python pipeline/expl_agent.py save <paperId> <json>  # 에이전트가 쓴 해설 JSON 을 검사해 explanations/ 에 합친다

save 입력 형식: {"<no>": {"key_point": str, "explanation": str, "choices": [str, ...], "tip": str}, ...}
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"
EXPL = DATA / "explanations"
CIRCLED = "①②③④⑤"
MODEL_TAG = "claude-opus-5-5 (agent)"

# 수요가 큰 시험부터
PRIORITY = ["gong9", "realtor", "social1", "gong7", "housing", "local", "security", "labor", "appraiser",
            "tax", "customs", "patent", "logistics", "tourguide", "youthcounsel"]


def existing(pid: str) -> dict:
    f = EXPL / f"{pid}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def queue(n: int) -> None:
    ix = json.loads((DATA / "index.json").read_text())["papers"]
    rank = {e: i for i, e in enumerate(PRIORITY)}
    todo = [p for p in ix if p.get("exam", "psat") in rank and p.get("answersFinal", True)
            and (p.get("explained") or 0) < p["count"]]
    core = {"국어", "영어", "한국사", "행정법총론", "행정학개론"}

    def key(p):
        # 공무원은 공통 과목(국어·영어·한국사·행정법·행정학)을 먼저, 전공 과목은 그 시험 맨 뒤로
        tier = 0 if p["exam"] not in ("gong9", "gong7", "local") or p["subject"] in core else 1
        return (tier, rank[p["exam"]], -int(p["year"]), p["id"])

    todo.sort(key=key)
    for p in todo[:n]:
        print(p["id"])


def plain(h: str) -> str:
    """문항 HTML → 에이전트가 읽기 쉬운 텍스트 (표는 HTML 그대로 둔다)"""
    h = re.sub(r"</p>\s*<p[^>]*>", "\n", h)
    h = re.sub(r"<br\s*/?>", "\n", h)
    h = re.sub(r"</?(p|span|div)[^>]*>", "", h)
    return html.unescape(h).strip()


def prep(pid: str, out: Path) -> None:
    import fitz

    paper = json.loads((DATA / "papers" / f"{pid}.json").read_text())
    text = {}
    tf = DATA / "text" / f"{pid}.json"
    if tf.exists():
        text = json.loads(tf.read_text())
    done = existing(pid)
    out.mkdir(parents=True, exist_ok=True)
    pdf = None
    lines = [f"# {paper['year']}년 {' / '.join(paper['exams'])} {paper['subject']} ({pid})", ""]
    n = 0
    for q in paper["questions"]:
        no = str(q["no"])
        if no in done:
            continue
        n += 1
        ans = q["answer"]
        nch = len(q.get("choices") or []) or paper.get("choices") or 4
        ans_txt = "모든 선택지 정답 처리" if len(ans) >= nch else ", ".join(CIRCLED[a - 1] for a in ans)
        lines += [f"## {no}번  (선택지 {nch}개, 공식 정답: {ans_txt})"]
        t = text.get(no)
        if t:
            stem = plain(t["stem"])
            for k, path in (t.get("figs") or {}).items():
                stem = re.sub(rf"<img[^>]*data-fig=['\"]{k}['\"][^>]*>", f"[그림: {DATA / path}]", stem)
            lines.append(stem)
            for i, c in enumerate(t.get("choices") or []):
                lines.append(f"{CIRCLED[i]} {plain(c)}")
        else:
            # 글자 변환이 없는 문항 → 문제 영역 그림을 보고 풀게 한다
            pdf = pdf or fitz.open(DATA / "pdf" / f"{paper.get('pdf', pid)}.pdf")
            regions = (q.get("shared", {}).get("regions") or []) + q["regions"]
            for i, r in enumerate(regions):
                png = out / f"{pid}-{no}-{i}.png"
                pdf[r["page"]].get_pixmap(clip=fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"]), dpi=150).save(png)
                lines.append(f"[문항 그림 — Read 로 열어 볼 것: {png}]")
        lines.append("")
    (out / f"{pid}.md").write_text("\n".join(lines))
    print(f"{out / (pid + '.md')}  ({n}문항)")


def save(pid: str, src: Path) -> None:
    paper = json.loads((DATA / "papers" / f"{pid}.json").read_text())
    qs = {str(q["no"]): q for q in paper["questions"]}
    new = json.loads(src.read_text())
    ok, bad = {}, []
    for no, e in new.items():
        q = qs.get(str(no))
        if not q or not isinstance(e, dict):
            bad.append(f"{no}: 없는 문항")
            continue
        nch = len(q.get("choices") or []) or paper.get("choices") or 4
        miss = [k for k in ("key_point", "explanation", "choices", "tip") if k not in e]
        if miss:
            bad.append(f"{no}: 항목 빠짐 {miss}")
            continue
        if not isinstance(e["choices"], list) or len(e["choices"]) not in (0, nch):
            bad.append(f"{no}: choices {len(e['choices'])}개 (선택지 {nch}개여야 함)")
            continue
        if len(e["explanation"].strip()) < 20:
            bad.append(f"{no}: 해설이 너무 짧음")
            continue
        ok[str(no)] = {k: e[k] for k in ("key_point", "explanation", "choices", "tip")} | {"model": MODEL_TAG}
    if ok:
        cur = existing(pid)
        cur.update(ok)
        EXPL.mkdir(parents=True, exist_ok=True)
        (EXPL / f"{pid}.json").write_text(json.dumps(cur, ensure_ascii=False))
    left = len(qs) - len(existing(pid))
    print(f"saved {len(ok)}, rejected {len(bad)}, 남은 문항 {left}")
    for b in bad:
        print("  !", b)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "queue":
        queue(int(sys.argv[3]) if len(sys.argv) > 3 else 50)
    elif cmd == "prep":
        prep(sys.argv[2], Path(sys.argv[3]))
    elif cmd == "save":
        save(sys.argv[2], Path(sys.argv[3]))
