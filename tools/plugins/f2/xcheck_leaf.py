#!/usr/bin/env python3
"""PLG-F2-3 (#515) 別算法検算: leaf_list.py (closure_stats.py の IR 解析 + audit_icall.py の recursive descent) とは独立に、
対象 23 関数の集合を再導出して突合する。

  IR 側    : p.final.ll を `define` 単位に切り、本文の `call`/`invoke` の callee トークンを数える (closure_stats.py の正規表現は使わない)
             IR leaf = callee が `@__asm_*` / `@llvm.*` 以外の @name でも %reg でもない (= 呼ぶものが無い)
  機械語側 : 閉包 ranges を関数単位に capstone 線形 sweep し、call 命令を 3 種に分類
             (a) 即値 call (直接) (b) rip 相対で IAT slot を指す call (import) (c) それ以外の間接 call
             強い leaf = (a)(b)(c) が全て 0
  突合     : {IR leaf かつ (c)=0} == leaf.json の集合 か。 加えて 強い leaf の個数、(a)(b) を持つのに IR leaf な関数 (= 直接 call/import 呼出しが IR から脱落) を報告
  python3 tools/plugins/f2/xcheck_leaf.py
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')
leaf = json.load(open(os.path.join(W, 'f2', 'leaf.json')))
want = {(r['block'], int(r['va'], 16)) for r in leaf}
blocks = sorted(int(os.path.basename(p).split('.')[0]) for p in os.listdir(os.path.join(W, 'f2')) if p.endswith('.icall.json'))

CALL = re.compile(r'\b(?:call|invoke)\b[^\n]*?\s(@[\w.$]+|%[\w.$]+)\(')


def ir_leaf(path):
    out, cur, calls = {}, None, []
    for ln in open(path, errors='replace'):
        if ln.startswith('define '):
            m = re.search(r'@(function_[0-9a-f]+)\(', ln)
            cur, calls = (m.group(1) if m else None), []
        elif ln.startswith('}') and cur:
            out[int(cur[len('function_'):], 16)] = not any(not (c.startswith('@__asm_') or c.startswith('@llvm.')) for c in calls)
            cur = None
        elif cur:
            calls += CALL.findall(ln)
    return out


got, strong_all, ir_only_dropped = set(), 0, []
for b in blocks:
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b), fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {i.address for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) for i in d.imports if i.address}
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    irl = ir_leaf(os.path.join(W, 'batch', str(b), 'p.final.ll'))
    for r in open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % b)).read().replace(',', '\n').split():
        lo, hi = (int(x, 16) for x in r.split('-'))
        n_dir = n_iat = n_ind = 0
        for i in md.disasm(pe.get_data(lo - base, hi - lo + 1), lo):
            if i.mnemonic != 'call':
                continue
            o = i.operands[0]
            if o.type == X86_OP_IMM:
                n_dir += 1
            elif o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP and (i.address + i.size + o.mem.disp) in iat:
                n_iat += 1
            else:
                n_ind += 1
        il = irl.get(lo)
        if il and n_ind == 0:
            got.add((b, lo))
        if il and n_ind == 0 and (n_dir or n_iat):
            ir_only_dropped.append((b, hex(lo), n_dir, n_iat))
        strong_all += bool(il and not (n_dir or n_iat or n_ind))
print('別算法で再導出: %d 関数 (IR leaf かつ 機械語 間接 call 0)' % len(got))
print('leaf.json      : %d 関数' % len(want))
print('集合一致: %s  (差分 got-want=%s want-got=%s)' % ('EQ' if got == want else 'DIFF', sorted(got - want), sorted(want - got)))
print('強い leaf (機械語に call 命令が 1 つも無い & IR leaf): %d 関数' % strong_all)
print('IR leaf なのに機械語に直接 call / import call がある (IR から call が脱落): %d 関数 %s' % (len(ir_only_dropped), ir_only_dropped))
sys.exit(0 if got == want else 1)
