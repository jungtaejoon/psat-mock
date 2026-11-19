"""큐넷 최종정답표 → 이미지 (정답이 표 그림으로만 들어 있어 사람이/모델이 읽어야 한다).

  python pipeline/qnet_answers.py prepare <gId>   # data/qnet/<gId>/ansimg/ 에 PNG + manifest.json
  python pipeline/qnet_answers.py merge <gId>     # 두 번 따로 읽은 answers_A/B.json 대조 → answers.json + 불일치 목록
  python pipeline/qnet_answers.py check <gId>     # answers.json 형식·번호 연속성 검사
  python pipeline/qnet_answers.py read-api <gId> <선택지 수>  # (CI) 아직 안 읽은 정답표를 Claude API 로 두 번 읽어 대조

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
            if not path.exists():
                continue
            ext = path.suffix.lower()
            try:
                if ext == ".pdf":
                    doc = fitz.open(path)
                    for i, page in enumerate(doc):
                        name = f"{p['seq']}-{f['fseq']}-p{i + 1}.png"
                        page.get_pixmap(dpi=130).save(dst / name)
                        imgs.append(name)
                elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".gif"):
                    name = f"{p['seq']}-{f['fseq']}.png"
                    (dst / name).write_bytes(to_png(path.read_bytes()))
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
        nums = sorted({int(k) for k in e["answers"]} | {int(x) for x in e.get("text_items", [])})
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


def _key(e: dict) -> tuple:
    return (e["year"], e.get("round"), e.get("stage"), e["period"], e.get("booklet"), (e.get("track") or "").replace(" ", ""))


def merge(gid: str, choices: int) -> list[str]:
    """두 결과가 완전히 같은 항목만 answers.json 에 넣고, 다른 곳은 diff 로 남긴다 (다시 읽어 확정)."""
    src = QNET / gid
    # 두 판독이 1차/round 표기를 다르게 붙이기도 해서, 게시물·교시·구분(track)·시작 번호로 맞춘다
    def mk(e: dict) -> tuple:
        return (e.get("post"), e["period"], (e.get("track") or "").replace(" ", ""), e["subjects"][0]["from"] if e.get("subjects") else 0, (e["subjects"][0]["name"] if e.get("subjects") else "").replace(" ", "")[:4])

    a = {mk(e): e for e in json.loads((src / "answers_A.json").read_text())}
    b = {mk(e): e for e in json.loads((src / "answers_B.json").read_text())}
    prev = {mk(e): e for e in json.loads((src / "answers.json").read_text())} if (src / "answers.json").exists() else {}
    merged, diffs = dict(prev), []
    for k in sorted(set(a) | set(b), key=str):
        if k in prev:
            continue
        ea, eb = a.get(k), b.get(k)
        e0 = a.get(k) or b.get(k)
        tag = f"{e0['year']} " + " ".join(str(x) for x in k if x not in (None, ""))
        if not ea or not eb:
            diffs.append(f"{tag}: 한쪽에만 있음")
            continue
        # 1차 표기는 있는 쪽을 따른다
        ea = dict(ea, stage=ea.get("stage") or eb.get("stage"))
        if not ea or not eb:
            diffs.append(f"{tag}: 한쪽에만 있음")
            continue
        sa = [(s["name"].replace(" ", ""), s["from"], s["to"]) for s in ea["subjects"]]
        sb = [(s["name"].replace(" ", ""), s["from"], s["to"]) for s in eb["subjects"]]
        bad = [n for n in sorted(set(ea["answers"]) | set(eb["answers"]), key=int) if sorted(ea["answers"].get(n) or []) != sorted(eb["answers"].get(n) or [])]
        if sorted(ea.get("text_items", [])) != sorted(eb.get("text_items", [])):
            bad.append("주관식 목록")
        if [x[1:] for x in sa] != [x[1:] for x in sb]:
            diffs.append(f"{tag}: 과목 범위 다름 {sa} / {sb}")
        elif bad or ea.get("unclear") or eb.get("unclear"):
            diffs.append(f"{tag}: 정답 다름 {bad} 불명확 {sorted(set(ea.get('unclear', [])) | set(eb.get('unclear', [])))}")
        else:
            merged[k] = {kk: vv for kk, vv in ea.items() if kk != "unclear"}
    (src / "answers.json").write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=1))
    (src / "answers_diff.json").write_text(json.dumps(diffs, ensure_ascii=False, indent=1))
    return diffs


READ_PROMPT = """이 이미지들은 한국 국가자격시험 최종정답표입니다. 표의 숫자를 정확히 옮겨 JSON 만 출력하세요.
형식: [{"year": 2025, "round": "정기"|"특별"|null, "stage": "1차"|"2차"|null, "period": 1, "booklet": "A"|null,
"subjects": [{"name": "과목명", "from": 1, "to": 25}], "answers": {"1": [3], "2": [1,2,3,4]}}]
- 교시(period)·과목·형별 표마다 항목 하나. A형과 B형이 따로 있으면 A형만. 형별 표시가 없으면 booklet null.
- 문항 번호는 정답표에 적힌 그대로, 복수 정답은 목록으로, 모두 정답이면 [1..선택지 수].
- 게시물 제목: {title}"""


def read_api(gid: str, choices: int, model: str = "claude-haiku-5-5") -> None:
    """answers.json 에 없는 정답 게시물만 API 로 두 번 읽고, 두 결과가 같은 항목만 추가한다."""
    import base64
    import re as _re

    import anthropic

    src = QNET / gid
    manifest = json.loads((src / "ansimg" / "manifest.json").read_text())
    done = json.loads((src / "answers.json").read_text()) if (src / "answers.json").exists() else []
    seen_posts = {e.get("post") for e in done}
    client = anthropic.Anthropic()
    added = 0
    for m in manifest:
        if m["post"] in seen_posts or not m["images"] or (m["year"] or 0) < 2014:
            continue
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode((src / "ansimg" / n).read_bytes()).decode()}} for n in m["images"][:6]]
        content.append({"type": "text", "text": READ_PROMPT.replace("{title}", m["title"])})
        reads = []
        for _ in range(2):
            r = client.messages.create(model=model, max_tokens=8000, messages=[{"role": "user", "content": content}])
            txt = "".join(b.text for b in r.content if b.type == "text")
            mm = _re.search(r"\[.*\]", txt, _re.S)
            reads.append(json.loads(mm.group(0)) if mm else [])
        a = {_key(dict(e, year=m["year"])): e for e in reads[0]}
        b = {_key(dict(e, year=m["year"])): e for e in reads[1]}
        for k in a:
            if k in b and a[k]["answers"] == b[k]["answers"] and [(s["from"], s["to"]) for s in a[k]["subjects"]] == [(s["from"], s["to"]) for s in b[k]["subjects"]]:
                done.append(dict(a[k], post=m["post"], year=m["year"]))
                added += 1
            else:
                print("  두 번 읽은 결과가 달라 보류:", m["year"], m["title"], k)
    (src / "answers.json").write_text(json.dumps(done, ensure_ascii=False, indent=1))
    errs = check(gid, choices)
    print(f"read-api {gid}: {added}개 추가", "| 검사 문제:" if errs else "", "; ".join(errs))


if __name__ == "__main__":
    cmd, gid = sys.argv[1], sys.argv[2]
    if cmd == "prepare":
        prepare(gid)
    elif cmd == "merge":
        diffs = merge(gid, int(sys.argv[3]) if len(sys.argv) > 3 else 5)
        print("\n".join(diffs) or "모두 일치")
    elif cmd == "read-api":
        read_api(gid, int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    elif cmd == "check":
        errs = check(gid, int(sys.argv[3]) if len(sys.argv) > 3 else 5)
        print("\n".join(errs) or "ok")
        sys.exit(1 if errs else 0)
