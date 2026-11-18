"""해설 파일 검수.

  python pipeline/check_explanations.py

- 형식: 문항 수, choices 5개, 필수 필드
- 정답 모순: 해설 본문이 '정답은 ③' 처럼 공식 정답과 다른 번호를 주장하는 경우
- 다른 문항 해설: 해설 글이 자기 문항보다 같은 문제지의 다른 문항 텍스트와 더 많이 겹치는 경우가
  한 문제지에 3개 이상이면 (공통 지문 때문에 1~2개는 정상) 문제지 전체를 의심
- 정답표 의심 문구: 해설이 사용자에게 '정답 표기 확인 필요', '책형 차이' 같은 말을 하는 경우
- _review 에 남은 문항
문제가 있으면 종료 코드 1.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"
C = "①②③④⑤"
KEY_DOUBT = re.compile(r"책형|meta\.json|정답 ?표기|제공 정답|정답표|공식 정답과 (?:다르|불일치)")


def grams(s: str) -> set[str]:
    s = re.sub(r"[^가-힣]", "", s)
    return {s[i : i + 2] for i in range(len(s) - 1)}


def main() -> int:
    problems = 0
    total = 0
    for f in sorted((DATA / "explanations").glob("*.json")):
        pid = f.stem
        d = json.loads(f.read_text())
        paper = json.loads((DATA / "papers" / f"{pid}.json").read_text())
        qs = {q["no"]: q for q in paper["questions"]}
        keys = [k for k in d if k.isdigit()]
        total += len(keys)
        msgs = []
        if len(keys) != len(qs):
            msgs.append(f"문항 수 {len(keys)}/{len(qs)}")
        swapped = []
        for k in keys:
            e, q = d[k], qs[int(k)]
            if not (isinstance(e.get("choices"), list) and len(e["choices"]) == 5 and e.get("explanation") and "key_point" in e):
                msgs.append(f"{k}번 형식 오류")
                continue
            if len(q["answer"]) < 5:
                txt = e["explanation"]
                claims = set(re.findall(r"정답[은는이:]?\s*([①②③④⑤])", txt)) | set(
                    re.findall(r"([①②③④⑤])[^\n.]{0,6}(?:이 정답|가 정답)", txt))
                claimed = {C.index(c) + 1 for c in claims}
                if claimed and not claimed & set(q["answer"]):
                    msgs.append(f"{k}번 정답 모순 (공식 {q['answer']}, 해설 {sorted(claimed)})")
            if KEY_DOUBT.search(e["explanation"] + " ".join(e["choices"]) + e.get("tip", "")):
                msgs.append(f"{k}번 정답표 의심 문구")
            et = grams(e["explanation"] + " ".join(e["choices"]))
            own = len(et & grams(q["text"])) / max(1, len(et))
            other = max((len(et & grams(o["text"])) / max(1, len(et)) for n, o in qs.items() if n != int(k)), default=0)
            if other > own + 0.05:
                swapped.append(k)
        if len(swapped) >= 3:
            msgs.append(f"다른 문항 내용으로 보이는 해설 {len(swapped)}개: {swapped}")
        if d.get("_review"):
            msgs.append(f"검토 필요 {d['_review']}")
        if msgs:
            problems += 1
            print(pid, "|", "; ".join(msgs))
    print(f"{total}문항 검사, 문제 있는 문제지 {problems}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
