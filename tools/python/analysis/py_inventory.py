#!/usr/bin/env python3
"""FL 同梱 Python (mac Python.framework 3.12.1) と本プロジェクトの wasm CPython の構成差分を実測する。
  python3 analysis/py_inventory.py > analysis/python_inventory.json   (wasm の builtin 一覧は work/wasm_builtins.json を参照)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from paths import FL_MAC_DIR  # noqa: E402

FL = f"{FL_MAC_DIR}/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL"
FW = f"{FL}/Shared/Python/Python.framework/Versions/3.12"
LIB = f"{FW}/lib/python3.12"
HERE = os.path.dirname(os.path.abspath(__file__))


def du(p):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs if not os.path.islink(os.path.join(d, f)))


dyn = sorted(re.sub(r"\.cpython-312-darwin\.so$", "", f) for f in os.listdir(f"{LIB}/lib-dynload"))
test_mods = [m for m in dyn if m.startswith(("_test", "_xxtest", "xx", "_ctypes_test"))]
fl_dyn = [m for m in dyn if m not in test_mods]
wasm = json.load(open(os.path.join(HERE, "..", "work", "wasm_builtins.json")))
builtin = set(wasm["builtin_module_names"])
# lib-dynload の名前 -> wasm 側での提供有無 (static builtin)
missing = sorted(m for m in fl_dyn if m not in builtin)
present = sorted(m for m in fl_dyn if m in builtin)
py_files = [os.path.join(d, f) for d, _, fs in os.walk(LIB) for f in fs if f.endswith(".py")]
top_pkgs = sorted(d for d in os.listdir(LIB) if os.path.isdir(f"{LIB}/{d}") and d not in ("lib-dynload", "__pycache__"))
res = {
    "fl_python_version": "3.12.1 (python.org macOS framework build; /Users/sysadmin/build/v3.12.1)",
    "framework_total_bytes": du(f"{FL}/Shared/Python/Python.framework"),
    "python_dylib_bytes": os.path.getsize(f"{FW}/Python"),
    "stdlib_py_files": len(py_files),
    "stdlib_top_packages": top_pkgs,
    "has_test_pkg": os.path.isdir(f"{LIB}/test"),
    "site_packages": os.listdir(f"{LIB}/site-packages"),
    "fl_extra_lib": {"Shared/Python/Lib": sorted(os.listdir(f"{FL}/Shared/Python/Lib"))},
    "lib_dynload_total": len(dyn),
    "lib_dynload_nontest": len(fl_dyn),
    "present_in_wasm_builtin": present,
    "missing_in_wasm": missing,
    "wasm_builtin_count": len(builtin),
    "extra_dylibs": sorted(f for f in os.listdir(f"{FW}/lib") if f.endswith(".dylib")),
    "fl_specific_in_lib_dynload": [m for m in dyn if "fl" in m.lower() and not m.startswith("_")],
}
json.dump(res, sys.stdout, indent=1)
