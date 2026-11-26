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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scrape as sc  # noqa: E402
import pdfutil  # noqa: E402
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


CIRC_NUM = {c: str(i) for i, c in enumerate("①②③④⑤⑥⑦⑧⑨", 1)} | {chr(0x24B6 + k): chr(65 + k) for k in range(26)}  # Ⓐ→A


def hwp_tokens(data: bytes) -> list[str]:
    """HWP 본문 문단 글자 → 줄 목록 (표 칸마다 한 문단)"""
    import io
    import struct
    import zlib

    import olefile

    o = olefile.OleFileIO(io.BytesIO(data))
    compressed = o.openstream("FileHeader").read()[36] & 1
    out = []
    for name in sorted((e for e in o.listdir() if e[0] == "BodyText"), key=lambda e: int(e[1][7:])):
        raw = o.openstream(name).read()
        if compressed:
            raw = zlib.decompress(raw, -15)
        k = 0
        while k + 4 <= len(raw):
            h = struct.unpack_from("<I", raw, k)[0]
            tag, size = h & 0x3FF, h >> 20
            k += 4
            if size == 0xFFF:
                size = struct.unpack_from("<I", raw, k)[0]
                k += 4
            if tag == 67:  # PARA_TEXT
                t = raw[k : k + size].decode("utf-16le", "replace")
                t = re.sub(r"[\x00-\x1f].{7}|[\x00-\x1f]", "", t)  # 확장 제어문자(8글자) 제거
                out += [x.strip() for x in t.split("\n") if x.strip()]
            k += size
    return out


def _broken_font_map(doc) -> dict[int, str]:
    """MuPDF 가 못 여는 글꼴(하위 글꼴 종류가 잘못 적힌 Type0)은 글자가 '\\x00\\x03' 처럼 코드 그대로 나온다.
    그런 글꼴의 ToUnicode 표를 직접 읽어 코드 → 글자 표를 만든다."""
    out: dict[int, str] = {}
    seen = set()
    for page in doc:
        for xref, _ext, typ, *_ in page.get_fonts():
            if xref in seen or typ != "Type0":
                continue
            seen.add(xref)
            d = doc.xref_get_key(xref, "DescendantFonts")[1]
            m = re.search(r"(\d+) 0 R", d)
            if not m or doc.xref_get_key(int(m.group(1)), "Subtype")[1] in ("/CIDFontType0", "/CIDFontType2"):
                continue
            tu = doc.xref_get_key(xref, "ToUnicode")[1]
            m = re.match(r"(\d+) 0 R", tu)
            if not m:
                continue
            cmap = doc.xref_stream(int(m.group(1))).decode("latin-1")
            for blk in re.findall(r"beginbfchar(.*?)endbfchar", cmap, re.S):
                for a, b in re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", blk):
                    if b.lower() != "ffff":
                        out[int(a, 16)] = bytes.fromhex(b).decode("utf-16be", "replace")
            for blk in re.findall(r"beginbfrange(.*?)endbfrange", cmap, re.S):
                for a, b, c in re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", blk):
                    for k in range(int(a, 16), int(b, 16) + 1):
                        out[k] = chr(int(c, 16) + k - int(a, 16))
    return out


def _fix_codes(t: str, cmap: dict[int, str]) -> str:
    if cmap and re.fullmatch(r"(?:\x00[\s\S])+", t):
        codes = [ord(t[k + 1]) for k in range(0, len(t), 2)]
        if all(c in cmap for c in codes):
            return "".join(cmap[c] for c in codes)
    return t


def _attachments(pst_id: str) -> list[tuple[str, bytes]]:
    """게시물 첨부 PDF·HWP 들 (ZIP 안의 것 포함)"""
    import io
    import urllib.parse
    import zipfile

    html = sc.post("/oprut/EvmArPrblmCransGdDtl.do", {"pstId": pst_id, "bbsId": "BBSMSTR_000000000138"}).text
    out = []
    for fid in re.findall(r'fn_getFile\("([^"]+)"', html):
        try:
            files = sc.post("/oprut/GetAtchFileLst.do", {"atchFileId": fid}).json()
        except ValueError:  # 지워진 첨부는 오류 페이지가 온다
            files = []
        for o in files:
            ext = (o.get("fileExtnNm") or "").lower()
            if ext not in ("pdf", "zip", "hwp"):
                continue
            r = sc.S.get(sc.BASE + "/rccom/view" + urllib.parse.quote(o["filePathNm"]), timeout=60)
            data = r.content if r.ok else b""
            if ext == "pdf" and data[:4] != b"%PDF":
                data = sc.fetch_via_widget(fid) or b""
            if data[:4] == b"%PDF":
                out.append(("pdf", data))
            elif data[:4] == b"\xd0\xcf\x11\xe0":
                out.append(("hwp", data))
            elif data[:2] == b"PK":
                z = zipfile.ZipFile(io.BytesIO(data))
                for zi in z.infolist():
                    e = zi.filename.lower().rsplit(".", 1)[-1]
                    if e in ("pdf", "hwp"):
                        out.append((e, z.read(zi)))
    out.sort(key=lambda x: x[0] != "pdf")  # PDF 먼저, 글자가 깨졌으면 HWP
    return out


def _norm_subject(t: str) -> str:
    """과목명 비교용: 괄호 설명·공백·가운뎃점 제거 ('인사ㆍ조직론' = '인사·조직론', '국어(지역인재9급)' → '국어')"""
    return re.sub(r"[^0-9A-Za-z가-힣]", "", re.sub(r"\(.*?\)", "", t))


def _rows(toks: list[str]) -> list[dict]:
    """정답표 글자 줄 → 행 목록"""
    # 다듬기: "15　데이터베이스론"(연번이 붙은 과목명) → 과목명만, "정답" "없음" 두 조각 → 한 칸(문항 무효 = 모두 정답)
    fixed: list[str] = []
    for t in toks:
        t = re.sub(r"^\d+[\s\u3000]+(?=[가-힣A-Za-z])", "", t)
        if t == "없음" and fixed and fixed[-1] == "정답":
            fixed[-1] = "정답없음"
            continue
        fixed.append(t)
    toks = fixed
    nums = {int(m.group(1)) for t in toks if (m := re.fullmatch(r"(\d{1,2})번", t))}
    nums |= {int(t) for t, u in zip(toks, toks[1:]) if u == "번" and t.isdigit()}  # '1' '번' 으로 나뉜 머리줄
    toks = [t for t in toks if t != "번"]
    if not nums:
        return []
    sizes = sorted({max(nums), 25, 20}, reverse=True)
    ans_re = re.compile(r"[1-5](\s*,\s*[1-5])*|전항.*|모두.*|정답없음")
    out: list[dict] = []
    name: list[str] = []  # 과목명 칸이 두 줄로 나뉘기도 한다 ('정보' + '보호론')
    subject, i = None, 0
    while i < len(toks):
        t = toks[i]
        # 책형(가·A·S·②·Ⓑ…) + 정답 n 개 → 현재 과목의 한 행 (한 과목에 책형이 여럿일 수 있다)
        if subject and re.fullmatch(r"[가-힣A-Za-z①-⑨Ⓐ-Ⓩ]형?", t):
            n = next((n for n in sizes if len(toks[i + 1 : i + 1 + n]) == n and all(ans_re.fullmatch(v) for v in toks[i + 1 : i + 1 + n])), 0)
            if n:
                ans = [[int(x) for x in re.findall(r"[1-5]", v)] or [1, 2, 3, 4] for v in toks[i + 1 : i + 1 + n]]
                b = t.rstrip("형")
                out.append(dict(subject=subject, booklet=CIRC_NUM.get(b, b), answers=ans))
                name = []
                i += 1 + n
                continue
        if not re.fullmatch(r"[\d,]+|\d+번|연번|과목명|과목|과목코드|코드|책형|.*정답표.*|.*시행\)", t) and len(t.replace(" ", "")) >= 2 and not t.startswith("20"):
            name.append(_norm_subject(t))
            subject = "".join(name)
        else:
            name = []
        i += 1
    return out


def answer_table(pst_id: str) -> list[dict]:
    """확정정답 게시물 정답표(PDF, 글자가 깨졌으면 HWP) → [{subject, booklet, answers}]"""
    if pst_id in _table_cache:
        return _table_cache[pst_id]
    import fitz

    out: list[dict] = []
    for kind, data in _attachments(pst_id):
        try:
            if kind == "pdf":
                doc = fitz.open(stream=data, filetype="pdf")
                cmap = _broken_font_map(doc)
                toks = [_fix_codes(t, cmap).strip() for page in doc for t in page.get_text().split("\n") if t.strip()]
            else:
                toks = hwp_tokens(data)
        except Exception:  # noqa: BLE001
            continue
        if "정답" not in "".join(toks[:8]):
            continue  # 문제지 첨부는 건너뛴다
        # 한 게시물에 정답표가 여럿일 수 있다 (2014 지방직: '지방7급 등' 표와 '방재안전직 9급' 표에 국어·영어·한국사가 모두 있다).
        # 표 제목을 행에 남겨 두고, 같은 표의 PDF·HWP 중복만 거른다
        title = next((t for t in toks[:8] if "정답" in t), "")
        seen = {(x["subject"], x["booklet"], x["title"]) for x in out}
        out += [dict(r, title=title) for r in _rows(toks) if (r["subject"], r["booklet"], title) not in seen]
    _table_cache[pst_id] = out
    return out


def answers_for(r: dict) -> tuple[list[list[int]] | None, bool]:
    if r.get("cransSeCd") in ("1", "2"):
        a = sc.answers_from_popup(r)
        return a, bool(a) and r["cransSeCd"] == "2"
    if r.get("cfmtnAnswRlsPstId"):
        name = _norm_subject(r["sbjctNm"])
        bk = (r.get("bktpNm") or "").strip()
        rows = [row for row in answer_table(r["cfmtnAnswRlsPstId"]) if row["subject"] == name and row["booklet"] == CIRC_NUM.get(bk, bk or row["booklet"])]
        if len({json.dumps(row["answers"]) for row in rows}) > 1:
            # 같은 과목이 여러 정답표에 있으면 과목명 괄호의 급수('국어(지방9급)', '국어(한문포함)(지방7급등)')가 제목에 든 표를 고른다
            grade = _grade(r["sbjctNm"])
            rows = [row for row in rows if grade and grade in row["title"].replace(" ", "")]
            if len(rows) != 1:
                return None, False  # 어느 표인지 모르면 틀린 정답을 쓰느니 비워 둔다
        if rows:
            return rows[0]["answers"], True
    return None, False


def pdf_booklet(src: Path) -> str | None:
    """문제지 첫 쪽에 인쇄된 책형(A·B·C·D…)"""
    import fitz

    try:
        m = re.search(r"([A-Z])\s*책\s*형", fitz.open(src)[0].get_text())
    except Exception:  # noqa: BLE001
        return None
    return m.group(1) if m else None


def _grade(sbjct_nm: str) -> str | None:
    """'국어(한문포함)(지방7급등)' → '7급'"""
    m = re.findall(r"\(([^()]*\d급[^()]*)\)", sbjct_nm)
    g = re.search(r"\d급", m[-1]) if m else None
    return g.group(0) if g else None


# 같은 해·같은 시험에 이름이 같은 과목이 급수별로 따로 있으면(2014 지방직 국어·영어·한국사: 7급 등 / 9급) 주소가 겹친다.
# 겹치면 급수를 주소와 과목명에 붙인다. 이미 공개된 주소는 그대로 둔다 (아래 과목은 급수 없는 주소를 계속 쓴다).
KEEP_PLAIN_ID = {
    "local-2014-34-국어": "국어(지방9급)",
    "local-2014-34-영어": "영어(지방7급등)",
    "local-2014-34-한국사": "한국사(지방7급등)",
}


def build(exam_id: str, only: str | None = None, rebuild: bool = False, since: int = 0) -> None:
    exam = next(e for e in CATALOG["exams"] if e["id"] == exam_id)
    (OUT / "papers").mkdir(parents=True, exist_ok=True)
    (OUT / "pdf").mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    made, problems = 0, []
    for test_cd in exam["gosi"]:
        all_rows = rows_of(test_cd)
        names: dict[tuple, set] = {}
        for r in all_rows:
            names.setdefault((r["enfcYr"], re.sub(r"\(.*?\)", "", r["sbjctNm"]).strip()), set()).add(r["sbjctNm"])
        for r in all_rows:
            if only and only not in r["sbjctNm"]:
                continue
            subject = re.sub(r"\(.*?\)", "", r["sbjctNm"]).strip()
            grade = _grade(r["sbjctNm"]) if len(names[(r["enfcYr"], subject)]) > 1 else None
            if subject.endswith("영역"):
                continue  # 7급 PSAT(언어논리·자료해석·상황판단)은 PSAT 시험에 이미 있다
            year = int(r["enfcYr"])
            if year < since:
                continue
            slug = re.sub(r"[\s/·()]+", "", subject)
            pid = f"{exam_id}-{year}-{test_cd}-{slug}"
            if grade:  # 급수만 다른 같은 이름 과목
                subject = f"{subject}({grade})"
                if KEEP_PLAIN_ID.get(pid) != r["sbjctNm"]:
                    pid = f"{pid}-{grade}"
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
            # 목록의 책형과 문제지 PDF 의 책형이 다른 경우가 있다(2017 지방직 식용작물·응용역학개론: B 행에 Ⓓ책형 PDF).
            # 정답은 PDF 에 인쇄된 책형 것을 쓴다.
            booklet = r.get("bktpNm")
            pdf_bk = pdf_booklet(src)
            if pdf_bk and booklet and pdf_bk != booklet:
                alt, alt_final = answers_for(dict(r, bktpNm=pdf_bk))
                if alt:
                    answers, final, booklet = alt, alt_final, pdf_bk
                else:
                    problems.append(f"{year} {subject}: 목록 책형 {booklet} / PDF 책형 {pdf_bk}, {pdf_bk} 정답 없음")
                    continue
            try:
                meta, qs = segment.segment(src, len(answers), exam["choices"], 1, [subject])
            except Exception as ex:  # noqa: BLE001
                problems.append(f"{year} {subject}: 문항 나누기 실패 ({ex})")
                continue
            for q in qs:
                q["answer"] = answers[q["no"] - 1]
            pdf_id = f"{exam_id}-{hashlib.sha1(src.read_bytes()).hexdigest()[:12]}"
            pdfutil.copy_compressed(src, OUT / "pdf" / f"{pdf_id}.pdf")
            paper = dict(id=pid, exam=exam_id, group=r.get("testNm") and exam.get("groupOf", {}).get(test_cd) or exam["name"], year=year,
                         subject=subject, exams=[r.get("testNm") or exam["name"]], booklet=booklet, answersFinal=final,
                         choices=exam["choices"], pdf=pdf_id, **meta, questions=qs)
            (OUT / "papers" / f"{pid}.json").write_text(json.dumps(paper, ensure_ascii=False))
            made += 1
    for p in problems:
        print("  !", p)
    print(f"{exam_id}: 문제지 {made}개, 문제 {len(problems)}건")


if __name__ == "__main__":
    # --since=2025 : 그 해 이후만 (CI 매일 갱신용: 정답이 새로 확정된 시험만 보면 된다)
    since = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--since=")), 0)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args[:1] or [e["id"] for e in CATALOG["exams"] if e.get("gosi") and e["status"] == "live"]
    for ex in ids:
        build(ex, args[1] if len(args) > 1 else None, "--rebuild" in sys.argv, since)
