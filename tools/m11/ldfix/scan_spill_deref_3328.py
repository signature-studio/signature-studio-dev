#!/usr/bin/env python3
"""scan_spill_deref_3328.py — #3328 (CI-149): スピル引数 deref の走査の定義 (取りこぼし・偽陽性・比較側)。

scan_spill_deref_2502.py の定義 (S: 引数レジスタを spill 枠へ退避 → L: 枠を別レジスタへ読み直す →
D: 読み直した値を 1 段 deref して引数レジスタ Rb へ入れる → C: D の後 6 命令以内に call) は変えない。
本スクリプトは、その上に次の 3 種を分けて出す (定義の正本は REPORT_3328.md §1):

  CALL : 2502 の候補 (S→L→D→C)。D と call の間で Rb が再ロード以外で書き換えられても候補のまま
         (演算結果が引数になる形。rewrite_va を記録)。
  EXCL : 2502 の候補のうち、D と call の間で Rb が spill 枠から再ロードされたもの (偽陽性。call 時点の値は
         argK 自身。REPORT_2555 §3 の 3 件)。演算で Rb が書き換わっただけの候補は EXCL にしない。
  COPY : 取りこぼし検出 (0x7888f0)。`mov Rc, argreg` の複写 (Rc は callee-saved に限る) を alias に入れ、
         D の後 6 命令以内の call が直接呼出し (`call 0x...`) のものだけ。間接呼出し (vtable) を除く。
  CMP  : 比較側。S→L→D の後、Rb が call の前 (窓内・書換え前) に cmp/test で読まれる。

使い方: python3 scan_spill_deref_3328.py IR.ll --pe PE.bin --out OUT.json
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
from scan_spill_deref_2502 import ARG, S_RE, REG2_RE, SLOT_RE, DEREF_RE, DST_RE, NOWRITE, full  # noqa: E402

WIN = 6
CALLEE = ('rbx', 'rsi', 'rdi', 'rbp', 'r12', 'r13', 'r14', 'r15')
W32 = {'rcx': 'ecx', 'rdx': 'edx', 'r8': 'r8d', 'r9': 'r9d'}


def deref_events(ins, copy_alias):
    """2502 の scan と同じ alias 規則で、D (1 段 deref して引数レジスタへ入れる命令) を全て返す (C 判定は含めない)"""
    spill, alias, out = {}, {}, []
    for i, x in enumerate(ins):
        op = x.op_str
        dst = DST_RE.match(op)
        if x.mnemonic != 'mov':
            if dst and x.mnemonic not in NOWRITE:
                alias.pop(full(dst.group(1)), None)
            continue
        m = S_RE.match(op)
        if m and m.group(2) in ARG:
            spill[m.group(1)] = m.group(2)
            continue
        m = REG2_RE.match(op)
        if copy_alias and m and m.group(2) in ARG and m.group(1) not in ARG:
            alias[full(m.group(1))] = (m.group(2), 'copy')
            continue
        m = SLOT_RE.match(op)
        if m and m.group(2) in spill:
            alias[full(m.group(1))] = (spill[m.group(2)], 'spill')
            continue
        m = DEREF_RE.match(op)
        if m and full(m.group(2)) in alias and m.group(1) in ARG:
            arg, src = alias[full(m.group(2))]
            out.append({'i': i, 'va': x.address, 'rb': m.group(1), 'arg': arg, 'src': src, 'base': full(m.group(2))})
            alias.pop(m.group(1), None)
            continue
        if dst:
            alias.pop(full(dst.group(1)), None)
    return out


def is_reload(z, stored):
    """spill 枠 (引数を退避した枠) から、そのまま引数レジスタを読み直す命令か (枠の値は argK 自身)"""
    m = SLOT_RE.match(z.op_str)
    return z.mnemonic == 'mov' and m is not None and m.group(2) in stored


def writes(z, reg):
    if z.mnemonic in NOWRITE or z.mnemonic in ('push', 'call', 'jmp') or z.mnemonic.startswith('j'):
        return False
    d = DST_RE.match(z.op_str)
    return d is not None and full(d.group(1)) == reg


def reads(z, reg):
    names = '|'.join(re.escape(n) for n in (reg, W32.get(reg, reg)))
    return re.search(r'(?<![a-z0-9])(%s)(?![a-z0-9])' % names, z.op_str) is not None


def stored_before(ins, i):
    """ins[:i] までに引数レジスタを退避した枠 (slot 名 → 引数レジスタ)"""
    st = {}
    for y in ins[:i]:
        s = S_RE.match(y.op_str)
        if y.mnemonic == 'mov' and s and s.group(2) in ARG:
            st[s.group(1)] = s.group(2)
    return st


def classify(ins, e):
    """D 1 件を CALL / EXCL / COPY / CMP に振り分ける (1 件から複数の kind が出うる)"""
    i, rb = e['i'], e['rb']
    win = [(i + 1 + j, z) for j, z in enumerate(ins[i + 1:i + 1 + WIN])]
    cidx = next((j for j, (_, z) in enumerate(win) if z.mnemonic == 'call'), None)
    kinds = []
    if cidx is not None:
        seg = win[:cidx]
        reload = next((z for k, z in seg if is_reload(z, stored_before(ins, k)) and z.op_str.split(',')[0] == rb), None)
        rewrite = next((z for k, z in seg if writes(z, rb)), None)
        call = win[cidx][1]
        rec = dict(e, call_va='0x%x' % call.address, callee=call.op_str, direct=call.op_str.startswith('0x'))
        if reload is not None:
            kinds.append(dict(rec, kind='EXCL', excl_va='0x%x' % reload.address))
        else:
            extra = {} if rewrite is None else {'rewrite_va': '0x%x' % rewrite.address}
            kinds.append(dict(rec, kind='CALL' if e['src'] == 'spill' else 'COPY', **extra))
    for k, z in win:
        if writes(z, rb):
            break
        if z.mnemonic in ('cmp', 'test') and reads(z, rb):
            if e['src'] == 'spill':
                kinds.append(dict(e, kind='CMP', cmp_va='0x%x' % z.address))
            break
    return kinds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    names = re.findall(r'^define [^\n]*@function_([0-9a-f]+)\(', open(a.ir, errors='replace').read(), re.M)
    m = Machine(a.pe)
    res = {}
    seen = 0
    for nm in names:
        va = int(nm, 16)
        ins = m.disasm_fn(va)
        if ins is None:
            continue
        seen += 1
        for copy_alias in (False, True):
            for e in deref_events(ins, copy_alias):
                if e['src'] != ('copy' if copy_alias else 'spill'):
                    continue
                for r in classify(ins, e):
                    if r['kind'].startswith('COPY') and not (r.get('direct') and r['base'] in CALLEE):
                        continue
                    r.pop('i')
                    r['deref_va'] = '0x%x' % r.pop('va')
                    r['deref_reg'] = r.pop('rb')
                    res.setdefault(r['kind'], {}).setdefault('0x%x' % va, []).append(r)
    summary = {k: {'functions': len(v), 'deref_sites': sum(len(x) for x in v.values())} for k, v in sorted(res.items())}
    out = {'ir_functions': len(names), 'with_pdata': seen, 'summary': summary, 'functions': res}
    json.dump(out, open(a.out, 'w'), indent=1, ensure_ascii=False)
    print('[scan_3328] IR 関数 %d / .pdata 有り %d / %s' % (len(names), seen,
          ' / '.join('%s %d 関数 %d 箇所' % (k, v['functions'], v['deref_sites']) for k, v in summary.items())))


if __name__ == '__main__':
    main()
