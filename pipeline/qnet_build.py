"""큐넷 문제지 + 최종정답 → 사이트용 문제지(과목별).

  python pipeline/qnet_build.py <시험 id>     # web/src/exams.json 의 qnet(gId) 사용

입력: data/qnet/<gId>/posts.json(qnet.py fetch), answers.json(정답표를 읽어 대조한 결과)
출력: web/public/data/papers/<id>.json (과목 하나 = 문제지 하나), web/public/data/pdf/<pdf id>.pdf

- 게시물 제목·파일명에서 연도, 정기/특별, 1차/2차, 교시, A/B형을 읽어 정답표 항목과 맞춘다.
- A형·B형이 함께 있으면 A형(정답표도 A형 기준)만 쓴다.
- 한 PDF(한 교시)를 통째로 나눈 뒤 정답표의 과목 범위로 잘라 과목별 문제지를 만든다.
  문항 번호는 과목 안에서 1부터 다시 매기고, 시험지에 인쇄된 번호는 orig 에 남긴다.
- PDF 는 한 번만 복사하고 과목별 문제지가 pdf 필드로 함께 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdfutil  # noqa: E402
import segment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QNET = ROOT / "data" / "qnet"
OUT = ROOT / "web" / "public" / "data"
CATALOG = json.loads((ROOT / "web" / "src" / "exams.json").read_text())


def parse(text: str) -> dict:
    """제목/파일명에서 시험 구분 정보"""
    t = text.replace(" ", "")
    m_period = re.search(r"([1-4])교시", t)
    if re.search(r"[1-4](?:[,~·][1-4])+교시", t):
        m_period = None  # '1,2교시'·'1~4교시': 여러 교시가 한 파일에 있다 (교시별 쪽은 period_pages 로 고른다)
    m_book = re.search(r"([ABab])형", t)
    return dict(
        round="특별" if "특별" in t else ("정기" if "정기" in t else None),
        stage="2차" if "2차" in t else ("1차" if "1차" in t else None),
        period=int(m_period.group(1)) if m_period else None,
        booklet=m_book.group(1).upper() if m_book else None,
    )


def paper_files(gid: str) -> list[dict]:
    """문제지 PDF 목록 (ZIP 안의 PDF 포함). 각 항목: path, year, round, stage, period, booklet, post, kogl"""
    src = QNET / gid
    posts = json.loads((src / "posts.json").read_text())
    out = []
    for p in posts.values():
        if p["kind"] != "paper" or not p["year"]:
            continue
        for f in p["files"]:
            path = src / f["local"]
            if not path.exists():
                continue
            ext = path.suffix.lower()
            items: list[tuple[Path, str]] = []
            if ext == ".pdf":
                items.append((path, f["name"]))
            elif ext == ".hwp" and path.with_suffix(".hwp.pdf").exists():
                items.append((path.with_suffix(".hwp.pdf"), f["name"]))  # pipeline/hwp2pdf.py 로 바꿔 둔 것
            elif ext == ".zip":
                xdir = src / "x"
                xdir.mkdir(exist_ok=True)
                z = zipfile.ZipFile(path)
                for i, info in enumerate(z.infolist()):
                    name = info.filename
                    try:
                        name = name.encode("cp437").decode("cp949")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                    low = name.lower()
                    if low.endswith(".hwp"):
                        conv = xdir / f"{p['seq']}-{f['fseq']}-{i}.hwp.pdf"
                        if conv.exists():
                            items.append((conv, Path(name).name))
                        continue
                    if not low.endswith(".pdf"):
                        continue
                    dst = xdir / f"{p['seq']}-{f['fseq']}-{i}.pdf"
                    if not dst.exists():
                        dst.write_bytes(z.read(info))
                    items.append((dst, Path(name).name))
            for path_, name in items:
                info = parse(p["title"])
                for k, v in parse(name).items():  # 파일명 정보가 더 구체적이다
                    if v is not None:
                        info[k] = v
                out.append(dict(path=path_, name=name, title=p["title"], year=p["year"], post=p["seq"], kogl=p.get("kogl"), **info))
    return out


def session_of(text: str) -> int | None:
    m = re.search(r"제\s*(\d{1,3})\s*회", text or "")
    return int(m.group(1)) if m else None


def compatible(e: dict, f: dict) -> bool:
    if e["year"] != f["year"]:
        return False
    # 한 해에 시험이 두 번(예: 청소년상담사 2016 제14회·제15회) 있으면 회차가 같은 문제지만
    se, sf = e.get("session"), session_of(f["title"] + " " + f["name"])
    if se and sf and se != sf:
        return False
    if e.get("track"):
        # 급수·일반/기계 같은 구분이 제목이나 파일명에 들어 있어야 한다
        hay = (f["title"] + f["name"]).replace(" ", "")
        tk = e["track"].replace(" ", "")
        if tk not in hay and tk.replace("경비지도사", "") not in hay and tk[:3] not in hay:
            return False
        # 청소년상담사 1·2·3급처럼 급수가 다르면 다른 시험지. 게시물 제목엔 급수가 다 적혀 있으니 파일명을 먼저 본다
        grade = re.search(r"(\d)급", tk)
        name_grades = re.findall(r"\d급", f["name"].replace(" ", ""))
        if grade and name_grades and grade.group(0) not in name_grades:
            return False
    if (e.get("round") == "특별") != (f["round"] == "특별"):
        return False
    if e.get("stage") and f["stage"] and e["stage"] != f["stage"]:
        return False
    if f["period"] is not None and e["period"] != f["period"]:
        return False
    return True


def pick(cands: list[dict], entry: dict) -> dict | None:
    if not cands:
        return None
    # 교시가 안 적힌 파일이 여럿이면 과목 이름이 파일명에 들어 있는 것을 고른다
    names = [x["name"].replace(" ", "") for x in entry.get("subjects", [])]
    by_subject = [c for c in cands if any(n and n[:4] in c["name"].replace(" ", "") for n in names)]
    if by_subject:
        cands = by_subject
    want = entry.get("booklet") or "A"
    same = [c for c in cands if c["booklet"] == want] or [c for c in cands if c["booklet"] is None] or cands
    # 교시가 적힌 파일을 우선
    # 큐넷이 올린 PDF 를 HWP 에서 바꾼 PDF 보다 먼저 (같은 시험지가 둘 다 있을 때)
    same.sort(key=lambda c: (str(c["path"]).endswith(".hwp.pdf"), c["period"] is None, c["name"]))
    return same[0]


def period_pages(path: Path, period: int) -> Path:
    """한 PDF 에 여러 교시가 들어 있으면(관세사 2014·2018~2020 1차: 1·2교시 합본) 그 교시 쪽만 떼어 낸 PDF.
    쪽 머리글·꼬리글의 'N교시' 로 교시를 가른다. 교시가 하나뿐이거나 머리글·꼬리글이 없으면(그림 PDF) 원본 그대로."""
    import fitz

    doc = fitz.open(path)
    marks: list[int | None] = []
    for page in doc:
        r = page.rect
        head = "".join(page.get_text(clip=fitz.Rect(0, y0, r.width, y1)) for y0, y1 in ((0, r.height * 0.12), (r.height * 0.88, r.height))).replace(" ", "")
        m = re.findall(r"([1-4])교시", head)
        marks.append(int(m[0]) if len(set(m)) == 1 else None)
    found = [m for m in marks if m]
    if len(set(found)) < 2 or period not in found:
        return path
    cur = found[0]
    pages = []
    for i, m in enumerate(marks):
        cur = m or cur  # 표시 없는 쪽은 앞 쪽의 교시
        if cur == period:
            pages.append(i)
    out = path.with_name(f"{path.stem}-{period}교시.pdf")
    if not out.exists():
        sub = fitz.open()
        for i in pages:
            sub.insert_pdf(doc, from_page=i, to_page=i)
        sub.save(out, garbage=3, deflate=True)
    return out


def seg_range(path, n: int, choices: int, first: int, heads: list[str]):
    """문항 first..first+n-1 을 나눈다. 시험지 번호가 1부터 다시 시작하면 1부터 찾고 번호를 옮긴다"""
    try:
        return segment.segment(path, n, choices, first, heads)
    except Exception:  # noqa: BLE001
        meta, qs = segment.segment(path, n, choices, 1, heads)
        for q in qs:
            q["no"] += first - 1
        return meta, qs


def slug(s: str) -> str:
    return re.sub(r"[\s/·()\[\]]+", "", s)


def build(exam_id: str, rebuild: bool = False) -> None:
    exam = next(e for e in CATALOG["exams"] if e["id"] == exam_id)
    gid = exam["qnet"]
    choices = exam["choices"]
    entries = json.loads((QNET / gid / "answers.json").read_text())
    posts = json.loads((QNET / gid / "posts.json").read_text())
    for e in entries:
        e["session"] = session_of(posts.get(f"answer-{e.get('post')}", {}).get("title", ""))
    # 같은 해 회차가 둘 이상이면 첫 회차를 뺀 나머지 회차에만 주소에 "-제N회" 를 붙인다 (기존 주소 유지)
    first_session = {}
    for e in entries:
        if e["session"] and not e.get("round"):
            first_session[e["year"]] = min(first_session.get(e["year"], e["session"]), e["session"])
    files = paper_files(gid)
    has_special = any(e.get("round") == "특별" for e in entries)
    multi_stage = len({e.get("stage") for e in entries if e.get("stage")}) > 1
    (OUT / "papers").mkdir(parents=True, exist_ok=True)
    (OUT / "pdf").mkdir(parents=True, exist_ok=True)
    made, problems = [], []
    for e in sorted(entries, key=lambda x: (-x["year"], x.get("round") or "", x["period"])):
        tag = f"{e['year']} {e.get('round') or ''} {e.get('stage') or ''} {e['period']}교시".replace("  ", " ")
        track = f"-{slug(e['track'])}" if e.get("track") else ""
        extra_session = e.get("session") and not e.get("round") and e["session"] != first_session.get(e["year"])
        prefix = f"{exam_id}-{e['year']}{'-제' + str(e['session']) + '회' if extra_session else ''}{'-특별' if e.get('round') == '특별' else ''}{'-' + e['stage'] if e.get('stage') == '2차' else ''}{track}-{e['period']}교시-"
        if not rebuild and any((OUT / "papers").glob(f"{prefix}*.json")):
            continue  # 이미 만든 교시 (CI 는 새로 생긴 것만)
        f = pick([f for f in files if compatible(e, f)], e)
        if not f:
            problems.append(f"{tag}: 맞는 문제지 파일 없음")
            continue
        f = dict(f, path=period_pages(f["path"], e["period"]))
        if not f.get("kogl"):
            problems.append(f"{tag}: 공공누리 표시 없음 → 보류")
            continue
        subs_all = e["subjects"]
        first, last = subs_all[0]["from"], subs_all[-1]["to"]
        # 보통은 교시 PDF 하나에 과목 여러 개. 옛 시험은 과목마다 파일이 따로 있다 → 과목별로 나눈다
        chunks = []  # (파일, meta, 문항들, 이 파일의 과목들)
        try:
            meta, qs = seg_range(f["path"], last - first + 1, choices, first, [x["name"] for x in subs_all])
            chunks.append((f, meta, qs, subs_all))
        except Exception as ex:  # noqa: BLE001
            err = ex
            for sub in subs_all:
                key = sub["name"].replace(" ", "")[:3]
                # 과목별 파일: 공통 과목(예: 회계학) 파일엔 선택과목 이름이 없으니 선택과목(track) 조건은 빼고 과목 이름으로 고른다
                cands = [g for g in files if compatible(dict(e, track=None), g) and key and key in g["name"].replace(" ", "")]
                g = pick(cands, dict(e, subjects=[sub]))
                if not g:
                    chunks = []
                    break
                try:
                    meta, qs = seg_range(g["path"], sub["to"] - sub["from"] + 1, choices, sub["from"], [sub["name"]])
                except Exception:  # noqa: BLE001
                    chunks = []
                    break
                chunks.append((g, meta, qs, [sub]))
            if not chunks:
                problems.append(f"{tag}: 문항 나누기 실패 ({err}) ← {f['name']}")
                continue
        for f, meta, qs, subs in chunks:
            pdf_id = f"{exam_id}-{e['year']}-{hashlib.sha1(f['path'].read_bytes()).hexdigest()[:10]}"
            pdfutil.copy_compressed(f["path"], OUT / "pdf" / f"{pdf_id}.pdf")
            parts = ["특별시험" if e.get("round") == "특별" else ("정기시험" if has_special else "")]
            parts += [e.get("stage") or "" if multi_stage else "", e.get("track") or ""]
            group = " ".join(p for p in parts if p) or "필기"
            text_items = {int(x) for x in e.get("text_items", [])}
            for s in subs:
                sq = []
                for q in qs:
                    if s["from"] <= q["no"] <= s["to"] and q["no"] not in text_items:  # 주관식은 빼고 객관식만
                        ans = e["answers"].get(str(q["no"]))
                        nq = dict(q, orig=q["no"], no=len(sq) + 1, answer=ans)
                        sq.append(nq)
                if not sq:
                    continue
                if any(q["answer"] is None for q in sq):
                    problems.append(f"{tag} {s['name']}: 정답 빠진 문항")
                    continue
                pid = f"{prefix}{slug(s['name'])}"
                paper = dict(
                    id=pid,
                    exam=exam_id,
                    group=group,
                    year=e["year"],
                    subject=s["name"],
                    exams=[exam["name"] + (" 특별시험" if e.get("round") == "특별" else "") + (f" 제{e['session']}회" if extra_session else "")],
                    answersFinal=True,
                    choices=choices,
                    kogl=f.get("kogl"),
                    pdf=pdf_id,
                    source=dict(post=f["post"], title=f["title"], answerPost=e.get("post")),
                    **meta,
                    questions=sq,
                )
                (OUT / "papers" / f"{pid}.json").write_text(json.dumps(paper, ensure_ascii=False))
                made.append((pid, len(sq), sum("choices" in q for q in sq)))
    for pid, n, c in made:
        print(f"ok {pid}: {n}문항 (보기 위치 {c})")
    for p in problems:
        print("  !", p)
    print(f"{exam_id}: 문제지 {len(made)}개, 문제 {len(problems)}건")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for ex in args or [e["id"] for e in CATALOG["exams"] if e.get("qnet") and e["status"] == "live"]:
        build(ex, rebuild="--rebuild" in sys.argv)
