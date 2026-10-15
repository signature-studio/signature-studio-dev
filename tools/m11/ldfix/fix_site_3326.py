#!/usr/bin/env python3
"""fix_site_3326.py — #3326 (CI-148): 同類型 (DEFECTS.md D4) の誤り 5 箇所を site 単位で直す。

同類型: 機械語は、スピルした引数 argK の指す値 (*argK) を呼出し先の引数に渡すのに、base IR は
argK そのもの (アドレス) を渡している。REPORT_2555.md §2 の表で「誤り」と判定された箇所のうち、
IR の該当引数が `%argK` (または `%argK` の trunc / ptrtoint / `%0` = ptrtoint argK) の単純な形のもの。

各 site について次を行う (fail-closed):
  1. 機械語照合: スピル命令・argK の再読込み・1 段 deref・call を capstone で照合 (mnemonic と operand 文字列が
     完全一致しなければ assert で止める)。
  2. IR 照合: 対象行が base 形 (1 件だけ一致) のときだけ書き換える。適用済みの IR は拒否する (二重適用の防止)。
  3. 書き換え: 呼出しの直前に argK の 1 段 load を置き、引数をその値に差し替える (機械語の deref 位置と一致)。

範囲外 (本ファイルでは直さない): 0x44f040・0x47b4a0・0x47cf10・0xc40770 (比較・GEP・null 経路の複雑型。子 issue)、
0x450560 (fix_450560.py が直す)、0x6074b0 (ldfix.py の既存 pass が直す)、0x413340 の 3 番目引数 (別類型の疑い)。

使い方:
  python3 fix_site_3326.py IN.ll OUT.ll --pe PE.bin
  python3 fix_site_3326.py IN.ll OUT.ll --pe PE.bin --negctl   # ネガティブコントロール (拒否されることを確認)
"""
import argparse
import copy
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from ldmach import Machine  # noqa: E402

# 各 site: 機械語の期待 (VA, mnemonic, op_str)・base IR の対象行 (old)・置換後の行 (new)
# new の最後の行が呼出し (または trunc) で、その前に argK の 1 段 load を置く。
SITES = [
    dict(name='0x413340 -> 0x412fc0 (arg1, k=2)', fn=0x413340, call_va=0x4133bc,
         machine=[(0x413349, 'mov', 'qword ptr [rsp + 0x30], rcx'),
                  (0x4133a5, 'mov', 'rax, qword ptr [rsp + 0x30]'),
                  (0x4133aa, 'mov', 'rcx, qword ptr [rax]'),
                  (0x4133bc, 'call', '0x412fc0')],
         old='%20 = trunc i64 %arg1 to i32',
         new=['%ldfx3326a_p = inttoptr i64 %arg1 to ptr',
              '%ldfx3326a = load i64, ptr %ldfx3326a_p, align 8',
              '%20 = trunc i64 %ldfx3326a to i32']),
    dict(name='0x44fb40 -> 0x414850 (arg1, k=2)', fn=0x44fb40, call_va=0x44fbbc,
         machine=[(0x44fb51, 'mov', 'qword ptr [rsp + 0x50], rcx'),
                  (0x44fbac, 'call', '0x414850'),
                  (0x44fbb4, 'mov', 'rax, qword ptr [rsp + 0x50]'),
                  (0x44fbb9, 'mov', 'rcx, qword ptr [rax]'),
                  (0x44fbbc, 'call', '0x414850')],
         old='%21 = call i64 @function_414850(i64 %arg2)',
         new=['%ldfx3326b_p = inttoptr i64 %arg1 to ptr',
              '%ldfx3326b = load i64, ptr %ldfx3326b_p, align 8',
              '%21 = call i64 @function_414850(i64 %ldfx3326b)']),
    dict(name='0x450420 -> 0x4503c0 (arg1 -> argpos 2, k=1)', fn=0x450420, call_va=0x450457,
         machine=[(0x450424, 'mov', 'qword ptr [rsp + 0x30], rcx'),
                  (0x45044f, 'mov', 'rax, qword ptr [rsp + 0x30]'),
                  (0x450454, 'mov', 'rdx, qword ptr [rax]'),
                  (0x450457, 'call', '0x4503c0')],
         old='%11 = call i64 @function_4503c0(i64 %arg2, i64 %arg2)',
         new=['%ldfx3326c_p = inttoptr i64 %arg1 to ptr',
              '%ldfx3326c = load i64, ptr %ldfx3326c_p, align 8',
              '%11 = call i64 @function_4503c0(i64 %arg2, i64 %ldfx3326c)']),
    dict(name='0x4506e0 -> 0x4133f0 (arg1 -> argpos 2, k=1)', fn=0x4506e0, call_va=0x45073c,
         machine=[(0x4506e8, 'mov', 'qword ptr [rsp + 0x30], rcx'),
                  (0x450734, 'mov', 'rax, qword ptr [rsp + 0x30]'),
                  (0x450739, 'mov', 'rdx, qword ptr [rax]'),
                  (0x45073c, 'call', '0x4133f0')],
         old='%19 = call i64 @function_4133f0(i64 %0, i64 %0)',
         new=['%ldfx3326d_p = inttoptr i64 %arg1 to ptr',
              '%ldfx3326d = load i64, ptr %ldfx3326d_p, align 8',
              '%19 = call i64 @function_4133f0(i64 %0, i64 %ldfx3326d)']),
    dict(name='0x7888f0 -> 0x4133f0 (rbx 複写経由の arg1 -> argpos 2, k=1)', fn=0x7888f0, call_va=0x788957,
         machine=[(0x7888fb, 'mov', 'rbx, rcx'),
                  (0x7888fe, 'mov', 'rsi, rdx'),
                  (0x788951, 'mov', 'rcx, rsi'),
                  (0x788954, 'mov', 'rdx, qword ptr [rbx]'),
                  (0x788957, 'call', '0x4133f0')],
         old='%16 = call i64 @function_4133f0(i64 %arg2, i64 %arg2)',
         new=['%ldfx3326e_p = inttoptr i64 %arg1 to ptr',
              '%ldfx3326e = load i64, ptr %ldfx3326e_p, align 8',
              '%16 = call i64 @function_4133f0(i64 %arg2, i64 %ldfx3326e)']),
]


def verify_machine(m, site):
    fn = site['fn']
    code = m.read(fn - 0x400000, site['call_va'] + 16 - fn)
    import capstone
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    got = {i.address: (i.mnemonic, i.op_str) for i in cs.disasm(code, fn)}
    for addr, mn, ops in site['machine']:
        assert addr in got, '%s: 機械語 0x%x が逆アセンブルできない' % (site['name'], addr)
        assert got[addr] == (mn, ops), '%s: 機械語 0x%x が想定と違う: %r != %r' % (site['name'], addr, got[addr], (mn, ops))
    return len(site['machine'])


def patch_site(src, site):
    fn = site['fn']
    fns = list(re.finditer(r'^define [^\n]*@function_%x\(.*?\n}\n' % fn, src, re.M | re.S))
    assert len(fns) == 1, '%s: function の定義が 1 件でない: %d' % (site['name'], len(fns))
    body = fns[0].group(0)
    lines = body.split('\n')
    idx = [i for i, ln in enumerate(lines) if ln.strip() == site['old']]
    assert len(idx) == 1, '%s: base 行が 1 件でない (%d 件。適用済み or 想定外の IR): %r' % (site['name'], len(idx), site['old'])
    i = idx[0]
    ind = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
    lines[i:i + 1] = [ind + x for x in site['new']]
    return src[:fns[0].start()] + '\n'.join(lines) + src[fns[0].end():]


def apply_all(src, sites, m):
    n = 0
    for s in sites:
        n += verify_machine(m, s)
        src = patch_site(src, s)
    return src, n


def negctl(src, m):
    """ネガティブコントロール: 次の 4 つはすべて拒否されなければならない (拒否されなければ exit 1)"""
    out, _ = apply_all(src, SITES, m)
    cases = []
    # NC1: 二重適用 (適用済みの IR に再適用)
    cases.append(('NC1 二重適用', out, SITES))
    # NC2: 機械語の deref の operand を 1 つ変える (機械照合で拒否)
    s2 = copy.deepcopy(SITES)
    s2[0]['machine'][2] = (0x4133aa, 'mov', 'rcx, qword ptr [rax + 8]')
    cases.append(('NC2 機械照合 (deref operand の改変)', src, s2))
    # NC3: call 位置の VA をずらす (機械語の対応が取れない)
    s3 = copy.deepcopy(SITES)
    s3[2]['machine'][3] = (0x450458, 'call', '0x4503c0')
    cases.append(('NC3 call VA のずれ', src, s3))
    # NC4: IR 行が base 形でない (対象行の引数を変えた IR)
    s4 = copy.deepcopy(SITES)
    s4[4]['old'] = '%16 = call i64 @function_4133f0(i64 %arg2, i64 %arg1)'
    cases.append(('NC4 IR base 形の不一致', src, s4))
    bad = 0
    for name, text, sites in cases:
        try:
            apply_all(text, sites, m)
        except AssertionError as e:
            print('[fix_site_3326] %s: 拒否 OK (%s)' % (name, str(e)[:120]))
        else:
            print('[fix_site_3326] %s: 拒否されなかった (NG)' % name)
            bad += 1
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--negctl', action='store_true')
    a = ap.parse_args()
    m = Machine(a.pe)
    src = open(a.src, errors='replace').read()
    if a.negctl:
        bad = negctl(src, m)
        print('[fix_site_3326] ネガティブコントロール: NG %d 件' % bad)
        sys.exit(1 if bad else 0)
    out, n = apply_all(src, SITES, m)
    assert out != src
    open(a.dst, 'w').write(out)
    print('[fix_site_3326] 機械語 %d 命令を検証 (%d site)。site 単位で argK の 1 段 load を挿入' % (n, len(SITES)))


if __name__ == '__main__':
    main()
