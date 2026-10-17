#!/usr/bin/env python3
"""CreateInstance (0x1aef60) の計算ジャンプ表 (RVA 0x442000・k = 0〜16) の経路を IR に戻す (T-SH-161 #6184)。

RetDec は `cmp r8,0x10; jbe 0x1af070` (n ≤ 16 で表を引く経路) を `icmp ult %arg3, 17` の `ret` に化かす。
表の 17 件の飛び先を x86 から逆アセンブルして書込み (rcx/rax 基準の offset と幅) を取り出し、
同じ書込みを `switch i64 %arg3` の case として IR に戻す。表の飛び先にだけ入る define 9 件は IR から外す。

usage: ci_restore_jump_table.py <block24360_PE.bin> <ci.rs.ll> <ci.rj.ll>
x86 の前提 (逆アセンブルで確認): 表の飛び先に入る時点で rcx = arg1 + n・rax = arg1・
rdx = 0x0101010101010101 * (arg2 & 0xff)。各飛び先は書込みの後に ret する。
書込みは [arg1, arg1 + n) を重なりなく埋めること (外れたら exit 1)。
"""
import re, sys, struct
import pefile, capstone

ENTRY_DEF = "function_1801aef60"
TABLE_RVA = 0x442000
TABLE_N = 17
BR_OLD = "br i1 %0, label %dec_label_pc_1801af028, label %dec_label_pc_1801aef7e"
BR_NEW = "br i1 %0, label %ci_jt, label %dec_label_pc_1801aef7e"
RET_LABEL = "dec_label_pc_1801af028"
WIDTH = {"qword": 8, "dword": 4, "word": 2, "byte": 1}
REG_W = {"rdx": 8, "edx": 4, "dx": 2, "dl": 1}
MEM = re.compile(r"mov (qword|dword|word|byte) ptr \[(rcx|rax)(?: ([+-]) (0x[0-9a-f]+|\d+))?\], (rdx|edx|dx|dl)")


def case_stores(img, md, ib, k, rva):
    if k == 0:
        return []
    out, addr = [], rva
    for _ in range(12):
        ins = next(md.disasm(bytes(img[addr:addr + 15]), ib + addr))
        if ins.mnemonic == "ret":
            break
        m = MEM.fullmatch(f"{ins.mnemonic} {ins.op_str}")
        if not m:
            sys.exit(f"[restore_jt] 想定外の命令 (k={k} {addr:#x}): {ins.mnemonic} {ins.op_str}")
        w_name, base, sign, num, reg = m.groups()
        if WIDTH[w_name] != REG_W[reg]:
            sys.exit(f"[restore_jt] 幅と reg が合わない (k={k} {addr:#x}): {ins.op_str}")
        disp = 0 if num is None else int(num, 0) * (1 if sign == "+" else -1)
        # rcx は計算ジャンプの時点で arg1 + n (0x1af085 add rcx, r8)。rax は arg1 (0x1af088 mov rax, r11)
        out.append(((k if base == "rcx" else 0) + disp, WIDTH[w_name]))
        addr += ins.size
    else:
        sys.exit(f"[restore_jt] ret に届かない (k={k})")
    pos = 0
    for off, w in sorted(out):
        if off != pos:
            sys.exit(f"[restore_jt] 書込みが [0,{k}) を重なりなく埋めない (k={k}): {sorted(out)}")
        pos += w
    if pos != k:
        sys.exit(f"[restore_jt] 書込みの総幅 {pos} ≠ n {k} (k={k})")
    return out


def emit_case(k, stores):
    lines = [f"ci_jt_{k}:"]
    for i, (off, w) in enumerate(stores):
        if off == 0:
            a = "%arg1"
        else:
            a = f"%ci_jt_{k}_a{i}"
            lines.append(f"  {a} = add i64 %arg1, {off}")
        p = f"%ci_jt_{k}_p{i}"
        lines.append(f"  {p} = inttoptr i64 {a} to i{8 * w}*")
        if w == 8:
            v = "%ci_jt_v"
        else:
            v = f"%ci_jt_{k}_t{i}"
            lines.append(f"  {v} = trunc i64 %ci_jt_v to i{8 * w}")
        lines.append(f"  store i{8 * w} {v}, i{8 * w}* {p}, align 1")
    lines.append(f"  br label %{RET_LABEL}")
    return lines


def ir_stores(body):
    adds = dict(re.findall(r"%(ci_jt_\d+_a\d+) = add i64 %arg1, (\d+)", body))
    ptr_src = dict(re.findall(r"%(ci_jt_\d+_p\d+) = inttoptr i64 %(\S+?) to", body))
    out = []
    for w, p in re.findall(r"store i(\d+) %\S+, i\d+\* %(ci_jt_\d+_p\d+), align 1", body):
        a = ptr_src[p]
        off = 0 if a == "arg1" else int(adds[a])
        out.append((off, int(w) // 8))
    return sorted(out)


def check_ir(rj_path, cases):
    rj = open(rj_path).read()
    bad = []
    for k, want in cases.items():
        if k == 0:
            continue
        m = re.search(r"^ci_jt_%d:\n(.*?)(?=^ci_jt_\d+:|^%s:)" % (k, RET_LABEL), rj, re.M | re.S)
        if not m:
            bad.append(f"k={k} ラベル無し")
            continue
        got = ir_stores(m.group(1))
        if got != sorted(want):
            bad.append(f"k={k} x86 {sorted(want)} != IR {got}")
    if bad:
        sys.exit("[restore_jt] x86 と IR の書込みが一致しない: " + "; ".join(bad))
    print(f"[restore_jt] check: k=1..16 の書込み (offset, 幅) が x86 と一致 (34 件)")


def main():
    pe_path, rs_path, out_path = sys.argv[1:4]
    pe = pefile.PE(pe_path, fast_load=True)
    img = pe.get_memory_mapped_image()
    ib = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    text = open(rs_path).read()

    if text.count(BR_OLD) != 1:
        sys.exit("[restore_jt] 入口の分岐が想定と違う (RetDec の形が変わった)")
    if len(re.findall(r"^define [^@]*@%s\(" % ENTRY_DEF, text, re.M)) != 1:
        sys.exit("[restore_jt] 入口の define が 1 件でない")
    if text.count("\n" + RET_LABEL + ":") != 1:
        sys.exit("[restore_jt] 戻し先 ret ブロックが 1 件でない")

    targets = {k: struct.unpack_from("<I", img, TABLE_RVA + 4 * k)[0] for k in range(TABLE_N)}
    cases = {k: case_stores(img, md, ib, k, targets[k]) for k in range(TABLE_N)}

    head = ["ci_jt:",
            "  %ci_jt_v0 = urem i32 %arg2, 256",
            "  %ci_jt_v1 = zext i32 %ci_jt_v0 to i64",
            "  %ci_jt_v = mul i64 %ci_jt_v1, 72340172838076673",
            "  switch i64 %arg3, label %ci_jt_default [",
            f"    i64 0, label %{RET_LABEL}"]
    head += [f"    i64 {k}, label %ci_jt_{k}" for k in range(1, TABLE_N)]
    head += ["  ]", "ci_jt_default:", "  unreachable"]
    body = []
    for k in range(1, TABLE_N):
        body += emit_case(k, cases[k])

    # 表の飛び先 (case 本体の先頭) にある define は、case に吸収するので外す。外す前に IR の call 参照が無いことを確かめる。
    lines = text.split("\n")
    defs = {}
    for name in {f"function_{ib + targets[k]:x}" for k in range(1, TABLE_N)}:
        idx = [i for i, l in enumerate(lines) if re.match(r"^define [^@]*@%s\(" % re.escape(name), l)]
        if not idx:
            continue
        s = idx[0]
        e = next(i for i in range(s, len(lines)) if lines[i].startswith("}"))
        defs[name] = (s, e)
        for i, l in enumerate(lines):
            if s <= i <= e or re.match(r"^define ", l):
                continue
            if re.search(r"call [^@\n]*@%s\(" % re.escape(name), l):
                sys.exit(f"[restore_jt] 表の飛び先 define が call から参照されている: {name}")
    drop = set()
    for s, e in defs.values():
        drop.update(range(s, e + 1))
    kept = [l for i, l in enumerate(lines) if i not in drop]

    text = "\n".join(kept)
    text = text.replace(BR_OLD, BR_NEW, 1)
    text = text.replace("\n" + RET_LABEL + ":", "\n" + "\n".join(head + body) + "\n\n" + RET_LABEL + ":", 1)
    open(out_path, "w").write(text)
    print(f"[restore_jt] switch k=1..16 (書込み {sum(len(cases[k]) for k in range(1, TABLE_N))} 件・k=0 は ret) -> {out_path}")
    print(f"[restore_jt] removed define {len(defs)}: {', '.join(sorted(defs))}")
    check_ir(out_path, cases)


if __name__ == "__main__":
    main()
