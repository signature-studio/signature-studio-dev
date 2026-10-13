"""Fruity Wrapper (block19091/23676) の関数数・decode 成功率・CreatePlugInstance の位置を実測する。

使い方 (cwd=リポジトリルート):
  FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/measure_decode.py
出力: tools/hostbridge/wrapper_lift/work/decode_<block>.json
数え方:
  funcs      = .pdata の RUNTIME_FUNCTION を chain 併合した関数数 (pe.Image.func_at の併合規則)
  insns      = 関数範囲内を線形 decode した命令数 (capstone, 64bit)
  bad        = capstone が decode できなかったバイト位置 (1 byte 進めて継続) の数
  decode_ok  = 関数のうち bad が 0 の関数の割合
"""
import json
import os
import sys
import time

import capstone
import pefile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "liftlib"))
from liftlib.pe import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")
FL = os.environ["FL_WIN64_DIR"]


def measure(name):
    path = os.path.join(FL, name)
    img = Image(path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    seen = set()
    funcs = 0
    funcs_ok = 0
    insns = 0
    bad = 0
    t0 = time.time()
    for (b, e) in img.pdata_functions():
        rng = img.func_at(b, merge=True)
        if rng is None:
            continue
        key = rng
        if key in seen:
            continue
        seen.add(key)
        fb, fe = rng
        code = img.read(fb, fe - fb)
        funcs += 1
        fbad = 0
        off = 0
        while off < len(code):
            n = 0
            for ins in md.disasm(code[off:off + 16], fb + off):
                n = ins.size
                insns += 1
                break
            if n == 0:
                fbad += 1
                off += 1
            else:
                off += n
        bad += fbad
        if fbad == 0:
            funcs_ok += 1
    dt = time.time() - t0

    img.pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    exports = {}
    if hasattr(img.pe, "DIRECTORY_ENTRY_EXPORT"):
        for sym in img.pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if sym.name:
                exports[sym.name.decode()] = img.base + sym.address
    cpi = exports.get("CreatePlugInstance")

    res = {
        "file": name,
        "imagebase": hex(img.base),
        "sizeofimage": img.size,
        "pdata_entries": len(img.pdata_functions()),
        "funcs_merged": funcs,
        "funcs_decode_clean": funcs_ok,
        "funcs_decode_clean_ratio": round(funcs_ok / funcs, 4) if funcs else None,
        "insns": insns,
        "bad_positions": bad,
        "exports": sorted(exports),
        "CreatePlugInstance_va": hex(cpi) if cpi else None,
        "decode_seconds": round(dt, 2),
        "capstone": capstone.__version__,
        "pefile": pefile.__version__,
    }
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "decode_%s.json" % name.split("_")[0]), "w") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in res.items() if k != "exports"}, ensure_ascii=False))


def negative_control(name="block19091_PE.bin"):
    img = Image(os.path.join(FL, name))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False

    def bad_of(code, fb):
        bad = 0
        off = 0
        while off < len(code):
            n = 0
            for ins in md.disasm(code[off:off + 16], fb + off):
                n = ins.size
                break
            if n == 0:
                bad += 1
                off += 1
            else:
                off += n
        return bad

    funcs = []
    seen = set()
    for (b, e) in img.pdata_functions():
        rng = img.func_at(b, merge=True)
        if rng is None or rng in seen:
            continue
        seen.add(rng)
        funcs.append(rng)
    ok = 0
    bad = 0
    first_clean = None
    for fb, fe in funcs:
        code = img.read(fb, fe - fb)
        fbad = bad_of(code, fb)
        bad += fbad
        if fbad == 0:
            ok += 1
            if first_clean is None:
                first_clean = (fb, fe, code)
    fb, fe, code = first_clean
    inj = bytearray(code)
    inj[0] = 0x06
    inj_bad = bad_of(bytes(inj), fb)
    print(json.dumps({
        "baseline": {"funcs": len(funcs), "decode_clean": ok, "bad": bad},
        "injected": {"func": hex(fb), "byte0": "0x06", "bad_in_func": inj_bad},
        "after": {"decode_clean": ok - (1 if inj_bad else 0), "bad": bad + inj_bad},
    }, ensure_ascii=False))


if __name__ == "__main__":
    if "--nc" in sys.argv:
        negative_control()
    else:
        for n in ["block19091_PE.bin", "block23676_PE.bin"]:
            measure(n)
