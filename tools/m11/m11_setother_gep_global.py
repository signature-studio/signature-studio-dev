#!/usr/bin/env python3
"""set_other 非 imm の gep 17 件 (lea [reg+d]) と書込可能グローバル global_store 3 件の接続判定 (#4891 / M11-N227 / 親 #3907).

入力は m11_setother_mem_class.py の出力 mem_class_rows.json のうち conn が gep / global_store の行。
IR (boot_final 系の final3_base.ll) は変更しない。区分は 実値化 / 復元不能 / 未決 の 3 値で、未分類 0 を確認する。

global_store (書込可能グローバル VA を読む 3 件):
  対象は呼出し元 CFG 上の最後のグローバル格納 (store)。IR で VA を指す store を全件数える。
  store が 0 件なら 未決 (no_store_in_ir)。store があっても値の到達定義は未実装なので 未決 (store_value_unchecked)。
gep (lea [reg+d] の 17 件):
  対象は基底 reg の SSA 値に対する GEP。基底 SSA の特定は未実装のため 未決 (base_ssa_unmapped)。

global_store の PE 側確認 (--pe を渡したとき・#4906 / M11-N229):
  対象 VA を読む命令の走査で、PE コード内の書込み経路を全関数から数える。
  (a) rip 相対の書込み (mov [rip+d], r) (b) lea で VA を作る (c) 即値に VA を持つ (d) .data 内の絶対ポインタ。
  4 経路とも 0 件なら pe_no_direct_store。ただし計算で作ったポインタ経由の書込みは見えない (区分は未決のまま)。

使い方: python3 m11_setother_gep_global.py mem_class_rows.json --ir final3_base.ll --out gep_global_rows.json [--pe PE]
"""
import argparse, collections, json, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))

ap = argparse.ArgumentParser()
ap.add_argument('rows'); ap.add_argument('--ir', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--pe', default=None)
a = ap.parse_args()
rows = json.load(open(a.rows))
ir = open(a.ir).read().split('\n')
TARGET = [r for r in rows if r['conn'] in ('gep', 'global_store')]


def pe_direct_stores(pe_path, targets):
    """PE 全関数の走査 (キャッシュ無し・1 パス)。targets (VA の集合) への 4 経路の件数を返す。"""
    import ldmach, pefile
    m = ldmach.Machine(pe_path)
    hits = {t: collections.Counter() for t in targets}
    for va, (rva, size) in list(m.fns.items()):
        for x in m.cs.disasm(m.read(rva, size), va):
            for o in ldmach.memops_of(m.cs, x) or []:
                r = o.get('rip_rva')
                if r in hits and o.get('write'):
                    hits[r]['rip_store'] += 1
            if x.mnemonic == 'lea' and 'rip +' in x.op_str:
                t = x.address + x.size + int(re.search(r'rip \+ (0x[0-9a-f]+|\d+)', x.op_str).group(1), 0)
                if t in hits:
                    hits[t]['lea'] += 1
            for o in x.operands:
                if o.type == 2 and o.imm in hits:
                    hits[o.imm]['imm'] += 1
    pe = pefile.PE(pe_path, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    for t in targets:
        ab = struct.pack('<Q', ib + t)
        for s in pe.sections:
            d = s.get_data()
            i = d.find(ab)
            while i != -1:
                hits[t]['abs_ptr'] += 1
                i = d.find(ab, i + 1)
    return hits


def store_count(va):
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


out = []
cache = {}
gvas = {int(r['def'], 16) + 7 + int(re.search(r'\[rip \+ (0x[0-9a-f]+|\d+)\]', r['def_insn']).group(1), 0)
        for r in TARGET if r['conn'] == 'global_store'}
pe_hits = pe_direct_stores(a.pe, gvas) if a.pe and gvas else {}
for r in TARGET:
    x = dict(r)
    if r['conn'] == 'global_store':
        va = int(r['def'], 16) + 7 + int(re.search(r'\[rip \+ (0x[0-9a-f]+|\d+)\]', r['def_insn']).group(1), 0)
        if va not in cache:
            cache[va] = store_count(va)
        n, fns = cache[va]
        x['target_va'] = hex(va)
        x['store_count'] = n
        x['store_fns'] = fns[:5]
        if a.pe:
            c = pe_hits.get(va, collections.Counter())
            x['pe_hits'] = {k: c.get(k, 0) for k in ('rip_store', 'lea', 'imm', 'abs_ptr')}
        if n == 0:
            x.update({'class': '未決', 'why': 'no_store_in_ir'})
        else:
            x.update({'class': '未決', 'why': 'store_value_unchecked'})
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
