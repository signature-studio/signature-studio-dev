#!/usr/bin/env python3
"""SR-4: RetDec raw .ll の浮動小数点 ALU 命令被覆。
usage: sr4_cov.py <pe> <raw.ll> <begin_hex> <end_hex>  -> JSON (stdout)
機械語 [begin,end) を線形掃引して FP ALU 命令 (cvt*/ucomis*/comis* と、mov* 以外の *ss/*sd/*ps/*pd。同一レジスタ xor の zero idiom は除外) を数え、
そのうち raw .ll の `!{i64 <addr>}` (insn.addr メタデータ) に現れるアドレスの割合を返す。
jump table などで RetDec が到達できなかった領域を『lift 成功』に見せないための被覆検査 (命令の取りこぼしは bit 比較の乱数入力では見えない経路に潜む)。"""
import sys, re, json
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe_path, ll_path, b, e = sys.argv[1], sys.argv[2], int(sys.argv[3], 16), int(sys.argv[4], 16)
pe = pefile.PE(pe_path, fast_load=True)
IMG = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
addrs = {int(m.group(1)) for m in re.finditer(r'^!\d+ = !\{i64 (\d+)\}', open(ll_path).read(), re.M)}
md = Cs(CS_ARCH_X86, CS_MODE_64)
total = hit = n_insn = 0
miss = []
for i in md.disasm(img[b - IMG:e - IMG], b):
    n_insn += 1
    m = i.mnemonic
    fp = m.startswith(('cvt', 'ucomis', 'comis')) or (m.endswith(('ss', 'sd', 'ps', 'pd')) and not m.startswith('mov'))
    if not fp:
        continue
    ops = [o.strip() for o in i.op_str.split(',')]
    if m in ('xorps', 'xorpd', 'pxor') and len(ops) == 2 and ops[0] == ops[1]:
        continue
    total += 1
    if i.address in addrs:
        hit += 1
    elif len(miss) < 5:
        miss.append(hex(i.address))
print(json.dumps(dict(begin=hex(b), end=hex(e), machine_insn=n_insn, fp_alu=total, fp_alu_in_ir=hit,
                      fp_alu_cov=(hit / total if total else 1.0), first_missing=miss)))
