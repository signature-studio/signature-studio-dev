#!/usr/bin/env python3
# M5 (a) 素材選定: win FLEngine_x64.dll から「純計算 leaf 小関数」候補を機械走査する。
#
#   python3 scan_pure.py --input <FLEngine_x64.dll> --out work/pure_candidates.json
#
# 方法 (M2 pescan.py の PE 部分を継承):
#   1. .pdata (RUNTIME_FUNCTION) を ground truth の関数境界として使う
#      (M2 実測: .pdata 57,816 vs Ghidra 59,009 = delta 2.02%)。
#   2. capstone で各関数を disassemble し特徴量を採る:
#      - direct call / indirect call / rip-relative メモリ参照の数
#      - 直前 ret の有無, 命令数, 使用命令クラス (整数ALUのみ / SSE / その他)
#   3. direct call の target から caller xref 数 (逆辺数) を集計。
#   4. leaf (call 0 / indirect 0) かつ xref 属さん 1..2000, size 40..1024 で
#      候補を絞り, 特徴量付きで top-N を出す。
#      → 後段で pseudo-C 相当を人手確認し bit-exact 素材 2 本を選ぶ。

import argparse
import json
import struct
import sys

try:
    import capstone
except ImportError as e:
    print(f"[scan_pure] FAIL: capstone が無い: {e}", file=sys.stderr)
    sys.exit(1)


def parse_pe_sections(data):
    pe_off, = struct.unpack("<I", data[0x3C:0x40])
    opt_off = pe_off + 24
    nsec, = struct.unpack("<H", data[pe_off + 6:pe_off + 8])
    optsz, = struct.unpack("<H", data[pe_off + 20:pe_off + 22])
    sec_off = opt_off + optsz
    sections = []
    for i in range(nsec):
        e = sec_off + i * 40
        name = data[e:e + 8].split(b"\0")[0].decode("latin1")
        vsize, vaddr, raw_size, raw_ptr = struct.unpack("<IIII", data[e + 8:e + 24])
        sections.append({"name": name, "vsize": vsize, "vaddr": vaddr,
                         "raw_size": raw_size, "raw_ptr": raw_ptr})
    return sections


def rva_to_file(sections, rva):
    for s in sections:
        if s["raw_size"] and s["vaddr"] <= rva < s["vaddr"] + s["vsize"]:
            off = rva - s["vaddr"]
            if off < s["raw_size"]:
                return s["raw_ptr"] + off
    return None


def parse_ghidra_bounds(path, image_base=0x400000):
    """Ghidra 分析結果の関数境界 (functions_csv: "FUN_00410010","ram:00410010","26")。"""
    import csv
    out = []
    with open(path) as fh:
        for row in csv.reader(fh):
            if not row or row[0] == "name" or not row[0].startswith("FUN_"):
                continue
            va = int(row[0][4:], 16)
            size = int(row[2])
            out.append((va - image_base, va - image_base + size))
        return out


def parse_pdata(data, sections):
    pe_off, = struct.unpack("<I", data[0x3C:0x40])
    opt_off = pe_off + 24
    dd = opt_off + 112
    exc_rva, exc_size = struct.unpack("<II", data[dd + 8 * 3: dd + 8 * 3 + 8])
    if not exc_rva:
        return []
    base = rva_to_file(sections, exc_rva)
    out = []
    i = 0
    while True:
        b, e, u = struct.unpack("<III", data[base + i * 12: base + i * 12 + 12])
        if b == 0:
            break
        out.append((b, e))
        i += 1
    return out


def classify(code_bytes, base=0):
    """1 関数分のマシン語を disassemble して特徴量を返す (失敗は None)。"""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    n_insn = 0
    direct = []         # rel32 call/jmp target の集合
    indirect = 0
    foot_jmp = False    # 末尾 tail-jmp (thunk)
    classes = set()
    const64 = set()
    rips = []
    stack_reads = []    # [reg - K] 形式の負オフセット (Delphi VMT header 読み)
    fss = 0             # scalar float arith (addss/mulss/subss/divss) の数
    loop = False        # 後方 jump (loop) の有無
    for ins in md.disasm(code_bytes, base):
        n_insn += 1
        if ins.mnemonic == "ret":
            foot_jmp = False
            continue
        if ins.mnemonic == "jmp":
            foot_jmp = True   # 直後が無い = 末尾
        if ins.mnemonic.startswith("call"):
            ops = ins.operands
            if ops and ops[0].type == capstone.x86.X86_OP_IMM:
                direct.append(ops[0].imm & 0xFFFFFFFFFFFF)
            else:
                indirect += 1
            continue
        if ins.mnemonic.startswith("j") and ins.operands and \
                ins.operands[0].type == capstone.x86.X86_OP_IMM:
            pass
        cls = ins.mnemonic.split()[0]
        if cls in ("addss","mulss","subss","divss","sqrtss","maxss","minss"):
            fss += 1
        if cls.startswith("j") and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM \
                and ins.operands[0].imm < ins.address:
            loop = True
        if cls.startswith("v") and cls[1:] in (
                "addps","mulps","subps","divps","movaps","movups","andps",
                "orps","xorps","cvtsi2ss","cvttsd2si","minps","maxps",
                "addsd","mulsd","subsd","divsd","movss","movsd","ucomiss",
                "comiss","cvtss2si","sqrtss", "addsd","pcmpeqd","punpck"):
            classes.add("simd/fp")
        elif cls in ("cvttss2si","divps") or "ss" in cls or "sd" in cls:
            classes.add("simd/fp")
        # 即値 (リテラル) 収集 - uint64 幅の即値
        for o in ins.operands:
            if o.type == capstone.x86.X86_OP_IMM:
                v = o.imm
                if 64 < v < (1 << 31) or v < -64:
                    pass
            elif o.type == capstone.x86.X86_OP_MEM:
                disp = o.mem.disp
                if disp < 0 and abs(disp) <= 0x200:
                    stack_reads.append(disp)
                if o.mem.base == capstone.x86.X86_REG_RIP:
                    rips.append(base + ins.address + ins.size + disp)
            if o.type == capstone.x86.X86_OP_IMM:
                if abs(o.imm) > 0xFFFF:
                    const64.add(o.imm & 0xFFFFFFFF)
    # mulb: mul tables (多バイト即値) は binutils 圏で引けないため省略。
    return {
        "n_insn": n_insn,
        "direct": sorted(set(direct)),
        "indirect": indirect,
        "classes": sorted(classes),
        "const": sorted(const64),
        "rips": sorted(rips),
        "neg_disp_reads": len(stack_reads),
        "tail_jmp": foot_jmp,
        "fss": fss,
        "loop": loop,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size-min", default="40")
    ap.add_argument("--size-max", default="1024")
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--bounds", default="ghidra",
                    help="ghidra (functions_csv) / pdata")
    ap.add_argument("--ghidra-csv", default="")
    args = ap.parse_args()

    data = open(args.input, "rb").read()
    sections = parse_pe_sections(data)
    if args.bounds == "ghidra":
        if not args.ghidra_csv:
            print("[scan_pure] FAIL: --bounds ghidra には --ghidra-csv が要る",
                  file=sys.stderr)
            sys.exit(2)
        bounds = parse_ghidra_bounds(args.ghidra_csv)
        src = "ghidra"
    else:
        bounds = parse_pdata(data, sections)
        src = "pdata"
    print(f"[scan_pure] bounds={src} functions={len(bounds)}")

    sx = int(args.size_min, 0)
    exx = int(args.size_max, 0)
    # 1) 特徴量走査
    feats = {}
    for (b, e) in bounds:
        size = e - b
        if not (sx <= size <= exx):
            continue
        fo = rva_to_file(sections, b)
        if fo is None:
            continue
        code = data[fo:fo + size]
        try:
            f = classify(code, b)
        except Exception:
            continue
        if f is None:
            continue
        feats[b] = f

    # 2) caller xref (direct call target → 参照数)
    xref = {}
    for (b, f) in feats.items():
        for t in f["direct"]:
            xref[t] = xref.get(t, 0) + 1

    # 3) leaf 純計算候補の抽出
    cands = []
    for (b, f) in feats.items():
        if f["direct"] or f["indirect"]:
            continue
        if xref.get(b, 0) < 1:
            continue
        if f["n_insn"] < 3:
            continue
        cands.append({
            "va": b, "size": None, "n_insn": f["n_insn"],
            "xrefs": xref.get(b, 0), "classes": f["classes"],
            "const": [f"0x{c:x}" for c in f["const"][:24]],
            "rips": [f"0x{r:x}" for r in f["rips"][:8]],
            "fss": f["fss"], "loop": f["loop"],
            "neg_disp_reads": f["neg_disp_reads"],
        })
    # size 補完
    bounds_map = {b: e for (b, e) in bounds}
    for c in cands:
        c["size"] = bounds_map.get(c["va"], None) - c["va"] if bounds_map.get(c["va"], None) is not None else None

    # leaf 純整数の優越多に sort (n_insn 少なめ / 使用 register 密度高)
    cands.sort(key=lambda c: (c["n_insn"], -c["xrefs"]))
    print(f"[scan_pure] leaf candidates={len(cands)}")

    out = {"input": args.input, "bounds_src": src, "functions": len(bounds),
           "size_min": sx, "size_max": exx,
           "leaf_count": len(cands), "candidates": cands[:args.limit]}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"[scan_pure] wrote {args.out}")


if __name__ == "__main__":
    sys.exit(main())
