"""Render assets/qhealth.svg into a multi-size Windows .ico (PNG-compressed entries, Vista+)."""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[2]
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def main(out: Path) -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841 (needed by QPainter)
    renderer = QSvgRenderer(str(ROOT / "assets" / "qhealth.svg"))
    images = [render_png(renderer, s) for s in SIZES]
    offset = 6 + 16 * len(SIZES)
    entries = b""
    for size, data in zip(SIZES, images):
        # width/height 0 means 256; 32 bpp; PNG payload
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out.write_bytes(struct.pack("<HHH", 0, 1, len(SIZES)) + entries + b"".join(images))
    print(f"wrote {out} ({len(SIZES)} sizes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "packaging" / "windows" / "qhealth.ico")
