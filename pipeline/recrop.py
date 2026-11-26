"""잘못 잘린 문항 그림을 PDF 에서 다시 자른다.

  python pipeline/recrop.py plan <문제지 id 접두어> [--out plan.json]     # 새 위치 계산 (설치 안 함)
  python pipeline/recrop.py montage plan.json <폴더>                       # 옛 그림 | 새 그림 비교 이미지
  python pipeline/recrop.py install plan.json [--only ids.txt]            # 새 그림을 같은 경로에 덮어쓰기

방법
1. 옛 그림(200 dpi)을 문항 영역 렌더링에서 템플릿 매칭으로 찾아 대략 위치를 얻는다.
2. 보기 그림(choices 안의 <img>)이면 문제지 JSON 의 보기 칸(①… 표시 오른쪽)에서 잉크가 있는 부분.
3. 본문 그림이면 영역 안 글줄 가운데 본문·보기 글자와 같은 줄(= 문장)을 찾아, 옛 그림 가운데 위·아래로
   가장 가까운 문장 줄 사이 띠를 잡고, 그 띠 안의 잉크 범위(영역 전체 폭에서)를 자른다.
   같은 띠에 그림이 여럿이면 옛 그림 가로 위치의 중간에서 나눈다.
plan.json 의 rect 를 손으로 고친 뒤 install 하면 그 위치로 자른다.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

import cv2
import fitz
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"
DPI = 200
K = 72 / DPI
CIRC = "①②③④⑤"


def norm(s: str) -> str:
    return re.sub(r"[\s ·ㆍ.,()（）\[\]「」『』<>〈〉:;\"'‘’“”`~\-–—]", "", s)


def plain(h: str) -> str:
    h = re.sub(r"<[^>]+>", " ", h)
    return html.unescape(h)


def regions_of(q: dict) -> list[dict]:
    return (q.get("shared", {}).get("regions") or []) + q["regions"]


def render(page: fitz.Page, rect: fitz.Rect) -> np.ndarray:
    pm = page.get_pixmap(clip=rect, dpi=DPI, colorspace=fitz.csGRAY)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)[:, :, 0].copy()


def ink_bbox(page: fitz.Page, rect: fitz.Rect, pad: float = 3.0, thr: int = 200) -> fitz.Rect | None:
    if rect.is_empty or rect.width < 2 or rect.height < 2:
        return None
    a = render(page, rect)
    m = a < thr
    # 위·아래 끝의 외따로 떨어진 가로줄(상자 테두리 등)은 뺀다
    rows = np.where(m.any(1))[0]
    while len(rows) > 2:
        cut = False
        for edge in (0, -1):
            rI = rows[edge]
            run = [rI]
            k = edge
            while True:
                k2 = k + (1 if edge == 0 else -1)
                if abs(k2) >= len(rows) or abs(rows[k2] - run[-1]) != 1:
                    break
                run.append(rows[k2]); k = k2
            if len(run) <= 3:
                nxt = rows[len(run)] if edge == 0 else rows[-len(run) - 1]
                gap = abs(nxt - run[-1])
                wide = max(m[r].sum() for r in run) > 0.6 * m.shape[1]
                if gap >= 8 and wide:
                    m[run, :] = False
                    cut = True
        if not cut:
            break
        rows = np.where(m.any(1))[0]
    ys, xs = np.where(m)
    if len(xs) == 0:
        return None
    r = fitz.Rect(rect.x0 + xs.min() * K - pad, rect.y0 + ys.min() * K - pad,
                  rect.x0 + (xs.max() + 1) * K + pad, rect.y0 + (ys.max() + 1) * K + pad)
    return r & rect


def locate(doc, q, png: Path):
    """옛 그림이 있던 (영역, PDF 좌표, 일치도)"""
    t = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
    best = None
    for r in regions_of(q):
        rr = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
        a = render(doc[r["page"]], rr)
        if t is None or a.shape[0] < t.shape[0] or a.shape[1] < t.shape[1]:
            continue
        m = cv2.matchTemplate(a, t, cv2.TM_SQDIFF_NORMED)
        v, _, loc, _ = cv2.minMaxLoc(m)
        if best is None or v < best[2]:
            x, y = loc
            best = (r, fitz.Rect(rr.x0 + x * K, rr.y0 + y * K, rr.x0 + (x + t.shape[1]) * K, rr.y0 + (y + t.shape[0]) * K), v)
    return best


def lines_in(page, rect):
    out = []
    for b in page.get_text("dict", clip=rect)["blocks"]:
        for ln in b.get("lines", []):
            s = "".join(sp["text"] for sp in ln["spans"])
            if s.strip():
                out.append((fitz.Rect(ln["bbox"]) & rect, s))
    # 같은 높이의 조각을 한 줄로
    out.sort(key=lambda x: (round(x[0].y0), x[0].x0))
    merged = []
    for r, s in out:
        if merged and abs(merged[-1][0].y0 - r.y0) < 2.5 and abs(merged[-1][0].y1 - r.y1) < 2.5:
            merged[-1] = (merged[-1][0] | r, merged[-1][1] + " " + s)
        else:
            merged.append((r, s))
    return merged


def hangul(s: str) -> str:
    return "".join(re.findall(r"[가-힣]", s))


def is_prose(s: str, ref: str, width: float, rwidth: float, x0: float = 0.0, rx0: float = 0.0) -> bool:
    """본문·보기 글줄인가. ref 는 norm(본문+보기). 그림 옆 설명(영역 왼쪽 30 % 밖에서 시작)은 문장으로 치지 않는다"""
    s2 = re.sub(r"[\ue000-\uf8ff]", "", s)
    n = norm(s2)
    if re.match(r"^\s*(문\s*)?\d{1,2}\s*\.", s2):
        return True
    if not n:
        return False
    if n[0] in CIRC:
        return True
    if x0 - rx0 > 0.22 * rwidth:
        return False
    h = hangul(n)
    href = hangul(ref)
    if len(n) >= 6 and n in ref and len(h) >= 2:
        return True
    if h and h in href and s2.rstrip().endswith("?"):
        return True
    if len(h) >= 3 and h in href and (width > 0.45 * rwidth or s2.rstrip().endswith(("?", ".", ")", "다"))):
        return True
    return False


def choice_cells(doc, regs, n, ref):
    """보기 그림: 영역의 잉크 덩어리를 ① … 표시에 나눠 준다.
    덩어리는 표시와 같은 줄(세로 거리 최소)이면서 표시 오른쪽에 있는 가장 가까운 표시의 것.
    모든 표시보다 완전히 위에 있는 덩어리(본문 그림·머리글)와 문장 줄은 뺀다."""
    found = {}
    for ri, r in enumerate(regs):
        rr = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
        for i in range(n):
            for m in doc[r["page"]].search_for(CIRC[i], clip=rr):
                found[i] = (ri, m)
    if len(found) != n:
        return {}
    out = {}
    for ri in sorted({v[0] for v in found.values()}):
        r = regs[ri]
        rr = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
        page = doc[r["page"]]
        mk = {i: m for i, (rj, m) in found.items() if rj == ri}
        a = render(page, rr)
        ink = (a < 200).astype(np.uint8)
        def px(rc):
            return (max(0, int((rc.x0 - rr.x0) / K) - 2), max(0, int((rc.y0 - rr.y0) / K) - 2),
                    int((rc.x1 - rr.x0) / K) + 3, int((rc.y1 - rr.y0) / K) + 3)
        for m in mk.values():
            x0, y0, x1, y1 = px(m)
            ink[y0:y1, x0:x1] = 0
        for lr, s in lines_in(page, rr):
            if is_prose(s, ref, lr.width, rr.width, lr.x0, rr.x0) and norm(s)[:1] not in CIRC:
                x0, y0, x1, y1 = px(lr)
                ink[y0:y1, x0:x1] = 0
        top_m = min(m.y0 for m in mk.values())
        dil = cv2.dilate(ink, np.ones((15, 15), np.uint8))
        cnt, lab, stats, _ = cv2.connectedComponentsWithStats(dil)
        boxes = {i: None for i in mk}
        for c in range(1, cnt):
            x, y, w, h, _ = stats[c]
            if not ink[y:y + h, x:x + w][lab[y:y + h, x:x + w] == c].any():
                continue
            cr = fitz.Rect(rr.x0 + x * K, rr.y0 + y * K, rr.x0 + (x + w) * K, rr.y0 + (y + h) * K)
            if cr.y1 < top_m - 2:
                continue
            cx = (cr.x0 + cr.x1) / 2
            best = None
            for i, m in mk.items():
                my = (m.y0 + m.y1) / 2
                dy = 0 if cr.y0 <= my <= cr.y1 else min(abs(cr.y0 - my), abs(cr.y1 - my))
                left = m.x0 <= cx
                key = (not left, round(dy / 6), -m.x0 if left else m.x0)
                if best is None or key < best[0]:
                    best = (key, i)
            i = best[1]
            boxes[i] = cr if boxes[i] is None else boxes[i] | cr
        for i, bx in boxes.items():
            if bx is not None:
                cell = fitz.Rect(bx.x0 - 1, bx.y0 - 1, bx.x1 + 1, bx.y1 + 1) & rr
                out[i] = (r["page"], rr, cell)
    return out


def plan_question(doc, paper, q, t, figdir):
    figs = t.get("figs") or {}
    if not figs:
        return []
    ref = norm(plain(t.get("stem", "")) + " " + " ".join(plain(c) for c in t.get("choices", [])))
    choice_of = {}
    for i, c in enumerate(t.get("choices", [])):
        for f in re.findall(r'data-fig=["\']([^"\']+)["\']', c):
            choice_of[f] = i
    regs = regions_of(q)
    out = []
    olds = {}
    for fid, path in figs.items():
        png = DATA / path
        if not png.exists():
            out.append({"fid": fid, "path": path, "err": "no png"})
            continue
        loc = locate(doc, q, png)
        if loc is None:
            out.append({"fid": fid, "path": path, "err": "no match"})
            continue
        olds[fid] = loc
    marks = choice_cells(doc, regs, len(t.get("choices", [])), ref) if choice_of else {}
    for fid, path in figs.items():
        if fid not in olds:
            continue
        r, old, score = olds[fid]
        page = doc[r["page"]]
        rr = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
        rec = {"fid": fid, "path": path, "page": r["page"], "old": [round(v, 1) for v in old], "score": round(score, 4)}
        new = None
        if fid in choice_of and choice_of[fid] in marks:
            pg, rreg, cell = marks[choice_of[fid]]
            page = doc[pg]
            rec["page"] = pg
            new = ink_bbox(page, cell)
            rec["kind"] = "choice"
        else:
            rec["kind"] = "stem"
            lines = lines_in(page, rr)
            cy = (old.y0 + old.y1) / 2
            top, bot = rr.y0, rr.y1
            href = hangul(ref)
            circ_tops = [lr.y0 for lr, s in lines if norm(re.sub(r"[\ue000-\uf8ff]", "", s))[:1] in CIRC and (lr.y0 + lr.y1) / 2 > cy]
            for lr, s in lines:
                lc = (lr.y0 + lr.y1) / 2
                s2 = re.sub(r"[\ue000-\uf8ff]", "", s).strip()
                n, h = norm(s2), hangul(s2)
                left = lr.x0 - rr.x0 <= 0.22 * rr.width
                if lc < cy:
                    ok = is_prose(s, ref, lr.width, rr.width, lr.x0, rr.x0) or (
                        left and h and h in href and s2.endswith((")", "다", "?", ".", "다)")))
                    if ok:
                        top = max(top, lr.y1 + 0.5)
                else:
                    ok = bool(n) and (n[0] in CIRC or re.match(r"^(문\s*)?\d{1,2}\s*\.", s2)
                                      or re.match(r"^\s*[ㄱ-ㅎ]\s*\.", s2) or "보기" in n or "보 기" in s2
                                      or (is_prose(s, ref, lr.width, rr.width, lr.x0, rr.x0)
                                          and (lr.width > 0.55 * rr.width or s2.endswith(("다.", "?", "다")))))
                    if ok:
                        bot = min(bot, lr.y0 - 0.5)
            # 그림 뒤 본문이 표 머리글(<tr>)·캡션이면 첫 보기 줄 바로 위 그만큼의 줄은 경계
            tail = t.get("stem", "").split(f'data-fig="{fid}"')[-1] if f'data-fig="{fid}"' in t.get("stem", "") else t.get("stem", "").split(f"data-fig='{fid}'")[-1]
            nrows = tail.count("<tr") + len(re.findall(r'class="cap"', tail))
            if nrows and circ_tops:
                c0 = min(circ_tops)
                above = sorted([lr for lr, s in lines if cy < (lr.y0 + lr.y1) / 2 and lr.y1 <= c0 + 0.5], key=lambda r: -r.y0)
                for lr in above[:nrows]:
                    if c0 - lr.y1 < 30:
                        bot = min(bot, lr.y0 - 0.5)
            band = fitz.Rect(rr.x0, top, rr.x1, bot)
            # 같은 띠의 다른 그림과 가로로 나누기
            for f2, (r2, o2, _) in olds.items():
                if f2 == fid or r2 is not r or f2 in choice_of:
                    continue
                if min(o2.y1, old.y1) - max(o2.y0, old.y0) > 0.3 * min(o2.height, old.height):
                    mid = ((old.x0 + old.x1) / 2 + (o2.x0 + o2.x1) / 2) / 2
                    if (o2.x0 + o2.x1) / 2 > (old.x0 + old.x1) / 2:
                        band.x1 = min(band.x1, mid)
                    else:
                        band.x0 = max(band.x0, mid)
                elif o2.y0 >= cy and o2.y0 < band.y1:
                    band.y1 = (old.y1 + o2.y0) / 2 if o2.y0 > old.y1 else (cy + (o2.y0 + o2.y1) / 2) / 2
                elif o2.y1 <= cy and o2.y1 > band.y0:
                    band.y0 = (old.y0 + o2.y1) / 2 if o2.y1 < old.y0 else (cy + (o2.y0 + o2.y1) / 2) / 2
            new = ink_bbox(page, band)
        if new is None:
            rec["err"] = "empty"
            new = old
        rec["rect"] = [round(v, 1) for v in new]
        o, n = old, new
        i = o & n
        inter = 0 if i.is_empty else i.width * i.height
        u = o | n
        rec["iou"] = round(inter / max(1e-6, u.width * u.height), 3)
        # 잉크 차이(pt² 근사): 옛 그림에만 있던 잉크(뺀 것), 새 그림에만 있는 잉크(더한 것)
        if rec["page"] == r["page"]:
            pg = doc[rec["page"]]
            big = (o | n) & fitz.Rect(pg.rect)
            arr = render(pg, big) < 200
            def m(rc):
                z = np.zeros_like(arr)
                x0, y0 = int((rc.x0 - big.x0) / K), int((rc.y0 - big.y0) / K)
                x1, y1 = int((rc.x1 - big.x0) / K), int((rc.y1 - big.y0) / K)
                z[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
                return z
            mo, mn = m(o), m(n)
            rec["removed"] = int((arr & mo & ~mn).sum())
            rec["added"] = int((arr & mn & ~mo).sum())
        out.append(rec)
    return out


def cmd_plan(a):
    res = {}
    for pf in sorted((DATA / "papers").glob(f"{a.prefix}*.json")):
        paper = json.loads(pf.read_text())
        tf = DATA / "text" / pf.name
        if not tf.exists():
            continue
        text = json.loads(tf.read_text())
        doc = fitz.open(DATA / "pdf" / f"{paper['pdf']}.pdf")
        for q in paper["questions"]:
            t = text.get(str(q["no"]))
            if not t:
                continue
            for rec in plan_question(doc, paper, q, t, None):
                res[f"{paper['id']}|{q['no']}|{rec['fid']}"] = rec
        print(pf.stem, file=sys.stderr)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=0))
    print(len(res), "figures;", sum(1 for r in res.values() if r.get("iou", 1) < 0.9), "changed")


def crop(doc, rec):
    return doc[rec["page"]].get_pixmap(clip=fitz.Rect(rec["rect"]), dpi=DPI)


def _docs():
    cache = {}

    def get(pid):
        if pid not in cache:
            paper = json.loads((DATA / "papers" / f"{pid}.json").read_text())
            cache[pid] = fitz.open(DATA / "pdf" / f"{paper['pdf']}.pdf")
        return cache[pid]
    return get


def cmd_montage(a):
    from PIL import Image, ImageDraw, ImageFont

    plan = json.loads(Path(a.plan).read_text())
    keys = [k for k, r in plan.items() if "rect" in r and (a.all or r.get("iou", 1) < a.iou)]
    if a.only:
        want = set(Path(a.only).read_text().split())
        keys = [k for k in keys if k in want or k.rsplit("|", 1)[0] in want or k.split("|")[0] in want]
    get = _docs()
    out = Path(a.dir)
    out.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 22)
    W = 1500
    rows, n = [], 0
    for k in keys:
        rec = plan[k]
        pid = k.split("|")[0]
        oldim = Image.open(DATA / rec["path"]).convert("RGB")
        pm = crop(get(pid), rec)
        newim = Image.frombytes("RGB", (pm.width, pm.height), pm.samples) if pm.n == 3 else Image.open(__import__("io").BytesIO(pm.tobytes("png"))).convert("RGB")
        sc = min(1.0, (W / 2 - 20) / max(oldim.width, newim.width, 1))
        oi = oldim.resize((max(1, int(oldim.width * sc)), max(1, int(oldim.height * sc))))
        ni = newim.resize((max(1, int(newim.width * sc)), max(1, int(newim.height * sc))))
        h = max(oi.height, ni.height) + 34
        row = Image.new("RGB", (W, h), "white")
        d = ImageDraw.Draw(row)
        d.text((5, 2), f"{k}  iou={rec.get('iou')} {rec.get('kind')} {rec.get('err', '')}", fill="blue", font=font)
        row.paste(oi, (5, 30))
        row.paste(ni, (W // 2 + 5, 30))
        d.rectangle([4, 29, 6 + oi.width, 31 + oi.height], outline="red")
        d.rectangle([W // 2 + 4, 29, W // 2 + 6 + ni.width, 31 + ni.height], outline="green")
        rows.append(row)
        if sum(r.height for r in rows) > a.height:
            n = _flush(rows, out, n, W)
            rows = []
    if rows:
        n = _flush(rows, out, n, W)
    print(len(keys), "figures in", n, "sheets")


def _flush(rows, out, n, W):
    from PIL import Image

    H = sum(r.height for r in rows)
    im = Image.new("RGB", (W, H), (200, 200, 200))
    y = 0
    for r in rows:
        im.paste(r, (0, y))
        y += r.height
    im.save(out / f"m{n:03d}.png")
    return n + 1


def cmd_install(a):
    plan = json.loads(Path(a.plan).read_text())
    keys = list(plan)
    if a.only:
        want = set(Path(a.only).read_text().split())
        keys = [k for k in keys if k in want]
    get = _docs()
    c = 0
    for k in keys:
        rec = plan[k]
        if "rect" not in rec or rec.get("skip"):
            continue
        crop(get(k.split("|")[0]), rec).save(DATA / rec["path"])
        c += 1
    print("installed", c)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("prefix"); p.add_argument("--out", default="recrop_plan.json")
    p = sub.add_parser("montage"); p.add_argument("plan"); p.add_argument("dir"); p.add_argument("--iou", type=float, default=0.9)
    p.add_argument("--all", action="store_true"); p.add_argument("--only"); p.add_argument("--height", type=int, default=2600)
    p = sub.add_parser("install"); p.add_argument("plan"); p.add_argument("--only")
    a = ap.parse_args()
    {"plan": cmd_plan, "montage": cmd_montage, "install": cmd_install}[a.cmd](a)


if __name__ == "__main__":
    main()
