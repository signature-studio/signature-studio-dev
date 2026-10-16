#!/usr/bin/env python3
"""PY-183 (#3288): 0x1051720 の 10519c6 枝 (cur と new の表示枝) の副作用を PE 上で再照合する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py183_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
REPORT_PY183.md の結論 (リテラル全文・呼出し辺・分岐条件・書込み先・ac の読出し) を PE から照合する。
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
SECS = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
        for s in PEF.sections]
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

LITERALS = [
    (0x1051BF0, " is waiting for pickup: "),
    (0x1051C30, "%.2f"),
    (0x1051C48, "%"),
    (0x1051C58, " "),
    (0x1051C68, " < "),
    (0x1051C7C, " > "),
    (0x1050650, " - "),
    (0x1050664, "Omni - "),
    (0x1050680, "Time stretch"),
    (0x1050978, "Unknown event"),
    (0x10509A0, " (#"),
    (0x10509B4, ")"),
    (0x11F13C4, "cents"),
    (0x11F13DC, "cent"),
    (0x11F13F4, "%d %s"),
    (0x11F140C, "+"),
]

CALLS = [
    (0x10519E0, "0x104f580"),
    (0x10519F7, "0x414c70"),
    (0x1051A11, "0x104d2b0"),
    (0x1051A27, "0x104d2b0"),
    (0x1051A3A, "0x414e70"),
    (0x1051A7E, "0x43dd60"),
    (0x1051A95, "0x414c70"),
    (0x1051AE0, "0x414da0"),
    (0x1051B25, "0x414da0"),
    (0x1051B3E, "0x11f1a20"),
    (0x105183D, "0xf82a10"),
    (0xF82A58, "0xf829c0"),
    (0xF82AA4, "0xf829c0"),
    (0xF82B3E, "0xf829c0"),
    (0xF82B62, "0xf829c0"),
    (0x1051965, "0x11f1a20"),
    (0x11F1A33, "0x4232e0"),
    (0x11F1A42, "0x4133f0"),
    (0x11F1A55, "0x423980"),
    (0x11F1A61, "0xbd68e0"),
    (0xBD691D, "0x666780"),
    (0x104D562, "0x11f12c0"),
    (0x104F7A9, "0x414c70"),
    (0x104FA21, "0x40fe90"),
    (0x104FA41, "0x8da350"),
    (0x11F134D, "0x43dd60"),
]

FAILS = []


def v2o(va):
    rva = va - BASE
    for vaddr, vsz, praw, rsz in SECS:
        if vaddr <= rva < vaddr + max(vsz, rsz):
            return praw + (rva - vaddr)
    return None


def ins_at(va):
    o = v2o(va)
    for ins in MD.disasm(RAW[o:o + 16], va, 1):
        return ins
    return None


def rip_target(va):
    ins = ins_at(va)
    if ins is None or "rip" not in ins.op_str:
        return None
    part = ins.op_str.split("rip")[1].strip()
    sign = 1 if part[0] == "+" else -1
    disp = int(part[1:].split("]")[0].strip(), 16)
    return ins.address + ins.size + sign * disp


def u16z(va, n=64):
    o = v2o(va)
    out = []
    for i in range(0, n * 2, 2):
        c = RAW[o + i:o + i + 2]
        if c == b"\x00\x00":
            break
        out.append(c.decode("utf-16-le"))
    return "".join(out)


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def mov_stores(lo, hi):
    out = []
    va = lo
    while va < hi:
        ins = ins_at(va)
        if ins is None:
            va += 1
            continue
        dst = ins.op_str.split(",")[0]
        if ins.mnemonic == "mov" and "ptr [" in dst and "[rbp" not in dst and "[rsp" not in dst:
            out.append(hex(va))
        va += ins.size
    return out


def main():
    for va, want in LITERALS:
        got = u16z(va)
        check(f"literal {hex(va)} = {got!r}", got == want, f"(want {want!r})")
    for va, target in CALLS:
        ins = ins_at(va)
        ok = ins is not None and ins.mnemonic == "call" and ins.op_str == target
        check(f"call {hex(va)} -> {target}", ok, f"({ins.mnemonic} {ins.op_str})" if ins else "")
    check("0x1051720 bb 初期値 0xff", ins_at(0x105180D).op_str == "byte ptr [rbp + 0xbb], 0xff")
    check("0xff 経路の入口 (0x1051849 jne 0x1051909)", ins_at(0x1051849).op_str == "0x1051909")
    check("0x105182a lea r9, [rbp+0xac] (&ac を f82a10 へ渡す)",
          ins_at(0x105182A).mnemonic == "lea" and ins_at(0x105182A).op_str == "r9, [rbp + 0xac]")
    check("f82a10 が r9 (&ac) を [rbp+0xa8] に保存 (0xf82a24)",
          ins_at(0xF82A24).op_str == "qword ptr [rbp + 0xa8], r9")
    check("f82a10 の r8b≠0 不一致 return (0xf82a49 jne 0xf82b69)", ins_at(0xF82A49).op_str == "0xf82b69")
    check("f829c0 の bb 書込み (0xf829cb byte [rax], dl)", ins_at(0xF829CB).op_str == "byte ptr [rax], dl")
    check("f829c0 の ac 書込み (0xf829e0 ac←0 / 0xf82a01 ac←(v>>8&0xff)-1)",
          ins_at(0xF829E0).op_str == "dword ptr [rax], 0" and ins_at(0xF82A01).op_str == "dword ptr [rax], r8d")
    check("f82a10 本体の ac 書込み (0xf82acd ac←0) と bb 書込み (0xf82ada bb←0)",
          ins_at(0xF82ACD).op_str == "dword ptr [rax], 0" and ins_at(0xF82ADA).op_str == "byte ptr [rax], 0")
    check("0x104f580..0x1050600 の mov store (rbp/rsp 以外) は 0x1050540 の 1 件 (0x16bb13c)",
          mov_stores(0x104F580, 0x1050600) == ["0x1050540"], str(mov_stores(0x104F580, 0x1050600)))
    check("10519c6 枝 0x10519c6..0x1051b74 の mov store は rbp/rsp 相対のみ",
          mov_stores(0x10519C6, 0x1051B74) == [], str(mov_stores(0x10519C6, 0x1051B74)))
    stores = []
    va = 0x1051909
    while va < 0x105193C:
        ins = ins_at(va)
        if "rbp + 0xac" in ins.op_str:
            stores.append((hex(va), ins.mnemonic, ins.op_str))
        va += ins.size
    check("0xff 経路 0x1051909..0x105193c に ac (rbp+0xac) の参照が無い (読出しは 0x105193c)",
          stores == [], str(stores))
    ins = ins_at(0x105193C)
    check("0x105193c が ac を読む (movsxd rcx, dword ptr [rbp + 0xac])",
          ins.mnemonic == "movsxd" and ins.op_str == "rcx, dword ptr [rbp + 0xac]")
    ac_writes = []
    va = 0x1051720
    while va < 0x1051B44:
        ins = ins_at(va)
        if ins.mnemonic == "mov" and ins.op_str.startswith("dword ptr [rbp + 0xac], "):
            ac_writes.append(hex(va))
        va += ins.size
    check("0x1051720 本体内の ac への直接書込みは bb==0 経路の 0x1051857 と 0x10518b2 の 2 箇所のみ",
          ac_writes == ["0x1051857", "0x10518b2"], str(ac_writes))
    check("0x105194b je 0x10519c6 (sign == ac で 10519c6 枝)",
          ins_at(0x105194B).op_str == "0x10519c6")
    check("0x1051a9a/0x1051aa0 cur<new の比較は int (cmp [rbp+0xbc], ebx; jge)",
          ins_at(0x1051A9A).op_str == "dword ptr [rbp + 0xbc], ebx"
          and ins_at(0x1051AA0).op_str == "0x1051ae7")
    check("0x1051a41 jne 0x1051a9a (wstring 不一致)", ins_at(0x1051A41).op_str == "0x1051a9a")
    check("0x11f1a20 の表示先 lea rcx -> 0x16bd1a0", rip_target(0x11F1A38) == 0x16BD1A0)
    check("0x11f1a20 のフラグ mov [rip] -> 0x16bd1a8 (sil)", rip_target(0x11F1A47) == 0x16BD1A8)
    check("0xbd68e0 フラグ表 lea -> 0x16b6dcc (cmp byte [r8+id])",
          rip_target(0xBD68E7) == 0x16B6DCC and rip_target(0xBD68F5) == 0x16B6DCC)
    check("0xbd68e0 イベント先 mov rax,[rip] -> 0x16b6e00", rip_target(0xBD6901) == 0x16B6E00)
    check("0x104f580 chan 範囲 cmp eax,0x10000000 / jb 0x104f75a",
          ins_at(0x104F714).op_str == "eax, 0x10000000" and ins_at(0x104F719).op_str == "0x104f75a")
    check("0x104f580 chan==0xfff 分岐 (jne 0x1050532)", ins_at(0x104F7B6).op_str == "0x1050532")
    check("0x104f580 低位 4 → 0x104fa17 (je 0x104fa17)", ins_at(0x104F842).op_str == "0x104fa17")
    check("0x104fa17 の Time stretch 判定 cmp [rbx+0x160], 5",
          ins_at(0x104FA2A).op_str == "dword ptr [rbx + 0x160], 5")
    check("0x104d2b0 低位 4 → 0x104d55b (je 0x104d55b)", ins_at(0x104D3AE).op_str == "0x104d55b")
    check("0x11f12c0 の |v|==1 分岐 (je 0x11f1305)", ins_at(0x11F12F1).op_str == "0x11f1305")
    check("0x11f12c0 の符号 '+' 分岐 (test eax,eax; jle 0x11f1370)",
          ins_at(0x11F1357).op_str == "0x11f1370")
    check("0x11f12c0 の書式呼出し第 4 引数 r9d=1", ins_at(0x11F1347).op_str == "r9d, 1")
    check("0x1050546 の判定が 0x1050540 の store と同番地 (0x16bb13c)",
          rip_target(0x1050540) == 0x16BB13C and rip_target(0x1050546) == 0x16BB13C)
    format_checks()
    spec_checks()
    round_checks()
    desc_checks()
    desc_text_checks()
    typecheck_checks()
    pct_fmt_checks()
    round_facts_checks()
    print(f"summary: {'OK' if not FAILS else str(len(FAILS)) + ' FAIL'}")
    return 1 if FAILS else 0


def format_checks():
    # PY-192: 書式エンジン 0x43dde0 の変換指定子の分岐と、0x43aa10(key, 8) の 16 進出力
    check("0x43dd60 が 0x43dd90 を呼ぶ (0x43dd77)", ins_at(0x43DD77).op_str == "0x43dd90")
    check("0x43dd90 が 0x43dde0 を呼ぶ (0x43dda5)", ins_at(0x43DDA5).op_str == "0x43dde0")
    check("0x43dde0 が 0x43e240 (書式本体) を呼ぶ 0x43dc00 経路 (0x43de79 call 0x43dc00)",
          ins_at(0x43DE79).op_str == "0x43dc00" and ins_at(0x43DC22).op_str == "0x43e240")
    check("0x43e240 の変換指定子 'D' (0x44) → 0x43eaa7 (je)", ins_at(0x43EA91).op_str == "0x43eaa7")
    check("0x43eaa7 の 'D' が符号付き整数 0x43a7e0 を呼ぶ", ins_at(0x43EAB4).op_str == "0x43a7e0")
    check("0x43e240 の 'U' (0x55) → 0x43eabb (je) → 0x43a850 (符号なし)",
          ins_at(0x43EA9A).op_str == "0x43eabb" and ins_at(0x43EAC8).op_str == "0x43a850")
    check("0x43e240 の 'X' (0x58) → 0x43eacf (jmp 0x43eaa5) → 0x43aa10 (xor r8: 最小桁 0)",
          ins_at(0x43EAA5).op_str == "0x43eacf" and ins_at(0x43EADF).op_str == "0x43aa10"
          and ins_at(0x43EADC).op_str == "r8, r8")
    check("0x43e240 の 'F' 系: 0x43ecb5 が精度 0x12 で 0x43fce0 を呼ぶ (0x43ece7)",
          ins_at(0x43ECC6).op_str == "r9b, 2" and ins_at(0x43ECC9).op_str == "dword ptr [rsp + 0x20], 0x12"
          and ins_at(0x43ECE7).op_str == "0x43fce0")
    check("0x43a7e0 の符号 flag (setl r9b, 0x43a7fa) を 0x43a3f0 の r8 に渡す (0x43a803)",
          ins_at(0x43A7FA).mnemonic == "setl" and ins_at(0x43A803).op_str == "r8d, r9d")
    check("0x43a3f0 が '-' (0x2d) を書く (0x43a48c)", ins_at(0x43A48C).op_str == "word ptr [r8], 0x2d")
    check("0x43aa10 の pad 文字 0x30 (0x43aa37) と 0x43a890 呼出し (0x43aa41)",
          ins_at(0x43AA37).op_str == "word ptr [rsp + 0x20], 0x30" and ins_at(0x43AA41).op_str == "0x43a890")
    check("0x1050566 mov r8d, 8 → 0x105056c call 0x43aa10 (0x104f580 の 16 進 8 桁)",
          ins_at(0x105056C).op_str == "0x43aa10" and ins_at(0x1050566).op_str == "r8d, 8")
    check("0x43a890 の桁表 (word, 0x43a920) = '0123456789ABCDEF'",
          u16z(rip_target(0x43A920), 16) == "0123456789ABCDEF")
    check("0x43a890 の 2 桁表 (dword, 0x43a900) の [0x0a] = '0A' と [0xff] = 'FF'",
          u16z(rip_target(0x43A900) + 4 * 0x0A, 2) == "0A" and u16z(rip_target(0x43A900) + 4 * 0xFF, 2) == "FF")


def spec_checks():
    # #4481 (PY-311): 書式 0x43e240 の kind 9 の 'S' 分岐・'G'/'E' の精度 clamp・第 5〜7 引数の流れ
    check("0x43e240 の kind 9 (文字列) が 'S' 分岐 0x43eb1c へ (0x43e993・0x43e9c0)",
          ins_at(0x43E993).op_str == "0x43eb1c" and ins_at(0x43E9C0).op_str == "0x43eb1c")
    check("0x43eb1c が spec 'S' (0x53) を比較し、外れると 0x43eb7e (0x43eb24)",
          ins_at(0x43EB1C).op_str == "word ptr [rbp + 0x16a], 0x53" and ins_at(0x43EB24).op_str == "0x43eb7e")
    check("'S' 分岐の 1 文字化: al==2 は byte 0x414890 (0x43eb39), 他は word 0x414890 (0x43eb4f)",
          ins_at(0x43EB26).op_str == "al, 2" and ins_at(0x43EB31).op_str == "dx, byte ptr [rbp + 0xb0]"
          and ins_at(0x43EB39).op_str == "0x414890" and ins_at(0x43EB4F).op_str == "0x414890")
    check("'S' 分岐の文字列ポインタ取得 0x414850 (0x43eb5b) → 0x43eb71 call 0x43dfd0",
          ins_at(0x43EB5B).op_str == "0x414850" and ins_at(0x43EB71).op_str == "0x43dfd0")
    check("'S' 以外は 0x43eb7e で xor ecx → call 0x43db50 (0x43eb88) で r8d = [rbp+0x5c] を渡す",
          ins_at(0x43EB84).op_str == "r8d, dword ptr [rbp + 0x5c]" and ins_at(0x43EB88).op_str == "0x43db50")
    check("'G'/'E' の精度 clamp: 0x43eb9e が 'G' (0x47)・0x43eba8 が 'E' (0x45)",
          ins_at(0x43EB9E).op_str == "word ptr [rbp + 0x16a], 0x47" and ins_at(0x43EBA8).op_str == "word ptr [rbp + 0x16a], 0x45")
    check("'G'/'E' の clamp 値 0xf (0x43ebbb) / 他の clamp 値 2 (0x43ebd0)",
          ins_at(0x43EBBB).op_str == "dword ptr [rbp + 0x16c], 0xf" and ins_at(0x43EBD0).op_str == "dword ptr [rbp + 0x16c], 2")
    check("spec 'M' (0x4d) 分岐 0x43ebda が 7 番目の引数の byte [+9] を精度へ入れる (0x43ebe4・0x43ebeb・0x43ebf0)",
          ins_at(0x43EBDA).op_str == "word ptr [rbp + 0x16a], 0x4d" and ins_at(0x43EBE4).op_str == "rcx, qword ptr [rbp + 0x1d0]"
          and ins_at(0x43EBEB).op_str == "rcx, byte ptr [rcx + 9]" and ins_at(0x43EBF0).op_str == "dword ptr [rbp + 0x16c], ecx")
    check("0x43dd60 と 0x43dd90 は r9 を書かない (第 4 引数は 0x43dde0 まで素通し)", not any(
        (ins_at(va) is not None and ins_at(va).op_str.split(",")[0].strip() == "r9d") or
        (ins_at(va) is not None and ins_at(va).op_str.split(",")[0].strip() == "r9")
        for va in range(0x43DD60, 0x43DDB3)))
    check("0x43dde0 が r9 を rbx に保存 (0x43de11) し、6 番目 [rsp+0x28] に rbx を渡す (0x43de5c)",
          ins_at(0x43DE11).op_str == "rbx, r9" and ins_at(0x43DE5C).op_str == "qword ptr [rsp + 0x28], rbx")
    check("0x43dc00 が 0x43e240 の 6 番目を [rsp+0x68] → [rsp+0x28] で渡す (0x43dc0e・0x43dc13)",
          ins_at(0x43DC0E).op_str == "rax, qword ptr [rsp + 0x68]" and ins_at(0x43DC13).op_str == "qword ptr [rsp + 0x28], rax")
    check("0x43dde0 の 7 番目 [rbp+0x20b0] を 0x43dc00 へ渡す (0x43de61・0x43de68)",
          ins_at(0x43DE61).op_str == "rcx, qword ptr [rbp + 0x20b0]" and ins_at(0x43DE68).op_str == "qword ptr [rsp + 0x30], rcx")
    check("0x43dd6b と 0x43ddc4 の lea は第 5 引数に slot 0x15ec3b0 の address を置く",
          rip_target(0x43DD6B) == 0x15EC3B0 and rip_target(0x43DDC4) == 0x15EC3B0)
    check("slot 0x15ec3b0 は .bss (SizeOfRawData 0)・PE 上に初期値の実体無し",
          section_of(0x15EC3B0).Name.rstrip(b"\0") == b".bss" and section_of(0x15EC3B0).SizeOfRawData == 0)
    check("0x43dfd0 は r9d == -1 のとき 0x413680 で NUL 終端長を求める (0x43dffb・0x43e000)",
          ins_at(0x43DFF7).op_str == "r9d, -1" and ins_at(0x43E000).op_str == "0x413680")
    check("0x43eb71 は 'S' 文字列を r9d = -1 (NUL 終端まで) で 0x43dfd0 へ渡す (0x43eb6d)",
          ins_at(0x43EB6D).op_str == "r9d, 0xffffffff")
    check("0x414850 は rcx 非 0 ならそれを返し、0 なら [0x13a8040]+0x10 (0x414858・0x41485f)",
          ins_at(0x414858).op_str.startswith("rax, qword ptr [rip") and ins_at(0x41485F).op_str == "rax, [rax + 0x10]")
    check("0x13a8040 の静的内容は .text (0x413fec) を指し、文字列ではない (fallback の先は PE 上で確定できない)",
          rip_target(0x414858) == 0x13A8040 and section_of(0x13A8040).Name.rstrip(b"\0") == b".data")
    reads = []
    va = 0x43E240
    while va < 0x43F1D0:
        ins = ins_at(va)
        if ins is None:
            break
        if "rbp + 0x1c8]" in ins.op_str:
            reads.append(hex(va))
        va += ins.size
    check("0x43e240 の 6 番目 [rbp+0x1c8] は 0x43e2db の 1 箇所だけで読まれる (ebx = flag + 1)",
          reads == ["0x43e2db"] and ins_at(0x43E2DB).op_str == "ebx, dword ptr [rbp + 0x1c8]"
          and ins_at(0x43E2E1).op_str == "ebx, 1", str(reads))


def round_checks():
    # PY-330 (#4478): %.2f の経路 0x440d30 (r8b=0 の枝) の 18 桁正規化と BCD 化
    check("0x441380 が r8b=0 で 0x440d30 を呼ぶ (0x44139e〜0x4413a2)",
          ins_at(0x441396).op_str == "r8b, r8b" and ins_at(0x4413A2).op_str == "0x440d30")
    check("0x43ecb5 の %.2f 系は精度 0x12 を 0x43fce0 へ渡す (0x43ecc9 / 0x43ece7)",
          ins_at(0x43ECC9).op_str == "dword ptr [rsp + 0x20], 0x12" and ins_at(0x43ECE7).op_str == "0x43fce0")
    check("0x440d30 の指数抽出 (0x440e42〜0x440e5d) と 0x40ef40 呼出し (0x440e7a)",
          ins_at(0x440E72).op_str == "edx, 0x12" and ins_at(0x440E7A).op_str == "0x40ef40")
    check("0x440d30 の 0x40c660 呼出し (0x440e7f) は cvtsd2si rax, xmm0 (0x40c660)",
          ins_at(0x440E7F).op_str == "0x40c660" and ins_at(0x40C660).mnemonic == "cvtsd2si"
          and ins_at(0x40C660).op_str == "rax, xmm0")
    check("0x440d30 の 1e18 比較 ucomisd (0x440e93 → 0x13ab318 = 1e18)",
          ins_at(0x440E93).mnemonic == "ucomisd" and rip_target(0x440E93) == 0x13AB318
          and struct_double(0x13AB318) == 1e18)
    check("0x440d30 の 10 による除算 (0x440e9d cvtsi2sd → 0x13ab320 = 10)",
          rip_target(0x440E9D) == 0x13AB320 and struct_int(0x13AB320) == 10)
    check("0x440d30 の繰上げ (0x440eb7 add word [rax],1) は 1e18 以上のときだけ (0x440ea5 divsd)",
          ins_at(0x440EAA).mnemonic == "divsd" and ins_at(0x440EB3).op_str == "rax, qword ptr [rbx + 0x30]")
    check("0x440d30 は精度 18 桁固定 (0x440e72 mov edx, 0x12)",
          ins_at(0x440E72).op_str == "edx, 0x12")
    ldm = RAW[v2o(0x40A36C):v2o(0x40A36C) + 7]
    ldm_va = 0x40A36C + 7 + struct_int(0x40A36C + 3)
    check("0x40a36c の ldmxcsr の参照先は MXCSR 大域 0x13a5054・既定値 0x1f80 は RC (bit 13-14) = 0 (最近接・偶数)",
          ldm[:3] == b"\x0f\xae\x15" and ldm_va == 0x13A5054 and (struct_int(0x13A5054) & 0x6000) == 0)
    check("0x440d30 → 0x440c10 呼出し (0x440ec7) と 0x440c10 内の 0x40c660 (0x440c50)",
          ins_at(0x440EC7).op_str == "0x440c10" and ins_at(0x440C50).op_str == "0x40c660")
    check("0x440c10 の 18 桁 BCD 化 (10 進 9 桁 × 2 の除算マジック 0x440c66 ... 0x440cf3)",
          ins_at(0x440C66).op_str == "rax, 0xa3d70a3d70a3d70b" and ins_at(0x440CF3).op_str == "r8d, 1"
          and ins_at(0x440D00).op_str == "0x440c60")


def round_facts_checks():
    # PY-335 (#4513): %.2f の桁出力 0x43f580 は丸め命令を持たない・桁取得 0x43f550 は 0 埋め・
    # 0x40ef40 は MXCSR の下位マスク 0x800 (UM) だけを扱う (RC 未変更)
    kinds = []
    va = 0x43F580
    while va < 0x43F6C8:
        ins = ins_at(va)
        if ins is None:
            break
        kinds.append(ins.mnemonic)
        va += ins.size
    check("0x43f580 (桁出力) に cvt/round 系命令が無い", not any(
        k.startswith("cvt") or k.startswith("round") for k in kinds))
    check("0x43f550 (桁取得) の空桁は '0' 埋め (mov al, 0x30 at 0x43f567)",
          ins_at(0x43F567).op_str == "al, 0x30")
    check("0x40ef40 が MXCSR 設定 0x40a2c0 を ecx=0x800, edx=0x800 で呼ぶ (0x40ef56〜0x40ef60)",
          ins_at(0x40EF56).op_str == "ecx, 0x800" and ins_at(0x40EF5B).op_str == "edx, 0x800"
          and ins_at(0x40EF60).op_str == "0x40a2c0")
    check("0x40a2c0 の変更マスクは 0x1f80 (0x40a2cb)", ins_at(0x40A2CB).op_str == "esi, 0x1f80")
    check("0x440d30 の精度 0x12 (18 桁) は 0x440e72 で固定", ins_at(0x440E72).op_str == "edx, 0x12")


def struct_double(va):
    import struct
    return struct.unpack("<d", RAW[v2o(va):v2o(va) + 8])[0]


def struct_int(va):
    import struct
    return struct.unpack("<i", RAW[v2o(va):v2o(va) + 4])[0]


def qword_at(va):
    o = v2o(va)
    return int.from_bytes(RAW[o:o + 8], "little")


def qword(va):
    o = v2o(va)
    return int.from_bytes(RAW[o:o + 8], "little")


def section_of(va):
    rva = va - BASE
    for s in PEF.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s
    return None


def desc_checks():
    # PY-323 (#4399): desc = [[0x15e2200]+0x940]。0x15e2200 は .data のポインタ slot (初期値 0x16bcaf0)、
    # 0x16bcaf0 は .bss のオブジェクト、desc の格納先は 0x16bd430 (.bss・PE 上に実体無し = 初期値 0)
    def sec(va):
        s = section_of(va)
        return s.Name.rstrip(b"\0") if s else None
    check("0x15e2200 は .data の slot で初期値 0x16bcaf0 (PY-323)",
          sec(0x15E2200) == b".data" and qword_at(0x15E2200) == 0x16BCAF0)
    check("0x16bcaf0 は .bss 内 (オブジェクト)", sec(0x16BCAF0) == b".bss")
    check("desc の格納先 0x16bd430 は .bss 内で、ファイル上の実体無し (PE 初期値 0)",
          sec(0x16BD430) == b".bss" and section_of(0x16BD430).SizeOfRawData == 0)
    check("0x1196017 が 0x16bcaf0 を書く (mov [rip],rax)",
          ins_at(0x1196017).op_str == "qword ptr [rip + 0x526ad2], rax" and rip_target(0x1196017) == 0x16BCAF0)
    check("0xb6fe51 が [rcx+0x940] へ rax を書く (候補 1 件・rcx は引数由来)",
          ins_at(0xB6FE51).op_str == "qword ptr [rcx + 0x940], rax")
    check("0xb6fe4d の rcx は [rbp+0x20] (引数の保存元 0xb6fb8c)",
          ins_at(0xB6FE4D).op_str == "rcx, qword ptr [rbp + 0x20]"
          and ins_at(0xB6FB8C).op_str == "qword ptr [rbp + 0x20], rcx")


def desc_text_checks():
    # PY-191 (#3377): 0x104f2d0 の desc 経路。out1 = trim(マーカー除去(区切り '|' 以降 (無ければ全体)))
    check("0x104f2d0 の desc 判定 (test rax,rax; je 0x104f346) と空時の out1 クリア (0x104f351 → 0x412d60)",
          ins_at(0x104F300).op_str == "0x104f346" and ins_at(0x104F351).op_str == "0x412d60")
    check("0x104f2d0 の連鎖 0x605020 (0x104f311) → 0x662d20 (0x104f31e) → 0x439c90 (0x104f32b) → 0x4133f0 (0x104f33f)",
          ins_at(0x104F311).op_str == "0x605020" and ins_at(0x104F31E).op_str == "0x662d20"
          and ins_at(0x104F32B).op_str == "0x439c90" and ins_at(0x104F33F).op_str == "0x4133f0")
    check("0x104f2d0 の入力は [desc+0xe4] (0x104f30a)", ins_at(0x104F30A).op_str == "rdx, qword ptr [rax + 0xe4]")
    check("0x605020 の区切り文字 '|' (0x60507c) と 0x44b430 → 0x4150d0 (0x605036・0x44b43a)",
          u16z(0x60507C, 1) == "|" and ins_at(0x605036).op_str == "0x44b430"
          and ins_at(0x44B43A).op_str == "0x4150d0" and ins_at(0x44B434).op_str == "r8d, 1")
    check("0x605020 の一致時 0x414ec0(out, S, 検出位置+1, 0x7fffffff) (0x605055・0x60505f)",
          ins_at(0x60503D).op_str == "0x60504c" and ins_at(0x605055).op_str == "r8d, 1"
          and ins_at(0x60505F).op_str == "0x414ec0")
    check("0x605020 の不一致時は全体を複写 0x4133f0 (0x605045)", ins_at(0x605045).op_str == "0x4133f0")
    check("0x4150d0 の戻り値は 1 始まりの位置 (0x4151c1 add rdx,2 → 0x4151c8 sub rax,r10 → 0x4151cb shr rax,1)",
          ins_at(0x4151C1).op_str == "rdx, 2" and ins_at(0x4151C8).op_str == "rax, r10"
          and ins_at(0x4151CB).op_str == "rax, 1" and ins_at(0x41511F).op_str == "r10, rdx")
    check("0x414f20 は 1 始まりの pos から count 文字を削除 (sub esi,1 at 0x414f51 → 0x414f20 内の 0x414f5a 以降)",
          ins_at(0x414F51).op_str == "esi, 1" and ins_at(0x414F5A).op_str == "edi, ecx")
    check("0x662c30 の先頭判定 cmp word [rax],0x5e (^) → 0x662c50 へ繰り返し (0x662cfa・0x662cfe)",
          ins_at(0x662CFA).op_str == "word ptr [rax], 0x5e" and ins_at(0x662CFE).op_str == "0x662c50")
    check("0x662c30 の 2 文字目分岐: '.' (0x662c5e → 0x662cba)・'?' (0x662c65 → 0x662c6f)・{^,_,`} の検索経路 (0x662c6a の範囲内)",
          ins_at(0x662C5E).op_str == "0x662cba" and ins_at(0x662C65).op_str == "0x662c6f"
          and ins_at(0x662C6D).op_str == "0x662cd2" and ins_at(0x662C6A).op_str == "eax, 3")
    check("0x662c30 の 'a' (0x61) は範囲外: cmp eax,3 (0x662c6a) の jae (0x662c6d) が 0x662cd2 へ (0x61-0x5e = 3)",
          ins_at(0x662C6A).mnemonic == "cmp" and ins_at(0x662C6D).mnemonic == "jae" and ins_at(0x662C6D).op_str == "0x662cd2")
    check("0x662c30 '.' 分岐: 3 文字削除 (0x662cc2) + flags |= 2 (0x662ccd)",
          ins_at(0x662CC2).op_str == "r8d, 3" and ins_at(0x662CCD).op_str == "dword ptr [rsi], 2")
    check("0x662c30 既定分岐: 2 文字削除 (0x662cda) で flags は変えない",
          ins_at(0x662CDA).op_str == "r8d, 2" and ins_at(0x662CE0).op_str == "0x414f20")
    check("0x662c30 '?'・'^'・'_'・'`' 分岐: 2 文字削除後に '^' (0x662d1c) を検索 (0x662c82・0x662c8c)",
          ins_at(0x662C82).op_str == "rcx, [rip + 0x93]" and rip_target(0x662C82) == 0x662D1C
          and u16z(0x662D1C, 1) == "^" and ins_at(0x662C8C).op_str == "r8d, 1")
    check("0x662c30 の '_'・'`' の flags |= 1 (0x662cb5) と、'^'・'?' は flags 無し (0x662cae・0x662cb3)",
          ins_at(0x662CAE).op_str == "0x662ce5" and ins_at(0x662CB0).op_str == "edi, 0x3f"
          and ins_at(0x662CB5).op_str == "dword ptr [rsi], 1")
    check("0x439c90 の trim は (<= 0x20) の 16bit 文字を両端から削る (0x439cc0・0x439cd0・0x439cf6)",
          ins_at(0x439CC0).op_str == "word ptr [rdx + r8*2], 0x20" and ins_at(0x439CD0).op_str == "word ptr [rdx + r8*2], 0x20"
          and ins_at(0x439CF6).op_str == "word ptr [rdx + r8*2], 0x20")
    check("0x662d20 は flags (0x662d2f の r8=[rbp+0x2c]) を捨てる (out は [rbp+0x40] への複写のみ)",
          ins_at(0x662D2F).op_str == "r8, [rbp + 0x2c]" and ins_at(0x662D33).op_str == "0x662c30")


def typecheck_checks():
    # PY-324 (#4400): 0x104fa17 の型判定 0x40fe90(obj, T) と 0x410010 の継承鎖の歩き方
    check("0x40fe90 が null なら false (test rcx,rcx; je 0x40fea5)",
          ins_at(0x40FE94).op_str == "rcx, rcx" and ins_at(0x40FE97).op_str == "0x40fea5")
    check("0x40fe90 が *obj (vtable) を取り 0x410010 を呼ぶ (0x40fe9c)",
          ins_at(0x40FE99).op_str == "rcx, qword ptr [rcx]" and ins_at(0x40FE9C).op_str == "0x410010")
    check("0x40fe90 の戻り al=1 は 0x410010 の al が非 0 のとき (0x40fea1/0x40fea3)",
          ins_at(0x40FEA1).op_str == "al, al" and ins_at(0x40FEA3).op_str == "0x40fea9")
    check("0x410010 の比較 cmp rax,rdx; je 0x410026 (一致で true)",
          ins_at(0x410013).op_str == "rax, rdx" and ins_at(0x410016).op_str == "0x410026")
    check("0x410010 の基底の辿り方 mov rax,[rax-0x78] (0x410018)",
          ins_at(0x410018).mnemonic == "mov" and "rax - 0x78" in ins_at(0x410018).op_str)
    check("0x410010 の空判定 test rax,rax; je 0x410029 (0x41001f) と [rax] 読み (0x410021)",
          ins_at(0x41001F).op_str == "0x410029" and ins_at(0x410021).op_str == "rax, qword ptr [rax]")
    check("0x410010 のループ戻り jmp 0x410013 (0x410024)", ins_at(0x410024).op_str == "0x410013")
    check("0x104fa1a の型記述子セル = [rip-0x6cdf1] → 0xfe2c30 (mov rdx)",
          rip_target(0x104FA1A) == 0xFE2C30)
    check("0xfe2c30 の値 (T) = 0xfe2cf8 (.text 内の定数・読取専用)", qword(0xFE2C30) == 0xFE2CF8)
    check("T=0xfe2cf8 の基底 (T-0x78 → 0xfe28b0 → 0xfe2978) の 1 段目", qword(0xFE2CF8 - 0x78) == 0xFE28B0 and qword(0xFE28B0) == 0xFE2978)
    check("0x104fa21 call 0x40fe90 → 0x104fa26 test al,al → 0x104fa28 je 0x104fa4b",
          ins_at(0x104FA21).op_str == "0x40fe90" and ins_at(0x104FA28).op_str == "0x104fa4b")


def pct_fmt_checks():
    # PY-311 (#4225): %.2f 経路の呼出し辺と 0x43dd60 の r9 の流れ (丸め規則は未確定)
    check("0x43ecb5 の %.2f 系 (精度 0x12) が 0x43fce0 を呼ぶ (0x43ece7)", ins_at(0x43ECE7).op_str == "0x43fce0")
    check("0x43fce0 が 0x43f800 を呼ぶ (0x43fd16)", ins_at(0x43FD16).op_str == "0x43f800")
    check("0x43f800 が 0x441380 を呼ぶ (0x43f8ee)", ins_at(0x43F8EE).op_str == "0x441380")
    check("0x441380 が 0x440d30 を呼ぶ (0x4413a2)", ins_at(0x4413A2).op_str == "0x440d30")
    check("0x440d30 の 10 のべき乗の換算 call 0x40ef40 (0x440e7a)", ins_at(0x440E7A).op_str == "0x40ef40")
    check("0x440d30 の整数化 call 0x40c660 = cvtsd2si (0x440e7f)", ins_at(0x440E7F).op_str == "0x40c660"
          and ins_at(0x40C660).mnemonic == "cvtsd2si")
    check("0x440d30 の桁生成 call 0x440c10 (0x440ec7)", ins_at(0x440EC7).op_str == "0x440c10")
    check("0x440c10 の 0 埋め call 0x40d210 (0x440c2d)", ins_at(0x440C2D).op_str == "0x40d210")
    check("0x440c10 の絶対値 call 0x40c660 (0x440c50)", ins_at(0x440C50).op_str == "0x40c660")
    check("0x43dd60 → 0x43dd90 (0x43dd77)", ins_at(0x43DD77).op_str == "0x43dd90")
    check("0x43dd90 → 0x43dde0 (0x43dda5)", ins_at(0x43DDA5).op_str == "0x43dde0")
    check("0x43dde0 → 0x43dc00 (0x43de79)", ins_at(0x43DE79).op_str == "0x43dc00")
    check("0x43dc00 → 0x43e240 (0x43dc22)", ins_at(0x43DC22).op_str == "0x43e240")
    check("0x43dde0 が r9 を rbx に保存 (0x43de11 mov rbx, r9)", ins_at(0x43DE11).op_str == "rbx, r9")
    check("0x43dde0 の 6 番目引数 (rbx) を 0x43dc00 の [rsp+0x28] に渡す (0x43de5c)",
          ins_at(0x43DE5C).op_str == "qword ptr [rsp + 0x28], rbx")
    check("0x43e240 は 6 番目の引数を [rbp+0x1c8] で読む (0x43e2db)",
          ins_at(0x43E2DB).op_str == "ebx, dword ptr [rbp + 0x1c8]")


if __name__ == "__main__":
    sys.exit(main())
