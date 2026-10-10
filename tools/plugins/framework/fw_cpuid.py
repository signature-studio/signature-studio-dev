#!/usr/bin/env python3
"""fw_cpuid.py — `__asm_cpuid*` (RetDec の cpuid helper, aggregate 戻り) を固定署名へ正規化する.

RetDec は cpuid を `call %N @__asm_cpuid[__(n)](i32 leaf)` (戻り = {i32,i32,i32,i32} aggregate) に
するが, chunk 毎に aggregate 型名 (%0..%3) と helper 名が揺れ, liftlib simd gen の canon 化が
不正シンボル (`__asm_cpuid__?d`) になる。本 pass は単一の %fw_cpuid_ret 型 + @fw_cpuid に統一し,
直後の extractvalue %N %res, k を %fw_cpuid_ret 袠りに書き換える。実装は fw_rt.c。

  python3 fw_cpuid.py IN.ll OUT.ll
"""
import re, sys


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src, errors='replace').read().split('\n')
    out = []
    call_re = re.compile(r'call (%\d+) @__asm_cpuid(?:__(\d+))?\((i32 [^)]*)\)')
    n = 0
    pending = []      # (result_name, old_type) — 直後の extractvalue を書き換える
    for l in lines:
        if l.startswith('declare ') and '@__asm_cpuid' in l:
            continue
        m = call_re.search(l)
        if m:
            res = None
            rm = re.match(r'\s*(%[\w.-]+) = ', l)
            if rm:
                res = rm.group(1)
            l = call_re.sub('call %fw_cpuid_ret @fw_cpuid(\\3)', l, count=1)
            pending.append((res, m.group(1)))
            n += 1
            out.append(l)
            continue
        # 直後の extractvalue 書き換え (call の result を使うもの)
        if pending:
            for res, oldty in list(pending):
                if res and ('extractvalue %s %s,' % (oldty, res)) in l:
                    l = l.replace('extractvalue %s %s,' % (oldty, res),
                                  'extractvalue %%fw_cpuid_ret %s,' % res)
                # res が他の命令に使われたら pending から外す (extractvalue 群は call 直後に固まる)
            for res, oldty in list(pending):
                if not re.search(r'extractvalue %s %s,' % (oldty, res), l) and re.search(r'\b%s\b' % re.escape(res), l):
                    pending.remove((res, oldty))
        out.append(l)
    # 型と declare を最初の define の前に挿入
    ins = ['%fw_cpuid_ret = type { i32, i32, i32, i32 }',
           'declare %fw_cpuid_ret @fw_cpuid(i32) local_unnamed_addr']
    for i, l in enumerate(out):
        if l.startswith('define '):
            out[i:i] = ins
            break
    open(dst, 'w').write('\n'.join(out))
    print('[cpuid] normalized call sites: %d' % n)


if __name__ == '__main__':
    main()
