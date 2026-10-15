#!/usr/bin/env python3
"""set_other 非 imm のスタック slot 読込 (load_stack・chain>load_stack) と frame 内 lea (lea_stack) の接続判定 (#3906 / M11-N196 / 親 #3142).

入力は m11_setother_nonimm_class.py の出力 nonimm_class_rows.json のうち、理由が load_stack / chain>load_stack / lea_stack の行。
IR は変更しない (分類のみ)。

フレーム定数 C: 呼出し元の prologue で entry rsp から `mov rbp, rsp` までの減算量 (push 8・sub rsp imm の合計)。
retdec の IR 名 stack_var_X は X = d - C (機械語 [rbp+d] に対応)。C は呼出し元 IR の alloca 名で検証する (検証数を出力)。
  lea_stack   : `lea r, [rbp+d]` の値を、呼出し元 IR の `%stack_var_(d-C) = alloca` (接尾辞なし) に接続する。
                接続できれば実値化 (値 = その alloca の番地)。alloca が無ければ未決 (lea_alloca_absent)。
  load_stack  : `[rbp+d]` の読込を、同じ slot への最後の格納まで直線区間で後ろ向きに探す。
                区間は分岐先・call・ret/jmp・ポインタ経由の書込み・slot を覆う別幅の書込みで打ち切る (未決)。
                qword の即値格納なら実値化。reg 格納 (slot_reg) などは未決 (理由付き)。

使い方: python3 m11_setother_mem_class.py nonimm_class_rows.json --pe PE --ir IR.ll --out mem_class_rows.json
"""
import argparse, collections, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
import capstone
import ldmach

ap = argparse.ArgumentParser()
ap.add_argument('rows'); ap.add_argument('--pe', required=True); ap.add_argument('--ir', required=True)
ap.add_argument('--out', required=True)
a = ap.parse_args()

M64 = (1 << 64) - 1
NOWRITE = {'bt', 'cmp', 'test', 'push', 'ucomiss', 'ucomisd', 'comiss', 'comisd', 'nop', 'nopw', 'nopl', 'ret'}
MEM = re.compile(r'\[(rbp|rsp)\s*([+-])\s*(0x[0-9a-fA-F]+|\d+)\]')
ALLOCA = re.compile(r'^\s*%(stack_var_-?\d+)(\.[^ ]*)? = alloca\b')
HEAD = re.compile(r'^define\b.*?@(function_[0-9a-fA-F]+)\(')

mach = ldmach.Machine(a.pe)
cs = mach.cs


def frame_const(ins):
    """entry rsp から mov rbp, rsp までの減算量。rsp を別の仕方で動かす命令が先にあれば None。"""
    tot = 0
    for x in ins[:24]:
        if x.mnemonic == 'push':
            tot += 8
        elif x.mnemonic == 'sub' and x.op_str.startswith('rsp, '):
            tot += int(x.op_str.split(',')[1], 0)
        elif x.mnemonic == 'mov' and x.op_str == 'rbp, rsp':
            return tot
        elif split_ops(x.op_str)[0] == 'rsp' or x.mnemonic in ('pop', 'leave'):
            return None
    return None


def ir_allocas(path):
    """関数名 → {exact: 接尾辞なしの stack_var 名, suffixed: 接尾辞付きの stack_var 名}。"""
    out, cur = {}, None
    for line in open(path):
        if line.startswith('define'):
            m = HEAD.match(line)
            cur = m.group(1) if m else None
            if cur:
                out.setdefault(cur, {'exact': set(), 'suffixed': set()})
        elif line.startswith('}'):
            cur = None
        elif cur:
            m = ALLOCA.match(line)
            if m:
                out[cur]['suffixed' if m.group(2) else 'exact'].add(m.group(1))
    return out


def mem_base_disp(op):
    m = MEM.search(op)
    if not m:
        return None
    d = int(m.group(3), 0)
    return m.group(1), (-d if m.group(2) == '-' else d)


def split_ops(s):
    p = s.split(',', 1)
    return p[0].strip(), (p[1].strip() if len(p) > 1 else '')


def load_def(ins, idx, base, d, tg):
    """[base+d] を読む命令 ins[idx] の直前で、同じ slot への最後の格納を直線区間で探す。"""
    k = idx - 1
    while k >= 0:
        if ins[k + 1].address in tg:
            return ('未決', 'slot_merge', None, None)
        x = ins[k]
        at = hex(x.address)
        if x.mnemonic == 'call':
            return ('未決', 'slot_call', None, at)
        if x.mnemonic in ('ret', 'jmp'):
            return ('未決', 'slot_branch', None, at)
        if x.mnemonic.startswith('j') or x.mnemonic in NOWRITE:
            k -= 1
            continue
        if base == 'rsp' and (x.mnemonic in ('push', 'pop', 'leave') or split_ops(x.op_str)[0] == 'rsp'):
            return ('未決', 'slot_base', None, at)
        if split_ops(x.op_str)[0] == 'rbp' and base == 'rbp':
            return ('未決', 'slot_base', None, at)
        for mo in ldmach.memops_of(cs, x):
            if not mo['write'] or mo.get('rip_rva') is not None:
                continue
            if mo['base'] not in (base, 'rbp', 'rsp', None):
                return ('未決', 'slot_ptr_write', None, at)
            if mo['base'] is None:
                return ('未決', 'slot_abs_write', None, at)
            if mo['base'] != base:
                return ('未決', 'slot_alias_base', None, at)
            if mo['disp'] == d and mo['kind'] == 'store' and mo['size_bits'] == 64:
                dst, src = split_ops(x.op_str)
                if x.mnemonic == 'mov' and re.fullmatch(r'-?(0x[0-9a-fA-F]+|\d+)', src):
                    return ('実値化', 'slot_imm', int(src, 0) & M64, at)
                if x.mnemonic == 'mov' and re.fullmatch(r'r[a-z0-9]+|e[a-z]+', src):
                    return ('未決', 'slot_reg', None, at)
                return ('未決', 'slot_other:' + x.mnemonic, None, at)
            if mo['disp'] < d + 8 and mo['disp'] + mo['size_bits'] // 8 > d:
                return ('未決', 'slot_overlap', None, at)
        k -= 1
    return ('未決', 'slot_entry', None, None)


rows_in = [r for r in json.load(open(a.rows))
           if r['reason'] == 'lea_stack' or r['reason'].endswith('load_stack')]
allocas = ir_allocas(a.ir)
fcache = {}
out_rows = []
cnt = collections.Counter()
xtab = collections.Counter()
c_ok = c_bad = 0
for r in rows_in:
    cva = int(r['caller'].split('_')[1], 16)
    if cva not in fcache:
        ins = mach.disasm_fn(cva) or []
        fcache[cva] = (ins, {x.address: i for i, x in enumerate(ins)},
                       {x.operands[0].imm for x in ins if x.mnemonic.startswith('j') and x.operands
                        and x.operands[0].type == capstone.CS_OP_IMM}, frame_const(ins))
    ins, pos, tg, C = fcache[cva]
    da = int(r['def'], 16)
    idx = pos[da]
    mb = mem_base_disp(ins[idx].op_str)
    if mb is None or C is None:
        cls, why, val = '未決', ('no_frame' if C is None else 'no_mem_operand'), None
    elif mb[0] != 'rbp':
        cls, why, val = '未決', 'rsp_base', None
    else:
        d = mb[1]
        X = d - C
        name = 'stack_var_%d' % X
        ia = allocas.get(r['caller'], {'exact': set(), 'suffixed': set()})
        present = name in ia['exact'] or name in ia['suffixed']
        c_ok += present
        c_bad += not present
        if r['reason'] == 'lea_stack':
            if name in ia['exact']:
                cls, why, val = '実値化', 'lea_alloca', '&%' + name
            elif name in ia['suffixed']:
                cls, why, val = '未決', 'lea_alloca_suffixed', None
            else:
                cls, why, val = '未決', 'lea_alloca_absent', None
        else:
            cls, why, val, _ = load_def(ins, idx, 'rbp', d, tg)
            if val is not None:
                val = hex(val)
    cnt[cls] += 1
    xtab[(r['ledger'], why, cls)] += 1
    out_rows.append({'caller': r['caller'], 'callee': r['callee'], 'k': r['k'], 'pos': r['pos'],
                     'ledger': r['ledger'], 'prev_reason': r['reason'], 'class': cls, 'reason': why,
                     'value': val, 'def': r['def'], 'def_insn': ins[idx].mnemonic + ' ' + ins[idx].op_str})
print('[mem-class] 対象 %d 件 (スタック slot 読込・frame lea)' % len(out_rows))
for k in ('実値化', '復元不能', '未決'):
    print('  %-8s %d' % (k, cnt[k]))
print('[mem-class] C 検証 (stack_var_(d-C) の alloca が呼出し元 IR に在る): 在 %d / 無 %d' % (c_ok, c_bad))
print('[mem-class] 台帳 kind × 理由 × 区分')
for (led, why, cls), v in sorted(xtab.items()):
    print('  %-12s %-22s %-8s %d' % (led, why, cls, v))
json.dump(out_rows, open(a.out, 'w'), indent=1)
