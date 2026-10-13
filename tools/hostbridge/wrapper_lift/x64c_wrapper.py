"""Fruity Wrapper (block19091/23676) を x64c (tools/ott/lift/x64c.py) で実 lift する (#917 受入条件 2)。

x64c.py は IMG=0x180000000 (OTT DLL の ImageBase) を定数で持つ。本ドライバは実行時に
IMG / SHIFT / IMG_SIZE を Wrapper の ImageBase・SizeOfImage に差し替えてから main() を呼ぶ。
SHIFT=0 (VA を変換しない)。x64c.py 本体は変更しない (tools/ott は読取のみ)。

使い方 (cwd=リポジトリルート):
  FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/x64c_wrapper.py block19091_PE.bin <out_dir>
出力: <out_dir>/ott_lifted.c, <out_dir>/lift_meta.json, <out_dir>/entries.json
"""
import importlib.util
import json
import os
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "liftlib"))
from liftlib.pe import Image  # noqa: E402

X64C = os.path.join(HERE, "..", "..", "ott", "lift", "x64c.py")


def main():
    name, out_dir = sys.argv[1], sys.argv[2]
    path = os.path.join(os.environ["FL_WIN64_DIR"], name)
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    size = pe.OPTIONAL_HEADER.SizeOfImage
    img = Image(path)
    rngs = []
    seen = set()
    for (b, _e) in img.pdata_functions():
        r = img.func_at(b, merge=True)
        if r and r not in seen:
            seen.add(r)
            rngs.append(r[0])
    spec = importlib.util.spec_from_file_location("x64c_mod", X64C)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.IMG = base
    mod.SHIFT = 0
    mod.IMG_SIZE = size
    _orig_xreg = mod.FnLift.xreg

    # reg_name が None のレジスタは Unsup にして関数単位で fail-fast させる (生成 C の他の挙動は変えない)。
    def xreg(self, ins, rid):
        if ins.reg_name(rid) is None:
            raise mod.Unsup("xreg None")
        return _orig_xreg(self, ins, rid)

    mod.FnLift.xreg = xreg
    os.makedirs(out_dir, exist_ok=True)
    entries = os.path.join(out_dir, "entries.json")
    with open(entries, "w") as fh:
        json.dump({"roots": rngs, "calltgt": []}, fh)
    sys.argv = ["x64c.py", "--pe", path, "--entries", entries, "--out", out_dir, "--closure", "0"]
    mod.main()
    # x64c.py の i_cmpxchg (main 1491/1493 行) は amask に既に ULL を含むため、生成 C に ULLULL が出る。
    # x64c.py 本体は変更しない (範囲外) ので、Wrapper 側の後処理で吸収する (REPORT §6)。
    c_path = os.path.join(out_dir, "ott_lifted.c")
    with open(c_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    with open(c_path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("ULLULL", "ULL"))


if __name__ == "__main__":
    main()
