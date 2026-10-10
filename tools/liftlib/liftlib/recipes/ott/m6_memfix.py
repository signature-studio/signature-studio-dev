#!/usr/bin/env python3
"""m6_memfix.py (M6b): lift IR 内の破損 CRT memmove/memset define を C 実装へ置換.

問題 (M6 検証で特定):
  - function_1801a2a20 (CRT memmove 系, define あり) の IR 本体は
    * 32 byte copy ループが retdec 自動生成 unverifield i256 型 helper
      (@__asm_vmovdqu / @__asm_vmovdqa / @__asm_vmovntdq) を使用 — C 側で i256 は
      ABI を一致させられない (_BitInt(256) 非対応)。
    * 内部で `call i64 @function_1801a2a00()` — 部分リフト (--select-ranges) の
      引数解析破損 (0-arg call, dst/src/n が IR 上存在しない)。
    * vmovdqa の dst-store が IR 上失われている (32B copy が store なしで lift)。
  - function_1801a30d0 (CRT memset 系) も同様に `call void @function_1801a30b0()`
    (0-arg) を残し, 内部 store の正体が不明。

対応: この 2 define を丸ごと取り除き, C 側 (m6_rt.c) 提供
  function_1801a2a20(dst=arg1, src=arg2, n=arg3) = memmove   [(i64,i64,i64,i64) → i64]
  function_1801a30d0(dst=arg1, ch=arg2, n=arg3) = memset     [(i64,i32,i64) → i64]
へ置換する。m6_rt.c はこれらと同一 signature で定義する。
副次効果: i256 系 helper の未解決 import と a2a00/a30b0 の 0-arg 不一致が消える。

使い方: python3 m6_memfix.py SRC_LL DST_LL
"""
import re
import sys

TARGETS = {
    'function_1801a2a20': 'declare i64 @function_1801a2a20(i64, i64, i64, i64) local_unnamed_addr',
    'function_1801a30d0': 'declare i64 @function_1801a30d0(i64, i32, i64) local_unnamed_addr',
}

# 削除対象の call 行 (結果値が呼出後利用されない retdec 0-arg tail / 破損 lift):
#   function_1801a9a6c()/1801a9b38() = sqrt/sqrtf の domain-check CRT 報告経路
#   (実体 = x86 では xmm0 を受け取り, 値は SSE 汎用で再計算される; lift では 0-arg
#    で引数ドロップ + 報告機構 (c1584→c20c8→...) が RetDec の stack OOB を起こす。
#    全 4 呼出 site で戻り値未使用を確認済み (m6b t1 再現) → 删 (call 削除) で問題なし)
DROP_CALL_RES = [re.compile(r'^  %[\w.\-]+ = call i64 @function_1801a9a6c\(\)$'),
                 re.compile(r'^  %[\w.\-]+ = call i64 @function_1801a9b38\(\)$')]


def remove_define(lines, name, declare_line, report):
    start = None
    for i, l in enumerate(lines):
        if re.match(r'^define [^{]*@' + name + r'\(', l):
            start = i
            break
    if start is None:
        report.append('MISS define: ' + name)
        return lines
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j].rstrip('\n') == '}':
            end = j
            break
    if end is None:
        report.append('MISS close-brace: ' + name)
        return lines
    report.append('removed define %s: lines %d..%d (%d lines)' % (name, start + 1, end + 1, end - start + 1))
    return lines[:start] + [declare_line, ''] + lines[end + 1:]


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src).read().split('\n')
    report = []
    for name, decl in TARGETS.items():
        lines = remove_define(lines, name, decl, report)
    ok = all(not r.startswith('MISS') for r in report)
    for r in report:
        print('[memfix]', r)

    # (2) 死 code 削除: 戻り値未使用の破損 0-arg sqrt 報告 call
    kept, ndrop = [], 0
    for ln in lines:
        if any(rx.match(ln) for rx in DROP_CALL_RES):
            ndrop += 1
            continue
        kept.append(ln)
    lines = kept
    print('[memfix] dropped dead 0-arg sqrt-report calls (a9a6c/a9b38):', ndrop)

    # (3) 検収: i256 helper 呼出 residual 及び define/declare 二重
    n256 = 0
    for ln in lines:
        if 'call' in ln and ('@__asm_vmovdqu(' in ln or '@__asm_vmovdqa(' in ln or '@__asm_vmovntdq(' in ln):
            n256 += 1
    print('[memfix] i256 helper call residual:', n256)
    if n256:
        ok = False
    for name, decl in TARGETS.items():
        n = sum(1 for ln in lines if ln.startswith('define ') and '@' + name + '(' in ln)
        d = sum(1 for ln in lines if ln.startswith('declare ') and '@' + name + '(' in ln)
        print('[memfix] %s: defines=%d declares=%d (define=0 / declare>=1 が正)' % (name, n, d))
        if n:
            ok = False
    print('[memfix] lines out:', len(lines))
    open(dst, 'w').write('\n'.join(lines))
    print('[memfix] wrote', dst)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
