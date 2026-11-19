"""큐넷(한국산업인력공단) 국가전문자격 기출 수집.

  python pipeline/qnet.py list <gId>          # 게시물 목록 확인
  python pipeline/qnet.py fetch <gId> [연도]   # 문제지·최종정답 내려받기 → data/qnet/<gId>/

게시판
- 기출문제 내려받기: boardId=Q004, code=1008
- 최종정답:         boardId=Q004, code=1206
로그인·대기열 없이 GET 으로 목록·상세·첨부를 받을 수 있다. 서버 부담을 줄이려고 요청 사이 1초 쉰다.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

BASE = "https://www.q-net.or.kr/cst003.do"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "qnet"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (compatible; alltests-archive-bot/1.0)"
BOARD = {"paper": "1008", "answer": "1206"}
MENU = {"paper": "cst00309", "answer": "cst00310"}


def get(params: dict, binary: bool = False):
    for attempt in range(4):
        try:
            r = S.get(BASE, params=params, timeout=60)
            r.raise_for_status()
            time.sleep(1.0)
            return r.content if binary else r.content.decode("utf-8", "replace")
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def list_posts(gid: str, kind: str) -> list[dict]:
    """게시판 전체 목록: [{seq, title, date}]"""
    rows: list[dict] = []
    seen: set[str] = set()
    for page in range(1, 80):
        h = get(dict(id="cst00301s01", gSite="L", gId=gid, page=page, schText="", schType="", boardId="Q004", code=BOARD[kind]))
        found = re.findall(r"goNext\('(\d+)',\s*'\d+',\s*'\w*'\)\">(.*?)</a>.*?<td[^>]*>.*?</td>\s*<td[^>]*>(.*?)</td>", h, re.S)
        new = [(a, html.unescape(re.sub("<[^>]+>", "", t)).strip(), re.sub(r"\s+", "", re.sub("<[^>]+>", "", d))) for a, t, d in found]
        new = [n for n in new if n[0] not in seen]
        if not new:
            break
        for a, t, d in new:
            seen.add(a)
            rows.append(dict(seq=a, title=t, date=d))
    return rows


def detail(gid: str, seq: str, kind: str) -> dict:
    """게시물 상세: 첨부 파일 목록과 공공누리 유형"""
    h = get(dict(id="cst00302", gSite="L", gId=gid, artlSeq=seq, boardId="Q004", code=BOARD[kind], menuType=MENU[kind]))
    files = [dict(path=p, name=html.unescape(n), fseq=s) for p, n, s in re.findall(r"fileDown\('([^']+)',\s*'([^']+)',\s*'(\d+)'\)", h)]
    # 공공누리: 보이는 블록의 유형 이미지 (new_img_opentype01.png → 1유형). 숨김(hide) 블록인 AI 학습용(10)은 제외
    kogl = None
    for cls, num in re.findall(r'class="codeView(\w*)[^"]*"[^>]*>.*?opentype(\d\d)', h, re.S):
        if "hide" not in cls and num in ("01", "02", "03", "04"):
            kogl = int(num)
            break
    if kogl is None:
        m = re.search(r"new_img_opentype0([1-4])", h)
        kogl = int(m.group(1)) if m else None
    return dict(files=files, kogl=kogl)


def download(gid: str, seq: str, f: dict) -> bytes:
    return get(
        dict(id="cst00302s01", gSite="L", gId=gid, fileCode="R001", filePath=f["path"], fileName=f["name"], fileSeq=f["fseq"], artlSeq=seq, href="0"),
        binary=True,
    )


def year_of(title: str) -> int | None:
    m = re.search(r"(20\d\d|19\d\d)\s*년", title)
    return int(m.group(1)) if m else None


def fetch(gid: str, only_year: int | None = None) -> None:
    dst = OUT / gid
    dst.mkdir(parents=True, exist_ok=True)
    meta_path = dst / "posts.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    for kind in ("paper", "answer"):
        for p in list_posts(gid, kind):
            y = year_of(p["title"])
            if only_year and y != only_year:
                continue
            if "공지" in p["title"] or y is None or y < 2013:
                continue
            key = f"{kind}-{p['seq']}"
            if key in meta:  # 이미 처리한 게시물 (CI 에서는 원본 파일이 없어도 다시 받지 않는다)
                continue
            d = detail(gid, p["seq"], kind)
            for f in d["files"]:
                ext = Path(f["name"]).suffix.lower()
                f["local"] = f"{kind}-{p['seq']}-{f['fseq']}{ext}"
                if not (dst / f["local"]).exists():
                    (dst / f["local"]).write_bytes(download(gid, p["seq"], f))
            meta[key] = dict(kind=kind, seq=p["seq"], title=p["title"], date=p["date"], year=y, kogl=d["kogl"], files=d["files"])
            print(kind, y, p["title"], [f["name"] for f in d["files"]], "kogl", d["kogl"], flush=True)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    cmd, gid = sys.argv[1], sys.argv[2]
    if cmd == "list":
        for kind in ("paper", "answer"):
            for p in list_posts(gid, kind):
                print(kind, p["seq"], p["date"], p["title"])
    elif cmd == "fetch":
        fetch(gid, int(sys.argv[3]) if len(sys.argv) > 3 else None)
