"""web/public/data/papers/*.json 전부를 모아 index.json 을 만든다 (PSAT·큐넷 등 모든 시험 공통).

  python pipeline/build_index.py

문제지 파일이 정답(answers)이 있는 문항만 담고 있다고 보고, 해설 수는 explanations/<id>.json 에서 센다.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "data"
META = ("id", "exam", "group", "year", "subject", "exams", "answersFinal", "choices", "kogl")


def main() -> None:
    index = []
    for f in sorted((OUT / "papers").glob("*.json")):
        p = json.loads(f.read_text())
        if p.get("hidden"):
            continue
        e = {k: p[k] for k in META if p.get(k) is not None}
        e.setdefault("exam", "psat")
        e["count"] = len(p["questions"])
        expl = OUT / "explanations" / f.name
        e["explained"] = sum(1 for k in json.loads(expl.read_text()) if k.isdigit()) if expl.exists() else 0
        index.append(e)
    index.sort(key=lambda x: (x["exam"], -x["year"], x.get("group", ""), x["exams"][0] if x["exams"] else "", x["subject"]))
    (OUT / "index.json").write_text(json.dumps(dict(papers=index), ensure_ascii=False))
    by = {}
    for e in index:
        by.setdefault(e["exam"], [0, 0])
        by[e["exam"]][0] += 1
        by[e["exam"]][1] += e["count"]
    print("index:", ", ".join(f"{k} {v[0]}개/{v[1]}문항" for k, v in by.items()))


if __name__ == "__main__":
    main()
