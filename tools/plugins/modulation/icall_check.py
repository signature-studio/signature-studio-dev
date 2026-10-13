#!/usr/bin/env python3
"""間接 call の脱落監査: 閉包の機械語にある非 IAT 間接 call (静的 site) と、lift 後 IR (work/batch/<block>/p.final.ll) の間接 call の件数を比べる。
  - 静的 site / IR 側は tools/icall/audit_icall.py (recursive descent) の `call_non_iat` / `ir_call_ind_total`
  - 別算法の検算: 閉包 ranges を capstone の線形 sweep で逆アセンブルして数えた非 IAT 間接 call (audit と食い違えば測定自体が不正 = exit 1)
  - 判定: IR の間接 call が静的 site より少ない block は「脱落あり」。 `emcc -c` の通過はこれを検出しない ((icall §4) D1。 PLG-F2 #199 の発見)
usage: icall_check.py [--gate] [--ir-name p.final.ll] [--batch-dir work/batch] [--facts work/modulation/facts.json] [--out work/modulation/icall]
  既定: 表と件数を出し、 検算の不一致 (または audit 失敗) のときだけ exit 1。 脱落ありは exit 0 のまま「k/8 本」と出す (e2e は測定として使う)
  --gate: 脱落あり (IR < 静的) が 1 本でもあれば exit 1
前提: modulation_e2e.sh 実行済み (work/closure, work/batch)。 出力: work/modulation/icall/<block>.icall.json
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
import pefile  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--gate', action='store_true')
ap.add_argument('--ir-name', default='p.final.ll')
ap.add_argument('--batch-dir', default=os.path.join(P, 'work', 'batch'))
ap.add_argument('--out', default=os.path.join(P, 'work', 'modulation', 'icall'))
ap.add_argument('--facts', default=os.path.join(P, 'work', 'modulation', 'facts.json'))
a = ap.parse_args()
F = json.load(open(a.facts))
OUT = a.out
os.makedirs(OUT, exist_ok=True)


def sweep(pe, ranges_txt):
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {i.address for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) for i in d.imports if i.address}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    n = 0
    for r in ranges_txt.replace(',', '\n').split():
        lo, hi = (int(x, 16) for x in r.split('-'))
        for i in md.disasm(pe.get_data(lo - base, hi - lo + 1), lo):
            if i.mnemonic != 'call' or i.operands[0].type == X86_OP_IMM:
                continue
            o = i.operands[0]
            if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP and (i.address + i.size + o.mem.disp) in iat:
                continue
            n += 1
    return n


print('| プラグイン | block | 静的 site (audit) | 別算法 (線形 sweep) | call あり関数 | IR の間接 call | 入口スロットの静的 → IR | 脱落 |')
print('|---|--:|--:|--:|--:|--:|---|---|')
tot = [0, 0, 0]
ndrop = nbad = 0
for name, f in F.items():
    b = f['block']
    rt = open(os.path.join(P, 'work', 'closure', 'block%05d.ranges.txt' % b)).read()
    ff = os.path.join(OUT, '%d.funcs' % b)
    open(ff, 'w').write('\n'.join(r.split('-')[0] for r in rt.replace(',', '\n').split()) + '\n')
    pe_path = os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b)
    js = os.path.join(OUT, '%d.icall.json' % b)
    r = subprocess.run([sys.executable, os.path.join(P, '..', 'icall', 'audit_icall.py'), '--pe', pe_path,
                        '--ir', os.path.join(a.batch_dir, str(b), a.ir_name), '--funcs', ff, '--json', js, '--label', str(b)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print('icall_check: audit_icall.py 失敗 block %d: %s' % (b, r.stderr[-300:]), file=sys.stderr)
        sys.exit(1)
    j = json.load(open(js))
    sw = sweep(pefile.PE(pe_path, fast_load=True), rt)
    st, ir = j['call_non_iat'], j['ir_call_ind_total']
    c = json.load(open(os.path.join(P, 'work', 'closure', 'block%05d.json' % b)))
    cmp_ = {x['fn']: x for x in j['per_fn_cmp']}
    ent = ['%s %d→%d' % (s, cmp_[v]['static_call_ind'], cmp_[v]['ir_call_ind']) for s, v in c['entries'].items()
           if v in cmp_ and cmp_[v]['static_call_ind']]
    drop = ir < st
    ndrop += drop
    nbad += sw != st
    tot[0] += st; tot[1] += sw; tot[2] += ir
    print('| %s | %d | %d | %d%s | %d | %d | %s | %s |' % (name, b, st, sw, '' if sw == st else ' (**不一致**)', j['fns_with_indirect_call'], ir,
                                                          ', '.join(ent) or '—', '**あり**' if drop else 'なし'))
print('| 計 | | %d | %d | | %d | | |' % tuple(tot))
print('icall_check: 検算 %s (audit と線形 sweep の不一致 %d 本) / IR の間接 call が静的 site に満たない殻 = %d/%d 本' % (
    'OK' if not nbad else 'NG', nbad, ndrop, len(F)))
sys.exit(1 if nbad or (a.gate and ndrop) else 0)
