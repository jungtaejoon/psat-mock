"""공유 미리보기 이미지(og.png)와 파비콘 PNG/ICO 를 만든다. macOS 기본 글꼴(Apple SD Gothic Neo) 사용.

  python web/scripts/make-og.py
"""
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

WEB = Path(__file__).resolve().parent.parent
PUB = WEB / "public"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
BG, BRAND, INK, SUB, ACC = "#0f1a3c", "#1f4fd8", "#ffffff", "#c9d4f2", "#8fb0ff"


def font(size, weight):
    return ImageFont.truetype(FONT, size, index={"m": 2, "sb": 4, "b": 6}[weight])


def og():
    ix = json.loads((PUB / "data" / "index.json").read_text())["papers"]
    nq = sum(p["count"] for p in ix)
    years = [int(p["year"]) for p in ix]
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    # 오른쪽: OMR 답안지 칸
    import random
    rnd = random.Random(7)
    for r in range(9):
        filled = rnd.randrange(5)
        for c in range(5):
            x, y = 922 + c * 48, 100 + r * 54
            box = (x - 19, y - 19, x + 19, y + 19)
            if c == filled:
                d.ellipse(box, fill="#4a5a86")
            else:
                d.ellipse(box, outline="#3d4a70", width=3)
    x = 86
    d.text((x, 172), f"9급·7급 공무원 · PSAT · 자격증 등 {len({p.get('exam', 'psat') for p in ix})}개 시험", font=font(30, "sb"), fill=ACC)
    d.text((x, 222), "기출문제 무료 모의고사", font=font(76, "b"), fill=INK)
    d.text((x, 330), f"{min(years)}~{max(years)} 기출 {len(ix):,}과목 · {nq:,}문항", font=font(36, "m"), fill=SUB)
    cx = x
    for chip in ("실전 타이머·OMR", "자동 채점", "문항별 해설"):
        w = d.textlength(chip, font=font(26, "b"))
        d.rounded_rectangle((cx, 412, cx + w + 44, 462), radius=25, fill=BRAND)
        d.text((cx + 22, 421), chip, font=font(26, "b"), fill=INK)
        cx += w + 44 + 16
    # 아래: 로고 + 주소
    logo = fitz.open(PUB / "favicon.svg")[0].get_pixmap(matrix=fitz.Matrix(44 / 28, 44 / 28), alpha=True)
    li = Image.frombytes("RGBA", (logo.width, logo.height), logo.samples)
    im.paste(li, (x, 545), li)
    d.text((x + 58, 549), "올테스트", font=font(32, "b"), fill=INK)
    d.text((x + 58 + d.textlength("올테스트", font=font(32, "b")) + 16, 554), "alltests.ai.kr", font=font(27, "m"), fill=ACC)
    im.save(PUB / "og.png", optimize=True)


def icons():
    svg = (PUB / "favicon.svg").read_text()
    page = fitz.open(stream=svg.encode(), filetype="svg")[0]
    page.get_pixmap(matrix=fitz.Matrix(48 / 28, 48 / 28), alpha=True).save("/tmp/_f48.png")
    Image.open("/tmp/_f48.png").save(PUB / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    # iOS 홈 화면 아이콘은 모서리를 직접 둥글리므로 꽉 찬 사각형으로
    full = svg.replace('<rect x="1" y="1" width="26" height="26" rx="7"', '<rect width="28" height="28"')
    fitz.open(stream=full.encode(), filetype="svg")[0].get_pixmap(matrix=fitz.Matrix(180 / 28, 180 / 28)).save(
        PUB / "apple-touch-icon.png")


if __name__ == "__main__":
    icons()
    og()
