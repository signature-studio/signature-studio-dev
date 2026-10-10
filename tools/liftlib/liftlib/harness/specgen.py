"""specgen.py — 機械語から差分ハーネス spec の雛形を自動生成する (人手調整前提の skeleton)。

  python3 -m liftlib specgen <image.pe> <func_va_hex> [--name N]

方法 (制御フロー非追跡の線形走査):
  - 関数入口 live-in の引数 GPR (rcx/rdx/r8/r9) を buffer と見なし, レジスタの「由来 (buffer, offset)」を追跡
  - `mov r64,[b+d]` で読んだ値を後でアドレス基準に使うなら, そのフィールドはポインタ → 子 buffer
  - メモリ operand のアクセスから フィールド (offset, 型: f32/f64/u32/u8/u64) を収集 (read されるもののみ乱数化)
  - 添字付きアクセス (base+index*scale) は配列領域として buffer を 1KB 以上にする
出力: spec JSON (フィールド分布は既定値; ループ回数等の整数フィールドは手で範囲を絞ること)。
"""
import json
import re
import sys

from ..mc import MFunc, GPR_ARGS
from ..pe import Image

_F32 = {"movss", "addss", "subss", "mulss", "divss", "minss", "maxss", "sqrtss", "comiss", "ucomiss", "cvtss2sd", "cvtsi2ss"}
_F64 = {"movsd", "addsd", "subsd", "mulsd", "divsd", "minsd", "maxsd", "sqrtsd", "comisd", "ucomisd", "cvtsd2ss", "cvtsi2sd"}


def _kind(it):
    m = it.mnem.lstrip("v") if it.mnem.startswith("v") and len(it.mnem) > 3 else it.mnem
    if m in _F32:
        return "f32"
    if m in _F64:
        return "f64"
    sz = it.mem["size"]
    return {1: "u8", 2: "u16", 4: "u32", 8: "u64"}.get(sz, "bytes%d" % sz)


def gen(image, func_va, name="auto"):
    img = Image(image)
    rng = img.func_at(func_va)
    mf = MFunc(img, *rng) if rng else None
    live = mf.live_in()
    prov = {}                 # reg -> (buf, off)
    bufs = {}                 # name -> dict(fields={off: dict}, maxoff, array)
    args = []
    for k, r in enumerate(GPR_ARGS):
        if r in live:
            nm = "arg%d" % k
            prov[r] = (nm, 0)
            bufs[nm] = dict(fields={}, maxoff=0, array=False)
            args.append({"ptr": nm})
        else:
            args.append(None)
    while args and args[-1] is None:
        args.pop()
    nchild = [0]
    ptr_used = set()

    def newbuf():
        nchild[0] += 1
        nm = "p%d" % nchild[0]
        bufs[nm] = dict(fields={}, maxoff=0, array=False)
        return nm

    for va in mf.order:
        it = mf.insns[va]
        m = it.mnem
        if it.mem and it.mem["base"] in prov and not it.mem["lea"]:
            b, o = prov[it.mem["base"]]
            off = o + it.mem["disp"]
            d = bufs[b]
            if it.mem["index"]:
                d["array"] = True
            else:
                f = d["fields"].setdefault(off, dict(kind=None, read=False, write=False, size=it.mem["size"]))
                f["read"] |= bool(it.mem["read"])
                f["write"] |= bool(it.mem["write"])
                f["size"] = it.mem["size"]
                f["kind"] = f["kind"] or _kind(it)
                d["maxoff"] = max(d["maxoff"], off + it.mem["size"])
                # 64-bit pointer load: dest がポインタ
                if m == "mov" and it.mem["read"] and it.mem["size"] == 8 and it.ops[0].type == 1:
                    from ..mc import _canon_reg
                    dst = _canon_reg(it._ci, it.ops[0].reg)
                    child = d.setdefault("children", {}).get(off) or newbuf()
                    d.setdefault("children", {})[off] = child
                    prov[dst] = (child, 0)
                    f["kind"] = "ptr?"
                    continue
        # コピー / lea / add imm
        if m == "mov" and len(it.ops) == 2 and it.ops[0].type == 1 and it.ops[1].type == 1:
            from ..mc import _canon_reg
            a, bb = _canon_reg(it._ci, it.ops[0].reg), _canon_reg(it._ci, it.ops[1].reg)
            if bb in prov:
                prov[a] = prov[bb]
            else:
                prov.pop(a, None)
            continue
        if m == "lea" and it.mem and it.mem["base"] in prov and not it.mem["index"]:
            from ..mc import _canon_reg
            a = _canon_reg(it._ci, it.ops[0].reg)
            b, o = prov[it.mem["base"]]
            prov[a] = (b, o + it.mem["disp"])
            continue
        for w in it.writes:
            if w in prov and not (it.mem and it.mem["base"] == w):
                prov.pop(w, None)
    spec = dict(name=name, func="0x%x" % func_va, wasm_func="function_%x" % func_va, scenarios=200, steps=1, seed=1,
                note="specgen 雛形: ループ回数/サイズ等の整数フィールドは手で範囲を絞り, ポインタ/配列サイズを確認すること",
                vars=[], args=args, buffers={})
    gens = {"f32": {"unif": [-2, 2]}, "f64": {"unif": [-2, 2]}, "u8": {"choice": [0, 1]}, "u16": {"int": [0, 3]},
            "u32": {"int": [0, 3]}, "u64": {"int": [0, 3]}}
    names = {}
    for nm, d in bufs.items():
        size = max(d["maxoff"] + 64, 1024 if d["array"] else 128)
        fields = []
        for off in sorted(d["fields"]):
            f = d["fields"][off]
            if f["kind"] == "ptr?":
                fields.append({"off": off, "ptr": d["children"][off]})
            elif f["read"] and f["kind"] in gens:
                fields.append({"off": off, "type": f["kind"], "gen": gens[f["kind"]]})
        spec["buffers"][nm] = dict(size=size, fields=fields)
    return spec


def main(argv):
    img, va = argv[0], int(argv[1], 16)
    nm = argv[argv.index("--name") + 1] if "--name" in argv else "auto"
    print(json.dumps(gen(img, va, nm), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
