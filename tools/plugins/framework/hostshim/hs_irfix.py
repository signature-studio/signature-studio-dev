#!/usr/bin/env python3
"""hs_irfix.py — CAB-195: CreatePlugInstance (function_6bdde0) の引数経路修復。

背景: fw_stage2 の lift では export 入口 function_6bdde0 が `define i64 @function_6bdde0()`
(0 引数) になり、rcx(Host)/rdx(Tag) が RetDec の unknown-value 定数で置換されている
(実 IR 実測。DllMain 0x6c13a0 は %arg1..4 付きで正常 — fw_entry_fix 対象)。
このままでは Host/Tag が定数になり host 呼出記録も [this+0xbc] も成立しない。

定数名は lift 版ごとに RetDec が振り直す (旧 IR: @689=Host / @688=Tag、
現行 fw_flat4_canon3.ll: @396=Host / @395=Tag)。役割は store 先 (BLK+0x08/+0x10/+0x18) と
ptrtoint の位置で決まるので、body に現れる既知の名前組を検出して使う。どれも無ければ失敗する。

修復 (関数 body 内のみ, 計 8 箇所):
  1. define に (i64 %arg1, i64 %arg2) を付与 → fw_table.py が BLK-ABI wrapper
     (BLK+8=Host, +0x10=Tag) を自動生成する
  2. `store Host → BLK+0x08` (rcx=Host)  x2 → store i64 %arg1
  3. `store Tag → BLK+0x10` (rdx=Tag)   x2 → store i64 %arg2
  4. `store Tag → BLK+0x18` (r8=Tag)    x1 → store i64 %arg2  (TTestPlug.Create の r8)
  5. `%ce18.. = ptrtoint ptr Host`       x1 → add i64 %arg1, 0  (r9=Host)
  6. `%ce17.. = ptrtoint ptr Tag`        x1 → add i64 %arg2, 0  (rdx=(Tag&~0xff)|1 の素)
  7. 版チェック呼出 `%12 = call i64 @function_6b8a60()` → `add i64 1, 0`
     (native 6b8a60 は r8=0 で test/jle により no-op → 常に al=1。lift 後の 6b8a60 は
      RetDec が引数を定数置換しているため IR 修復が増幅する — r8=0 経路の厳密な
      挙動は戻り値 1 なのでこれで等価。r8>0 経路は本 smoke 未到達, REPORT §5)
  class ref (0x6BDC60) / r8=0 (版チェック) / r9=0x70E3C0 の定数 store は実機実測どおり保持。

使い方: python3 hs_irfix.py <in.ll> <out.ll>
出力: 置換件数を検証し、期待数と違えば exit 1 (本修復のリグレッション検知)。
"""
import re, sys

# (Host, Tag) の定数名の既知の組。新しい lift 版で名前が変わったらここに足す。
CONST_SETS = [('@689', '@688'), ('@396', '@395')]


def pick_consts(body):
    text = '\n'.join(body)
    for h, t in CONST_SETS:
        if ('ptr %s,' % h) in text and ('ptr %s,' % t) in text:
            return h, t
    print('[hs_irfix] Host/Tag 定数が function_6bdde0 に無い (既知の組: %s) — lift の前提が変わった'
          % CONST_SETS)
    sys.exit(1)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src, errors='replace').read().split('\n')
    # function_6bdde0 の body 範囲を特定
    lo = hi = None
    for i, l in enumerate(lines):
        if l.startswith('define ') and '@function_6bdde0(' in l:
            lo = i
        elif lo is not None and l == '}':
            hi = i
            break
    if lo is None:
        print('[hs_irfix] function_6bdde0 が見つからない'); sys.exit(1)
    body = lines[lo:hi + 1]
    H, T = pick_consts(body)
    n = [0]

    def sub(old, new, expect):
        cnt = 0
        out = []
        for l in body:
            if old in l:
                l = l.replace(old, new)
                cnt += 1
            out.append(l)
        body[:] = out
        if cnt != expect:
            print('[hs_irfix] 置換数不一致 (%d != %d): %s' % (cnt, expect, old[:80]))
            sys.exit(1)
        n[0] += cnt

    # 1. signature (0 引数 → 2 引数)
    sub('define i64 @function_6bdde0() local_unnamed_addr {',
        'define i64 @function_6bdde0(i64 %arg1, i64 %arg2) local_unnamed_addr {', 1)
    # 2/3. Host/Tag の定数 store → 引数
    ST = ', ptr inttoptr (i64 %d to ptr), align 8'
    sub('store ptr getelementptr inbounds ([2 x i8], ptr %s, i64 0, i64 0)' % H + (ST % 9048072),
        'store i64 %arg1' + (ST % 9048072), 2)
    sub('store ptr getelementptr inbounds ([2 x i8], ptr %s, i64 0, i64 0)' % T + (ST % 9048080),
        'store i64 %arg2' + (ST % 9048080), 2)
    sub('store ptr getelementptr inbounds ([2 x i8], ptr %s, i64 0, i64 0)' % T + (ST % 9048088),
        'store i64 %arg2' + (ST % 9048088), 1)
    # 5/6. ptrtoint 定数 → 引数 (r9=Host, rdx 素)
    sub('%%ce18n11_function_6bdde0 = ptrtoint ptr %s to i64' % H,
        '%ce18n11_function_6bdde0 = add i64 %arg1, 0', 1)
    sub('%%ce17n11_function_6bdde0 = ptrtoint ptr %s to i64' % T,
        '%ce17n11_function_6bdde0 = add i64 %arg2, 0', 1)
    # 7. 版チェック (r8=0 → no-op → al=1): 呼出を定数へ + ret slot への store。
    #    呼出側は wasm 戻り値 %12 でなく abi_ret_load (BLK+0x80 再読込) で al を判定する
    #    ため、定数 1 を BLK+0x80 に store しないと al=0 扱いで ctor が即 return 0 する
    #    (hs_e2e 実測: plug=0 / rec=0 — 6bdde0 が版チェックで抜けていた)。
    #    (native 6b8a60 は r8=0 で test/jle により no-op → 常に al=1。r8>0 経路は本 smoke
    #     未到達, REPORT §5)
    sub('%12 = call i64 @function_6b8a60()',
        '%12 = add i64 1, 0\n  store i64 1, ptr inttoptr (i64 9048192 to ptr), align 8', 1)
    # 残存確認: body 内に Host/Tag の定数が残っていないこと
    rest = '\n'.join(body)
    for g in (H, T):
        if g in rest:
            print('[hs_irfix] %s が body に残存' % g); sys.exit(1)
    lines[lo:hi + 1] = body
    open(dst, 'w').write('\n'.join(lines))
    print('[hs_irfix] function_6bdde0 patched: %d 置換 (Host=%s Tag=%s; signature+2x(Host,Tag)+Tag_r8+Host_r9+Tag_rdx素) -> %s' % (n[0], H, T, dst))


if __name__ == '__main__':
    main()
