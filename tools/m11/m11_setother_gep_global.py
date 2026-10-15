#!/usr/bin/env python3
"""set_other 非 imm の gep 17 件 (lea [reg+d]) と書込可能グローバル global_store 3 件の接続判定 (#4891 / M11-N227 / 親 #3907).

入力は m11_setother_mem_class.py の出力 mem_class_rows.json のうち conn が gep / global_store の行。
IR (boot_final 系の final3_base.ll) は変更しない。区分は 実値化 / 復元不能 / 未決 の 3 値で、未分類 0 を確認する。

global_store (書込可能グローバル VA を読む 3 件):
  対象は呼出し元 CFG 上の最後のグローバル格納 (store)。IR で VA を指す store を全件数える。
  store が 0 件なら 未決 (no_store_in_ir)。store があっても値の到達定義は未実装なので 未決 (store_value_unchecked)。
gep (lea [reg+d] の 17 件):
  対象は基底 reg の SSA 値に対する GEP。基底 SSA の特定は未実装のため 未決 (base_ssa_unmapped)。

gep の基底 reg (--pe 指定時): lea 直前の基底 reg の到達定義を機械語で後ろ向きに辿る (#4905 / M11-N228)。
  mov reg, imm (dst が 64bit 名・32bit 名のとき。上位は 0 拡張): 実値化 (base_const)
  mov al/ax, imm (8・16bit 部分書込。上位保持)          : 未決 (base_partial)
  call の戻り値 (呼出し先が揮発族 reg を書く): 復元不能 (base_call_ret)
  merge・分岐・stack slot 読込・ポインタ読込 : 未決 (base_merge / base_branch / base_stack_slot / base_ptr_load)
  定義が見つからない                        : 未決 (base_entry)
--pe を外すと従来どおり 未決 (base_ssa_unmapped)。

使い方: python3 m11_setother_gep_global.py mem_class_rows.json --ir final3_base.ll --out gep_global_rows.json [--pe PE]
"""
import argparse, collections, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
sys.path.insert(0, HERE)
import capstone
import ldmach
import m11_argrecover as AR

VOLATILE = {'rcx', 'rdx', 'r8', 'r9', 'rax', 'r10', 'r11'}
FULL64 = {'rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp'} | {'r%d' % i for i in range(8, 16)}
FULL32 = {'eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp'} | {'r%dd' % i for i in range(8, 16)}
IMM = re.compile(r'-?(0x[0-9a-f]+|\d+)')
NOWRITE = {'cmp', 'test', 'bt'}
SUBREG = {}
for _full, _subs in {
        'rax': ('eax', 'ax', 'al', 'ah'), 'rbx': ('ebx', 'bx', 'bl', 'bh'),
        'rcx': ('ecx', 'cx', 'cl', 'ch'), 'rdx': ('edx', 'dx', 'dl', 'dh'),
        'rsi': ('esi', 'si', 'sil'), 'rdi': ('edi', 'di', 'dil'),
        'rbp': ('ebp', 'bp', 'bpl'), 'rsp': ('esp', 'sp', 'spl')}.items():
    SUBREG[_full] = _full
    for _s in _subs:
        SUBREG[_s] = _full
for _i in range(8, 16):
    SUBREG['r%d' % _i] = 'r%d' % _i
    SUBREG['r%dd' % _i] = 'r%d' % _i
    SUBREG['r%dw' % _i] = 'r%d' % _i
    SUBREG['r%db' % _i] = 'r%d' % _i


def mov_imm_class(dst):
    """mov dst, imm の区分。64bit 名・32bit 名は全幅を定義する (32bit は上位 0 拡張)。8・16bit 名は上位を保持する部分書込。"""
    if dst in FULL64 or dst in FULL32:
        return '実値化', 'base_const'
    return '未決', 'base_partial'


def gep_base(cf, r):
    """lea [base+d] の base reg の到達定義を後ろ向きに辿って (区分, 理由) を返す。cf は AR.Fn。"""
    li = next((i for i, x in enumerate(cf.ins) if x.address == int(r['def'], 16)), None)
    if li is None:
        return '未決', 'lea_not_found'
    m = re.search(r'\[(\w+)', cf.ins[li].op_str)
    base = m.group(1)
    tg = {x.operands[0].imm for x in cf.ins if x.mnemonic.startswith('j') and x.operands and x.operands[0].type == capstone.CS_OP_IMM}
    j = li - 1
    while j >= 0:
        if cf.ins[j + 1].address in tg:
            return '未決', 'base_merge'
        x = cf.ins[j]
        if x.mnemonic == 'call':
            if base in VOLATILE:
                return '復元不能', 'base_call_ret'
            j -= 1
            continue
        if x.mnemonic in ('ret', 'jmp'):
            return '未決', 'base_branch'
        dst, src = [p.strip() for p in x.op_str.split(',', 1)] if ',' in x.op_str else (x.op_str.strip(), '')
        if base in cf.rw(x)[1] or (x.mnemonic not in NOWRITE and SUBREG.get(dst) == base):
            if x.mnemonic == 'mov' and IMM.fullmatch(src):
                return mov_imm_class(dst)
            if x.mnemonic == 'mov' and re.search(r'\[(rbp|rsp)', src):
                return '未決', 'base_stack_slot'
            if x.mnemonic == 'mov' and '[' in src:
                return '未決', 'base_ptr_load'
            return '未決', 'base_other:' + x.mnemonic
        j -= 1
    return '未決', 'base_entry'


def store_count(ir, va):
    """IR 全体で VA (i64 十進) を指すアドレスへの store 件数と、その呼出し元関数名の集合。"""
    alias = set()
    pat_alias = re.compile(r'(%\S+) = inttoptr i64 ' + str(va) + r' to ptr')
    for l in ir:
        m = pat_alias.search(l)
        if m:
            alias.add(m.group(1))
    lit = re.compile(r'inttoptr \(i64 ' + str(va) + r' to ptr\)|inttoptr i64 ' + str(va) + r' to ptr')
    fn = None
    fns = []
    n = 0
    for l in ir:
        if l.startswith('define'):
            fn = l.split('@')[1].split('(')[0]
        if not l.lstrip().startswith('store ') and ' store ' not in l:
            continue
        if lit.search(l) or any(re.search(re.escape(x) + r'(?![\w.])', l.split('store', 1)[1]) for x in alias):
            n += 1
            fns.append(fn)
    return n, fns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rows'); ap.add_argument('--ir', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--pe', default=None)
    a = ap.parse_args()
    rows = json.load(open(a.rows))
    ir = open(a.ir).read().split('\n')
    TARGET = [r for r in rows if r['conn'] in ('gep', 'global_store')]
    _mach = ldmach.Machine(a.pe) if a.pe else None
    _fn = {}

    def fn(va):
        if va not in _fn:
            _fn[va] = AR.Fn(_mach, va)
        return _fn[va]

    out = []
    cache = {}
    for r in TARGET:
        x = dict(r)
        if r['conn'] == 'global_store':
            va = int(r['def'], 16) + 7 + int(re.search(r'\[rip \+ (0x[0-9a-f]+|\d+)\]', r['def_insn']).group(1), 0)
            if va not in cache:
                cache[va] = store_count(ir, va)
            n, fns = cache[va]
            x['target_va'] = hex(va)
            x['store_count'] = n
            x['store_fns'] = fns[:5]
            if n == 0:
                x.update({'class': '未決', 'why': 'no_store_in_ir'})
            else:
                x.update({'class': '未決', 'why': 'store_value_unchecked'})
        elif a.pe:
            x['class'], x['why'] = gep_base(fn(int(r['caller'].split('_')[1], 16)), r)
        else:
            x.update({'class': '未決', 'why': 'base_ssa_unmapped'})
        out.append(x)

    json.dump(out, open(a.out, 'w'), ensure_ascii=False, indent=1)
    cnt = collections.Counter(r['class'] for r in out)
    print('[gep-global] 対象 %d 件 (gep %d・global_store %d)' % (len(out), sum(r['conn'] == 'gep' for r in out), sum(r['conn'] == 'global_store' for r in out)))
    print('  実値化   %d' % cnt['実値化'])
    print('  復元不能 %d' % cnt['復元不能'])
    print('  未決     %d' % cnt['未決'])
    print('  未分類   %d' % (len(out) - cnt['実値化'] - cnt['復元不能'] - cnt['未決']))
    for k, v in sorted(collections.Counter((r['conn'], r['why']) for r in out).items()):
        print('  %-14s %-24s %d' % (k[0], k[1], v))
    for r in out:
        if r['conn'] == 'global_store':
            print('  global_store %s va=%s stores=%d %s' % (r['caller'], r['target_va'], r['store_count'], r['store_fns']))


if __name__ == '__main__':
    main()
