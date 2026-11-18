"""큐넷 최종정답표 → 이미지 (정답이 표 그림으로만 들어 있어 사람이/모델이 읽어야 한다).

  python pipeline/qnet_answers.py prepare <gId>   # data/qnet/<gId>/ansimg/ 에 PNG + manifest.json
  python pipeline/qnet_answers.py check <gId>     # answers.json 형식·번호 연속성 검사

PDF 는 쪽마다 그림으로 렌더링하고, HWP 는 문서 안에 들어 있는 그림(BinData)을 꺼낸다.
읽은 결과는 data/qnet/<gId>/answers.json 에 아래 형식으로 둔다 (정답표에 적힌 그대로):

[{"post": "5249531", "year": 2025, "round": "정기"|"특별"|null, "stage": "1차"|"2차"|null,
  "period": 1, "booklet": "A"|null,
  "subjects": [{"name": "국사", "from": 1, "to": 25}, ...],
  "answers": {"1": [3], "2": [1, 4], ...}}]          # 복수 정답은 여러 개, 전원 정답은 [1..선택지수]
"""
from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
QNET = ROOT / "data" / "qnet"


def hwp_images(path: Path) -> list[bytes]:
    """HWP(5.x, 배포용 아님) 안의 그림. 정답표는 보통 BinData 의 BMP/PNG 다."""
    import olefile

    o = olefile.OleFileIO(str(path))
    out = []
    for s in o.listdir():
        if s[0] != "BinData":
            continue
        raw = o.openstream(s).read()
        # 압축 문서는 그림도 deflate 로 압축돼 있다
        for data in (raw, _inflate(raw)):
            if data and data[:2] in (b"BM",) or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
                out.append(data)
                break
    return out


def _inflate(b: bytes) -> bytes | None:
    try:
        return zlib.decompress(b, -15)
    except zlib.error:
        return None


def hwpx_images(path: Path) -> list[bytes]:
    import zipfile

    z = zipfile.ZipFile(path)
    return [z.read(n) for n in z.namelist() if n.lower().startswith("bindata/") and n.lower().endswith((".png", ".bmp", ".jpg", ".jpeg"))]


def to_png(data: bytes) -> bytes:
    pix = fitz.Pixmap(data)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    return pix.tobytes("png")


def prepare(gid: str) -> None:
    src = QNET / gid
    posts = json.loads((src / "posts.json").read_text())
    dst = src / "ansimg"
    dst.mkdir(exist_ok=True)
    manifest = []
    for key, p in sorted(posts.items(), key=lambda kv: (-(kv[1]["year"] or 0), kv[0])):
        if p["kind"] != "answer" or (p["year"] or 0) < 2013:
            continue
        imgs = []
        for f in p["files"]:
            path = src / f["local"]
            ext = path.suffix.lower()
            try:
                if ext == ".pdf":
                    doc = fitz.open(path)
                    for i, page in enumerate(doc):
                        name = f"{p['seq']}-{f['fseq']}-p{i + 1}.png"
                        page.get_pixmap(dpi=130).save(dst / name)
                        imgs.append(name)
                elif ext in (".hwp", ".hwpx"):
                    for i, data in enumerate(hwp_images(path) if ext == ".hwp" else hwpx_images(path)):
                        png = to_png(data)
                        if len(png) < 3000:  # 로고·선 같은 작은 그림은 건너뛴다
                            continue
                        name = f"{p['seq']}-{f['fseq']}-i{i + 1}.png"
                        (dst / name).write_bytes(png)
                        imgs.append(name)
            except Exception as e:  # noqa: BLE001
                print("  skip", f["name"], e)
        manifest.append(dict(post=p["seq"], year=p["year"], title=p["title"], images=imgs))
        print(p["year"], p["title"][:40], len(imgs), "images")
    (dst / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))


def check(gid: str, choices: int) -> list[str]:
    """answers.json 기본 검사: 과목 범위가 이어지는지, 모든 번호에 1..choices 정답이 있는지"""
    errs = []
    entries = json.loads((QNET / gid / "answers.json").read_text())
    for e in entries:
        tag = f"{e['year']} {e.get('round') or ''} {e.get('stage') or ''} {e['period']}교시 {e.get('booklet') or ''}".strip()
        subs = e["subjects"]
        nums = sorted(int(k) for k in e["answers"])
        if not subs or subs[0]["from"] != (nums[0] if nums else 1):
            errs.append(f"{tag}: 첫 과목 시작 번호가 정답 번호와 다름")
        for a, b in zip(subs, subs[1:]):
            if b["from"] != a["to"] + 1:
                errs.append(f"{tag}: 과목 범위가 끊김 {a['name']}~{b['name']}")
        want = list(range(subs[0]["from"], subs[-1]["to"] + 1)) if subs else []
        if nums != want:
            errs.append(f"{tag}: 정답 번호 {len(nums)}개, 과목 범위 {len(want)}개")
        for k, v in e["answers"].items():
            if not v or any(not (1 <= x <= choices) for x in v):
                errs.append(f"{tag}: {k}번 정답 값 {v}")
    return errs


if __name__ == "__main__":
    cmd, gid = sys.argv[1], sys.argv[2]
    if cmd == "prepare":
        prepare(gid)
    elif cmd == "check":
        errs = check(gid, int(sys.argv[3]) if len(sys.argv) > 3 else 5)
        print("\n".join(errs) or "ok")
        sys.exit(1 if errs else 0)
