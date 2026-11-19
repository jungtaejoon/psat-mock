"""사이트에 올리는 PDF 를 가볍게 복사한다 (GitHub Pages 용량 한도 1GB 를 아끼려고)."""
from __future__ import annotations

import shutil
from pathlib import Path


def copy_compressed(src: Path, dst: Path) -> None:
    """안 쓰는 객체를 지우고 스트림을 다시 압축해 저장한다. 오히려 커지면 원본을 그대로 복사한다."""
    import fitz

    if dst.exists():
        return
    try:
        doc = fitz.open(src)
        tmp = dst.with_suffix(".tmp.pdf")
        doc.save(tmp, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True, use_objstms=1)
        doc.close()
        if tmp.stat().st_size < Path(src).stat().st_size:
            tmp.replace(dst)
            return
        tmp.unlink()
    except Exception:  # noqa: BLE001
        pass
    shutil.copyfile(src, dst)
