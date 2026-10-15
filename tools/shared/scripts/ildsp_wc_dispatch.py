#!/usr/bin/env python3
"""ildsp WaveformColouring_CreateInstance (0x1ac470) の vcall 0x1a9e2b の dispatch 先を静的に解決する。

usage: ildsp_wc_dispatch.py [PE] [--closure <json>] [--out <json>]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
  入力 closure: tools/shared/work/raw/ildsp_closure.json (先に ildsp_closure.py を実行して作る)
  既定 out: tools/shared/work/raw/ildsp_wc_dispatch.json (gitignore)
  検算: ildsp_wc_dispatch_check.py <json> (objdump で命令を読み直し、vtable を生バイトで読む別実装)

出力する事実:
  1. CreateInstance の vptr 格納 (`lea reg,[rip+vt]` の直後の `mov [base+disp],reg`) の場所と base/disp
  2. closure 内の vcall `call qword ptr [R+disp]` (R は this の vptr を `mov R,[rcx]` で読んだ値) の場所
  3. vptr の値 (vt の RVA) と disp から求めた slot 番号、slot の値 (DIR64 の VA から RVA へ)
  4. closure 内の他の vptr 格納 (WC 以外の vtable) の件数と場所 (参考)。格納箇所ごとに 1 件
  5. 他の vptr 格納の関数への直接の call/jmp 元 (exec セクション全走査)
  6. closure の間接 call の内訳 (vcall / IAT / 画像内ポインタ / レジスタ)
"""
import sys, os, json, argparse, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR
import pefile, capstone
import ildsp_survey as S
ROOT = os.path.dirname(HERE)

CTOR_RVA = 0x1ac470


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pe", nargs="?", default=os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin"))
    ap.add_argument("--closure", default=os.path.join(ROOT, "work", "raw", "ildsp_closure.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "raw", "ildsp_wc_dispatch.json"))
    a = ap.parse_args()

    closure = json.load(open(a.closure))
    exp = [x for x in closure["exports"] if x["export"].startswith("WaveformColouring")][0]
    vt_rva = int(exp["vtable"]["rva"], 16)
    fns = sorted(int(x, 16) for x in exp["vtable"]["function_rvas"])
    fn_set = set(fns)
    assert int(exp["entry_rva"], 16) == CTOR_RVA

    pe = pefile.PE(a.pe, fast_load=True)
    img = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
    pdata = {}
    for i in range(exc.Size // 12):
        b, e, _ = struct.unpack_from("<III", img, exc.VirtualAddress + i * 12)
        pdata[b] = e
    pdata_sorted = sorted(pdata)

    def fn_end(f):
        if f in pdata:
            return pdata[f]
        return next((x for x in pdata_sorted if x > f), text.VirtualAddress + text.Misc_VirtualSize)

    def insns(lo, hi):
        return list(md.disasm(bytes(img[lo:hi]), base + lo))

    def rip_target(ins):
        m = [o.mem for o in ins.operands if o.type == capstone.x86.X86_OP_MEM]
        if not m or m[0].base != capstone.x86.X86_REG_RIP:
            return None
        return ins.address + ins.size + m[0].disp - base

    # 1. vptr 格納: lea reg,[rip+X] (X は .text 外の vtable) の直後 4 命令以内の mov [base+disp],reg
    stores = []
    other_vt_sites = []
    for f in fns:
        ins_list = insns(f, fn_end(f))
        for k, ins in enumerate(ins_list):
            if ins.mnemonic != "lea" or ins.operands[0].type != capstone.x86.X86_OP_REG:
                continue
            t = rip_target(ins)
            if t is None or t < text.VirtualAddress + text.Misc_VirtualSize:
                continue
            v0 = struct.unpack_from("<Q", img, t)[0] - base
            if not (text.VirtualAddress <= v0 < text.VirtualAddress + text.Misc_VirtualSize):
                continue
            reg = ins.operands[0].reg
            for nxt in ins_list[k + 1:k + 5]:
                if nxt.mnemonic == "mov" and len(nxt.operands) == 2 and nxt.operands[0].type == capstone.x86.X86_OP_MEM \
                        and nxt.operands[1].type == capstone.x86.X86_OP_REG and nxt.operands[1].reg == reg:
                    m = nxt.operands[0].mem
                    rec = {"site": hex(nxt.address - base), "lea_site": hex(ins.address - base), "fn": hex(f),
                           "vtable": hex(t), "base_reg": nxt.reg_name(m.base), "disp": m.disp,
                           "text": nxt.op_str}
                    if t == vt_rva:
                        stores.append(rec)
                    else:
                        other_vt_sites.append(rec)
                    break

    # fns の範囲は重なりうる (pdata の無い関数は次の pdata 先頭まで)。同じ格納箇所を複数の関数が数えるため、
    # 箇所ごとに 1 件にする (fns は昇順なので後勝ち = 最も近い関数先頭)
    stores = list({s["site"]: s for s in stores}.values())
    other_vt_sites = list({s["site"]: s for s in other_vt_sites}.values())

    # 2. vcall: call qword ptr [R+disp] (R の値は this の vptr。R は mov R,[rcx] で読む)
    vcalls = []
    for f in fns:
        ins_list = insns(f, fn_end(f))
        for k, ins in enumerate(ins_list):
            if ins.mnemonic != "call" or not ins.op_str.startswith("qword ptr [") or "rip" in ins.op_str:
                continue
            m = ins.operands[0].mem
            base_reg = ins.reg_name(m.base)
            src = None
            for prev in ins_list[:k]:
                if prev.mnemonic == "mov" and prev.operands[0].type == capstone.x86.X86_OP_REG \
                        and prev.reg_name(prev.operands[0].reg) == base_reg:
                    src = prev
            vcalls.append({"site": hex(ins.address - base), "fn": hex(f), "text": ins.op_str,
                           "base_reg": base_reg, "disp": m.disp,
                           "base_load": (src.mnemonic + " " + src.op_str) if src else None,
                           "base_load_site": hex(src.address - base) if src else None})

    # 3. slot の解決: vt + disp の qword (DIR64 の VA) を RVA に直す。disp が 8 の倍数であること
    vcalls = list({v["site"]: v for v in vcalls}.values())
    result_vcalls = []
    for v in vcalls:
        if v["disp"] % 8 != 0:
            continue
        slot = v["disp"] // 8
        slot_rva = vt_rva + 8 * slot
        val = struct.unpack_from("<Q", img, slot_rva)[0] - base
        thunk = bytes(img[val:val + 4]) == bytes([0x48, 0x8b, 0x49, 0x08])
        n_insns = sum(1 for i in insns(val, fn_end(val)) if i.mnemonic != "int3") if val in fn_set else None
        result_vcalls.append({**v, "vt_rva": hex(vt_rva), "slot": slot, "slot_rva": hex(slot_rva),
                              "target_rva": hex(val), "target_in_closure": val in fn_set,
                              "thunk": thunk, "target_insns": n_insns})

    # 間接 call の内訳 (closure の関数内・命令アドレスで重複排除。ildsp_closure.py の間接 call 数と一致させる)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    iat = {imp.address - base for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) for imp in ent.imports if imp.address}
    ind = {}
    for f in fns:
        for ins in insns(f, fn_end(f)):
            if ins.mnemonic != "call" or ins.op_str.startswith("0x"):
                continue
            op = ins.operands[0]
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                ind[ins.address] = "IAT" if ins.address + ins.size + op.mem.disp - base in iat else "画像内ポインタ"
            elif op.type == capstone.x86.X86_OP_MEM:
                ind[ins.address] = "vcall"
            else:
                ind[ins.address] = "レジスタ"
    breakdown = {k: sum(1 for v in ind.values() if v == k) for k in ("vcall", "IAT", "画像内ポインタ", "レジスタ")}

    # 他 vtable 格納の関数 (0x164740 等) と vcall の関数への直接の call/jmp 元。exec セクション全体を線形走査する
    other_fns = sorted({int(s["fn"], 16) for s in other_vt_sites} | {int(v["fn"], 16) for v in vcalls})
    callers = {f: [] for f in other_fns}
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        lo = s.VirtualAddress
        for addr, m, ops in S.sweep(md, bytes(img[lo:lo + s.Misc_VirtualSize]), base + lo):
            if (m.startswith("call") or m == "jmp") and S.is_direct(ops) and int(ops, 16) - base in callers:
                callers[int(ops, 16) - base].append(hex(addr - base))

    print("# WaveformColouring_CreateInstance の vcall dispatch 解決 (ildsp_wc_dispatch.py)")
    print(f"vtable RVA: {hex(vt_rva)} / CreateInstance: {hex(CTOR_RVA)} / closure 関数数: {len(fns)}")
    print("")
    print("## vptr 格納 (WC vtable を書く箇所)")
    for s in stores:
        print(f"  site {s['site']} (lea {s['lea_site']}, fn {s['fn']}): {s['text']} (base {s['base_reg']}, disp {s['disp']:#x})")
    print(f"  件数 {len(stores)} (WC vtable への格納は 1 件であること)")
    print("")
    print("## 他 vtable の格納 (参考・closure 内)")
    print(f"  件数 {len(other_vt_sites)} (格納箇所ごとに 1 件)")
    for s in other_vt_sites:
        print(f"  site {s['site']} (fn {s['fn']}): vtable {s['vtable']} / {s['text']} (base {s['base_reg']}, disp {s['disp']:#x})")
    print("  他 vtable 格納の関数と vcall の関数への直接の call/jmp 元 (exec セクション全走査):")
    for f in other_fns:
        print(f"    fn {hex(f)} <- {callers[f]}")
    print("")
    print("## 間接 call の内訳 (closure 70 関数)")
    print(f"  vcall {breakdown['vcall']} / IAT {breakdown['IAT']} / 画像内ポインタ {breakdown['画像内ポインタ']} / レジスタ {breakdown['レジスタ']} / 計 {sum(breakdown.values())}")
    print("")
    print("## vcall")
    for r in result_vcalls:
        print(f"  site {r['site']} (fn {r['fn']}): call {r['text']} / base {r['base_reg']} <- {r['base_load']} @ {r['base_load_site']}")
        print(f"    disp {r['disp']:#x} -> slot {r['slot']} (slot RVA {r['slot_rva']}) -> target {r['target_rva']} / in closure: {r['target_in_closure']} / thunk: {r['thunk']} / insns (int3 除く): {r['target_insns']}")

    out = {"pe": a.pe, "vt_rva": hex(vt_rva), "ctor_rva": hex(CTOR_RVA),
           "stores": stores, "other_vtable_stores": other_vt_sites,
           "direct_callers": {hex(f): callers[f] for f in other_fns},
           "indirect_breakdown": breakdown, "vcalls": result_vcalls}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
