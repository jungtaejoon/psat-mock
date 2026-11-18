"""PSAT 기출 수집기.

국가공무원 채용시스템(gongmuwon.gosi.kr)의 '선택형 문제/정답' API에서
PSAT 3개 영역(언어논리·자료해석·상황판단) 문제 PDF와 정답을 받아
data/raw/ 아래에 저장하고 data/catalog.json 을 갱신한다.

이미 받은 시험은 건너뛰므로 주기적으로 실행하면 신규 시험만 추가된다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

BASE = "https://gongmuwon.gosi.kr"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CATALOG = ROOT / "data" / "catalog.json"

# PSAT 를 치르는 시험 종류 (testCd → 이름)
PSAT_TESTS = {
    "03": "5급 공채(행정)",
    "05": "5급 공채(과학기술)",
    "09": "외교관후보자",
    "15": "지역인재 7급",
    "06": "7급 공채",
    "28": "5급 민간경력자",
    "38": "7급 민간경력자",
}
SUBJECTS = {"언어논리영역": "언어논리", "자료해석영역": "자료해석", "상황판단영역": "상황판단"}
# 정답 비트마스크: 01=①, 02=②, 04=③, 08=④, 16=⑤, 00=전원정답, 32=아무거나 정답
BIT = {1: 1, 2: 2, 4: 3, 8: 4, 16: 5}

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (compatible; psat-archive-bot/1.0)"


def post(path: str, data: dict) -> requests.Response:
    for attempt in range(4):
        try:
            r = S.post(BASE + path, data=data, timeout=30)
            r.raise_for_status()
            time.sleep(0.3)
            return r
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def decode_answers(raw: str) -> list[list[int]]:
    """'16020204…' → [[5],[2],[2],[3]…]. 빈 리스트 = 모두 정답 처리."""
    out = []
    for i in range(0, len(raw), 2):
        v = int(raw[i : i + 2])
        if v == 0 or v == 32:
            out.append([1, 2, 3, 4, 5])
        else:
            out.append([n for b, n in BIT.items() if v & b])
    return out


def list_rows(test_cd: str) -> list[dict]:
    subs = post("/oprut/EvmArChcPrblmCransSbjctLst.do", {"testCd": test_cd}).json()
    rows = []
    for s in subs:
        if s["sbjctNm"] not in SUBJECTS:
            continue
        page = 1
        while True:
            d = post(
                "/oprut/EvmArChcPrblmCransSbjctInqSbjctTblLst.do",
                {"testCd": test_cd, "sbjctCd": s["sbjctCd"], "testCycl": s["testCycl"], "hdn_curr_page": page},
            ).json()
            rows += d["list"]
            if page >= d["pageNavi"]["totalPageCount"]:
                break
            page += 1
    return rows


def file_info(file_id: str, ext: str = "pdf") -> dict | None:
    """첨부 묶음에서 원하는 확장자 파일 정보를 고른다 (hwp·pdf 가 같이 묶여 있기도 하다)."""
    lst = post("/oprut/GetAtchFileLst.do", {"atchFileId": file_id}).json()
    for o in lst:
        if (o.get("fileExtnNm") or "").lower() == ext:
            return o
    return None


CIRC = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}


def answers_from_popup(r: dict) -> list[list[int]] | None:
    """구형 시험(정답구분 1·2): 정답보기 팝업 HTML 에 정답이 그대로 들어 있다."""
    resp = S.get(
        BASE + "/oprut/GosiJungdap.do",
        params=dict(enfcYr=r["enfcYr"], planCd=r["planCd"], cransSeCd=r["cransSeCd"], bktpNm=r["bktpNm"] or "", testCd=r["testCd"], sbjctCd=r["sbjctCd"]),
        timeout=30,
    )
    vals = dict(re.findall(r'name="cransNo(\d+)"[^>]*value="([^"]*)"', resp.text))
    out = []
    for i in range(1, 41):
        v = vals.get(str(i), "").strip()
        if not v:
            break
        nums = [CIRC[c] for c in v if c in CIRC] or [int(c) for c in re.findall(r"[1-5]", v)]
        out.append(nums if nums else [1, 2, 3, 4, 5])  # '전항정답' 등
    return out or None


def fetch_direct(file_path: str) -> bytes | None:
    url = BASE + "/rccom/view" + urllib.parse.quote(file_path)
    r = S.get(url, timeout=60)
    if r.ok and r.content[:4] == b"%PDF":
        return r.content
    return None


_pw = None


def fetch_via_widget(file_id: str) -> bytes | None:
    """현재 연도 파일은 RAONK 다운로더로만 받을 수 있어 헤드리스 브라우저를 쓴다."""
    global _pw
    from playwright.sync_api import sync_playwright

    if _pw is None:
        p = sync_playwright().start()
        b = p.chromium.launch()
        ctx = b.new_context(accept_downloads=True)
        pg = ctx.new_page()
        pg.goto(BASE + "/oprut/EvmArChcPrblmCransSbjctInqSbjctLst.do")
        pg.wait_for_function("typeof RAONKUPLOAD !== 'undefined'")
        pg.wait_for_timeout(1500)
        _pw = (p, b, pg)
    pg = _pw[2]
    try:
        with pg.expect_download(timeout=40000) as dl:
            pg.evaluate("id => fn_egov_downFile(id)", file_id)
        path = dl.value.path()
        data = Path(path).read_bytes()
        return data if data[:4] == b"%PDF" else None
    except Exception as e:  # noqa: BLE001
        print("   widget download failed:", e, file=sys.stderr)
        return None


def get_pdf(file_id: str) -> bytes | None:
    info = file_info(file_id)
    if info:
        data = fetch_direct(info["filePathNm"])
        if data:
            return data
    return fetch_via_widget(file_id)


def answers_from_post(pst_id: str, subject_nm: str, booklet: str) -> list[list[int]] | None:
    """정답 게시글 첨부 PDF(정답표)에서 해당 과목·책형 정답을 찾는다."""
    import fitz  # PyMuPDF

    html = post("/oprut/EvmArPrblmCransGdDtl.do", {"pstId": pst_id, "bbsId": "BBSMSTR_000000000138"}).text
    for fid in re.findall(r'fn_getFile\("([^"]+)"', html):
        info = file_info(fid)
        if not info:
            continue
        data = fetch_direct(info["filePathNm"]) or fetch_via_widget(fid)
        if not data:
            continue
        doc = fitz.open(stream=data, filetype="pdf")
        for page in doc:
            text = page.get_text()
            if SUBJECTS.get(subject_nm, subject_nm) not in text.replace(" ", ""):
                continue
            # 책형 표기: ㉮/㉯ 또는 가/나
            bk = {"가": "㉮", "나": "㉯"}.get(booklet, booklet)
            if bk not in text and f"{booklet}책형" not in text.replace(" ", ""):
                continue
            ans = parse_answer_table(page)
            if ans:
                return ans
    return None


def parse_answer_table(page) -> list[list[int]] | None:
    """정답표 페이지: '문번 정답' 열 쌍을 좌표로 묶는다."""
    words = page.get_text("words")  # x0,y0,x1,y1,word,...
    heads = [w for w in words if w[4] == "문번"]
    pairs: dict[int, int] = {}
    for h in heads:
        col_x0 = h[0]
        ans_head = min((w for w in words if w[4] == "정답" and w[0] > h[0] and abs(w[1] - h[1]) < 5), key=lambda w: w[0], default=None)
        if not ans_head:
            continue
        nums = [w for w in words if w[1] > h[3] and abs(w[0] - col_x0) < 25 and w[4].isdigit()]
        for n in nums:
            a = [w for w in words if abs(((w[1] + w[3]) / 2) - ((n[1] + n[3]) / 2)) < 4 and abs(w[0] - ans_head[0]) < 25]
            if a and re.fullmatch(r"[1-5,·]+", a[0][4]):
                pairs[int(n[4])] = a[0][4]
    if not pairs:
        return None
    n = max(pairs)
    if sorted(pairs) != list(range(1, n + 1)):
        return None
    return [[int(c) for c in re.findall(r"[1-5]", pairs[i])] for i in range(1, n + 1)]


def text_fingerprint(pdf: bytes) -> str:
    """같은 문제지가 여러 시험(5급 행정/과기/외교관 등)에 중복 등록돼 있어 본문으로 중복 제거."""
    import fitz

    doc = fitz.open(stream=pdf, filetype="pdf")
    body = []
    for page in doc:
        for line in page.get_text().splitlines():
            if re.search(r"쪽$|책형|필기시험|공채|채용", line):
                continue
            body.append(line.strip())
    return hashlib.sha1("".join(body).encode()).hexdigest()[:16]


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text()) if CATALOG.exists() else {"papers": {}, "sources": {}}
    papers, sources = catalog["papers"], catalog["sources"]
    added = 0

    for test_cd, test_nm in PSAT_TESTS.items():
        print(f"== {test_nm}")
        rows = list_rows(test_cd)
        seen = set()
        for r in rows:
            key = f"{r['enfcYr']}-{test_cd}-{r['sbjctCd']}"
            if key in seen:
                continue
            seen.add(key)
            src = sources.get(key)
            if src and src.get("paper") and src.get("final"):
                continue  # 확정정답까지 받은 시험은 다시 받지 않음
            subj = SUBJECTS[r["sbjctNm"]]
            print(f" - {r['enfcYr']} {subj} ({r['bktpNm']})", end=" ", flush=True)

            simu = post("/oprut/EvmArSimuTestSbjctPstIdOne.do", {"enfcYr": r["enfcYr"], "testCd": test_cd, "sbjctCd": r["sbjctCd"]}).json()
            answers = decode_answers(simu.get("wholAnswVl1") or "")
            pdf_id = simu.get("pdfPstFileId") or r.get("pdfPstFileId")
            final = bool(answers) and r.get("cransSeCd") in ("2", "4")
            if not answers and r.get("cransSeCd") in ("1", "2"):
                answers = answers_from_popup(r) or []
                final = bool(answers) and r["cransSeCd"] == "2"
                pdf_id = r.get("pdfPstFileId")  # 팝업 정답은 이 행의 책형 기준
            if not answers:
                pst = r.get("cfmtnAnswRlsPstId") or r.get("pransRlsPstId")
                if pst:
                    answers = answers_from_post(pst, r["sbjctNm"], r["bktpNm"] or "가") or []
                    final = bool(answers) and bool(r.get("cfmtnAnswRlsPstId"))
            if not pdf_id:
                print("no pdf")
                continue
            pdf = get_pdf(pdf_id)
            if not pdf:
                print("download failed")
                continue
            fp = text_fingerprint(pdf)
            pid = f"{r['enfcYr']}-{subj}-{fp}"
            (RAW / f"{pid}.pdf").write_bytes(pdf)
            p = papers.setdefault(pid, {"id": pid, "year": int(r["enfcYr"]), "subject": subj, "exams": [], "booklet": r["bktpNm"]})
            if test_nm not in p["exams"]:
                p["exams"].append(test_nm)
            if answers:
                p["answers"] = answers
                p["answersFinal"] = final
            sources[key] = {"paper": pid, "final": final}
            added += 1
            print(f"ok [{len(answers)}문항{'' if final else ' · 정답 미확정'}] → {pid}")

    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1))
    print(f"done. {added} updated, {len(papers)} unique papers")
    if _pw:
        _pw[1].close()
        _pw[0].stop()


if __name__ == "__main__":
    main()
