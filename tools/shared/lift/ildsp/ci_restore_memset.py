#!/usr/bin/env python3
"""CreateInstance (0x1aef60) の直接 jcc 先 0x1aef40 (rep stosb の memset ヘルパ) を IR に戻す (T-SH-163 #6231)。

x86: 0x1aefa7 `jne 0x1801aef40` は条件分岐。0x1aef40 は [rcx, rcx+r8) を al (= arg2 & 0xff) で埋め、
rax = r11 (= arg1) を入れて ret する。ret は 0x1aef60 の呼び出し元へ直接戻り、0x1aefa9 へは続かない。
RetDec は jcc を `call i64 @function_1801aef40` + fall-through に化かす (REPORT_CI §8-1)。
この段は、その call を memset ループ (byte 書込み n 回) に置き換え、戻りを `ret i64 %arg1` の block へ直接 br させる。
閉包規則は変えない (36 関数・961 命令のまま)。

usage: ci_restore_memset.py <block24360_PE.bin> <ci.rj.ll> <ci.rm.ll>
x86 の前提 (逆アセンブルで確認。外れたら exit 1): 0x1aefa7 が jne 0x1801aef40・0x1aef40 の 8 命令の形。
"""
import re, sys
import pefile, capstone

ENTRY_DEF = "function_1801aef60"
JCC_RVA = 0x1aefa7
HELPER_RVA = 0x1aef40
HELPER_ASM = ["push rdi", "mov eax, edx", "mov rdi, rcx", "mov rcx, r8", "rep stosb byte ptr [rdi], al",
              "mov rax, r11", "pop rdi", "ret"]
HELPER_NAME = "function_1801aef40"
RET_LABEL = "dec_label_pc_1801af028"
OLD_BR = "  br i1 %10, label %11, label %dec_label_pc_1801aefa9, !insn.addr !59"
NEW_BR = "  br i1 %10, label %ci_ms, label %dec_label_pc_1801aefa9, !insn.addr !59"
OLD_CALL = ("; <label>:11:                                     ; preds = %dec_label_pc_1801aefa0\n"
            "  %12 = call i64 @function_1801aef40(), !insn.addr !59\n"
            "  br label %dec_label_pc_1801aefa9, !insn.addr !59\n\n")
NEW_BLOCK = """ci_ms:
  %ci_ms_b = trunc i64 %2 to i8
  br label %ci_ms_loop

ci_ms_loop:
  %ci_ms_i = phi i64 [ 0, %ci_ms ], [ %ci_ms_i1, %ci_ms_body ]
  %ci_ms_c = icmp ult i64 %ci_ms_i, %arg3
  br i1 %ci_ms_c, label %ci_ms_body, label %%RET_LABEL

ci_ms_body:
  %ci_ms_a = add i64 %arg1, %ci_ms_i
  %ci_ms_p = inttoptr i64 %ci_ms_a to i8*
  store i8 %ci_ms_b, i8* %ci_ms_p, align 1
  %ci_ms_i1 = add i64 %ci_ms_i, 1
  br label %ci_ms_loop

""".replace("%%RET_LABEL", "%" + RET_LABEL)
DECL = "declare i64 @%s() local_unnamed_addr\n" % HELPER_NAME


def check_x86(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    img = pe.get_memory_mapped_image()
    ib = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    jcc = next(md.disasm(bytes(img[JCC_RVA:JCC_RVA + 15]), ib + JCC_RVA))
    if jcc.mnemonic != "jne" or jcc.op_str != "0x%x" % (ib + HELPER_RVA):
        sys.exit(f"[restore_memset] 0x{JCC_RVA:x} が jne 0x{ib + HELPER_RVA:x} でない: {jcc.mnemonic} {jcc.op_str}")
    addr, got = HELPER_RVA, []
    for _ in range(len(HELPER_ASM)):
        ins = next(md.disasm(bytes(img[addr:addr + 15]), ib + addr))
        got.append(f"{ins.mnemonic} {ins.op_str}".strip())
        addr += ins.size
    if got != HELPER_ASM:
        sys.exit(f"[restore_memset] 0x{HELPER_RVA:x} の形が想定と違う: {got}")


def main():
    pe_path, rj_path, out_path = sys.argv[1:4]
    check_x86(pe_path)
    text = open(rj_path).read()
    if len(re.findall(r"^define [^@]*@%s\(" % ENTRY_DEF, text, re.M)) != 1:
        sys.exit("[restore_memset] 入口の define が 1 件でない")
    if text.count(OLD_BR) != 1:
        sys.exit("[restore_memset] jcc の分岐が想定と違う (RetDec の形が変わった)")
    if text.count(OLD_CALL) != 1:
        sys.exit("[restore_memset] helper の call block が想定と違う")
    if text.count(DECL) != 1:
        sys.exit("[restore_memset] helper の declare が 1 件でない")
    if text.count("\n" + RET_LABEL + ":") != 1:
        sys.exit("[restore_memset] 戻し先 ret ブロックが 1 件でない")
    text = text.replace(OLD_BR, NEW_BR, 1)
    text = text.replace(OLD_CALL, NEW_BLOCK, 1)
    text = text.replace(DECL, "", 1)
    open(out_path, "w").write(text)
    print(f"[restore_memset] 0x{HELPER_RVA:x} (rep stosb) の call を memset ループに戻した -> {out_path}")


if __name__ == "__main__":
    main()
