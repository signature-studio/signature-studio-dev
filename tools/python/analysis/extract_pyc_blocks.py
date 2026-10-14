#!/usr/bin/env python3
# FL 同梱 pyc / pyscript / drum patterns を win64 の DATA block から復元する (PY-7 #78, PY-84 #2663)。
#   FL_WIN64_DIR=<fl-win64 展開先>/extracted python3.12 analysis/extract_pyc_blocks.py <out_dir>
# - magic cb0d0d0a (3.12 pyc) の block を marshal.loads し、co_filename から配置パスを得る。
# - pyscript (テキスト) は先頭 docstring の題名と import 行で同定する (ブロック名は元ファイル名を持たない)。
# - drum patterns は平文 JSON で、compatible_from と genres を持つ dict。
# - 各規則はちょうど 1 block に当たること。0 件・2 件以上なら何も書かず exit 3。
# 出力: <out_dir>/<相対パス>.pyc・<out_dir>/pyscript/{cpt,stack}.pyscript・<out_dir>/drum_patterns.json と manifest.json。FL 由来物なので commit しない。
import json
import marshal
import os
import re
import sys

MAGIC = b"\xcb\x0d\x0d\x0a"
PYSCRIPT_RULES = {
    "cpt": re.compile(r'\A"""\r?\nCPT comms script;[^\r\n]*\r?\n"""\r?\nfrom control import \*'),
    "stack": re.compile(r'\A"""\r?\nStack / Generator comms script;[^\r\n]*\r?\n"""\r?\nfrom control_rack import \*'),
}


def is_drum_patterns(data: bytes) -> bool:
    if data[:1] != b"{":
        return False
    try:
        d = json.loads(data.decode("utf8"))
    except (UnicodeDecodeError, ValueError):
        return False
    return isinstance(d, dict) and "compatible_from" in d and "genres" in d


def main() -> int:
    src = os.environ.get("FL_WIN64_DIR")
    if not src or not os.path.isdir(src):
        print("FL_WIN64_DIR/extracted not found", file=sys.stderr)
        return 2
    out = sys.argv[1]
    manifest = {"pyc": [], "text": [], "skipped": []}
    pycs = []
    scripts = {name: [] for name in PYSCRIPT_RULES}
    drums = []
    for f in sorted(os.listdir(src)):
        if not re.fullmatch(r"block\d+_DATA\.bin", f):
            continue
        p = os.path.join(src, f)
        data = open(p, "rb").read()
        if data[:4] == MAGIC:
            try:
                code = marshal.loads(data[16:])
            except Exception as e:  # noqa: BLE001
                manifest["skipped"].append({"block": f, "why": f"marshal: {e}"})
                continue
            rel = code.co_filename
            if rel.endswith(".py"):
                rel = rel[:-3] + ".pyc"
            pycs.append((f, rel, data))
            continue
        s = data.decode("utf8", "replace")
        for name, rule in PYSCRIPT_RULES.items():
            if rule.match(s):
                scripts[name].append((f, data))
        if is_drum_patterns(data):
            drums.append((f, data))
        if len(data) < 40000 and b"\x00" not in data:
            if "ScriptDialog(" in s or "def createDialog" in s or "def apply" in s:
                head = s.splitlines()[0] if s else ""
                manifest["text"].append({"block": f, "head": head[:120], "bytes": len(data)})
    errors = [f"pyscript {name}: {len(hits)} block ({', '.join(h[0] for h in hits)}) が一致 (期待 1)"
              for name, hits in scripts.items() if len(hits) != 1]
    if len(drums) != 1:
        errors.append(f"drum_patterns: {len(drums)} block ({', '.join(d[0] for d in drums)}) が一致 (期待 1)")
    if errors:
        for e in errors:
            print("ERROR: " + e, file=sys.stderr)
        return 3
    os.makedirs(out, exist_ok=True)
    for f, rel, data in pycs:
        rel_path = os.path.join(out, rel.lstrip("/"))
        os.makedirs(os.path.dirname(rel_path), exist_ok=True)
        with open(rel_path, "wb") as w:
            w.write(data)
        manifest["pyc"].append({"block": f, "path": rel})
    os.makedirs(os.path.join(out, "pyscript"), exist_ok=True)
    manifest["pyscript"] = []
    for name, hits in scripts.items():
        f, data = hits[0]
        path = f"pyscript/{name}.pyscript"
        with open(os.path.join(out, path), "wb") as w:
            w.write(data)
        manifest["pyscript"].append({"name": name, "block": f, "path": path, "bytes": len(data)})
    f, data = drums[0]
    with open(os.path.join(out, "drum_patterns.json"), "wb") as w:
        w.write(data)
    manifest["drum_patterns"] = {"block": f, "path": "drum_patterns.json", "bytes": len(data)}
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf8") as w:
        json.dump(manifest, w, ensure_ascii=False, indent=1)
    print(json.dumps({"pyc": len(manifest["pyc"]), "text_candidates": len(manifest["text"]),
                      "skipped": len(manifest["skipped"]), "pyscript": len(manifest["pyscript"]),
                      "drum_patterns": 1}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
