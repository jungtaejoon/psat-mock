"""스캔본(글자 층 없는) 큐넷 문제지: 쪽 그림을 AI 가 읽어 문항 위치를 찾고 문제지를 만든다.

  python pipeline/scan.py prepare                # (로컬) 대상 고르기 → PDF 압축 복사, data/scan/jobs.json
  python pipeline/scan.py submit                 # (CI) 아직 안 읽은 쪽을 배치로 제출 (Haiku 두 번, 어긋난 쪽은 Sonnet)
  python pipeline/scan.py collect                # (CI) 결과 받아 쪽마다 두 읽기를 비교 → 맞으면 확정
  python pipeline/scan.py build                  # 모든 쪽이 확정된 시험지 → web/public/data/papers/*.json

- 문항 위치는 두 번 따로 읽어 문항 번호 목록이 같고 상자가 거의 겹칠 때(IoU 0.8 이상)만 쓴다. 다르면 Sonnet 으로 한 번 더
  읽어 둘 중 하나와 맞으면 쓴다. 그래도 안 맞는 쪽이 있는 시험지는 만들지 않는다.
- 정답은 큐넷 최종정답(answers.json). 글자로 옮기기(텍스트 보기)는 convert.py 가 맡는다(스캔본은 두 번 읽어 비교).
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"
SCAN = ROOT / "data" / "scan"
JOBS = SCAN / "jobs.json"
STATE = SCAN / "state.json"
HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
DPI = 110
CATALOG = json.loads((ROOT / "web" / "src" / "exams.json").read_text())
SKIP_EXAMS = {"labor"}  # 노무사: 1교시 문제지가 큐넷에 없고 선택과목 파일만 있다

SYSTEM = """시험지 한 쪽의 그림을 보고, 이 쪽에 있는 문항들의 위치를 찾는 일입니다.

읽는 순서(2단이면 왼쪽 단 위→아래, 그다음 오른쪽 단)대로 "조각"을 나열하세요.
- 문항 조각: kind "question", no 는 인쇄된 문항 번호. 발문·자료·보기 ①~⑤ 까지 그 문항에 속한 것 전부를 감싸는 상자.
  문항이 단이나 쪽을 넘어 이어지면, 이어진 부분도 같은 no 의 조각으로 따로 적는다(이 쪽 맨 위에 앞 문항의 나머지가 있으면 그 번호로).
- 공통 지문 조각: "[1～3] 다음 글을 읽고…"처럼 여러 문항이 함께 쓰는 지문은 kind "shared", no 는 첫 번호, last_no 는 마지막 번호.
- box 는 쪽 전체에 대한 비율 [왼쪽, 위, 오른쪽, 아래]. 위아래로 2~3% 넉넉하게. 머리말·꼬리말·쪽 번호·과목 제목 띠·수험자 안내문은 넣지 않는다.
- 문항이 하나도 없는 쪽(표지·안내)이면 빈 목록.
번호를 지어내지 말고 그림에 보이는 번호만 쓴다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["question", "shared"]},
                    "no": {"type": "integer"},
                    "last_no": {"type": "integer"},
                    "box": {"type": "array", "items": {"type": "number"}},
                },
                "required": ["kind", "no", "box"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["segments"],
    "additionalProperties": False,
}


def load(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def save(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ prepare (로컬)

def prepare() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import qnet_build as qb

    jobs = load(JOBS, [])
    have = {j["id"] for j in jobs}
    for e in CATALOG["exams"]:
        if not (e.get("qnet") and e["status"] == "live") or e["id"] in SKIP_EXAMS:
            continue
        g = e["qnet"]
        files = qb.paper_files(g)
        built = {p.stem for p in (DATA / "papers").glob(f"{e['id']}-*.json")}
        for en in json.loads((ROOT / "data" / "qnet" / g / "answers.json").read_text()):
            track = f"-{qb.slug(en['track'])}" if en.get("track") else ""
            prefix = (f"{e['id']}-{en['year']}{'-특별' if en.get('round') == '특별' else ''}"
                      f"{'-' + en['stage'] if en.get('stage') == '2차' else ''}{track}-{en['period']}교시-")
            if any(b.startswith(prefix) for b in built) or prefix in have:
                continue
            f = qb.pick([f for f in files if qb.compatible(en, f)], en)
            if not f or not f.get("kogl"):
                continue
            doc = fitz.open(f["path"])
            if sum(len(p.get_text()) for p in doc) > len(doc) * 300:
                continue  # 글자 층이 있는 PDF 는 대상 아님
            pdf_id = f"{e['id']}-{en['year']}-{hashlib.sha1(Path(f['path']).read_bytes()).hexdigest()[:10]}"
            out = DATA / "pdf" / f"{pdf_id}.pdf"
            if not out.exists():
                # 스캔 그림을 150dpi JPEG 로 줄여 저장 (Cloudflare 파일 한도 25MB, 화면에는 충분)
                doc.rewrite_images(dpi_threshold=160, dpi_target=150, quality=70)
                doc.save(out, garbage=4, deflate=True, use_objstms=1)
            jobs.append(dict(id=prefix, exam=e["id"], entry=en, pdf=pdf_id, pages=len(fitz.open(out)),
                             source=dict(post=f["post"], title=f["title"], name=f["name"]), kogl=f["kogl"]))
            have.add(prefix)
            print("job", prefix, f["name"], f"{out.stat().st_size // 1024}KB", flush=True)
    save(JOBS, jobs)
    print(len(jobs), "jobs")


# ------------------------------------------------------------------ 배치

def page_png(pdf_id: str, page: int) -> bytes:
    doc = fitz.open(DATA / "pdf" / f"{pdf_id}.pdf")
    return doc[page].get_pixmap(dpi=DPI, colorspace=fitz.csGRAY).tobytes("jpeg", jpg_quality=80)


def params(pdf_id: str, page: int, model: str, variant: str) -> dict:
    hint = "" if variant == "a" else "\n(다시 확인하는 읽기입니다. 번호와 상자 경계를 한 번 더 꼼꼼히 보세요.)"
    return {
        "model": model,
        "max_tokens": 8000,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(page_png(pdf_id, page)).decode()}},
            {"type": "text", "text": f"이 쪽의 문항 조각을 찾아 주세요.{hint}"},
        ]}],
    }


def key(job_id: str, page: int) -> str:
    return f"{job_id}|{page}"


def api_id(k: str, read: str) -> str:
    return "s" + hashlib.sha1(f"{k}|{read}".encode()).hexdigest()[:40]


def submit(client) -> None:
    from anthropic.types.messages.batch_create_params import Request

    jobs = load(JOBS, [])
    st = load(STATE, {"batches": [], "ids": {}, "reads": {}, "pages": {}, "failed": {}})
    pending = set(st["ids"].values())
    reqs = []
    for j in jobs:
        for pg in range(j["pages"]):
            k = key(j["id"], pg)
            if k in st["pages"] or k in st["failed"]:
                continue
            reads = st["reads"].get(k, {})
            want = ["a", "b"] if not reads.get("needs_sonnet") else ["c"]
            for r in want:
                if r in reads or f"{k}|{r}" in pending:
                    continue
                cid = api_id(k, r)
                st["ids"][cid] = f"{k}|{r}"
                reqs.append(Request(custom_id=cid, params=params(j["pdf"], pg, SONNET if r == "c" else HAIKU, r)))
    for i in range(0, len(reqs), 300):
        chunk = reqs[i : i + 300]
        b = client.messages.batches.create(requests=chunk)
        st["batches"].append(b.id)
        save(STATE, st)
        print(f"submitted {b.id}: {len(chunk)}건", flush=True)
    if not reqs:
        print("읽을 쪽 없음")
    save(STATE, st)


def iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0


def same(r1: list, r2: list) -> bool:
    if [(s["kind"], s["no"]) for s in r1] != [(s["kind"], s["no"]) for s in r2]:
        return False
    return all(iou(a["box"], b["box"]) >= 0.8 for a, b in zip(r1, r2))


def merge(r1: list, r2: list) -> list:
    """두 읽기의 상자를 합친다(바깥쪽으로 — 글자가 잘리지 않게)"""
    out = []
    for a, b in zip(r1, r2):
        box = [min(a["box"][0], b["box"][0]), min(a["box"][1], b["box"][1]), max(a["box"][2], b["box"][2]), max(a["box"][3], b["box"][3])]
        out.append(dict(a, box=box))
    return out


def collect(client) -> None:
    st = load(STATE, {"batches": [], "ids": {}, "reads": {}, "pages": {}, "failed": {}})
    remaining = []
    for bid in st["batches"]:
        if client.messages.batches.retrieve(bid).processing_status != "ended":
            remaining.append(bid)
            continue
        for res in client.messages.batches.results(bid):
            full = st["ids"].pop(res.custom_id, None)
            if not full:
                continue
            k, r = full.rsplit("|", 1)
            segs = None
            if res.result.type == "succeeded" and res.result.message.stop_reason == "end_turn":
                text = next((b.text for b in res.result.message.content if b.type == "text"), "")
                try:
                    segs = [s for s in json.loads(text)["segments"] if len(s.get("box", [])) == 4]
                except (json.JSONDecodeError, KeyError):
                    segs = None
            st["reads"].setdefault(k, {})[r] = segs
        print("collected", bid, flush=True)
    st["batches"] = remaining
    # 판정
    ok = sonnet = bad = 0
    for k, reads in st["reads"].items():
        if k in st["pages"] or k in st["failed"]:
            continue
        a, b, c = reads.get("a"), reads.get("b"), reads.get("c")
        if a is not None and b is not None and same(a, b):
            st["pages"][k] = merge(a, b)
            ok += 1
        elif "c" in reads:
            pick = a if (c is not None and a is not None and same(a, c)) else b if (c is not None and b is not None and same(b, c)) else None
            if pick is not None:
                st["pages"][k] = merge(pick, c)
                ok += 1
            else:
                st["failed"][k] = "세 읽기가 서로 다름"
                bad += 1
        elif "a" in reads and "b" in reads:
            reads["needs_sonnet"] = True
            sonnet += 1
    save(STATE, st)
    print(f"쪽 확정 {ok}, Sonnet 필요 {sonnet}, 실패 {bad}; 전체 확정 {len(st['pages'])}")


# ------------------------------------------------------------------ 문제지 만들기

def build() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import qnet_build as qb

    jobs = load(JOBS, [])
    st = load(STATE, {"pages": {}, "failed": {}})
    made = 0
    for j in jobs:
        keys = [key(j["id"], pg) for pg in range(j["pages"])]
        if not all(k in st["pages"] for k in keys):
            continue
        doc = fitz.open(DATA / "pdf" / f"{j['pdf']}.pdf")
        regions: dict[int, list] = {}
        shared: list[tuple[int, int, list]] = []
        for pg, k in enumerate(keys):
            W, H = doc[pg].rect.width, doc[pg].rect.height
            for s in st["pages"][k]:
                x0, y0, x1, y1 = s["box"]
                r = dict(page=pg, x0=round(max(0, x0) * W, 1), y0=round(max(0, y0) * H, 1), x1=round(min(1, x1) * W, 1), y1=round(min(1, y1) * H, 1))
                if s["kind"] == "shared":
                    if shared and shared[-1][0] == s["no"]:
                        shared[-1][2].append(r)
                    else:
                        shared.append((s["no"], s.get("last_no") or s["no"], [r]))
                else:
                    regions.setdefault(s["no"], []).append(r)
        en = j["entry"]
        e = next(x for x in CATALOG["exams"] if x["id"] == j["exam"])
        subs = en["subjects"]
        want = set(range(subs[0]["from"], subs[-1]["to"] + 1)) - {int(x) for x in en.get("text_items", [])}
        # 교시 시험지 번호가 1부터 다시 시작하는 경우(예: 2교시 41~80번이 1~40번으로 인쇄): 순서대로 옮긴다
        if not want <= set(regions) and set(range(1, len(want) + 1)) <= set(regions):
            order = sorted(want)
            regions = {order[i - 1]: regions[i] for i in range(1, len(want) + 1)}
            shared = [(order[a - 1], order[min(b, len(order)) - 1], rs) for a, b, rs in shared if a <= len(order)]
        if not want <= set(regions):
            print("  ! 문항 번호가 모자람", j["id"], sorted(want - set(regions))[:10])
            continue
        ents = json.loads((ROOT / "data" / "qnet" / e["qnet"] / "answers.json").read_text())
        has_special = any(x.get("round") == "특별" for x in ents)
        multi_stage = len({x.get("stage") for x in ents if x.get("stage")}) > 1
        for s in subs:
            sq = []
            for no in range(s["from"], s["to"] + 1):
                if no not in want:
                    continue
                ans = en["answers"].get(str(no))
                if ans is None:
                    break
                q = dict(no=len(sq) + 1, orig=no, regions=regions[no], text="", answer=ans)
                sh = next((x for x in shared if x[0] <= no <= x[1]), None)
                if sh:
                    q["shared"] = dict(regions=sh[2], text="")
                sq.append(q)
            if len(sq) != sum(1 for no in range(s["from"], s["to"] + 1) if no in want):
                print("  ! 정답 빠짐", j["id"], s["name"])
                continue
            pid = f"{j['id']}{qb.slug(s['name'])}"
            parts = ["특별시험" if en.get("round") == "특별" else ("정기시험" if has_special else ""),
                     en.get("stage") or "" if multi_stage else "", en.get("track") or ""]
            paper = dict(id=pid, exam=j["exam"], group=" ".join(p for p in parts if p) or "필기", year=en["year"], subject=s["name"],
                         exams=[e["name"]], answersFinal=True, choices=e["choices"], kogl=j["kogl"], pdf=j["pdf"], scan=True,
                         source=dict(post=j["source"]["post"], title=j["source"]["title"], answerPost=en.get("post")),
                         width=doc[0].rect.width, height=doc[0].rect.height, pages=len(doc), questions=sq)
            (DATA / "papers" / f"{pid}.json").write_text(json.dumps(paper, ensure_ascii=False))
            made += 1
    print("만든 문제지", made)


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "prepare":
        prepare()
    elif cmd == "build":
        build()
    else:
        import anthropic

        client = anthropic.Anthropic()
        submit(client) if cmd == "submit" else collect(client)


if __name__ == "__main__":
    main()
