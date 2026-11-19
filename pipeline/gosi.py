"""인사혁신처 공무원 시험(9급·7급 공채, 지방직 등) 기출 수집 → 사이트용 문제지.

  python pipeline/gosi.py <시험 id> [과목 일부] [--rebuild]   # web/src/exams.json 의 gosi(testCd 목록) 사용

PSAT 수집기(scrape.py)와 같은 사이트·API 를 쓴다.
- 정답: 2012년 이전(정답구분 1·2)은 정답 팝업, 이후는 확정정답 게시물의 정답표 PDF(과목·책형별 행)에서 읽는다.
- 문제지 PDF 는 data/gosi/raw 에 받아 두고, 문항을 나눠 web/public/data/papers/<id>.json 으로 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scrape as sc  # noqa: E402
import segment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "gosi" / "raw"
OUT = ROOT / "web" / "public" / "data"
CATALOG = json.loads((ROOT / "web" / "src" / "exams.json").read_text())
_table_cache: dict[str, list[dict]] = {}


def rows_of(test_cd: str) -> list[dict]:
    subs = sc.post("/oprut/EvmArChcPrblmCransSbjctLst.do", {"testCd": test_cd}).json()
    rows = []
    for s in subs:
        page = 1
        while True:
            d = sc.post("/oprut/EvmArChcPrblmCransSbjctInqSbjctTblLst.do", {"testCd": test_cd, "sbjctCd": s["sbjctCd"], "testCycl": s["testCycl"], "hdn_curr_page": page}).json()
            rows += d["list"]
            if page >= d["pageNavi"]["totalPageCount"]:
                break
            page += 1
    return rows


def answer_table(pst_id: str) -> list[dict]:
    """확정정답 게시물 정답표 PDF → [{subject, booklet, answers}] (행마다 과목·책형·정답 N개)"""
    if pst_id in _table_cache:
        return _table_cache[pst_id]
    import fitz

    html = sc.post("/oprut/EvmArPrblmCransGdDtl.do", {"pstId": pst_id, "bbsId": "BBSMSTR_000000000138"}).text
    out: list[dict] = []
    for fid in re.findall(r'fn_getFile\("([^"]+)"', html):
        info = sc.file_info(fid)
        if not info:
            continue
        data = sc.fetch_direct(info["filePathNm"]) or sc.fetch_via_widget(fid)
        if not data or data[:4] != b"%PDF":
            continue
        doc = fitz.open(stream=data, filetype="pdf")
        if "정답" not in doc[0].get_text()[:200]:
            continue  # 문제지 첨부는 건너뛴다
        toks = [t.strip() for page in doc for t in page.get_text().split("\n") if t.strip()]
        n = max((int(m.group(1)) for t in toks if (m := re.fullmatch(r"(\d{1,2})번", t))), default=0)
        ans_re = re.compile(r"[1-5](\s*,\s*[1-5])*|전항.*|모두.*")
        subject, i = None, 0
        while i < len(toks) and n:
            t = toks[i]
            # 책형 한 글자 + 정답 n 개 → 현재 과목의 한 행 (한 과목에 책형이 여럿일 수 있다)
            if subject and re.fullmatch(r"[가-힣A-Za-z]형?", t) and all(ans_re.fullmatch(v) for v in toks[i + 1 : i + 1 + n]) and len(toks[i + 1 : i + 1 + n]) == n:
                ans = [[int(x) for x in re.findall(r"[1-5]", v)] or [1, 2, 3, 4] for v in toks[i + 1 : i + 1 + n]]
                out.append(dict(subject=subject, booklet=t.rstrip("형"), answers=ans))
                i += 1 + n
                continue
            if not re.fullmatch(r"[\d,]+|\d+번|연번|과목명|과목|코드|책형|정답표.*|.*시행\)", t) and len(t.replace(" ", "")) >= 2 and not t.startswith("20"):
                subject = re.sub(r"\(.*?\)", "", t.replace(" ", ""))
            i += 1
        if out:
            break
    _table_cache[pst_id] = out
    return out


def answers_for(r: dict) -> tuple[list[list[int]] | None, bool]:
    if r.get("cransSeCd") in ("1", "2"):
        a = sc.answers_from_popup(r)
        return a, bool(a) and r["cransSeCd"] == "2"
    if r.get("cfmtnAnswRlsPstId"):
        name = r["sbjctNm"].replace(" ", "")
        name = re.sub(r"\(.*?\)", "", name)  # '국어(지역인재9급)' → '국어'
        for row in answer_table(r["cfmtnAnswRlsPstId"]):
            if row["subject"] == name and row["booklet"] == (r.get("bktpNm") or row["booklet"]):
                return row["answers"], True
    return None, False


def build(exam_id: str, only: str | None = None, rebuild: bool = False) -> None:
    exam = next(e for e in CATALOG["exams"] if e["id"] == exam_id)
    (OUT / "papers").mkdir(parents=True, exist_ok=True)
    (OUT / "pdf").mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    made, problems = 0, []
    for test_cd in exam["gosi"]:
        for r in rows_of(test_cd):
            if only and only not in r["sbjctNm"]:
                continue
            subject = re.sub(r"\(.*?\)", "", r["sbjctNm"]).strip()
            year = int(r["enfcYr"])
            slug = re.sub(r"[\s/·()]+", "", subject)
            pid = f"{exam_id}-{year}-{test_cd}-{slug}"
            if not rebuild and (OUT / "papers" / f"{pid}.json").exists():
                continue
            if year < 2014 and exam.get("minYear", 2014) >= 2014:
                continue
            fid = r.get("pdfPstFileId")
            if not fid:
                problems.append(f"{year} {subject}: 문제지 없음")
                continue
            answers, final = answers_for(r)
            if not answers:
                problems.append(f"{year} {subject} {r.get('bktpNm')}: 정답 없음")
                continue
            src = RAW / f"{test_cd}-{year}-{hashlib.sha1(fid.encode()).hexdigest()[:10]}.pdf"
            if not src.exists():
                data = sc.get_pdf(fid)
                if not data:
                    problems.append(f"{year} {subject}: 내려받기 실패")
                    continue
                src.write_bytes(data)
            try:
                meta, qs = segment.segment(src, len(answers), exam["choices"], 1, [subject])
            except Exception as ex:  # noqa: BLE001
                problems.append(f"{year} {subject}: 문항 나누기 실패 ({ex})")
                continue
            for q in qs:
                q["answer"] = answers[q["no"] - 1]
            pdf_id = f"{exam_id}-{hashlib.sha1(src.read_bytes()).hexdigest()[:12]}"
            shutil.copyfile(src, OUT / "pdf" / f"{pdf_id}.pdf")
            paper = dict(id=pid, exam=exam_id, group=r.get("testNm") and exam.get("groupOf", {}).get(test_cd) or exam["name"], year=year,
                         subject=subject, exams=[r.get("testNm") or exam["name"]], booklet=r.get("bktpNm"), answersFinal=final,
                         choices=exam["choices"], pdf=pdf_id, **meta, questions=qs)
            (OUT / "papers" / f"{pid}.json").write_text(json.dumps(paper, ensure_ascii=False))
            made += 1
    for p in problems:
        print("  !", p)
    print(f"{exam_id}: 문제지 {made}개, 문제 {len(problems)}건")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build(args[0], args[1] if len(args) > 1 else None, "--rebuild" in sys.argv)
