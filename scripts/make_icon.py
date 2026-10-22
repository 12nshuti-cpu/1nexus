r"""Regenerate assets/nexus.ico and assets/nexus.png from the NEXUS mark in ui/brand.py.

Run from the project folder:  .venv\Scripts\python scripts\make_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from ui.brand import mark_image, write_ico  # noqa: E402


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # needed for painting
    assets = ROOT / "assets"
    write_ico(assets / "nexus.ico")
    mark_image(256).save(str(assets / "nexus.png"), "PNG")
    app.processEvents()
    print(f"Wrote {assets / 'nexus.ico'} and {assets / 'nexus.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
