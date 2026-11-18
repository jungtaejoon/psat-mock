"""문제지 PDF → 문항 단위 영역(좌표) + 텍스트.

PSAT 문제지는 2단 편집이다. 각 단에서 'N.' 으로 시작하는 줄을 문항 시작으로 보고
다음 문항 시작 전까지를 그 문항 영역으로 잡는다. 단·쪽을 넘어가는 문항과
'※ 다음 글을 읽고 물음에 답하시오. [문 25～문 26]' 같은 공통 지문도 처리한다.

결과: web/public/data/papers/{id}.json, web/public/data/pdf/{id}.pdf, web/public/data/index.json
웹에서는 pdf.js 로 해당 좌표만 잘라 그린다(벡터 그대로라 선명하고 용량이 작다).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CATALOG = ROOT / "data" / "catalog.json"
OUT = ROOT / "web" / "public" / "data"

Q_RE = re.compile(r"^\s*(?:문\s*)?(\d{1,2})\s*\.(?!\d)")
SHARED_RE = re.compile(r"^\s*(?:※|\[\s*(?:문\s*)?\d)")
RANGE_RE = re.compile(r"(\d{1,2})\s*\.?\s*[～~∼\-–]\s*(?:문\s*)?(\d{1,2})")
PAD = 3


def lines_of(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t:
                out.append((fitz.Rect(l["bbox"]), t))
    return out


def page_frame(page, lines):
    """머리말/꼬리말을 제외한 본문 세로 범위."""
    H = page.rect.height
    head = [r.y1 for r, t in lines if r.y1 < H * 0.06]
    # 꼬리말은 쪽 번호 같은 짧은 글만. 페이지 맨 아래 선택지(⑤ …)를 꼬리말로 오인하지 않도록 한다
    foot = [r.y0 for r, t in lines if r.y0 > H * 0.95 and re.fullmatch(r"[-–―\s]*\d{1,2}\s*(쪽)?[-–―\s]*|.*\d+\s*쪽.*", t)]
    # 같은 높이에 다른 본문 글자가 있으면 쪽 번호가 아니다(표 형태 선택지의 숫자 칸)
    foot = [y for y in foot if sum(1 for r, _ in lines if abs(r.y0 - y) < 3) == 1]
    top = max(head) + 2 if head else H * 0.04
    bottom = min(foot) - 2 if foot else H * 0.985
    # 머리말 아래 가로줄(도형)도 머리말로 본다
    W = page.rect.width
    for d in page.get_drawings():
        r = d["rect"]
        if r.height < 3 and r.width > W * 0.8:
            if r.y1 < H * 0.08:
                top = max(top, r.y1 + 2)
            elif r.y0 > H * 0.93:
                bottom = min(bottom, r.y0 - 2)
    return top, bottom


_ink_cache: dict[int, list[fitz.Rect]] = {}


def page_ink(page) -> list[fitz.Rect]:
    """페이지의 도형·이미지 영역 (문서별로 한 번만 계산)."""
    key = id(page.parent) * 1000 + page.number
    if key not in _ink_cache:
        W = page.rect.width
        # 두께 0 인 선(빈칸 상자 테두리 등)은 면적이 0 이라 intersects() 가 항상 거짓 → 살짝 부풀린다
        rects = [d["rect"] + (-0.6, -0.6, 0.6, 0.6) for d in page.get_drawings() if d["rect"].width < W * 0.98]
        rects += [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
        _ink_cache[key] = rects
    return _ink_cache[key]


def ink_bottom(page, rect: fitz.Rect, lines) -> float:
    """rect 안에서 실제 내용(텍스트·도형·이미지)이 끝나는 y."""
    ys = [r.y1 for r, _ in lines if r.intersects(rect) and r.y0 >= rect.y0 - 1]
    for r in page_ink(page):
        if r.intersects(rect) and r.y0 >= rect.y0 - 1:
            ys.append(min(r.y1, rect.y1))
    return max(ys) if ys else rect.y0


def segment(pdf_path: Path, n_questions: int):
    doc = fitz.open(pdf_path)
    _ink_cache.clear()
    W = doc[0].rect.width
    mid = W / 2
    # 1) 읽는 순서대로 '단' 목록을 만든다
    cols = []  # dict(page, x0, x1, top, bottom, lines)
    for pno, page in enumerate(doc):
        lines = lines_of(page)
        top, bottom = page_frame(page, lines)
        body = [(r, t) for r, t in lines if r.y0 >= top - 1 and r.y1 <= bottom + 1]
        spans_mid = [r for r, t in body if r.x0 < mid - 20 and r.x1 > mid + 20]
        if len(spans_mid) > len(body) * 0.5:  # 1단 편집 페이지
            cols.append(dict(page=pno, x0=0, x1=W, top=top, bottom=bottom, lines=body))
        else:
            L = [x for x in body if x[0].x0 < mid - 5]
            R = [x for x in body if x[0].x0 >= mid - 5]
            # 가운데 세로 구분선이 잘려 들어오지 않도록 오른쪽 단은 글자 시작점 조금 앞에서 자른다
            rx0 = max(mid + 1, min((r.x0 for r, _ in R), default=mid) - 8)
            cols.append(dict(page=pno, x0=0, x1=mid - 2, top=top, bottom=bottom, lines=L))
            cols.append(dict(page=pno, x0=rx0, x1=W, top=top, bottom=bottom, lines=R))

    # 2) 문항 시작 줄과 공통 지문 시작 줄을 순서대로 찾는다
    marks = []  # (col_idx, y, kind, num/range)
    expect = 1
    for ci, c in enumerate(cols):
        if not c["lines"]:
            continue
        left = min(r.x0 for r, _ in c["lines"])
        # 구형 문제지는 '문' 과 '1.' 이 서로 다른 텍스트 줄이다
        mun = [r for r, t in c["lines"] if t == "문"]
        ordered = sorted(c["lines"], key=lambda x: (x[0].y0, x[0].x0))
        for k, (r, t) in enumerate(ordered):
            if t == "문":
                continue
            labeled = any(abs(m.y0 - r.y0) < 4 and m.x1 <= r.x0 + 6 for m in mun)
            if r.x0 > left + 14 and not labeled:
                continue
            if labeled:
                r = fitz.Rect(min(m.x0 for m in mun if abs(m.y0 - r.y0) < 4), r.y0, r.x1, r.y1)
            m = Q_RE.match(t)
            if m and int(m.group(1)) == expect:
                marks.append((ci, r.y0, "q", expect))
                expect += 1
                continue
            if SHARED_RE.match(t):
                # 범위 표기가 다음 줄로 넘어가는 경우가 있어 두 줄 더 본다
                # 지문 안의 날짜 범위(예: 10～16일)와 구별하려고 다음 문항 번호로 시작하는 범위만 쓴다
                joined = " ".join(x[1] for x in ordered[k : k + 5])
                for rng in RANGE_RE.finditer(joined):
                    a, b = int(rng.group(1)), int(rng.group(2))
                    if a == expect and expect < b <= expect + 5:
                        marks.append((ci, r.y0, "s", (a, b)))
                        break
    found = expect - 1
    if found != n_questions:
        raise ValueError(f"문항 {found}/{n_questions}개만 찾음")

    # 3) 각 마크부터 다음 마크 직전까지를 영역으로 (단을 넘어가면 이어 붙임)
    page_objs = [doc[i] for i in range(len(doc))]
    pages = [page_objs[c["page"]] for c in cols]
    blocks = []  # (kind, key, [regions], text)
    for i, (ci, y, kind, key) in enumerate(marks):
        end_ci, end_y = (marks[i + 1][0], marks[i + 1][1]) if i + 1 < len(marks) else (len(cols) - 1, None)
        regions, texts = [], []
        for cj in range(ci, end_ci + 1):
            c = cols[cj]
            y0 = y if cj == ci else c["top"]
            y1 = end_y if (cj == end_ci and end_y is not None) else c["bottom"]
            if cj == end_ci and end_y is not None and cj != ci and y1 - y0 < 5:
                continue
            rect = fitz.Rect(c["x0"], y0 - PAD, c["x1"], y1 - PAD)
            if cj != ci and not any(rect.y0 <= r.y0 and r.y1 <= rect.y1 + 1 for r, _ in c["lines"]):
                continue  # 이어지는 단에 글자가 없으면(장식선뿐이면) 이어 붙이지 않는다
            bot = ink_bottom(pages[cj], rect, c["lines"])
            if bot - rect.y0 < 6:
                continue
            rect.y1 = min(rect.y1, bot + PAD + 2)
            regions.append(dict(page=c["page"], x0=round(rect.x0, 1), y0=round(rect.y0, 1), x1=round(rect.x1, 1), y1=round(rect.y1, 1)))
            texts.append("\n".join(t for r, t in sorted(c["lines"], key=lambda x: (x[0].y0, x[0].x0)) if rect.y0 <= r.y0 < rect.y1))
        blocks.append((kind, key, regions, "\n".join(texts)))

    questions = []
    shared = {}
    for kind, key, regions, text in blocks:
        if kind == "s":
            for n in range(key[0], key[1] + 1):
                shared[n] = dict(regions=regions, text=text)
        else:
            q = dict(no=key, regions=regions, text=text)
            if key in shared:
                q["shared"] = shared[key]
            questions.append(q)
    return dict(width=round(W, 1), height=round(doc[0].rect.height, 1), pages=len(doc)), questions


def _work(args):
    pid, src, n = args
    try:
        return pid, segment(Path(src), n), None
    except Exception as e:  # noqa: BLE001
        return pid, None, str(e)


def main(only: str | None = None) -> None:
    from concurrent.futures import ProcessPoolExecutor

    catalog = json.loads(CATALOG.read_text())
    (OUT / "papers").mkdir(parents=True, exist_ok=True)
    (OUT / "pdf").mkdir(parents=True, exist_ok=True)
    index, failed, jobs = [], [], []
    for pid, p in sorted(catalog["papers"].items()):
        if only and only not in pid:
            continue
        src = RAW / f"{pid}.pdf"
        if not src.exists():  # CI 에서는 원본 대신 배포용 사본을 쓴다
            src = OUT / "pdf" / f"{pid}.pdf"
        if not src.exists() or not p.get("answers"):
            failed.append((pid, "정답 또는 PDF 없음"))
            continue
        jobs.append((pid, str(src), len(p["answers"])))
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(_work, jobs))
    for (pid, src, _), (_, res, err) in zip(jobs, results):
        p = catalog["papers"][pid]
        src = Path(src)
        if err:
            failed.append((pid, err))
            continue
        meta, qs = res
        for q in qs:
            q["answer"] = p["answers"][q["no"] - 1]
        dst = OUT / "pdf" / f"{pid}.pdf"
        if src.resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        paper = dict(id=pid, year=p["year"], subject=p["subject"], exams=p["exams"], booklet=p.get("booklet"),
                     answersFinal=p.get("answersFinal", True), **meta, questions=qs)
        (OUT / "papers" / f"{pid}.json").write_text(json.dumps(paper, ensure_ascii=False))
        index.append(dict(id=pid, year=p["year"], subject=p["subject"], exams=p["exams"], count=len(qs),
                          answersFinal=p.get("answersFinal", True)))
    if not only:
        index.sort(key=lambda x: (-x["year"], x["exams"][0], x["subject"]))
        (OUT / "index.json").write_text(json.dumps(dict(papers=index), ensure_ascii=False))
    print(f"ok {len(index)}, failed {len(failed)}")
    for pid, why in failed:
        print("  FAIL", pid, why)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
