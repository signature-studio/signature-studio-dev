#!/usr/bin/env python3.12
"""FL 同梱の Python スクリプト群 (pyscript / device .py / Tools の .pyc) が import するモジュールと
エントリポイントを実測する。 3.12 で実行 (pyc の dis 用)。
  work/build-native/install/bin/python3.12 analysis/scripts_inventory.py > analysis/scripts_inventory.json
"""
import ast
import dis
import json
import marshal
import os
import sys
import types

FL = "/home/ubuntu/work/analysis/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL"
STD = set(sys.stdlib_module_names)
FLMODS = {"transport", "ui", "midi", "channels", "playlist", "patterns", "plugins", "arrangement", "general", "device",
          "mixer", "ilmcp", "flpianoroll", "enveditor", "launchMapPages", "screen", "utils", "flcpt", "flrack", "fl"}


def walk(co):
    yield co
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            yield from walk(c)


groups = {}
for d, _, fs in os.walk(FL):
    if "Python.framework" in d:
        continue
    for f in fs:
        p = os.path.join(d, f)
        rel = os.path.relpath(p, FL)
        if f.endswith(".pyc"):
            co = marshal.loads(open(p, "rb").read()[16:])
            imps = {i.argval.split(".")[0] for c in walk(co) for i in dis.get_instructions(c) if i.opname == "IMPORT_NAME" and i.argval}
            funcs = [c.co_name for c in co.co_consts if isinstance(c, types.CodeType)]
            kind = "pyc"
        elif f.endswith((".pyscript", ".py")) and f not in ("midi.py", "utils.py"):
            src = open(p, encoding="utf-8", errors="replace").read()
            try:
                tree = ast.parse(src)
            except SyntaxError as e:
                groups.setdefault(os.path.dirname(rel), []).append({"file": f, "error": str(e)})
                continue
            imps = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    imps |= {a.name.split(".")[0] for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                    imps.add(n.module.split(".")[0])
            funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
            kind = "py"
        else:
            continue
        groups.setdefault(os.path.dirname(rel), []).append(
            {"file": f, "kind": kind, "imports_std": sorted(i for i in imps if i in STD),
             "imports_fl": sorted(i for i in imps if i in FLMODS), "imports_other": sorted(i for i in imps if i not in STD and i not in FLMODS),
             "top_functions": [x for x in funcs if x[0] != "<"][:12]})

allstd = sorted({m for v in groups.values() for e in v for m in e.get("imports_std", [])})
allfl = sorted({m for v in groups.values() for e in v for m in e.get("imports_fl", [])})
other = sorted({m for v in groups.values() for e in v for m in e.get("imports_other", [])})
json.dump({"counts": {k: len(v) for k, v in sorted(groups.items())}, "stdlib_modules_used": allstd, "fl_modules_used": allfl,
           "other_imports": other, "groups": groups}, sys.stdout, indent=1)
