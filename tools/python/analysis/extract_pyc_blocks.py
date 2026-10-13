#!/usr/bin/env python3
# FL 同梱 pyc / pyscript を win64 の DATA block から復元する (PY-7 #78)。
#   FL_WIN64_DIR=<fl-win64 展開先>/extracted python3.12 analysis/extract_pyc_blocks.py <out_dir>
# - magic cb0d0d0a (3.12 pyc) の block を marshal.loads し、co_filename から配置パスを得る。
# - pyscript (テキスト) は先頭ヘッダ / 定義名で同定する (ブロック名は元ファイル名を持たない)。
# 出力: <out_dir>/<相対パス>.pyc および <out_dir>/pyscript/<name>.pyscript と manifest.json。FL 由来物なので commit しない。
import json
import marshal
import os
import re
import sys

MAGIC = b"\xcb\x0d\x0d\x0a"
PYSCRIPT_RULES = {
    "cpt": re.compile(r"ScriptDialog\(|def createDialog"),
}


def main() -> int:
    src = os.environ.get("FL_WIN64_DIR")
    if not src or not os.path.isdir(src):
        print("FL_WIN64_DIR/extracted not found", file=sys.stderr)
        return 2
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    manifest = {"pyc": [], "text": [], "skipped": []}
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
            rel_path = os.path.join(out, rel.lstrip("/"))
            os.makedirs(os.path.dirname(rel_path), exist_ok=True)
            with open(rel_path, "wb") as w:
                w.write(data)
            manifest["pyc"].append({"block": f, "path": rel})
        elif len(data) < 40000 and b"\x00" not in data:
            s = data.decode("utf8", "replace")
            if "ScriptDialog(" in s or "def createDialog" in s or "def apply" in s:
                head = s.splitlines()[0] if s else ""
                manifest["text"].append({"block": f, "head": head[:120], "bytes": len(data)})
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf8") as w:
        json.dump(manifest, w, ensure_ascii=False, indent=1)
    print(json.dumps({"pyc": len(manifest["pyc"]), "text_candidates": len(manifest["text"]),
                      "skipped": len(manifest["skipped"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
