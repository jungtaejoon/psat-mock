"""HWP 문제지 → PDF (로컬 전용: LibreOffice + H2Orestart 확장 + 나눔 글꼴).

  python pipeline/hwp2pdf.py <파일.hwp> [...]        # 같은 폴더에 <이름>.pdf

- H2Orestart 가 HWP(배포용 문서 포함)를 읽는다. LibreOffice.app/Contents/Resources/extensions/H2Orestart 에 풀어 둔다.
- 명령줄(headless) LibreOffice 는 macOS 시스템 글꼴을 못 써서 한글이 빈칸으로 나온다. 그래서 HWP → ODT 로 한 번 바꾼 뒤
  글꼴 이름을 나눔명조/나눔고딕(LibreOffice 사용자 글꼴 폴더에 둠)으로 바꾸고 ODT → PDF 로 내보낸다.
- 옛 시험(2014~2017)만 HWP 로 올라와 있어 한 번만 돌리면 된다. CI 에서는 쓰지 않는다.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
SERIF = ("바탕", "한양신명조", "명조", "휴먼명조", "HY신명조", "한컴바탕", "신명 신명조", "-윤명조120", "함초롬바탕", "#신명조",
         "한컴바탕확장", "Liberation Serif", "Linux Libertine G", "Times New Roman", "Times-Roman", "HCI")


def _family(face: str) -> str:
    base = re.sub(r"\d+$", "", face)
    if base.startswith("OpenSymbol"):
        return ""
    return "NanumMyeongjo" if any(base.startswith(s) for s in SERIF) else "NanumGothic"


def _fix_fonts(odt: Path, out: Path) -> None:
    zin = zipfile.ZipFile(odt)
    with zipfile.ZipFile(out, "w") as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename in ("content.xml", "styles.xml"):
                s = data.decode("utf-8")

                def rep(m: re.Match) -> str:
                    fam = _family(m.group(2))
                    return m.group(1) + (f"'{fam}'" if fam else m.group(3)) + m.group(4)

                s = re.sub(r'(<style:font-face style:name="([^"]*)" svg:font-family=")([^"]*)(")', rep, s)
                data = s.encode("utf-8")
            zout.writestr(it, data, compress_type=zipfile.ZIP_STORED if it.filename == "mimetype" else zipfile.ZIP_DEFLATED)


def _run(fmt: str, src: Path, outdir: Path) -> Path:
    env = dict(os.environ)
    if "JAVA_HOME" not in env:
        env["JAVA_HOME"] = subprocess.run(["/usr/libexec/java_home"], capture_output=True, text=True).stdout.strip()
    out = outdir / (src.stem + "." + fmt)
    # 앞 실행이 다 끝나기 전에 시작하면 가끔 실패한다 → 잠깐 쉬고 다시 (최대 3번)
    import time

    for attempt in range(3):
        r = subprocess.run([SOFFICE, "--headless", "--convert-to", fmt, "--outdir", str(outdir), str(src)],
                           capture_output=True, env=env, timeout=600)
        if r.returncode == 0 and out.exists():
            break
        time.sleep(5 * (attempt + 1))
    if not out.exists():
        raise RuntimeError(f"변환 실패: {src}")
    return out


def convert(hwp: Path, pdf: Path | None = None) -> Path:
    pdf = pdf or hwp.with_suffix(".pdf")
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        src = t / "doc.hwp"
        shutil.copyfile(hwp, src)
        odt = _run("odt", src, t)
        fixed = t / "doc2.odt"
        _fix_fonts(odt, fixed)
        out = _run("pdf", fixed, t)
        shutil.copyfile(out, pdf)
    return pdf


def qnet(gid: str) -> None:
    """큐넷 시험 하나의 문제지 HWP(ZIP 안 포함)를 모두 <파일>.hwp.pdf 로 바꿔 둔다. B형은 건너뛴다(정답표가 A형 기준)"""
    import json

    src = Path(__file__).resolve().parent.parent / "data" / "qnet" / gid
    posts = json.loads((src / "posts.json").read_text())
    jobs: list[tuple[Path, Path, str]] = []
    for p in posts.values():
        if p["kind"] != "paper" or not p["year"]:
            continue
        for f in p["files"]:
            path = src / f["local"]
            ext = path.suffix.lower()
            if ext == ".hwp":
                jobs.append((path, path.with_suffix(".hwp.pdf"), f["name"]))
            elif ext == ".zip" and path.exists():
                z = zipfile.ZipFile(path)
                for i, info in enumerate(z.infolist()):
                    name = info.filename
                    try:
                        name = name.encode("cp437").decode("cp949")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                    if name.lower().endswith(".hwp"):
                        xdir = src / "x"
                        xdir.mkdir(exist_ok=True)
                        h = xdir / f"{p['seq']}-{f['fseq']}-{i}.hwp"
                        if not h.exists():
                            h.write_bytes(z.read(info))
                        jobs.append((h, h.with_suffix(".hwp.pdf"), name))
    for hwp, pdf, name in jobs:
        if pdf.exists() or re.search(r"B\s*형|\(B\)|_B\b", name):
            continue
        try:
            convert(hwp, pdf)
            print("ok", name, flush=True)
        except Exception as ex:  # noqa: BLE001
            print("fail", name, ex, flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--qnet"]:
        for g in sys.argv[2:]:
            qnet(g)
    else:
        for a in sys.argv[1:]:
            print(convert(Path(a)))
