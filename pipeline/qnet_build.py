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
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import segment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QNET = ROOT / "data" / "qnet"
OUT = ROOT / "web" / "public" / "data"
CATALOG = json.loads((ROOT / "web" / "src" / "exams.json").read_text())


def parse(text: str) -> dict:
    """제목/파일명에서 시험 구분 정보"""
    t = text.replace(" ", "")
    m_period = re.search(r"([1-4])교시", t)
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
                    if not name.lower().endswith(".pdf"):
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


def compatible(e: dict, f: dict) -> bool:
    if e["year"] != f["year"]:
        return False
    if e.get("track"):
        # 급수·일반/기계 같은 구분이 제목이나 파일명에 들어 있어야 한다
        hay = (f["title"] + f["name"]).replace(" ", "")
        tk = e["track"].replace(" ", "")
        if tk not in hay and tk.replace("경비지도사", "") not in hay:
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
    want = entry.get("booklet") or "A"
    same = [c for c in cands if c["booklet"] == want] or [c for c in cands if c["booklet"] is None] or cands
    # 교시가 적힌 파일을 우선
    same.sort(key=lambda c: (c["period"] is None, c["name"]))
    return same[0]


def slug(s: str) -> str:
    return re.sub(r"[\s/·()\[\]]+", "", s)


def build(exam_id: str, rebuild: bool = False) -> None:
    exam = next(e for e in CATALOG["exams"] if e["id"] == exam_id)
    gid = exam["qnet"]
    choices = exam["choices"]
    entries = json.loads((QNET / gid / "answers.json").read_text())
    files = paper_files(gid)
    has_special = any(e.get("round") == "특별" for e in entries)
    multi_stage = len({e.get("stage") for e in entries if e.get("stage")}) > 1
    (OUT / "papers").mkdir(parents=True, exist_ok=True)
    (OUT / "pdf").mkdir(parents=True, exist_ok=True)
    made, problems = [], []
    for e in sorted(entries, key=lambda x: (-x["year"], x.get("round") or "", x["period"])):
        tag = f"{e['year']} {e.get('round') or ''} {e.get('stage') or ''} {e['period']}교시".replace("  ", " ")
        track = f"-{slug(e['track'])}" if e.get("track") else ""
        prefix = f"{exam_id}-{e['year']}{'-특별' if e.get('round') == '특별' else ''}{'-' + e['stage'] if e.get('stage') == '2차' else ''}{track}-{e['period']}교시-"
        if not rebuild and any((OUT / "papers").glob(f"{prefix}*.json")):
            continue  # 이미 만든 교시 (CI 는 새로 생긴 것만)
        f = pick([f for f in files if compatible(e, f)], e)
        if not f:
            problems.append(f"{tag}: 맞는 문제지 파일 없음")
            continue
        if not f.get("kogl"):
            problems.append(f"{tag}: 공공누리 표시 없음 → 보류")
            continue
        subs = e["subjects"]
        first, last = subs[0]["from"], subs[-1]["to"]
        try:
            meta, qs = segment.segment(f["path"], last - first + 1, choices, first, [x["name"] for x in subs])
        except Exception as ex:  # noqa: BLE001
            # 시험지 번호가 1부터 다시 시작하는 경우
            try:
                meta, qs = segment.segment(f["path"], last - first + 1, choices, 1, [x["name"] for x in subs])
                for q in qs:
                    q["no"] += first - 1
            except Exception:  # noqa: BLE001
                problems.append(f"{tag}: 문항 나누기 실패 ({ex}) ← {f['name']}")
                continue
        pdf_id = f"{exam_id}-{e['year']}-{hashlib.sha1(f['path'].read_bytes()).hexdigest()[:10]}"
        shutil.copyfile(f["path"], OUT / "pdf" / f"{pdf_id}.pdf")
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
                exams=[exam["name"] + (" 특별시험" if e.get("round") == "특별" else "")],
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
