#!/usr/bin/env python3
"""fw_entry_fix.py — DLL entry (function_6c13a0 = DllMain) の spill 値修復 (m11_ov.c 方式の IR 版 override).

native 実装 (block18983_PE.bin 0x6c13a0, capstone 実測):
    006c13ab  mov [rbp+0x30], rcx      ; home hinst
    006c13af  mov [rbp+0x3c], edx      ; home reason
    006c13b2  mov [rbp+0x40], r8       ; home reserved
    006c13d4  lea rcx, [rbp+0x48]      ; ┐
    006c13d8  lea rdx, [rip+0x51]      ; │ _StartLib(&ctx, TerminateProc, hinst, reason, [rsp+0x20]=reserved)
    006c13df  mov r8,  [rbp+0x30]      ; │   r8  = hinst  (= DllMain の rcx = %arg1)
    006c13e3  mov r9d, [rbp+0x3c]      ; │   r9  = reason (= DllMain の edx = %arg2)
    006c13f0  call 0x4189c0            ; ┘

RetDec は home 用の未モデル stack slot ([rbp+0x30]/[rbp+0x3c]) を落とし, _StartLib 呼出しの
ABI spill (icall_rewrite 生成) に文字列定数のアドレスを代入した (実測: r8 ← @"$"+0, r9 ← @"$"+0)。
このままでは _StartLib の `r9 == 1 (DLL_PROCESS_ATTACH)` 判定が偽になり InitUnits が空振りする。
本 pass は _StartLib 呼出し直前の spill block の r8/r9 を %arg1/%arg2 に差し替える。
(ir5 の A7 が !insn.addr を除去するため, 「call function_4189c0 直前の spill block」という構造で特定する)

  python3 fw_entry_fix.py IN.ll OUT.ll [--entry 6c13a0] [--site-call 4189c0] [--report r.json]
"""
import argparse, json, re

BLK_R8_GV = '8a1018'        # @global_var_8a1018 = BLK+0x18 (r8 slot)
BLK_R9_CONST = '9048096'    # BLK+0x20 (r9 slot) の即値
BLK_R8_SLOT = '9048088'     # BLK+0x18 (r8 slot) の即値 (BLK 域が 0 埋めの新 IR で使う)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--entry', default='6c13a0')
    ap.add_argument('--site-call', default='4189c0')
    ap.add_argument('--report')
    a = ap.parse_args()
    lines = open(a.src, errors='replace').read().split('\n')
    # entry define を探す
    lo = hi = None
    for i, l in enumerate(lines):
        if l.startswith('define ') and '@function_%s(' % a.entry in l:
            lo = i
            continue
        if lo is not None and l.startswith('}'):
            hi = i
            break
    if lo is None:
        raise SystemExit('entry function_%s が無い' % a.entry)
    # _StartLib 呼出し行
    call_i = None
    for i in range(lo, hi):
        if 'call' in lines[i] and '@function_%s(' % a.site_call in lines[i]:
            call_i = i
            break
    if call_i is None:
        raise SystemExit('entry 内に @function_%s の call が無い' % a.site_call)
    # call 直前 (~50 行) の spill block を走査
    r8_i = r9_i = None
    for i in range(call_i - 1, max(lo, call_i - 60), -1):
        l = lines[i]
        if r8_i is None and '@global_var_%s' % BLK_R8_GV in l and l.lstrip().startswith('store'):
            r8_i = i
        if r9_i is None and l.lstrip().startswith('store i64'):
            m = re.search(r'ptr (%ce[\w.-]+)\b', l)
            if m:
                # %ceX の定義行を探し inttoptr 9048096 か確認
                nm = m.group(1)
                for j in range(i - 1, max(lo, i - 80), -1):
                    dm = re.match(r'\s*%s = inttoptr i64 %s to ptr' % (re.escape(nm), BLK_R9_CONST), lines[j])
                    if dm:
                        r9_i = i
                        break
                    if lines[j].lstrip().startswith('store') or lines[j].startswith('dec_label'):
                        break
        if r8_i is not None and r9_i is not None:
            break
    n8 = n9 = 0
    if r8_i is not None:
        lines[r8_i] = re.sub(r'store .*?, ptr @global_var_%s,' % BLK_R8_GV,
                             'store i64 %%arg1, ptr @global_var_%s,' % BLK_R8_GV, lines[r8_i], count=1)
        n8 = 1
    if r9_i is not None:
        lines[r9_i] = re.sub(r'store i64 [^,]+, ptr ', 'store i64 %arg2, ptr ', lines[r9_i], count=1)
        n9 = 1
    # 新 IR (BLK 域を 0 埋めで再配置した版): spill 値は BLK slot の load (rcx/rdx の復元) のまま残る。
    # native の mov r8,[rbp+0x30] / mov r9d,[rbp+0x3c] に合わせて %arg1 / %arg2 へ直接結ぶ。
    if n8 == 0:
        for i in range(call_i - 1, max(lo, call_i - 60), -1):
            m = re.search(r'store i64 %[\w.-]+, ptr (%ce[\w.-]+)\b', lines[i])
            if m and any(re.match(r'\s*%s = inttoptr i64 %s to ptr' % (re.escape(m.group(1)), BLK_R8_SLOT), lines[j])
                         for j in range(i - 1, max(lo, i - 80), -1)):
                lines[i] = re.sub(r'store i64 %[\w.-]+,', 'store i64 %arg1,', lines[i], count=1)
                n8 = 1
                break
    out = '\n'.join(lines)
    open(a.dst, 'w').write(out)
    rep = {'entry': a.entry, 'site_call': a.site_call, 'r8_fixed': n8, 'r9_fixed': n9}
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[entry_fix]', json.dumps(rep))
    if n8 != 1 or n9 != 1:
        raise SystemExit('[entry_fix] 期待件数と不一致 (r8=%d r9=%d)' % (n8, n9))


if __name__ == '__main__':
    main()
