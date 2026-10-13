#!/usr/bin/env python3
"""ildsp (block24360_PE.bin, win64 PE) の規模調査を 1 コマンドで再現する。

usage: ildsp_survey.py [PE] [--out <json>]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
  既定 out: tools/shared/work/raw/ildsp_survey.json (gitignore)

出力:
  1. 全体: .text 命令数 / SIMD 比率 / 直接・間接 call / .pdata 関数数 / IPPCODE 節の命令数
  2. export ごとの closure 規模表 (関数数・命令数・SIMD 比率・間接 call 比率)
closure = export の RVA から、.pdata の関数境界を使い direct call と direct tail jmp を辿った到達集合。
間接 call は辿らず、件数だけ数える。"""
import sys, os, json, argparse, collections, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR
import pefile, capstone
ROOT = os.path.dirname(HERE)

REG_SIMD = ("xmm", "ymm", "zmm")
X87 = ("f",)


def classify(mnem, ops):
    if any(r in ops for r in REG_SIMD):
        return "simd"
    if mnem.startswith(X87):
        return "x87"
    return "scalar"


def is_direct(ops):
    return ops.startswith("0x")


def sweep(md, data, base):
    """線形走査。デコードできないバイトは 1 byte 飛ばして続行する。"""
    out = []
    off = 0
    while off < len(data):
        got = None
        for ins in md.disasm(data[off:off + 16], base + off):
            got = ins
            break
        if got is None:
            off += 1
            continue
        out.append((got.address, got.mnemonic, got.op_str))
        off += got.size
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pe", nargs="?", default=os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "raw", "ildsp_survey.json"))
    a = ap.parse_args()

    pe = pefile.PE(a.pe, fast_load=True)
    image = pe.get_memory_mapped_image()
    secs = {s.Name.rstrip(b"\0").decode(errors="replace"): s for s in pe.sections}
    text = secs[".text"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False

    # .pdata (例外ディレクトリ) を生データで読む。pefile の DIRECTORY_ENTRY_EXCEPTION は一部しか返さない
    exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
    funcs = {}
    for i in range(exc.Size // 12):
        b, e, _ = struct.unpack_from("<III", image, exc.VirtualAddress + i * 12)
        funcs[b] = e
    fn_sorted = sorted(funcs)

    # .text 全体の線形走査
    t_lo = text.VirtualAddress
    t_hi = t_lo + text.Misc_VirtualSize
    tins = sweep(md, bytes(image[t_lo:t_hi]), t_lo)
    tot = len(tins)
    cls = collections.Counter()
    calls_d = calls_i = 0
    for addr, m, ops in tins:
        cls[classify(m, ops)] += 1
        if m.startswith("call"):
            if is_direct(ops):
                calls_d += 1
            else:
                calls_i += 1
    whole = {
        "text_instructions": tot,
        "simd": cls["simd"], "x87": cls["x87"], "scalar": cls["scalar"],
        "simd_ratio": round(cls["simd"] / max(tot, 1), 4),
        "direct_calls": calls_d, "indirect_calls": calls_i,
        "indirect_ratio": round(calls_i / max(calls_d + calls_i, 1), 4),
        "pdata_functions": len(funcs),
    }
    ipp = secs.get("IPPCODE")
    if ipp is not None:
        ilo, ihi = ipp.VirtualAddress, ipp.VirtualAddress + ipp.Misc_VirtualSize
        ii = sweep(md, bytes(image[ilo:ihi]), ilo)
        ic = collections.Counter(classify(m, o) for _, m, o in ii)
        whole["ippcode_instructions"] = len(ii)
        whole["ippcode_simd_ratio"] = round(ic["simd"] / max(len(ii), 1), 4)

    import bisect
    fcache = {}

    def owner(t):
        # t を含む .pdata 関数の先頭 (無ければ None)
        i = bisect.bisect_right(fn_sorted, t) - 1
        if i >= 0 and fn_sorted[i] <= t < funcs[fn_sorted[i]]:
            return fn_sorted[i]
        return None

    def end_of(b):
        # .pdata の終端。無ければ次の .pdata 先頭か .text 末尾
        if b in funcs:
            return funcs[b]
        i = bisect.bisect_right(fn_sorted, b)
        return fn_sorted[i] if i < len(fn_sorted) else t_hi

    def func_insns(b):
        if b not in fcache:
            fcache[b] = sweep(md, bytes(image[b:end_of(b)]), b)
        return fcache[b]

    def closure(entry):
        entry = owner(entry) or entry
        seen, stack = set(), [entry]
        ins_n = simd = dc = ic = 0
        while stack:
            f = stack.pop()
            if f in seen:
                continue
            seen.add(f)
            for addr, m, ops in func_insns(f):
                ins_n += 1
                if classify(m, ops) == "simd":
                    simd += 1
                if m.startswith("call"):
                    if is_direct(ops):
                        dc += 1
                        g = owner(int(ops, 16))
                        if g is not None:
                            stack.append(g)
                    else:
                        ic += 1
                elif m == "jmp" and is_direct(ops):
                    t = int(ops, 16)
                    g = owner(t)
                    if g is not None and g != f:
                        stack.append(g)
        return {"functions": len(seen), "instructions": ins_n,
                "simd_ratio": round(simd / max(ins_n, 1), 4),
                "direct_calls": dc, "indirect_calls": ic,
                "indirect_ratio": round(ic / max(dc + ic, 1), 4)}

    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    exports = []
    exp = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
    if exp:
        for s in exp.symbols:
            name = s.name.decode(errors="replace") if s.name else f"#{s.ordinal}"
            exports.append((name, s.address))
    table = []
    for name, rva in sorted(exports):
        c = closure(rva)
        table.append({"export": name, "entry_rva": hex(rva), **c})

    res = {"pe": a.pe, "whole": whole, "exports": table}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)

    print(f"# ildsp survey: {os.path.basename(a.pe)}")
    print(json.dumps(whole, ensure_ascii=False))
    print("| export | entry | 関数数 | 命令数 | SIMD 比 | 直接call | 間接call | 間接比 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in table:
        print(f"| {r['export']} | {r['entry_rva']} | {r['functions']} | {r['instructions']} | "
              f"{r['simd_ratio']:.1%} | {r['direct_calls']} | {r['indirect_calls']} | {r['indirect_ratio']:.1%} |")


if __name__ == "__main__":
    main()
