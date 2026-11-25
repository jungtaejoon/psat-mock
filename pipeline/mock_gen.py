"""AI 모의고사 문항 창고: 기출의 형식·문항 배치를 본떠 새 문항을 만들고, 검증을 통과한 것만 쌓아 재사용한다.

  python pipeline/mock_gen.py plan                # 트랙(시험·계열·과목)과 칸(문항 번호)별 창고 현황, 이번 달 예산
  python pipeline/mock_gen.py run                 # (CI) 평가 반영(retire) → 끝난 배치 수거 → 예산 안에서 새로 제출 → 목록 갱신
  python pipeline/mock_gen.py retire|collect|submit|index

구조
- 트랙: (시험, 계열, 과목). 칸(slot) 수는 최근 기출의 문항 수, 칸 s 의 참고 자료는 최근 기출들의 s번 문항(단원·유형·배치를 따라간다).
- 칸마다 후보 문항을 per_slot 개까지 둔다. 사용자마다 칸별로 후보를 무작위로 골라(안 본 것 먼저) 세트가 서로 다르다.
- 만들기(Opus, 배치) → 다른 요청에서 정답을 모른 채 다시 풀어 검토 → 답이 같고 문제가 성립할 때만 창고에 넣는다.
- 사용자 평가(👍 좋아요 / 👎 별로예요 / 🚨 오류 있어요, Supabase reactions 의 a:<문제지>:<번호>)를 매일 읽어
  오류 2건 이상, 또는 별로예요 3건 이상이면서 좋아요의 2배 이상인 문항만 빼고(retired), 빈 자리는 새로 만든다.
  그 밖의 문항은 계속 재사용한다.
- 예산: data/mock/config.json 의 monthly_usd (매달 1일 KST 에 새로 시작). 실제 사용 토큰으로 계산한다.

출력
- web/public/data/papers/ai-<시험>-<계열>-<과목>.json (hidden, ai) + text/ + explanations/ 같은 이름
- web/public/data/mock/index.json: 화면에 보일 트랙 목록·창고 현황·이번 달 예산
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
DATA = ROOT / "web" / "public" / "data"
CONF = ROOT / "data" / "mock" / "config.json"
STATE = ROOT / "data" / "mock" / "state.json"
MOCK_INDEX = DATA / "mock" / "index.json"
EXAMS = {e["id"]: e for e in json.loads((ROOT / "web" / "src" / "exams.json").read_text())["exams"]}
MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 2.0, 10.0  # 배치 50% 할인 가격 (USD / MTok)
DEFAULT_PER_Q = 0.04  # 실측 전 문항 하나(만들기+검토) 예상 비용
SUPABASE = "https://hzyvylezebigwugffxii.supabase.co"
SUPABASE_KEY = "sb_publishable_QNI_tSA_PlIuAwc0ZvTrjA_WYwvylFi"  # 공개용 키 (집계 함수만 부른다)
CIRCLED = "①②③④⑤"
CORE = {"국어", "영어", "한국사", "행정법총론", "행정학개론"}
PRIORITY = ["gong9", "psat", "realtor", "social1", "gong7", "housing", "local", "security", "labor", "appraiser",
            "firemgr", "tax", "customs", "patent", "logistics", "tourguide", "youthcounsel"]

KST = dt.timezone(dt.timedelta(hours=9))


def month_key() -> str:
    return dt.datetime.now(KST).strftime("%Y-%m")


def load(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def save(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1))


def slug(s: str) -> str:
    return re.sub(r"[\s/·.,()\[\]]+", "", s)


def group_of(p: dict) -> str:
    if p.get("group"):
        return p["group"]
    ex = p.get("exams") or [""]
    if p.get("exam", "psat") == "psat":
        if any(e.startswith("5급 공채") or e == "외교관후보자" for e in ex):
            return "5급 공채·외교관"
        if any("민간경력자" in e or e == "7급 공채" for e in ex):
            return "7급 공채·민경채"
        if any(e.startswith("지역인재") for e in ex):
            return "지역인재 7급"
    return ex[0]


def plain(h: str) -> str:
    h = re.sub(r"</p>\s*<p[^>]*>", "\n", h or "")
    h = re.sub(r"<br\s*/?>", "\n", h)
    h = re.sub(r"<img[^>]*>", "[그림]", h)
    h = re.sub(r"</?(p|span|div)[^>]*>", "", h)
    import html as _h

    return _h.unescape(h).strip()


# ------------------------------------------------------------------ 트랙·칸

def tracks() -> list[dict]:
    """(시험, 계열, 과목)마다: 칸 수, 선택지 수, 칸별 참고 기출(최근 4개 연도)"""
    ix = load(DATA / "index.json", {"papers": []})["papers"]
    by: dict[tuple, list] = collections.defaultdict(list)
    for p in ix:
        by[(p.get("exam", "psat"), group_of(p), p["subject"])].append(p)
    this_year = dt.datetime.now(KST).year
    out = []
    for (exam, grp, subj), ps in by.items():
        if exam not in EXAMS:
            continue
        ps.sort(key=lambda p: -int(p["year"]))
        if int(ps[0]["year"]) < this_year - 3:
            continue  # 최근 몇 년 안 나온 과목은 뺀다
        n = collections.Counter(p["count"] for p in ps[:3]).most_common(1)[0][0]
        refs = [p for p in ps if p["count"] == n][:4]
        if not refs:
            continue
        out.append(dict(exam=exam, group=grp, subject=subj, slots=n,
                        choices=refs[0].get("choices") or EXAMS[exam].get("choices") or 4,
                        refs=[p["id"] for p in refs],
                        paper=f"ai-{exam}-{slug(grp)}-{slug(subj)}"))
    rank = {e: i for i, e in enumerate(PRIORITY)}

    def key(t):
        # 공무원 공통과목과 자격증 시험을 먼저, 공무원 전공과목은 뒤로
        gong = t["exam"] in ("gong9", "gong7", "local")
        return (0 if not gong or t["subject"] in CORE else 1, rank.get(t["exam"], 99), t["group"], t["subject"])

    return sorted(out, key=key)


def ai_paper(t: dict) -> dict:
    f = DATA / "papers" / f"{t['paper']}.json"
    if f.exists():
        return json.loads(f.read_text())
    return dict(id=t["paper"], exam=t["exam"], group=t["group"], year=dt.datetime.now(KST).year, subject=t["subject"],
                exams=[t["group"]], answersFinal=True, choices=t["choices"], hidden=True, ai=True,
                width=0, height=0, pages=0, slots=t["slots"], questions=[])


def active_by_slot(paper: dict) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = collections.defaultdict(list)
    for q in paper["questions"]:
        if not q.get("retired"):
            out[q["slot"]].append(q)
    return out


# ------------------------------------------------------------------ 다듬기

HEADER = re.compile(r"^((?:\s|<b>|<u>|<br>|<p>)*)(?:\[|［)\s*\d+\s*[～~∼〜\-–—]\s*\d+\s*(?:\]|］)\s*(?:</b>)?")


def strip_header(stem: str) -> str:
    """'[1～5]' 같은 묶음 머리말 제거 (문항을 하나씩 만들어 쓰므로 맞지 않는 표시)"""
    m = HEADER.match(stem)
    if not m:
        return stem
    opened = m.group(1) if "</b>" not in m.group(0) else m.group(1).replace("<b>", "")
    return opened + stem[m.end():]


def can_shuffle(d: dict) -> bool:
    """선택지 순서를 바꿔도 되는가: 순서 자체에 뜻이 있거나(㉠㉡·ㄱㄴ·(가)(나)·숫자순·길이순 조합), 번호를 말로 가리키면 안 된다"""
    ch = [plain(c) for c in d["choices"]]
    if len(set(ch)) != len(ch) or re.search("[①-⑤]", d["stem"] + "".join(ch)):
        return False
    # 기호로 시작하는 선택지(㉠ …, ㄱ·ㄷ, (나)-(가), A·C)가 둘 이상이면 순서에 뜻이 있다고 본다
    label = r"^(㉠|㉡|㉢|㉣|㉤|[ㄱ-ㅎ](?![가-힣])|[ⓐ-ⓔ]|[\[(]?[가-마][\])]|[A-E]\s*([,·→~－-]|$))"
    if sum(bool(re.match(label, c)) for c in ch) >= 2:
        return False
    # 짧은 수치만 늘어놓은 선택지는 크기순으로 싣는다
    if sum(bool(re.match(r"^[\s$\\\-−+약]*\d", c)) and len(c) <= 20 for c in ch) >= 2:
        return False
    if any(re.search(r"(위|앞)의 (모든|보기|선택지)|정답 ?없음|해당 ?없음|[Nn]one of the above|[Aa]ll of the above", c) for c in ch):
        return False
    notes = " ".join([d["key_point"], d["explanation"], d["tip"], *d["choice_notes"]])
    return not re.search(r"(?<!\d)[1-5]\s*번|[①-⑤]\s*[~～∼\-–]\s*[①-⑤]|(첫|두|세|네|다섯)\s*번째 선택지", notes)


def move_answer(d: dict, to: int) -> dict:
    """정답이 to 번에 오도록 선택지 순서를 바꾼다. 해설 속 ①~⑤ 와 선택지별 판단도 함께 옮긴다"""
    n = len(d["choices"])
    rest = [i for i in range(n) if i != d["answer"] - 1]
    rng = random.Random(hashlib.sha1(d["stem"].encode()).hexdigest())
    rng.shuffle(rest)
    order = rest[:]
    order.insert(to - 1, d["answer"] - 1)  # order[새 자리] = 옛 자리
    new_of = {CIRCLED[old]: CIRCLED[new] for new, old in enumerate(order)}

    def fix(x: str) -> str:
        return re.sub("[①-⑤]", lambda m: new_of.get(m.group(0), m.group(0)), x)

    notes = d["choice_notes"]
    return dict(d, choices=[d["choices"][i] for i in order], answer=to, key_point=fix(d["key_point"]),
                explanation=fix(d["explanation"]), tip=fix(d["tip"]),
                choice_notes=[fix(notes[i]) for i in order] if len(notes) == n else [fix(x) for x in notes])


def polish(d: dict, paper: dict, n: int) -> dict:
    """머리말을 떼고, 섞을 수 있으면 이 과목에서 가장 적게 쓴 자리로 정답을 옮긴다"""
    d = dict(d, stem=strip_header(d["stem"]))
    if not can_shuffle(d):
        return d
    used = collections.Counter(q["answer"][0] for q in paper["questions"] if not q.get("retired"))
    low = min(used[i] for i in range(1, n + 1))
    return move_answer(d, random.choice([i for i in range(1, n + 1) if used[i] == low]))


# ------------------------------------------------------------------ 요청

GEN_SYSTEM = """당신은 한국 국가시험 출제위원입니다. 실제 시험과 같은 형식의 새 객관식 문항을 한 개 만듭니다.
- 아래에 주는 기출들은 같은 시험·과목에서 같은 번호(배치)에 나온 문항입니다. 그 번호에 주로 나오는 단원·출제 유형·난이도를 따르되,
  기출의 문장·사례·지문을 베끼지 말고 새로운 내용으로 만드세요. 이미 만든 후보와도 겹치지 않게 하세요.
- 2026년 현재 법령·사실·학설 기준으로 정답이 정확히 하나로 확정되어야 합니다. 개정·폐지된 규정이나 논란 있는 내용은 피하세요.
- 선택지 수는 지정한 개수와 같아야 하고, 오답 선택지도 그럴듯해야 합니다. "옳은 것/옳지 않은 것", 「보기」(ㄱㄴㄷㄹ) 조합, 사례형, 계산형 등 기출의 유형을 따르세요.
- 그림이 꼭 필요한 문항은 만들지 마세요. 표는 <table> HTML 로, 줄바꿈은 <br>, 밑줄은 <u>, 굵게는 <b> 만 씁니다. 수식은 $...$ (LaTeX).
- 독해·지문형이면 지문을 stem 안에 함께 넣어 한 문항으로 완결되게 하세요.
- 이 문항만 따로 쓰므로 "[1～5]" 같은 묶음 머리말을 붙이지 마세요.
- 정답은 지정한 번호에 오게 하세요.
- explanation 은 정답 근거(개념·법령·계산)를 3~6문장으로, choices 는 선택지마다 맞고 틀린 이유 한 문장씩입니다."""

VERIFY_SYSTEM = """당신은 한국 국가시험 검수위원입니다. 새로 만든 객관식 문항을 정답을 모르는 상태에서 직접 풀고 검토합니다.
- answer: 정답이라고 판단한 선택지 번호(1부터).
- valid: 정답이 정확히 하나로 확정되고, 사실·법령·계산 오류가 없고, 문장이 명확하며, 실제 시험에 낼 만한 수준이면 true.
  정답이 둘 이상이거나 없음, 2026년 현재 기준으로 틀린 내용, 모호한 표현, 선택지 중복이 있으면 false.
- issue: false 인 이유 (true 면 빈 문자열)."""


def gen_schema(n: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "단원·주제 (짧게)"},
            "stem": {"type": "string", "description": "발문과 지문·보기 (선택지는 제외)"},
            "choices": {"type": "array", "items": {"type": "string"}, "description": f"선택지 {n}개 (번호 기호 없이)"},
            "answer": {"type": "integer", "description": "정답 선택지 번호 (1부터)"},
            "key_point": {"type": "string"},
            "explanation": {"type": "string"},
            "choice_notes": {"type": "array", "items": {"type": "string"}, "description": f"선택지별 판단 {n}개"},
            "tip": {"type": "string"},
        },
        "required": ["topic", "stem", "choices", "answer", "key_point", "explanation", "choice_notes", "tip"],
        "additionalProperties": False,
    }


VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "integer"}, "valid": {"type": "boolean"}, "issue": {"type": "string"}},
    "required": ["answer", "valid", "issue"],
    "additionalProperties": False,
}


_CACHE: dict = {}


def cached(p: Path, default):
    if p not in _CACHE:
        _CACHE[p] = load(p, default)
    return _CACHE[p]


def ref_block(t: dict, slot: int) -> str:
    parts = []
    for pid in t["refs"]:
        paper = cached(DATA / "papers" / f"{pid}.json", None)
        text = cached(DATA / "text" / f"{pid}.json", {})
        if not paper:
            continue
        q = next((x for x in paper["questions"] if x["no"] == slot), None)
        tx = text.get(str(slot))
        if not q:
            continue
        if tx:
            body = plain(tx["stem"]) + "\n" + "\n".join(f"{CIRCLED[i]} {plain(c)}" for i, c in enumerate(tx.get("choices") or []))
        else:  # 글자 변환이 없으면 PDF 에서 뽑은 글자 (표가 깨져 있을 수 있음)
            body = ((q.get("shared") or {}).get("text", "") + "\n" + (q.get("text") or "")).strip()
            if len(body) < 20:
                continue
        ans = ", ".join(CIRCLED[a - 1] for a in q["answer"] if 0 < a <= 5)
        parts.append(f"[{paper['year']}년 {slot}번] (정답 {ans})\n{body}")
    return "\n\n".join(parts) or "(참고 기출 없음)"


def gen_request(t: dict, slot: int, existing: list[str]) -> dict:
    ex = EXAMS[t["exam"]]["name"]
    others = "\n".join(f"- {s[:120]}" for s in existing) or "(없음)"
    user = (f"시험: {ex} / {t['group']} / 과목: {t['subject']} / {slot}번 (전체 {t['slots']}문항, 선택지 {t['choices']}개)\n\n"
            f"[같은 번호의 최근 기출]\n{ref_block(t, slot)}\n\n[이 번호에 이미 만든 후보 (겹치지 않게)]\n{others}\n\n[정답 번호] {random.randint(1, t['choices'])}번")
    return dict(model=MODEL, max_tokens=16000, system=GEN_SYSTEM, thinking={"type": "adaptive"},
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": gen_schema(t["choices"])}},
                messages=[{"role": "user", "content": user}])


def verify_request(t: dict, d: dict) -> dict:
    ex = EXAMS[t["exam"]]["name"]
    body = d["stem"] + "\n" + "\n".join(f"{CIRCLED[i]} {c}" for i, c in enumerate(d["choices"]))
    user = f"시험: {ex} / {t['group']} / 과목: {t['subject']}\n\n{body}"
    return dict(model=MODEL, max_tokens=12000, system=VERIFY_SYSTEM, thinking={"type": "adaptive"},
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": VERIFY_SCHEMA}},
                messages=[{"role": "user", "content": user}])


def api_id(s: str) -> str:
    return "m" + hashlib.sha1(s.encode()).hexdigest()[:40]


# ------------------------------------------------------------------ 상태·예산

def state() -> dict:
    st = load(STATE, {})
    for k, v in (("usage", {}), ("gen_batches", []), ("verify_batches", []), ("pending", {}), ("ids", {}), ("rejected", 0)):
        st.setdefault(k, v)
    return st


def config() -> dict:
    return load(CONF, {"monthly_usd": 30, "per_slot": 2})


def spent(st: dict, month: str | None = None) -> float:
    u = st["usage"].get(month or month_key(), {})
    return u.get("in", 0) / 1e6 * PRICE_IN + u.get("out", 0) / 1e6 * PRICE_OUT


def stage_cost(st: dict, kind: str) -> float:
    """요청 하나의 실측 비용 (gen 만들기 / verify 검토)"""
    x = st.get("stage", {}).get(kind, {})
    return x["usd"] / x["n"] if x.get("n", 0) >= 30 else DEFAULT_PER_Q * (0.85 if kind == "gen" else 0.15)


def per_question(st: dict) -> float:
    """만들기 + 검토 한 번씩. 검토를 기다리는 문항이 있어도 값이 부풀지 않도록 단계별로 잰다"""
    return stage_cost(st, "gen") + stage_cost(st, "verify")


def pending_cost(st: dict) -> float:
    """진행 중인 문항에 앞으로 더 들 비용 (초안이 나온 것은 검토비만)"""
    return sum(stage_cost(st, "verify") if "draft" in j else per_question(st) for j in st["pending"].values())


def add_usage(st: dict, msg, kind: str) -> None:
    u = st["usage"].setdefault(month_key(), {"in": 0, "out": 0, "made": 0})
    m = msg.usage
    i = (m.input_tokens or 0) + (getattr(m, "cache_creation_input_tokens", 0) or 0) + (getattr(m, "cache_read_input_tokens", 0) or 0)
    o = m.output_tokens or 0
    u["in"] += i
    u["out"] += o
    x = st.setdefault("stage", {}).setdefault(kind, {"usd": 0.0, "n": 0})
    x["usd"] = round(x["usd"] + i / 1e6 * PRICE_IN + o / 1e6 * PRICE_OUT, 6)
    x["n"] += 1


# ------------------------------------------------------------------ 평가 반영

def retire() -> None:
    import requests

    r = requests.post(f"{SUPABASE}/rest/v1/rpc/ai_feedback", json={},
                      headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    fb: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in r.json():
        fb[row["target"]][row["kind"]] += int(row["n"])
    changed = 0
    for f in sorted((DATA / "papers").glob("ai-*.json")):
        paper = json.loads(f.read_text())
        dirty = False
        for q in paper["questions"]:
            c = fb.get(f"a:{paper['id']}:{q['no']}", collections.Counter())
            q["fb"] = {k: c[k] for k in ("good", "bad", "wrong_answer") if c[k]}
            bad = c["wrong_answer"] >= 2 or (c["bad"] >= 3 and c["bad"] >= 2 * c["good"])
            if bad and not q.get("retired"):
                q["retired"] = dt.date.today().isoformat()
                changed += 1
            dirty = True
        if dirty:
            f.write_text(json.dumps(paper, ensure_ascii=False))
    print(f"평가 반영: 새로 뺀 문항 {changed}개")


# ------------------------------------------------------------------ 배치

def client():
    import anthropic

    return anthropic.Anthropic()


def submit_batch(cl, reqs: list, kind: str, st: dict) -> None:
    import time

    from anthropic.types.messages.batch_create_params import Request

    for i in range(0, len(reqs), 200):
        chunk = reqs[i:i + 200]
        b, err = None, ""
        for attempt in range(3):
            try:
                b = cl.messages.batches.create(requests=[Request(custom_id=c, params=p) for c, p in chunk])
                break
            except Exception as e:  # 인증 토큰 교환이 잠깐 실패하는 경우가 있어 새 클라이언트로 다시
                err = str(e)[:200]
                time.sleep(20)
                cl = client()
        if b is None:  # 크레딧 부족 등: 남은 요청은 모두 거두고 다음 실행에서 다시
            print(f"{kind} 배치 제출 실패: {err}")
            for c, _ in reqs[i:]:
                st["pending"].pop(st["ids"].pop(c, ""), None)
            break
        st[f"{kind}_batches"].append(b.id)
        save(STATE, st)
        print(f"submitted {kind} {b.id}: {len(chunk)}건")


def collect() -> None:
    st = state()
    if not (st["gen_batches"] or st["verify_batches"]):
        if st["pending"]:  # 제출에 실패해 남은 기록 정리
            print(f"배치 없이 남은 요청 {len(st['pending'])}건 정리")
            st["pending"], st["ids"] = {}, {}
            save(STATE, st)
        print("진행 중인 배치 없음")
        return
    cl = client()
    tmap = {t["paper"]: t for t in tracks()}
    verify_reqs = []
    for kind in ("gen", "verify"):
        left = []
        for bid in st[f"{kind}_batches"]:
            if cl.messages.batches.retrieve(bid).processing_status != "ended":
                left.append(bid)
                continue
            for res in cl.messages.batches.results(bid):
                key = st["ids"].pop(res.custom_id, None)
                job = st["pending"].get(key) if key else None
                if not job:
                    continue
                if res.result.type != "succeeded" or res.result.message.stop_reason != "end_turn":
                    st["pending"].pop(key, None)
                    continue
                msg = res.result.message
                add_usage(st, msg, kind)
                try:
                    out = json.loads(next(b.text for b in msg.content if b.type == "text"))
                except Exception:
                    st["pending"].pop(key, None)
                    continue
                t = tmap.get(job["paper"])
                if kind == "gen":
                    if not t or len(out["choices"]) != t["choices"] or not 1 <= out["answer"] <= t["choices"]:
                        st["pending"].pop(key, None)
                        st["rejected"] += 1
                        continue
                    job["draft"] = out
                    cid = api_id(key + ":v")
                    st["ids"][cid] = key
                    verify_reqs.append((cid, verify_request(t, out)))
                else:
                    d = job["draft"]
                    st["pending"].pop(key, None)
                    if not t or not out["valid"] or out["answer"] != d["answer"]:
                        st["rejected"] += 1
                        why = out.get("issue") or f"답 불일치 {out['answer']} vs {d['answer']}"
                        print(f"  탈락 {job['paper']} {job['slot']}번: {why}"[:200])
                        continue
                    accept(t, job["slot"], d, msg.model)
                    st["usage"][month_key()]["made"] = st["usage"][month_key()].get("made", 0) + 1
            print(f"collected {kind} {bid}")
        st[f"{kind}_batches"] = left
    save(STATE, st)
    if verify_reqs:
        submit_batch(cl, verify_reqs, "verify", st)
    save(STATE, st)


def accept(t: dict, slot: int, d: dict, model: str) -> None:
    paper = ai_paper(t)
    d = polish(d, paper, t["choices"])
    no = max((q["no"] for q in paper["questions"]), default=0) + 1
    paper["slots"] = t["slots"]
    paper["choices"] = t["choices"]
    paper["questions"].append(dict(no=no, slot=slot, regions=[], text=plain(d["stem"]), answer=[d["answer"]],
                                   topic=d["topic"], created=dt.date.today().isoformat()))
    (DATA / "papers" / f"{t['paper']}.json").write_text(json.dumps(paper, ensure_ascii=False))
    tf = DATA / "text" / f"{t['paper']}.json"
    text = load(tf, {})
    text[str(no)] = dict(stem=d["stem"], choices=d["choices"], figs={})
    tf.write_text(json.dumps(text, ensure_ascii=False))
    ef = DATA / "explanations" / f"{t['paper']}.json"
    ex = load(ef, {})
    notes = d["choice_notes"] if len(d["choice_notes"]) == t["choices"] else []
    ex[str(no)] = dict(key_point=d["key_point"], explanation=d["explanation"], choices=notes, tip=d["tip"],
                       model=f"{model} (AI 출제)")
    ef.write_text(json.dumps(ex, ensure_ascii=False))


def submit(limit: int | None = None) -> None:
    st, cf = state(), config()
    per_q = per_question(st)
    left = cf["monthly_usd"] - spent(st) - pending_cost(st)
    n_budget = max(int(left // per_q), 0)
    # 첫 실측 전에는 시험 삼아 조금만
    if sum(u.get("made", 0) for u in st["usage"].values()) < 30:
        if st["pending"]:
            print("시범 배치 결과를 기다리는 중")
            return
        n_budget = min(n_budget, cf.get("pilot", 40))
    n_budget = min(n_budget, cf.get("max_per_run", 300))  # 한 번에 너무 많이 내지 않는다 (매일 나눠 채움)
    if limit is not None:
        n_budget = min(n_budget, limit)
    print(f"AI 출제 예산: 이번 달 남은 ${left:.2f}, 문항당 약 ${per_q:.3f} → 최대 {n_budget}개")
    if n_budget <= 0:
        return
    busy = collections.Counter((j["paper"], j["slot"]) for j in st["pending"].values())
    allow = set(cf.get("exams") or [])  # 비어 있으면 모든 시험
    ts = [t for t in tracks() if not allow or t["exam"] in allow]
    # 폭 먼저: 모든 트랙의 한 벌을 채운 뒤 둘째 후보, 셋째 후보 …
    wants = []
    for r in range(1, cf["per_slot"] + 1):
        for t in ts:
            have = active_by_slot(ai_paper(t))
            for s in range(1, t["slots"] + 1):
                if len(have.get(s, [])) + busy[(t["paper"], s)] < r:
                    wants.append((t, s))
                    busy[(t["paper"], s)] += 1
                if len(wants) >= n_budget:
                    break
            if len(wants) >= n_budget:
                break
        if len(wants) >= n_budget:
            break
    if not wants:
        print("모든 칸이 채워져 있음")
        return
    reqs = []
    stamp = dt.datetime.now(KST).strftime("%Y%m%d%H%M%S")
    for i, (t, s) in enumerate(wants):
        have = [q["text"] for q in active_by_slot(ai_paper(t)).get(s, [])]
        key = f"{t['paper']}:{s}:{stamp}:{i}"
        cid = api_id(key)
        st["pending"][key] = dict(paper=t["paper"], slot=s)
        st["ids"][cid] = key
        reqs.append((cid, gen_request(t, s, have)))
    submit_batch(client(), reqs, "gen", st)
    save(STATE, st)


def index() -> None:
    st, cf = state(), config()
    out = []
    total = 0
    for t in tracks():
        f = DATA / "papers" / f"{t['paper']}.json"
        if not f.exists():
            continue
        have = active_by_slot(json.loads(f.read_text()))
        filled = sum(1 for s in range(1, t["slots"] + 1) if have.get(s))
        n = sum(len(v) for v in have.values())
        total += n
        out.append(dict(exam=t["exam"], group=t["group"], subject=t["subject"], paper=t["paper"], slots=t["slots"],
                        choices=t["choices"], filled=filled, active=n))
    MOCK_INDEX.parent.mkdir(parents=True, exist_ok=True)
    MOCK_INDEX.write_text(json.dumps(dict(
        month=month_key(), limitUsd=cf["monthly_usd"], spentUsd=round(spent(st), 2),
        perQuestionUsd=round(per_question(st), 4), total=total, tracks=out), ensure_ascii=False))
    print(f"mock index: 트랙 {len(out)}개, 문항 {total}개, 이번 달 ${spent(st):.2f}/{cf['monthly_usd']}")


def plan() -> None:
    st, cf = state(), config()
    ts = tracks()
    print(f"트랙 {len(ts)}개, 칸 {sum(t['slots'] for t in ts)}개 × 후보 {cf['per_slot']}")
    print(f"이번 달 ${spent(st):.2f}/{cf['monthly_usd']}, 문항당 ${per_question(st):.3f}, 진행 중 {len(st['pending'])}")
    for t in ts[:15]:
        have = active_by_slot(ai_paper(t))
        print(f"  {t['paper']}: {t['slots']}칸, 채움 {sum(1 for s in range(1, t['slots'] + 1) if have.get(s))}, 참고 {len(t['refs'])}개 연도")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "run", "retire", "collect", "submit", "index"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "plan":
        plan()
    elif a.cmd == "retire":
        retire()
    elif a.cmd == "collect":
        collect()
    elif a.cmd == "submit":
        submit(a.limit)
    elif a.cmd == "index":
        index()
    else:
        try:
            retire()
        except Exception as e:  # 평가 서버가 잠시 안 돼도 나머지는 진행
            print("평가 반영 실패:", str(e)[:200])
        collect()
        submit(a.limit)
        index()


if __name__ == "__main__":
    main()
