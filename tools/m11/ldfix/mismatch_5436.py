#!/usr/bin/env python3
"""mismatch_5436.py — #5436 (CI-219): judge_copy_3382.py の MISMATCH 行の呼出し件数不一致を原因別に分類する。

入力: judge_copy_3382.py の出力 JSON (--judge) と IR・PE。
各 MISMATCH 行 (関数 VA・call VA・callee) について、機械語の同じ呼出し先の件数と IR の件数を比べ、次の原因に分ける:
  THUNK     : callee が .text の jmp [IAT] (import thunk)。IR は import 名の呼出し (例 SysFreeString) として持つため @function_ に出ない
  ABSENT    : callee が関数本体の IR に 1 件も無い (thunk でない)
  IR_FEWER  : IR の件数が機械語より少ない (呼出しが落ちている)
  IR_MORE   : IR の件数が機械語より多い (機械語の 1 箇所が IR で複製されている)
  OTHER     : 上のどれでもない (人手で窓を読む)

使い方: python3 mismatch_5436.py IR.ll --pe PE.bin --judge JUDGE.json
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
from verify_deref_sites_2555 import fn_bodies  # noqa: E402

CALL_RE = re.compile(r'^\s*(?:%[\w.]+ = )?call [^\n]*@function_([0-9a-f]+)\((.*)\)\s*$', re.M)


def thunk_name(m, va):
    """jmp [rip+disp] の IAT スロット名。thunk でなければ None"""
    ins = list(m.cs.disasm(m.read(va - m.base, 8), va))
    if not ins or ins[0].mnemonic != 'jmp' or 'rip' not in ins[0].op_str:
        return None
    x = ins[0]
    disp = int(re.search(r'rip \+ (0x[0-9a-f]+)', x.op_str).group(1), 16)
    return iat_names(m).get(x.address + x.size + disp, 'IAT?')


def iat_names(m):
    if not hasattr(m, '_iat'):
        import pefile
        pe = pefile.PE(m.path, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        table = {}
        for e in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
            dll = e.dll.decode('latin1')
            for imp in e.imports:
                name = imp.name.decode('latin1') if imp.name else 'ord%s' % imp.ordinal
                table[imp.address] = '%s!%s' % (dll, name)
        m._iat = table
    return m._iat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--judge', required=True)
    a = ap.parse_args()
    rows = [r for r in json.load(open(a.judge)) if r['verdict'] == 'MISMATCH']
    fns = sorted({r['fn'][2:] for r in rows})
    bodies = fn_bodies(a.ir, set(fns))
    m = Machine(a.pe)
    m.path = a.pe
    tally = Counter()
    for r in rows:
        fva = int(r['fn'], 16)
        callee = r['callee']
        tva = int(callee, 16)
        mcount = sum(1 for x in m.disasm_fn(fva) or [] if x.mnemonic == 'call' and x.op_str == callee)
        body = bodies.get(r['fn'][2:]) or ''
        icount = sum(1 for mm in CALL_RE.finditer(body) if int(mm.group(1), 16) == tva)
        name = thunk_name(m, tva)
        if name:
            cause = 'THUNK'
        elif icount == 0:
            cause = 'ABSENT'
        elif icount < mcount:
            cause = 'IR_FEWER'
        elif icount > mcount:
            cause = 'IR_MORE'
        else:
            cause = 'OTHER'
        tally[cause] += 1
        print('%s call=%s callee=%s k=%s machine=%d ir=%d %s %s' % (
            r['fn'], r['call_va'], callee, r['k'], mcount, icount, cause, name or ''))
    print('[mismatch_5436] MISMATCH %d 行: %s' % (len(rows), dict(tally)))


if __name__ == '__main__':
    main()
