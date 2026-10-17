#!/usr/bin/env python3
"""set_other 非 imm のポインタ経由読込 (load_ptr・chain>load_ptr・mem_ptr 系) の接続判定 (#5392 / M11-N242 / 親 #4890).

入力は m11_setother_nonimm_class.py の出力 nonimm_class_rows.json のうち、理由が load_ptr (chain>load_ptr を含む) の行.
IR は変更しない (分類のみ)。

接続方式 (ptr_mem): `mov r, <幅> ptr [base+d]` の読込を、同じ関数内で同じ [base+d] へ最後に格納した命令まで
  直線区間で後ろ向きに探す。区間は次で打ち切る (未決・理由付き):
    slot_merge   : 読込命令が分岐先 (合流点)
    ptr_call     : 呼出し (別名の書込みが起きうる)。基底が非揮発 (rbx/rsi/rdi/rbp 等) で、
                   呼出し先が直接 call かつ再帰的に非スタック書込みを持たないときだけ区間を跨ぐ。
                   それ以外は未決 (間接 call・解決不能な先・書込みの可能性あり)
    ptr_base_def も揮発基底 (rax/rcx/rdx/r8〜r11) の call 跨ぎに使う (呼出しで値が変わる)
    ptr_branch   : ret/jmp (区間の外)
    ptr_base_def : 基底 reg の族を書き換える命令 (以後の [base+d] は別の番地)
    ptr_unknown_write : メモリ書込みの可能性がある未知の命令 (kind=other)・メモリオペランドを持つ set*
    ptr_alias_write   : 基底が違う書込み (別名の可能性)
    ptr_overlap  : 同じ基底で別幅・別 disp の書込みが読込範囲に重なる
  同じ基底・同じ幅・同じ disp の qword/dword の即値格納だけを実値化する (値 = 即値を幅で切った値)。
  幅が一致しない・reg 格納は未決 (ptr_reg_store / ptr_width_mismatch)。
  区間が関数先頭まで届いたら未決 (ptr_entry)。

使い方: python3 m11_setother_ptr_class.py nonimm_class_rows.json --pe PE --out ptr_class_rows.json
"""
import argparse, collections, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
import capstone
import ldmach

M64 = (1 << 64) - 1
NOWRITE = {'bt', 'cmp', 'test', 'push', 'ucomiss', 'ucomisd', 'comiss', 'comisd', 'nop', 'nopw', 'nopl', 'ret'}
MEM = re.compile(r'(byte|word|dword|qword) ptr \[(\w+)\s*([+-])\s*(0x[0-9a-fA-F]+|\d+)\]')
MEM0 = re.compile(r'(byte|word|dword|qword) ptr \[(\w+)\]')
WIDTH = {'byte': 8, 'word': 16, 'dword': 32, 'qword': 64}
IMM = re.compile(r'-?(0x[0-9a-fA-F]+|\d+)')
FAM = {}
for _r64, _names in (('rax', ('eax', 'ax', 'al', 'ah')), ('rbx', ('ebx', 'bx', 'bl', 'bh')),
                     ('rcx', ('ecx', 'cx', 'cl', 'ch')), ('rdx', ('edx', 'dx', 'dl', 'dh')),
                     ('rsi', ('esi', 'si', 'sil')), ('rdi', ('edi', 'di', 'dil')),
                     ('rbp', ('ebp', 'bp', 'bpl')), ('rsp', ('esp', 'sp', 'spl'))):
    FAM[_r64] = _r64
    for _n in _names:
        FAM[_n] = _r64
for _i in range(8, 16):
    for _suf in ('', 'd', 'w', 'b'):
        FAM['r%d%s' % (_i, _suf)] = 'r%d' % _i


def fam(reg):
    return FAM.get(reg, reg)


def mem_of(op):
    """オペランド文字列の [base±d] → (幅 bits, base 族, disp)。無ければ None。"""
    m = MEM.search(op)
    if m:
        d = int(m.group(4), 0)
        return WIDTH[m.group(1)], fam(m.group(2)), (-d if m.group(3) == '-' else d)
    m = MEM0.search(op)
    if m:
        return WIDTH[m.group(1)], fam(m.group(2)), 0
    return None


def split_ops(s):
    p = s.split(',', 1)
    return p[0].strip(), (p[1].strip() if len(p) > 1 else '')


def writes_reg(x, base):
    """命令 x が基底族 base の 64bit/32bit 値を書き換えるか (保守的に判定)。"""
    dst = split_ops(x.op_str)[0]
    if x.mnemonic in NOWRITE or x.mnemonic.startswith('j') or x.mnemonic.startswith('set'):
        return False
    if x.mnemonic in ('push', 'pop', 'call', 'leave', 'xchg', 'cmpxchg', 'xadd'):
        return True
    return fam(dst) == base


VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
READ_ONLY = ('test', 'cmps', 'ucomis', 'ucomi', 'comis', 'nop', 'prefetch', 'push')
READ_ONLY_EXACT = ('cmp', 'bt', 'lea')  # cmpxchg*・bts/btr/btc* は書込みありなので接頭辞では判定しない
STR_OPS = ('rep', 'movsb', 'movsw', 'movsq', 'stos', 'ins', 'outs', 'syscall', 'int', 'sysenter')


def call_target(x):
    """直接 call / jmp の先 VA。間接の場合は None。"""
    if x.operands and x.operands[0].type == capstone.CS_OP_IMM:
        return x.operands[0].imm
    return None


def insn_may_write_nonstack(mach, x, fn_range):
    """命令 x が rsp 基底以外の番地へ書く可能性があるか (保守的)。fn_range は所属関数の [lo, hi)。"""
    mn = x.mnemonic
    if mn.startswith(STR_OPS) or (mn in ('movsd', 'movsw') and not x.operands):
        return True
    if mn.startswith('j') and mn != 'jmp':
        return False
    if mn == 'jmp':
        t = call_target(x)
        return t is None or not (fn_range[0] <= t < fn_range[1])
    if mn in READ_ONLY_EXACT or mn.startswith(READ_ONLY) or mn == 'ret':
        return False
    body = mn[5:] if mn.startswith('lock ') else mn
    for i, op in enumerate(x.operands):
        if op.type != capstone.CS_OP_MEM:
            continue
        if i != 0 and not body.startswith(('xchg', 'xadd', 'cmpxchg')):
            continue
        base = mach.cs.reg_name(op.mem.base) if op.mem.base else None
        if base != 'rsp' or op.mem.index:
            return True
    return False


def callee_pure(mach, va, memo, stack=()):
    """関数 va が呼出し後に非スタックのメモリへ書かないか (直接 call の再帰を含む・循環は不可)。"""
    if va in memo:
        return memo[va]
    if va in stack:
        # 循環中の再入は未決側 (False) に倒す。推移結果としてのメモ化はこの値で確定する (保守的)
        return False
    ent = mach.fns.get(va)
    ins = mach.disasm_fn(va) if ent else None
    if not ins:
        memo[va] = False
        return False
    rng = (va, va + ent[1])
    ok = True
    for x in ins:
        if x.mnemonic == 'call':
            t = call_target(x)
            if t is None or not callee_pure(mach, t, memo, stack + (va,)):
                ok = False
                break
            continue
        if insn_may_write_nonstack(mach, x, rng):
            ok = False
            break
    memo[va] = ok
    return ok


def load_def(mach, ins, idx, base, d, width, tg, memo):
    """[base+d] を読む ins[idx] の直前で、同じ [base+d] への最後の格納を直線区間で探す。"""
    cs = mach.cs
    k = idx - 1
    while k >= 0:
        if ins[k + 1].address in tg:
            return ('未決', 'slot_merge', None)
        x = ins[k]
        if x.mnemonic == 'call':
            if base in VOLATILE:
                return ('未決', 'ptr_base_def', None)
            t = call_target(x)
            if t is None or not callee_pure(mach, t, memo):
                return ('未決', 'ptr_call', None)
            k -= 1
            continue
        if x.mnemonic in ('ret', 'jmp'):
            return ('未決', 'ptr_branch', None)
        if x.mnemonic.startswith('j') or x.mnemonic in NOWRITE:
            k -= 1
            continue
        if x.mnemonic.startswith('set') and '[' in x.op_str:
            return ('未決', 'ptr_unknown_write', None)
        if writes_reg(x, base):
            return ('未決', 'ptr_base_def', None)
        same = None
        mo_list = ldmach.memops_of(cs, x)
        for mo in mo_list:
            if mo.get('rip_rva') is not None:
                continue
            if mo['kind'] == 'other':
                return ('未決', 'ptr_unknown_write', None)
            if not mo['write']:
                continue
            if mo['base'] is None:
                return ('未決', 'ptr_abs_write', None)
            if mo['base'] != base:
                return ('未決', 'ptr_alias_write', None)
            if mo['index'] is not None:
                return ('未決', 'ptr_index_write', None)
            if mo['disp'] == d and mo['kind'] == 'store':
                same = (mo, x)
                break
            if mo['disp'] < d + width // 8 and mo['disp'] + mo['size_bits'] // 8 > d:
                return ('未決', 'ptr_overlap', None)
        if same is not None:
            mo, x = same
            dst, src = split_ops(x.op_str)
            if x.mnemonic != 'mov' or mo['size_bits'] != width:
                return ('未決', 'ptr_width_mismatch', None)
            if not IMM.fullmatch(src):
                return ('未決', 'ptr_reg_store', None)
            return ('実値化', 'ptr_imm', int(src, 0) & ((1 << width) - 1))
        k -= 1
    return ('未決', 'ptr_entry', None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rows'); ap.add_argument('--pe', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    mach = ldmach.Machine(a.pe)
    cs = mach.cs
    rows_in = [r for r in json.load(open(a.rows))
               if r['reason'].endswith('load_ptr')]
    fcache = {}
    memo = {}
    out_rows = []
    cnt = collections.Counter()
    for r in rows_in:
        cva = int(r['caller'].split('_')[1], 16)
        if cva not in fcache:
            ins = mach.disasm_fn(cva) or []
            fcache[cva] = (ins, {x.address: i for i, x in enumerate(ins)},
                           {x.operands[0].imm for x in ins if x.mnemonic.startswith('j') and x.operands
                            and x.operands[0].type == capstone.CS_OP_IMM})
        ins, pos, tg = fcache[cva]
        idx = pos.get(int(r['def'], 16))
        mem = mem_of(ins[idx].op_str) if idx is not None else None
        if mem is None:
            cls, why, val = '未決', 'no_mem_operand', None
        else:
            width, base, d = mem
            if base == 'rbp' or base == 'rsp':
                cls, why, val = '未決', 'frame_base', None
            else:
                cls, why, val = load_def(mach, ins, idx, base, d, width, tg, memo)
        if val is not None:
            val = hex(val)
        cnt[(cls, why)] += 1
        out_rows.append({'caller': r['caller'], 'callee': r['callee'], 'k': r['k'], 'pos': r['pos'],
                         'ledger': r['ledger'], 'prev_reason': r['reason'], 'class': cls, 'reason': why,
                         'value': val, 'def': r['def'], 'def_insn': ins[idx].mnemonic + ' ' + ins[idx].op_str
                         if idx is not None else r['def_insn']})
    print('[ptr-class] 対象 %d 件 (load_ptr・chain>load_ptr)' % len(out_rows))
    tot = collections.Counter(r['class'] for r in out_rows)
    for k in ('実値化', '復元不能', '未決'):
        print('  %-8s %d' % (k, tot[k]))
    print('  未分類   %d' % (len(out_rows) - tot['実値化'] - tot['復元不能'] - tot['未決']))
    print('[ptr-class] 理由別')
    for (cls, why), v in sorted(cnt.items()):
        print('  %-8s %-22s %d' % (cls, why, v))
    json.dump(out_rows, open(a.out, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
