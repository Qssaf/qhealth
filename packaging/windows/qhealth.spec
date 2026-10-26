# PyInstaller spec for QHealth on Windows.  Build from the repository root:
#   python packaging/windows/make_icon.py
#   pyinstaller packaging/windows/qhealth.spec --noconfirm
import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = Path(SPECPATH).resolve().parents[1]
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "qhealth_core" / "__init__.py").read_text()).group(1)
NUMERIC = tuple(int(p) for p in (VERSION.split(".") + ["0"] * 4)[:4])

# Version resource: names the process "QHealth" in Task Manager and in QHealth's own app list
version_file = Path(workpath) / "version_info.txt"
version_file.parent.mkdir(parents=True, exist_ok=True)
version_file.write_text(str(VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMERIC, prodvers=NUMERIC),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Qssaf"),
            StringStruct("FileDescription", "QHealth"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "QHealth"),
            StringStruct("LegalCopyright", "MIT License"),
            StringStruct("OriginalFilename", "QHealth.exe"),
            StringStruct("ProductName", "QHealth"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)), encoding="utf-8")

a = Analysis(
    [str(ROOT / "packaging" / "windows" / "qhealth_main.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "qhealth_gui" / "assets" / "ui"), "qhealth_gui/assets/ui")],
    hiddenimports=["PyQt6.QtSvg", "qhealth_core.win32"],
    excludes=["tkinter", "unittest", "pydoc"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QHealth",
    console=False,
    icon=str(ROOT / "packaging" / "windows" / "qhealth.ico"),
    version=str(version_file),
)
coll = COLLECT(exe, a.binaries, a.datas, name="QHealth")
