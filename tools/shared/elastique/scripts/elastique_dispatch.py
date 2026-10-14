#!/usr/bin/env python3
"""élastique (win elastique_x64.dll) の dispatch 層・IPPCODE 線形走査の外向き分岐・.reloc 照合を実測する (T-SH-10 / #152).

elastique_facts.py の追補 (同じ入力・同じ作業出力先)。依存: capstone のみ。
出力: work/elastique/dispatch.json と標準出力の要約。
  A. dispatch 層: 8 qword 単位の記録 [関数ポインタ(.data の枠) = thunk 頭, CPU クラス 0〜5 の実装 ×6, null, 次の枠]。
     thunk は `call 初期化スタブ` → `movsxd rax,[索引]` → `lea r10,[表]` → `jmp [r10+rax*8]`。
  B. IPPCODE の線形走査 (pdata に依らない・不正命令は 1 byte 飛ばす) の外向き直接分岐と、その飛び先のセクション。
  C. .reloc の DIR64 を全件照合 (絶対 8 バイトポインタの陽性対照・陰性対照)。
"""
import bisect
import collections
import json
import os
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM, Cs
from capstone.x86 import X86_REG_R10, X86_REG_RAX, X86_REG_RDI, X86_REG_RIP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elastique_facts import DEFAULT_DLL, OUT_DIR, parse_pe, pdata_funcs  # noqa: E402

STUB = 0x1803E71B0  # IPPCODE 内・非 pdata の初期化スタブ (push×4 → call → pop×4 → ret)
IDX = 0x1804AFC54   # dispatch 索引 (.data の dword)
CPU_FN = 0x1800015A0  # 索引の値を out 引数 (rdi) へ書く関数
SLOTS = 8           # 1 枠 = 8 qword


def main():
    dll = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DLL
    raw = open(dll, "rb").read()
    base, sections, image, dd = parse_pe(raw)
    assert base == 0x180000000, hex(base)
    sec = {s["name"]: s for s in sections}

    def rng(name):
        s = sec[name]
        return base + s["va"], base + s["va"] + s["vsize"]

    def sect_of(x):
        for s in sections:
            lo = base + s["va"]
            if lo <= x < lo + max(s["vsize"], s["rawsize"]):
                return s["name"]
        return "イメージ外"

    ipp, txt = rng("IPPCODE"), rng(".text")
    inside = lambda x, r: r[0] <= x < r[1]  # noqa: E731
    funcs = sorted(pdata_funcs(image, base, dd))
    fstarts = [a for a, _ in funcs]
    pd_end = dict(funcs)

    def pdata_of(x):
        i = bisect.bisect_right(fstarts, x) - 1
        if i >= 0 and x < pd_end[fstarts[i]]:
            return fstarts[i]
        return None

    def pdstatus(x):
        if x in pd_end:
            return "pdata先頭"
        return "pdata途中" if pdata_of(x) is not None else "pdata外"

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    def linear(lo, hi):
        """objdump 相当の線形走査。capstone は不正命令で停止するので、そこで 1 byte 飛ばして続ける。"""
        addr = lo
        while addr < hi:
            last = addr
            for ins in md.disasm(bytes(image[addr - base:hi - base]), addr):
                yield ins
                last = ins.address + ins.size
            if last >= hi:
                return
            addr = last + 1

    def is_rip_mem(op):
        return op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP

    def rip_target(ins, op):
        return ins.address + ins.size + op.mem.disp

    # ---- A. dispatch 層 ---------------------------------------------------
    sites = []
    for ins in linear(txt[0], txt[1]):
        ops = ins.operands
        if ins.mnemonic == "movsxd" and len(ops) == 2 and is_rip_mem(ops[1]) and rip_target(ins, ops[1]) == IDX:
            sites.append(ins.address)
    thunks = []
    for a in sites:
        h = a - 0x10
        w = list(md.disasm(bytes(image[a - base:a - base + 32]), a, count=3))
        assert image[h - base] == 0xE8 and h + 5 + struct.unpack_from("<i", image, h - base + 1)[0] == STUB, hex(h)
        assert w[1].mnemonic == "lea" and w[1].operands[0].reg == X86_REG_R10 and is_rip_mem(w[1].operands[1]), hex(a)
        tbl = rip_target(w[1], w[1].operands[1])
        jop = w[2].operands[0]
        assert w[2].mnemonic == "jmp" and jop.type == CS_OP_MEM and jop.mem.base == X86_REG_R10 \
            and jop.mem.index == X86_REG_RAX and jop.mem.scale == 8, hex(a)
        thunks.append({"head": h, "site": a, "table": tbl, "slot": tbl - 8})
    head_set = {t["head"] for t in thunks}
    slot_map = {t["slot"]: t for t in thunks}
    for t in thunks:
        assert struct.unpack_from("<Q", image, t["slot"] - base)[0] == t["head"], hex(t["slot"])
    all_recs_ok = all(struct.unpack_from("<Q", image, t["table"] - base + 48)[0] == 0 for t in thunks)

    # 索引の値域: CPU_FN の [rdi] への store (rdi = out 引数 = [rsp+0x28])
    f_cpu = pdata_of(CPU_FN)
    assert f_cpu == CPU_FN, hex(f_cpu or 0)
    out_stores = []
    for ins in md.disasm(bytes(image[f_cpu - base:pd_end[f_cpu] - base]), f_cpu):
        ops = ins.operands
        if ins.mnemonic == "mov" and ops and ops[0].type == CS_OP_MEM and ops[0].mem.base == X86_REG_RDI \
                and ops[0].mem.disp == 0 and ops[0].mem.index == 0:
            out_stores.append({"at": hex(ins.address), "op": ins.op_str})
    vals = set()
    for s in out_stores:
        try:
            vals.add(int(s["op"].split(",")[-1].strip(), 0))
        except ValueError:
            pass
    index_writes = []
    for name, r in (("IPPCODE", ipp), (".text", txt)):
        for ins in linear(r[0], r[1]):
            ops = ins.operands
            if ins.mnemonic == "mov" and ops and is_rip_mem(ops[0]) and rip_target(ins, ops[0]) == IDX:
                index_writes.append({"at": hex(ins.address), "in": name, "op": ins.op_str})
                if ops[1].type == CS_OP_IMM:
                    vals.add(ops[1].imm)
    index_domain = sorted(vals)
    assert index_domain == list(range(6)), index_domain

    variant_pairs = []  # (thunk head, j, target)
    recs = {}
    for t in thunks:
        rec = []
        for j in range(SLOTS):
            v = struct.unpack_from("<Q", image, t["table"] - base + 8 * j)[0]
            rec.append(v)
            if j in index_domain and v:
                variant_pairs.append((t["head"], j, v))
        recs[hex(t["head"])] = rec
    known = sorted(set(fstarts) | head_set | {T for _, _, T in variant_pairs})

    def body_end(x):
        if x in pd_end:
            return pd_end[x]
        i = bisect.bisect_right(known, x)
        cap = x + 0x1000
        if i < len(known):
            return min(known[i], cap)
        return cap

    def body_info(T):
        lo, hi = T, body_end(T)
        ipp_calls, text_calls = set(), set()
        for ins in md.disasm(bytes(image[lo - base:hi - base]), lo):
            if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == CS_OP_IMM:
                tg = ins.operands[0].imm
                if inside(tg, ipp):
                    ipp_calls.add(tg)
                elif inside(tg, txt):
                    text_calls.add(tg)
        return {"section": sect_of(T), "pdata": pdstatus(T), "end": hi,
                "ipp_direct_targets": len(ipp_calls), "text_direct_targets": sorted(text_calls)}

    tinfo = {}
    for _, _, T in variant_pairs:
        if T not in tinfo:
            tinfo[T] = body_info(T)
    hop2 = {}
    for ti in list(tinfo.values()):
        for T in ti["text_direct_targets"]:
            if T not in hop2 and T not in tinfo:
                hop2[T] = body_info(T)

    # 呼出し元: 枠 (.data の関数ポインタ) と thunk 頭への参照 (線形走査)
    slot_refs = collections.Counter()
    slot_callers = set()
    head_refs = collections.Counter()
    stub_calls = collections.Counter()
    for name, r in (("IPPCODE", ipp), (".text", txt)):
        for ins in linear(r[0], r[1]):
            ops = ins.operands
            if ins.mnemonic in ("call", "jmp") and ops and ops[0].type == CS_OP_IMM:
                if ops[0].imm == STUB:
                    stub_calls[name] += 1
                if ops[0].imm in head_set:
                    head_refs[(name, "直接" + ins.mnemonic)] += 1
            for op in ops:
                if is_rip_mem(op):
                    tg = rip_target(ins, op)
                    if tg in slot_map:
                        slot_refs[(name, ins.mnemonic)] += 1
                        if name == ".text":
                            slot_callers.add(pdata_of(ins.address) or ins.address)
                    if tg in head_set:
                        head_refs[(name, "rip-" + ins.mnemonic)] += 1
                elif op.type == CS_OP_IMM and op.imm in head_set and ins.mnemonic not in ("call", "jmp"):
                    head_refs[(name, "即値")] += 1

    # ---- B. IPPCODE の線形走査 -------------------------------------------
    lin_out = []
    lin_ind = collections.Counter()
    lin_rip = 0
    for ins in linear(ipp[0], ipp[1]):
        ops = ins.operands
        if ins.mnemonic in ("call", "jmp") and ops:
            if ops[0].type == CS_OP_IMM:
                if not inside(ops[0].imm, ipp):
                    lin_out.append({"src": hex(ins.address), "tgt": hex(ops[0].imm),
                                    "src_pdata": pdstatus(ins.address), "tgt_section": sect_of(ops[0].imm)})
            else:
                lin_ind[ins.mnemonic + ("_mem" if ops[0].type == CS_OP_MEM else "_reg")] += 1
        for op in ops:
            if is_rip_mem(op) and inside(rip_target(ins, op), ipp):
                lin_rip += 1

    # ---- C. .reloc DIR64 照合 ------------------------------------------
    e_lfanew = struct.unpack_from("<I", raw, 0x3C)[0]
    rva, size = struct.unpack_from("<II", raw, e_lfanew + 24 + 112 + 5 * 8)
    dir64 = collections.Counter()
    slot_dir64 = 0
    head_dir64 = 0
    total = 0
    off = 0
    while off < size:
        page, blk = struct.unpack_from("<II", image, rva + off)
        for k in range((blk - 8) // 2):
            w = struct.unpack_from("<H", image, rva + off + 8 + 2 * k)[0]
            if w >> 12 == 10:  # IMAGE_REL_BASED_DIR64
                tg_rva = page + (w & 0xFFF)
                v = struct.unpack_from("<Q", image, tg_rva)[0]
                total += 1
                if base + tg_rva in slot_map:
                    slot_dir64 += 1
                if v in head_set:
                    head_dir64 += 1
                dir64["IPPCODE" if inside(v, ipp) else (".text" if inside(v, txt) else sect_of(v))] += 1
        off += blk

    tgt_summary = collections.Counter()
    for T, ti in tinfo.items():
        tgt_summary[(ti["section"], ti["pdata"], "IPPCODEへ直接分岐あり" if ti["ipp_direct_targets"] else "なし")] += 1

    summary = {
        "A_dispatch": {
            "thunks": len(thunks),
            "thunk_movsxd_sites_linear": len(sites),
            "index_domain": index_domain,
            "index_writes": index_writes,
            "cpu_fn_out_stores_rdi": out_stores,
            "record_layout_null_slot6_all_zero": all_recs_ok,
            "stub_calls_by_section": dict(stub_calls),
            "slot_refs_by_section_mnemonic": {f"{k[0]} {k[1]}": v for k, v in slot_refs.items()},
            "slot_caller_funcs_text": len(slot_callers),
            "head_refs": {f"{k[0]} {k[1]}": v for k, v in head_refs.items()},
            "reach_variant_slots": len(variant_pairs),
            "reach_variant_distinct_targets": len(tinfo),
            "reach_variant_targets_by_section_pdata_ipp": {" | ".join(k): v for k, v in tgt_summary.items()},
            "hop2_distinct_targets": len(hop2),
            "hop2_by_section_pdata_ipp": {" | ".join(k): v for k, v in collections.Counter(
                (h["section"], h["pdata"], "IPPCODEへ直接分岐あり" if h["ipp_direct_targets"] else "なし")
                for h in hop2.values()).items()},
        },
        "B_ipp_linear": {
            "linear_out_total": len(lin_out),
            "linear_out_by_tgt_section": dict(collections.Counter(x["tgt_section"] for x in lin_out)),
            "linear_out_by_src_pdata": dict(collections.Counter(x["src_pdata"] for x in lin_out)),
            "linear_ipp_indirect": dict(lin_ind),
            "linear_rip_refs_ipp_to_ipp": lin_rip,
        },
        "C_reloc": {"dir64_total": total, "dir64_target_section": dict(dir64),
                    "dir64_at_slots": slot_dir64, "dir64_value_is_thunk_head": head_dir64},
    }
    out = {"file": os.path.basename(dll), "summary": summary, "linear_out_list": lin_out,
           "records": {k: [hex(x) if x else "0" for x in v] for k, v in recs.items()},
           "variant_targets": {hex(k): dict(v, text_direct_targets=[hex(x) for x in v["text_direct_targets"]])
                               for k, v in tinfo.items()},
           "hop2_targets": {hex(k): dict(v, text_direct_targets=[hex(x) for x in v["text_direct_targets"]])
                            for k, v in hop2.items()}}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "dispatch.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for t in thunks[:2]:
        print("thunk", hex(t["head"]), "slot", hex(t["slot"]), "table", hex(t["table"]))
        for j, v in enumerate(recs[hex(t["head"])]):
            if v and j in index_domain:
                ti = tinfo[v]
                print("  j=%d %s %s %s ipp_direct=%d text_direct=%s" % (
                    j, hex(v), ti["section"], ti["pdata"], ti["ipp_direct_targets"],
                    [(hex(x), hop2[x]["section"], hop2[x]["pdata"], hop2[x]["ipp_direct_targets"])
                     for x in ti["text_direct_targets"]]))


if __name__ == "__main__":
    main()
