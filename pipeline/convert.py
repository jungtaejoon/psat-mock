"""문항을 PDF 그림에서 HTML 텍스트로 옮긴다 (Claude Message Batches API, 50% 할인).

  python pipeline/convert.py scope add gong9-2026-     # 변환할 문제지 id 접두어 추가 (단계 승인 때)
  python pipeline/convert.py submit [--limit N]        # 범위 안의 변환 안 된 문항을 배치로 제출
  python pipeline/convert.py collect                   # 끝난 배치를 받아 검사 → 통과한 것만 저장
  python pipeline/convert.py check <결과.json> ...      # (개발용) 변환 결과 파일을 검사만

결과
- web/public/data/text/<문제지 id>.json  →  {"<no>": {"stem", "choices", "figs": {"f1": "fig/…png"}, "model"}}
- web/public/data/fig/<문제지 id>/<no>-f1.png  (그래프·도면 등 글자로 옮길 수 없는 부분만 원본에서 잘라 둔 그림)
- data/convert_state.json  →  범위(scope), 진행 중 배치, 재시도·포기 목록

검사(모두 통과해야 저장): 허용 태그만, 보기 개수, 수식을 뺀 글자가 PDF 글자와 98% 이상 같음(깨진 글자가 있는
문항은 90%), 그림 위치가 문항 안, 자신감 low 아님. Haiku 에서 걸리면 Sonnet 으로 한 번 더, 그래도 걸리면 PDF 로 둔다.
처음엔 모두 Haiku 로 보내고, 검사에 걸린 문항만 Sonnet 으로 한 번 더 보낸다. 범위에서 뺄 과목은 exclude.
인증: 로컬은 ANTHROPIC_API_KEY, CI 는 Workload Identity Federation (.github/workflows/update.yml).
"""
from __future__ import annotations

import argparse
import base64
import difflib
import html
import json
import re
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"
TEXT = DATA / "text"
FIG = DATA / "fig"
STATE = ROOT / "data" / "convert_state.json"
HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
DPI = 150
PUA = re.compile(r"[-\x00-\x08]")
ALLOWED = {"p", "br", "u", "b", "i", "sup", "sub", "div", "table", "thead", "tbody", "tr", "th", "td", "img", "span"}

SYSTEM = """당신은 시험 문항을 웹 페이지용 HTML 로 옮기는 편집자입니다. 문항 하나를 PDF 에서 잘라낸 그림과, 같은 영역에서 기계로 뽑은 글자가 주어집니다.
뽑은 글자는 글자 자체는 대체로 정확하지만 줄바꿈이 원본 줄 끝마다 들어가 있고, 낫표 「」·밑줄·상자·표 구조·수식이 빠지거나 깨져 있습니다(사용자 영역 문자 등). 글자는 뽑은 글자로 확인하고, 구조와 서식은 그림을 보고 정합니다.

출력 필드
- stem: 문항 번호("문 3." "3.")는 빼고 발문·지문·자료·<보기>까지 전부, 원본 순서대로.
- choices: 보기 ①②③④(⑤)의 내용만, 기호는 빼고 순서대로. 시험지의 보기 개수 그대로. 보기가 표 한 줄씩이면 각 보기를 그 행 내용으로("250 / 30" 처럼 칸을 " / " 로 잇는다). 그 표의 머리글 줄(예: (가) (나))은 stem 끝에 <table> 로 옮긴다. 이 설명의 문구를 결과에 넣지 말 것.
- figures: 글자·표로 옮길 수 없는 그래프·도면·회로·사진·지도만. box 는 그림 전체에 대한 비율 [왼쪽, 위, 오른쪽, 아래]를 조금 넉넉하게. 본문 그 자리에 <img data-fig="f1"> 를 넣는다. 보기 자체가 그림이면 choices 항목에 넣는다.
- confidence: high(원본과 똑같이 옮김) / medium(사소한 확신 없음) / low(옮기기 어려움 — 이유를 notes 에).
- notes: 짧게. 그림과 뽑은 글자가 다른 글자가 있으면 여기에 적는다(예: "뽑은 글자 '뚱' 은 그림에서도 '뚱'").

쓸 수 있는 HTML
- <p>, <br>(시·대화처럼 줄이 의미 있을 때만; 원본 줄 끝마다 넣지 말 것)
- <u>(밑줄 — "밑줄 친" 문항에서 특히 중요), <b>, <i>, <sup>, <sub>
- 지문 상자·<보기> 상자: <div class="box">…</div>, 상자 제목은 상자 안 첫 줄 <p class="box-title">&lt;보기&gt;</p>
- 표: <table><tr><th>/<td> (colspan·rowspan 가능). 표 제목·단위·주석은 표 앞뒤 <p class="cap">
- 수식: 인라인 \\( … \\), 별도 줄 \\[ … \\] (LaTeX). 단순 숫자·단위(70 km/h, 26.2 %)는 수식으로 만들지 말 것.
- 들여쓴 항목(ㄱ. ㄴ. / 가. 나.): <p class="item">ㄱ. …</p>
- 오른쪽 정렬(출처 등): <p class="right">
- 그 밖의 태그·style 금지. 「」 ㉠ ○ □ ※ ㆍ 같은 특수문자는 유니코드 그대로. < > & 는 &lt; &gt; &amp;.

원칙: 글자를 바꾸거나 고치거나 요약하지 않는다(오탈자도 원본대로). 빠뜨리지 않는다. 원본에 없는 것(정답 표시, 설명)을 더하지 않는다. 구조가 애매하면 원본 모양에 가깝게 하고 confidence 를 낮춘다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "stem": {"type": "string"},
        "choices": {"type": "array", "items": {"type": "string"}},
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "box": {"type": "array", "items": {"type": "number"}}},
                "required": ["id", "box"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
    },
    "required": ["stem", "choices", "figures", "confidence", "notes"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- 입력 만들기

def regions_of(q: dict) -> list[dict]:
    return (q.get("shared", {}).get("regions") or []) + q["regions"]


def stacked(doc: fitz.Document, regions: list[dict], dpi: int = DPI) -> tuple[bytes, list[tuple[dict, int, int]]]:
    """영역들을 위아래로 이어 붙인 PNG 와, 각 영역이 그림 안에서 차지하는 (영역, 위, 높이) 목록"""
    pics = [doc[r["page"]].get_pixmap(clip=fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"]), dpi=dpi) for r in regions]
    w, h = max(p.width for p in pics), sum(p.height for p in pics)
    out = fitz.open()
    page = out.new_page(width=w, height=h)
    spans, y = [], 0
    for r, p in zip(regions, pics):
        page.insert_image(fitz.Rect(0, y, p.width, y + p.height), pixmap=p)
        spans.append((r, y, p.height))
        y += p.height
    return out[0].get_pixmap(dpi=72).tobytes("png"), spans


def pdf_text(doc: fitz.Document, q: dict) -> str:
    return "".join(doc[r["page"]].get_text("text", clip=fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])) for r in regions_of(q))


def build_params(paper: dict, q: dict, doc: fitz.Document, model: str) -> dict:
    png, _ = stacked(doc, regions_of(q))
    n = paper.get("choices", 5)
    text = (
        f"[{paper['year']}년 {'/'.join(paper.get('exams', []))} {paper['subject']} {q.get('orig', q['no'])}번, 보기 {n}개]\n\n"
        f"[뽑은 글자]\n{pdf_text(doc, q)}"
    )
    return {
        "model": model,
        "max_tokens": 16000,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(png).decode()}},
            {"type": "text", "text": text},
        ]}],
    }


# ---------------------------------------------------------------- 검사

DASH = re.compile(r"[‐‑‒–—―－−~～_\-]")
# 서식으로 더해지는 글자(낫표·칸 구분 /·가운뎃점 변형)는 비교에서 뺀다
IGNORE = re.compile(r"[「」『』/\\＼ㆍᆞ·․‧∙•+=＝]")
TEX_SYM = {"log": "log", "ln": "ln", "sin": "sin", "cos": "cos", "tan": "tan", "exp": "exp", "lim": "lim", "max": "max",
           "min": "min", "sec": "sec", "csc": "csc", "cot": "cot", "det": "det", "mod": "mod", "bmod": "mod", "prod": "∏",
           "sum": "∑", "int": "∫", "sqrt": "√", "Pi": "Π", "partial": "∂", "nabla": "∇", "cdots": "⋯", "ldots": "…",
           "cdot": "·", "times": "×", "circ": "°", "prime": "′", "rightarrow": "→", "to": "→", "leftarrow": "←",
           "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "pm": "±", "div": "÷", "sim": "∼", "neq": "≠", "infty": "∞",
           "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ", "theta": "θ", "lambda": "λ", "mu": "μ",
           "pi": "π", "sigma": "σ", "Sigma": "Σ", "omega": "ω", "Omega": "Ω", "phi": "φ", "rho": "ρ", "eta": "η", "epsilon": "ε"}


QNUM = re.compile(r"문\s*\d{1,3}\s*\.?|^\s*\d{1,3}\s*\.(?!\d)\s*(?=\n?\s*문|$)|^\s*문\s*$", re.M)


def _norm(t: str) -> str:
    import unicodedata

    # <보기>·<표 1>·<그림>·<보고서> 같은 짧은 꺾쇠 제목 (PDF 에서는 그림으로 그려진 경우가 많다)
    t = re.sub(r"[<〈＜《]\s*[가-힣](?:\s*[가-힣]){0,5}\s*\d{0,2}\s*[>〉＞》]", "", t)
    t = t.replace("⟶", "→").replace("⟹", "⇒").replace("°", "o").replace("º", "o")
    t = QNUM.sub("", t)  # 문항 번호("문 6." / "6.\n문")는 어디에 있든 양쪽에서 뺀다
    t = IGNORE.sub("", t)
    t = unicodedata.normalize("NFKC", t)
    t = DASH.sub("", t)
    t = IGNORE.sub("", t)
    return re.sub(r"\s+", "", t)


def plain_pdf(t: str) -> str:
    t = PUA.sub("", t)
    t = re.sub(r"^\s*(문\s*)?\d{1,3}\s*\.", "", t)
    t = re.sub(r"[①②③④⑤]", "", t)
    return _norm(t)


def _math_text(m: re.Match) -> str:
    # 수식 안의 글자·숫자는 남긴다 (\frac{1}{2} → 12, \Delta H → H)
    t = re.sub(r"\\([a-zA-Z]+)", lambda k: TEX_SYM.get(k.group(1), ""), m.group(0)[2:-2])
    return re.sub(r"[{}^_&\\]", "", t)


def plain_conv(o: dict) -> str:
    s = o.get("stem", "") + "".join(o.get("choices", []))
    s = re.sub(r"\\\(.*?\\\)|\\\[.*?\\\]", _math_text, s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[①②③④⑤]", "", s)
    return _norm(s)


def tidy(o: dict) -> dict:
    """흔한 사소한 차이를 고친다: 본문 앞에 붙은 문항 번호("13." / "문 13.") 제거"""
    # 보기 앞에 붙은 ①~⑤ (화면에서 번호가 두 번 보인다)
    o["choices"] = [re.sub(r"^(\s*<p[^>]*>)?\s*[①②③④⑤]\s*", lambda m: m.group(1) or "", c, count=1) for c in o.get("choices", [])]
    o["stem"] = re.sub(r"^(\s*<p[^>]*>)?\s*(문\s*)?\d{1,3}\s*\.(?!\d)\s*", lambda m: m.group(1) or "", o.get("stem", ""), count=1)
    return o


def check(o: dict, src_text: str, n_choices: int, fig_text: str = "") -> list[str]:
    """문제가 없으면 빈 목록"""
    bad = []
    tags = {t.lower() for t in re.findall(r"</?\s*([a-zA-Z0-9]+)", o.get("stem", "") + "".join(o.get("choices", [])))}
    if tags - ALLOWED:
        bad.append(f"허용 안 된 태그 {sorted(tags - ALLOWED)}")
    if re.search(r"\sstyle\s*=|on\w+\s*=", o.get("stem", "") + "".join(o.get("choices", [])), re.I):
        bad.append("style/이벤트 속성")
    if len(o.get("choices", [])) != n_choices:
        bad.append(f"보기 {len(o.get('choices', []))}/{n_choices}개")
    a, b = plain_pdf(src_text), plain_conv(o)
    # 순서와 상관없이 빠진 글자·더해진 글자를 센다 (표 칸 순서가 달라도 통과, 빠뜨리거나 지어낸 것은 걸림)
    from collections import Counter

    ca, cb = Counter(a) - Counter(plain_pdf(fig_text)), Counter(b)
    missing, extra = sum((ca - cb).values()), sum((cb - ca).values())
    garbled = bool(PUA.search(src_text))  # 수식 글자가 깨진 문항: PDF 쪽에 없는 수식 글자가 변환 쪽에 생기는 것은 허용
    tol = max(2, int(len(a) * 0.01))
    if missing > (max(3, int(len(a) * 0.08)) if garbled else tol):
        bad.append(f"빠진 글자 {missing}개 ({''.join((ca - cb).elements())[:30]})")
    if not garbled and extra > tol:
        bad.append(f"더해진 글자 {extra}개 ({''.join((cb - ca).elements())[:30]})")
    ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a else 1.0
    ids = set(re.findall(r'data-fig="([^"]+)"', o.get("stem", "") + "".join(o.get("choices", []))))
    figs = {f["id"]: f["box"] for f in o.get("figures", [])}
    if ids - set(figs):
        bad.append("그림 자리만 있고 위치 없음")
    for fid, bx in figs.items():
        if len(bx) != 4 or not (0 <= bx[0] < bx[2] <= 1.001 and 0 <= bx[1] < bx[3] <= 1.001):
            bad.append(f"그림 {fid} 위치 이상 {bx}")
    if o.get("confidence") == "low":
        bad.append("자신감 low")
    o["_ratio"] = round(ratio, 4)
    return bad


def figure_rects(doc: fitz.Document, q: dict, o: dict) -> list[tuple[str, int, fitz.Rect]]:
    """모델이 준 그림 위치(이어 붙인 그림 기준 비율) → (그림 id, 쪽, PDF 좌표).
    이어 붙인 그림은 모든 영역을 같은 DPI 로 그렸으므로 픽셀 → PDF 좌표는 72/DPI 배."""
    out = []
    if not o.get("figures"):
        return out
    png, spans = stacked(doc, regions_of(q))
    pm = fitz.Pixmap(png)
    W, H, k = pm.width, pm.height, 72 / DPI
    for f in o["figures"]:
        if len(f.get("box", [])) != 4:
            continue
        x0, y0, x1, y1 = f["box"]
        py0, py1 = y0 * H, y1 * H
        # 그림 하나가 여러 영역에 걸치면 가장 많이 겹치는 영역에서 자른다
        r, top, _ = max(spans, key=lambda s: min(py1, s[1] + s[2]) - max(py0, s[1]))
        rect = fitz.Rect(r["x0"] + x0 * W * k - 2, r["y0"] + (py0 - top) * k - 2,
                         r["x0"] + x1 * W * k + 2, r["y0"] + (py1 - top) * k + 2) & fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
        if not rect.is_empty:
            out.append((f["id"], r["page"], rect))
    return out


def figure_text(doc: fitz.Document, rects) -> str:
    """그림으로 보여 줄 부분 안의 글자 (글자 비교에서 뺀다)"""
    return "".join(doc[pg].get_text("text", clip=rc) for _, pg, rc in rects)


def save_figures(paper: dict, doc: fitz.Document, q: dict, rects) -> dict:
    out = {}
    d = FIG / paper["id"]
    for fid, pg, rect in rects:
        d.mkdir(parents=True, exist_ok=True)
        name = f"{q['no']}-{fid}.png"
        doc[pg].get_pixmap(clip=rect, dpi=200).save(d / name)
        out[fid] = f"fig/{paper['id']}/{name}"
    return out


# ---------------------------------------------------------------- 상태

def api_id(cid: str) -> str:
    """배치 custom_id 는 영문·숫자·_- 64자까지만 → 문제지 id(한글 포함)를 해시로 바꾼다. 원래 id 는 상태 파일 ids 에 둔다"""
    import hashlib

    return "q" + hashlib.sha1(cid.encode()).hexdigest()[:40]


def load_state() -> dict:
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    for k, v in (("scope", []), ("exclude", []), ("batches", []), ("pending", []), ("sonnet", []), ("gave_up", {}), ("ids", {})):
        st.setdefault(k, v)
    return st


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def existing(pid: str) -> dict:
    f = TEXT / f"{pid}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def paper_pdf(paper: dict) -> fitz.Document:
    return fitz.open(DATA / "pdf" / f"{paper.get('pdf', paper['id'])}.pdf")


# ---------------------------------------------------------------- 명령

def _questions_to_send(st: dict):
    """범위 안에서 아직 변환 안 된 문항: (문제지, 문항, 모델)"""
    pending, sonnet = set(st["pending"]), set(st["sonnet"])
    for f in sorted((DATA / "papers").glob("*.json")):
        if not any(f.stem.startswith(s) for s in st["scope"]):
            continue
        if any(x in f.stem for x in st["exclude"]):
            continue  # 예: 영어 — PDF 글자 층에 영어가 없어 대조 검사를 할 수 없다 → PDF 로 둔다
        paper = json.loads(f.read_text())
        done = existing(paper["id"])
        for q in paper["questions"]:
            cid = f"{paper['id']}__{q['no']}"
            if str(q["no"]) in done or cid in pending or cid in st["gave_up"] or not regions_of(q):
                continue
            # 처음엔 모두 Haiku, 검사에 걸린 것만 Sonnet 으로 다시 (2026-11-20 절감형)
            yield paper, q, (SONNET if cid in sonnet else HAIKU)


def submit(client, limit: int | None) -> None:
    """500건씩 만들어 바로 제출한다 (한꺼번에 만들면 그림 때문에 메모리가 수 GB). 배치 대기열 한도에 걸리면 멈추고 다음 실행에서 이어 간다"""
    from anthropic.types.messages.batch_create_params import Request

    st = load_state()
    if not st["scope"]:
        print("변환 범위가 비어 있음 (convert.py scope add <접두어>)")
        return
    chunk, sent, docs = [], 0, {}

    def flush() -> bool:
        nonlocal chunk, sent
        if not chunk:
            return True
        try:
            b = client.messages.batches.create(requests=chunk)
        except Exception as ex:  # noqa: BLE001
            print(f"제출 멈춤 ({type(ex).__name__}: {str(ex)[:200]}) — 다음 실행에서 이어 감")
            for r in chunk:
                st["ids"].pop(r["custom_id"], None)
            chunk = []
            return False
        st["batches"].append(b.id)
        st["pending"] += [st["ids"][r["custom_id"]] for r in chunk]
        save_state(st)
        print(f"submitted {b.id}: {len(chunk)}건 (Sonnet {sum(r['params']['model'] == SONNET for r in chunk)})", flush=True)
        sent += len(chunk)
        chunk = []
        return True

    for paper, q, model in _questions_to_send(st):
        doc = docs.get(paper["id"])
        if doc is None:
            docs.clear()  # 문제지가 바뀌면 이전 PDF 는 닫는다
            doc = docs[paper["id"]] = paper_pdf(paper)
        cid = f"{paper['id']}__{q['no']}"
        chunk.append(Request(custom_id=api_id(cid), params=build_params(paper, q, doc, model)))
        st["ids"][api_id(cid)] = cid
        if len(chunk) >= 500 and not flush():
            break
        if limit and sent + len(chunk) >= limit:
            break
    else:
        flush()
    if limit and chunk:
        flush()
    print(f"제출 {sent}건" if sent else "변환할 새 문항 없음")


FAILED = ROOT / "data" / "convert_failed"


def judge(st: dict, cid: str, o: dict | None, model: str, papers: dict) -> tuple[str | None, dict | None]:
    """변환 결과 하나를 검사. 통과하면 (None, 저장할 항목), 아니면 (이유, None)"""
    if o is None:
        return "응답 이상", None
    pid, no = cid.rsplit("__", 1)
    paper = papers.get(pid) or json.loads((DATA / "papers" / f"{pid}.json").read_text())
    papers[pid] = paper
    q = next(x for x in paper["questions"] if str(x["no"]) == no)
    doc = paper_pdf(paper)
    o = tidy(o)
    rects = figure_rects(doc, q, o)
    bad = check(o, pdf_text(doc, q), paper.get("choices", 5), figure_text(doc, rects))
    if bad:
        return "; ".join(bad), None
    figs = save_figures(paper, doc, q, rects)
    return None, dict(stem=o["stem"], choices=o["choices"], figs=figs, model=model, ratio=o["_ratio"], conf=o["confidence"])


def record(st: dict, cid: str, model: str, reason: str | None, item: dict | None, o: dict | None, updates: dict) -> None:
    """판정 결과를 상태에 반영. 걸린 결과는 data/convert_failed 에 남겨 검사기를 고친 뒤 API 없이 다시 볼 수 있게 한다"""
    pid, no = cid.rsplit("__", 1)
    f = FAILED / f"{api_id(cid)}.json"
    if item is not None:
        updates.setdefault(pid, {})[no] = item
        st["gave_up"].pop(cid, None)
        if f.exists():
            f.unlink()
        return
    FAILED.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(dict(cid=cid, model=model, reason=reason, output=o), ensure_ascii=False))
    if model.startswith("claude-sonnet"):
        st["gave_up"][cid] = reason  # Sonnet 도 못 넘음 → PDF 로 둔다
    elif cid not in st["sonnet"]:
        st["sonnet"].append(cid)


def write_updates(st: dict, updates: dict) -> None:
    TEXT.mkdir(parents=True, exist_ok=True)
    done = set()
    for pid, items in updates.items():
        cur = existing(pid)
        cur.update(items)
        (TEXT / f"{pid}.json").write_text(json.dumps(cur, ensure_ascii=False))
        done |= {f"{pid}__{no}" for no in items}
    st["sonnet"] = [c for c in st["sonnet"] if c not in done]


def collect(client) -> bool:
    st = load_state()
    remaining, all_done = [], True
    saved, failed = 0, 0
    usage = {"in": 0, "out": 0, "cache_r": 0}
    papers: dict[str, dict] = {}
    pending = set(st["pending"])
    for bid in st["batches"]:
        b = client.messages.batches.retrieve(bid)
        if b.processing_status != "ended":
            remaining.append(bid)
            all_done = False
            continue
        updates: dict[str, dict] = {}
        for res in client.messages.batches.results(bid):
            cid = st["ids"].pop(res.custom_id, res.custom_id)
            pending.discard(cid)
            o, model = None, ""
            if res.result.type == "succeeded":
                msg = res.result.message
                model = msg.model
                u = msg.usage
                usage["in"] += u.input_tokens
                usage["out"] += u.output_tokens
                usage["cache_r"] += getattr(u, "cache_read_input_tokens", 0) or 0
                text = next((blk.text for blk in msg.content if blk.type == "text"), "")
                try:
                    o = json.loads(text) if msg.stop_reason == "end_turn" else None
                except json.JSONDecodeError:
                    o = None
                reason, item = judge(st, cid, o, model, papers)
            else:
                reason, item = f"요청 실패 ({res.result.type})", None
            record(st, cid, model or HAIKU, reason, item, o, updates)
            if reason:
                failed += 1
                print(f"  ! {cid}: {reason}")
            else:
                saved += 1
        write_updates(st, updates)
        st["pending"] = [c for c in st["pending"] if c in pending]
        st["batches"] = [x for x in st["batches"] if x != bid]
        save_state(st)  # 배치 하나 끝날 때마다 저장 (중간에 멈춰도 다시 받지 않게)
        print(f"collected {bid}", flush=True)
    st["batches"] = remaining
    st.setdefault("usage", {"in": 0, "out": 0, "cache_r": 0})
    for k in usage:
        st["usage"][k] += usage[k]
    save_state(st)
    print(f"저장 {saved}건, 걸림 {failed}건 (Sonnet 재시도 대기 {len(st['sonnet'])}, PDF 로 둠 {len(st['gave_up'])}), 토큰 {usage}")
    return all_done


def recheck() -> None:
    """data/convert_failed 에 남은 결과를 지금 검사기로 다시 본다 (API 호출 없음)"""
    st = load_state()
    papers: dict[str, dict] = {}
    updates: dict[str, dict] = {}
    ok = still = 0
    for f in sorted(FAILED.glob("*.json")) if FAILED.exists() else []:
        r = json.loads(f.read_text())
        reason, item = judge(st, r["cid"], r["output"], r["model"], papers)
        if item is not None:
            ok += 1
            record(st, r["cid"], r["model"], None, item, None, updates)
        else:
            still += 1
            r["reason"] = reason
            f.write_text(json.dumps(r, ensure_ascii=False))
    write_updates(st, updates)
    save_state(st)
    print(f"다시 검사: 통과 {ok}건, 여전히 걸림 {still}건")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scope", "submit", "collect", "check", "recheck"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "scope":
        st = load_state()
        if a.args[:1] == ["add"]:
            st["scope"] = sorted(set(st["scope"]) | set(a.args[1:]))
        elif a.args[:1] == ["exclude"]:
            st["exclude"] = sorted(set(st["exclude"]) | set(a.args[1:]))
        save_state(st)
        print("범위:", st["scope"], "제외:", st["exclude"])
        return
    if a.cmd == "recheck":
        recheck()
        return
    if a.cmd == "check":
        # check <sample.json> <결과 폴더> : 시범 결과 검사 (개발용)
        sample = json.loads(Path(a.args[0]).read_text())
        for it in sample:
            f = Path(a.args[1]) / f"{it['i']:02d}.json"
            if f.exists():
                o = json.loads(f.read_text())
                paper = json.loads((DATA / "papers" / f"{it['paper']}.json").read_text())
                q = next(x for x in paper["questions"] if x["no"] == it["no"])
                doc = paper_pdf(paper)
                bad = check(o, it["pdf_text"], it["choices"], figure_text(doc, figure_rects(doc, q, o)))
                print(it["i"], it["cat"], o["_ratio"], bad or "OK")
        return
    import anthropic

    client = anthropic.Anthropic()
    if a.cmd == "submit":
        submit(client, a.limit)
    else:
        collect(client)


if __name__ == "__main__":
    sys.exit(main())
