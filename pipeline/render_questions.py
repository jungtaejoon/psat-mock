"""문항을 PNG 로 렌더링 (해설 작성·검수용).

  python pipeline/render_questions.py <paperId> <출력폴더>

출력: <출력폴더>/<paperId>/q01.png … (공통 지문이 있으면 위에 붙여 한 장으로), meta.json(정답·추출 텍스트)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"


def main(pid: str, out: str) -> None:
    paper = json.loads((DATA / "papers" / f"{pid}.json").read_text())
    pdf = fitz.open(DATA / "pdf" / f"{paper.get('pdf', pid)}.pdf")
    dst = Path(out) / pid
    dst.mkdir(parents=True, exist_ok=True)
    meta = []
    for q in paper["questions"]:
        regions = (q.get("shared", {}).get("regions") or []) + q["regions"]
        pix = [pdf[r["page"]].get_pixmap(clip=fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"]), dpi=110) for r in regions]
        W = max(p.width for p in pix)
        H = sum(p.height for p in pix) + 10 * (len(pix) - 1)
        doc = fitz.open()
        page = doc.new_page(width=W, height=H)
        y = 0
        for p in pix:
            page.insert_image(fitz.Rect(0, y, p.width, y + p.height), pixmap=p)
            y += p.height + 10
        page.get_pixmap(dpi=72).save(dst / f"q{q['no']:02d}.png")
        meta.append({"no": q["no"], "answer": q["answer"], "image": f"q{q['no']:02d}.png",
                     "shared_text": q.get("shared", {}).get("text"), "text": q["text"]})
    (dst / "meta.json").write_text(json.dumps(
        {"id": pid, "year": paper["year"], "subject": paper["subject"], "exams": paper["exams"], "questions": meta},
        ensure_ascii=False, indent=1))
    print(dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
