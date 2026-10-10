#!/usr/bin/env python3
"""retdec_census.py — RetDec 生 lift (`!insn.addr` 付き .ll) と機械語を突合して欠陥類型を機械的に数える。

usage: retdec_census.py <core.pe> <raw.drc.ll> [--json out.json] [--label name]
分類 (すべて insn.addr を鍵に機械語側と IR 側を対応づける):
  C1 SSE 比較フラグ consumer (jcc/cmovcc/setcc の直近 flag 生成命令が comis*/ucomis*):
       - stale     : IR に br/select はあるが条件は comis 結果を参照しない (RetDec は comis を void asm 呼出として扱いフラグを出力しない)
       - missing   : IR に br/select 自体が無い (分岐脱落 = Gain の P1' 型)
  C2 xmm 呼出規約: 直接 call 先が xmm0-3 を live-in に持つのに IR の call が xmm を渡していない (引数落ち, Gain の F2')
       C2r: 呼出後に xmm0 が使われる (戻り値) のに IR が戻り値を捨てている
  C3 間接 call が IR に存在しない (vtable 経由, 例: call [rax+0x60])
  C4 整数 cmov が IR に無い (select 無し)
  C5 命令脱落: 機械語命令のうち IR 命令が 1 つも対応しないもの (nop/int3/push/pop/ret/prologue を除く)
  C6 整数フラグ consumer: br が存在 (比較対象として母数)
"""
import re, sys, json, argparse, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_REG, CS_OP_IMM
from capstone.x86 import X86_REG_RIP

ap = argparse.ArgumentParser()
ap.add_argument('pe'); ap.add_argument('ll'); ap.add_argument('--json'); ap.add_argument('--label', default='')
a = ap.parse_args()

pe = pefile.PE(a.pe); base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
txt = open(a.ll).read()
mdmap = {m.group(1): int(m.group(2)) for m in re.finditer(r'^!(\d+) = !\{i64 (\d+)\}', txt, re.M)}

funcs = {}
for m in re.finditer(r'^define [^\n]*@function_([0-9a-f]+)\(', txt, re.M):
    va = int(m.group(1), 16)
    s = m.start(); e = txt.index('\n}\n', s)
    funcs[va] = txt[s:e]

SSE_CMP = ('comiss', 'ucomiss', 'comisd', 'ucomisd')
SSE_REG = lambda n: n.startswith('xmm')
TRIVIAL = {'nop', 'int3', 'push', 'pop', 'ret', 'jmp', 'ud2', 'endbr64'}

def ir_index(body):
    idx = collections.defaultdict(list)
    for line in body.split('\n'):
        mm = re.search(r', !insn\.addr !(\d+)\s*$', line)
        if not mm: continue
        addr = mdmap.get(mm.group(1))
        s = line.strip()
        if s.startswith('br '): op = 'br'
        elif ' = select ' in s: op = 'select'
        elif ' call ' in s or s.startswith('call '):
            mc = re.search(r'call [^@]*@([\w.]+)\((.*)\)', s)
            op = 'call:' + (mc.group(1) if mc else '?') + ':' + (mc.group(2) if mc else '')
        elif ' = load ' in s: op = 'load'
        elif s.startswith('store '): op = 'store'
        elif s.startswith('ret'): op = 'ret'
        elif 'alloca' in s: op = 'alloca'
        else: op = 'other'
        idx[addr].append(op)
    return idx

def disasm_func(va, size):
    code = pe.get_data(va - base, size)
    return list(md.disasm(code, va))

def func_size(va):
    # pdata から
    pd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    import struct
    raw = pe.get_data(pd.VirtualAddress, pd.Size)
    ents = sorted(struct.unpack_from('<III', raw, i * 12) for i in range(len(raw) // 12))
    for b, e, u in ents:
        if base + b == va: return e - b
    return 0

def callee_xmm_livein(va):
    sz = func_size(va) or 64
    defd = set(); live = set()
    for i in disasm_func(va, sz):
        try: rd, wr = i.regs_access()
        except Exception: continue
        for r in rd:
            n = i.reg_name(r)
            if n in ('xmm0', 'xmm1', 'xmm2', 'xmm3') and n not in defd: live.add(n)
        for r in wr:
            defd.add(i.reg_name(r))
        if i.mnemonic == 'ret': break
    return live

res = collections.Counter(); per = {}
detail = []
for va, body in sorted(funcs.items()):
    size = func_size(va)
    ins = disasm_func(va, size)
    idx = ir_index(body)
    r = collections.Counter(); r['bytes'] = size; r['insns'] = len(ins)
    # BB leaders
    leaders = {va}
    for i in ins:
        if i.mnemonic.startswith('j') and i.operands and i.operands[0].type == CS_OP_IMM:
            leaders.add(i.operands[0].imm); leaders.add(i.address + i.size)
        if i.mnemonic == 'ret': leaders.add(i.address + i.size)
    last_flag = None   # (kind, addr)
    for k, i in enumerate(ins):
        m = i.mnemonic
        if i.address in leaders: last_flag = None
        ops = idx.get(i.address, [])
        # フラグ生成
        try: wr = [i.reg_name(x) for x in i.regs_access()[1]]
        except Exception: wr = []
        if m in SSE_CMP: last_flag = ('sse', i.address)
        elif 'eflags' in wr: last_flag = ('int', i.address)
        # consumer
        is_jcc = m.startswith('j') and m != 'jmp'
        is_cmov = m.startswith('cmov'); is_set = m.startswith('set')
        if is_jcc or is_cmov or is_set:
            kind = last_flag[0] if last_flag else 'unk'
            tag = 'jcc' if is_jcc else 'cmov' if is_cmov else 'setcc'
            if kind == 'sse':
                r['C1_sse_flag_consumers'] += 1
                has = ('br' in ops) if is_jcc else ('select' in ops)
                if has: r['C1_stale'] += 1
                else: r['C1_missing'] += 1
                detail.append(('C1', '%s' % ('stale' if has else 'missing'), '%x' % i.address, m))
            else:
                r['C6_int_flag_consumers'] += 1
                if is_cmov:
                    r['C4_cmov_int'] += 1
                    if 'select' not in ops: r['C4_cmov_int_dropped'] += 1
        # 呼出
        is_tail = (m == 'jmp' and i.operands and i.operands[0].type == CS_OP_IMM and not (va <= i.operands[0].imm < va + size))
        if (m == 'call' or is_tail) and i.operands:
            o = i.operands[0]
            if o.type == CS_OP_IMM:
                r['calls_direct'] += 1
                callee = o.imm
                livein = callee_xmm_livein(callee)
                irc = [x for x in ops if x.startswith('call:')]
                nargs = (irc[0].count(',') + 1) if irc and irc[0].split(':', 2)[2].strip() else 0
                if livein:
                    r['C2_calls_with_xmm_args'] += 1
                    # IR call は整数 1 引数 (RetDec は xmm 引数を渡さない)
                    if not any('float' in x or 'i128' in x or 'double' in x for x in irc): r['C2_xmm_args_dropped'] += 1
                    detail.append(('C2', 'xmm_args_dropped', '%x' % i.address, 'call %x live-in %s' % (callee, sorted(livein))))
                # 戻り xmm0 使用 (線形近似): call 直後で xmm0 が def より先に read されるか
                used = False
                for j in ins[k + 1:k + 12]:
                    try: rd, w2 = j.regs_access()
                    except Exception: break
                    rn = [j.reg_name(x) for x in rd]; wn = [j.reg_name(x) for x in w2]
                    if 'xmm0' in rn: used = True; break
                    if 'xmm0' in wn or j.mnemonic in ('call', 'ret', 'jmp'): break
                if used:
                    r['C2r_ret_xmm0_used'] += 1
                    r['C2r_ret_dropped'] += 1      # RetDec は call 戻り値 (i64) を xmm0 に接続しない
                    detail.append(('C2r', 'ret_xmm0_dropped', '%x' % i.address, 'call %x' % callee))
            else:
                r['C3_calls_indirect'] += 1
                if not any(x.startswith('call:') for x in ops):
                    r['C3_indirect_dropped'] += 1
                    detail.append(('C3', 'indirect_call_dropped', '%x' % i.address, i.op_str))
        # 命令脱落
        if m not in TRIVIAL and not ops and not (is_jcc):
            r['C5_insn_no_ir'] += 1
            r['C5_by_' + m] += 1
        if is_jcc and 'br' not in ops:
            r['C5_jcc_no_br'] += 1
    per['%x' % va] = dict(r)
    res.update(r)

out = {'label': a.label, 'funcs': per, 'total': dict(res), 'detail': detail}
if a.json: json.dump(out, open(a.json, 'w'), indent=1)
t = res
def pct(x, y): return '%.0f%%' % (100.0 * x / y) if y else 'n/a'
print('== %s: %d funcs, %d B, %d insns' % (a.label, len(funcs), t['bytes'], t['insns']))
print(' C1 SSE-flag consumers : %3d  (stale %d / missing %d)  = %s damaged' % (t['C1_sse_flag_consumers'], t['C1_stale'], t['C1_missing'], pct(t['C1_sse_flag_consumers'], t['C1_sse_flag_consumers'])))
print(' C2 xmm-arg calls      : %3d  of %d direct calls (arg-dropped %d); ret-xmm0 used %d (dropped %d)' % (t['C2_calls_with_xmm_args'], t['calls_direct'], t['C2_xmm_args_dropped'], t['C2r_ret_xmm0_used'], t['C2r_ret_dropped']))
print(' C3 indirect calls     : %3d  (dropped from IR %d)' % (t['C3_calls_indirect'], t['C3_indirect_dropped']))
print(' C4 int cmov           : %3d  (dropped %d)   C6 int-flag consumers %d' % (t['C4_cmov_int'], t['C4_cmov_int_dropped'], t['C6_int_flag_consumers']))
print(' C5 insn without IR    : %3d / %d (%s)  jcc-without-br %d' % (t['C5_insn_no_ir'], t['insns'], pct(t['C5_insn_no_ir'], t['insns']), t['C5_jcc_no_br']))
