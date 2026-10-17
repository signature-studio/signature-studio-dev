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
    fix_414390(lines)
    fix_40c4d0(lines)
    fix_40b3f0(lines)
    fix_40b370(lines)
    fix_40b550(lines)
    open(dst, 'w').write('\n'.join(lines))
    print('[hs_irfix] function_6bdde0 patched: %d 置換 (Host=%s Tag=%s; signature+2x(Host,Tag)+Tag_r8+Host_r9+Tag_rdx素) -> %s' % (n[0], H, T, dst))


def fix_414390(lines):
    # #2426: native 0x414390 は wcsncpy 相当 (rcx=dst, edx=count, r8=src) で入力を読む。
    # lift 版は rcx/rdx/r8 を読まず RetDec の定数 ptrtoint @G に畳んでいるため、count が
    # 定数のアドレス値になり src を終端まで読んで wasm 境界外へ出る (REPORT_2426 §2)。
    # 入力を caller が積む BLK+0x08 (rcx) / +0x10 (rdx) / +0x18 (r8) から読むように直す。
    lo = hi = None
    for i, l in enumerate(lines):
        if l.startswith('define ') and '@function_414390(' in l:
            lo = i
        elif lo is not None and l == '}':
            hi = i
            break
    if lo is None:
        print('[hs_irfix] function_414390 が見つからない (skip)'); return
    body = lines[lo:hi + 1]
    names = re.findall(r'%ce4n11_function_414390 = ptrtoint ptr (@\d+) to i32', '\n'.join(body))
    if len(names) != 1:
        print('[hs_irfix] function_414390 の定数名を特定できない: %d 件' % len(names)); sys.exit(1)
    RCX = re.search(r'%ce5n11_function_414390 = ptrtoint ptr (@\d+) to i64', '\n'.join(body))
    RDX = re.search(r'%ce7n11_function_414390 = ptrtoint ptr (@\d+) to i64', '\n'.join(body))
    R8 = re.search(r'%ce8n11_function_414390 = ptrtoint ptr (@\d+) to i64', '\n'.join(body))
    if not (RCX and RDX and R8):
        print('[hs_irfix] function_414390 の入力定数を特定できない'); sys.exit(1)
    rcx, rdx, r8 = RCX.group(1), RDX.group(1), R8.group(1)
    rules = [
        ('%%ce4n11_function_414390 = ptrtoint ptr %s to i32' % rdx,
         '%ce4n11_function_414390 = load i32, ptr inttoptr (i64 9048080 to ptr), align 8'),
        ('%%ce0n12_function_414390 = ptrtoint ptr %s to i32' % rdx,
         '%ce0n12_function_414390 = load i32, ptr inttoptr (i64 9048080 to ptr), align 8'),
        ('%%ce11n11_function_414390 = ptrtoint ptr %s to i32' % rdx,
         '%ce11n11_function_414390 = load i32, ptr inttoptr (i64 9048080 to ptr), align 8'),
        ('%%ce5n11_function_414390 = ptrtoint ptr %s to i64' % rcx,
         '%ce5n11_function_414390 = load i64, ptr inttoptr (i64 9048072 to ptr), align 8'),
        ('%%ce6n11_function_414390 = ptrtoint ptr %s to i64' % rcx,
         '%ce6n11_function_414390 = load i64, ptr inttoptr (i64 9048072 to ptr), align 8'),
        ('%%ce9n11_function_414390 = ptrtoint ptr %s to i64' % rcx,
         '%ce9n11_function_414390 = load i64, ptr inttoptr (i64 9048072 to ptr), align 8'),
        ('%%ce7n11_function_414390 = ptrtoint ptr %s to i64' % rdx,
         '%ce7n11_function_414390 = load i64, ptr inttoptr (i64 9048080 to ptr), align 8'),
        ('%%ce10n11_function_414390 = ptrtoint ptr %s to i64' % rdx,
         '%ce10n11_function_414390 = load i64, ptr inttoptr (i64 9048080 to ptr), align 8'),
        ('%%ce8n11_function_414390 = ptrtoint ptr %s to i64' % r8,
         '%ce8n11_function_414390 = load i64, ptr inttoptr (i64 9048088 to ptr), align 8'),
        ('store i16 0, ptr %s, align 8' % rcx,
         '%hs414390_dst = load i64, ptr inttoptr (i64 9048072 to ptr), align 8\n'
         '  %hs414390_dstp = inttoptr i64 %hs414390_dst to ptr\n'
         '  store i16 0, ptr %hs414390_dstp, align 8'),
    ]
    for old, new in rules:
        cnt = 0
        for i in range(lo, hi + 1):
            if old in lines[i]:
                lines[i] = lines[i].replace(old, new)
                cnt += 1
        if cnt != 1:
            print('[hs_irfix] function_414390 置換数不一致 (%d != 1): %s' % (cnt, old[:80])); sys.exit(1)
    rest = '\n'.join(lines[lo:hi + 1])
    for g in (names[0], rcx, rdx, r8):
        if g in rest:
            print('[hs_irfix] function_414390 に %s が残存' % g); sys.exit(1)
    print('[hs_irfix] function_414390 patched: 入力 rcx=%s rdx=%s r8=%s を BLK+0x08/+0x10/+0x18 から読む' % (rcx, rdx, r8))


def fix_40c4d0(lines):
    # #2534: native 0x40c4d0 は rcx=this で、[rcx] の VMT から [vt-0x80] の offset を読んで
    # once-init の slot を参照する。lift 版は rcx を文字列定数 @1 ("$") に畳み、[rcx] の読みも
    # 定数 -92 になっている (fold 元は "$" = 0x24 の 1 byte)。rcx は caller が積む BLK+0x08 から、
    # [rcx] は実メモリから読む。rdx/r8 は関数内で書換えないため、定数 store を消して caller の値を素通しにする。
    lo = hi = None
    for i, l in enumerate(lines):
        if l.startswith('define ') and '@function_40c4d0(' in l:
            lo = i
        elif lo is not None and l == '}':
            hi = i
            break
    if lo is None:
        print('[hs_irfix] function_40c4d0 が見つからない'); sys.exit(1)
    rules = [
        ('%ce5n11_function_40c4d0 = inttoptr i64 -92 to ptr', 1,
         '%hs40c_rcx = load i64, ptr inttoptr (i64 9048072 to ptr), align 8\n'
         '  %hs40c_vtp = inttoptr i64 %hs40c_rcx to ptr\n'
         '  %hs40c_vt = load i64, ptr %hs40c_vtp, align 8\n'
         '  %hs40c_vtm = add i64 %hs40c_vt, -128\n'
         '  %ce5n11_function_40c4d0 = inttoptr i64 %hs40c_vtm to ptr'),
        ('%ce6n11_function_40c4d0 = ptrtoint ptr @1 to i64', 1,
         '%ce6n11_function_40c4d0 = add i64 %hs40c_rcx, 0'),
        ('store ptr getelementptr inbounds ([2 x i8], ptr @1, i64 0, i64 0), ptr inttoptr (i64 9048072 to ptr), align 8', 1,
         'store i64 %hs40c_rcx, ptr inttoptr (i64 9048072 to ptr), align 8'),
        ('store ptr getelementptr inbounds ([2 x i8], ptr @2, i64 0, i64 0), ptr inttoptr (i64 9048080 to ptr), align 8', 1, ''),
        ('store ptr getelementptr inbounds ([2 x i8], ptr @4, i64 0, i64 0), ptr inttoptr (i64 9048088 to ptr), align 8', 2, ''),
    ]
    for old, expect, new in rules:
        cnt = 0
        for i in range(lo, hi + 1):
            if old in lines[i]:
                lines[i] = lines[i].replace(old, new)
                cnt += 1
        if cnt != expect:
            print('[hs_irfix] function_40c4d0 置換数不一致 (%d != %d): %s' % (cnt, expect, old[:80])); sys.exit(1)
    rest = '\n'.join(lines[lo:hi + 1])
    if re.search(r'ptr @[124]\b|i64 -92 ', rest):
        print('[hs_irfix] function_40c4d0 に定数 (@1/@2/@4・-92) が残存'); sys.exit(1)
    print('[hs_irfix] function_40c4d0 patched: rcx を BLK+0x08 から読み [rcx] を実メモリから読む (rdx/r8 は素通し)')


def fix_40b3f0(lines):
    # #2534: native 0x40b3f0 は (rcx=this, dl=flag) を取り、flag≠0 なら 40bce0 (rcx, rdx=flag) を呼ぶ。
    # lift 版は this を "$" 定数 @594、flag を "$" 定数 @593 に畳み、分岐と 40bce0 の引数が固定される。
    # this は BLK+0x08、flag は BLK+0x10 の下位 1 byte を entry で 1 回だけ読む (40bce0 が後で BLK+0x10 を書くため)。
    lo = hi = None
    for i, l in enumerate(lines):
        if l.startswith('define ') and '@function_40b3f0(' in l:
            lo = i
        elif lo is not None and l == '}':
            hi = i
            break
    if lo is None:
        print('[hs_irfix] function_40b3f0 が見つからない'); sys.exit(1)
    rules = [
        ('store ptr getelementptr inbounds ([2 x i8], ptr @594, i64 0, i64 0), ptr %.reg2mem', 1,
         '%ce5n11_function_40b3f0 = load i64, ptr inttoptr (i64 9048072 to ptr), align 8\n'
         '  %hs40b_this = inttoptr i64 %ce5n11_function_40b3f0 to ptr\n'
         '  store ptr %hs40b_this, ptr %.reg2mem'),
        ('%ce5n11_function_40b3f0 = ptrtoint ptr @594 to i64', 1, ''),
        ('%ce8n11_function_40b3f0 = ptrtoint ptr @594 to i64', 1, '%ce8n11_function_40b3f0 = add i64 %ce5n11_function_40b3f0, 0'),
        ('%ce6n11_function_40b3f0 = ptrtoint ptr @593 to i64', 1,
         '%ce6n11_function_40b3f0 = load i64, ptr inttoptr (i64 9048080 to ptr), align 8'),
        ('%ce7n11_function_40b3f0 = ptrtoint ptr @593 to i8', 1,
         '%ce7n11_function_40b3f0 = load i8, ptr inttoptr (i64 9048080 to ptr), align 1'),
        ('%ce9n11_function_40b3f0 = ptrtoint ptr @593 to i8', 1, '%ce9n11_function_40b3f0 = add i8 %ce7n11_function_40b3f0, 0'),
        ('%ce17n11_function_40b3f0 = ptrtoint ptr @593 to i8', 1, '%ce17n11_function_40b3f0 = add i8 %ce7n11_function_40b3f0, 0'),
        ('%ce18n11_function_40b3f0 = ptrtoint ptr @593 to i8', 1, '%ce18n11_function_40b3f0 = add i8 %ce7n11_function_40b3f0, 0'),
        ('store ptr getelementptr inbounds ([2 x i8], ptr @592, i64 0, i64 0), ptr inttoptr (i64 9048088 to ptr), align 8', 2, ''),
    ]
    for old, expect, new in rules:
        cnt = 0
        for i in range(lo, hi + 1):
            if old in lines[i]:
                lines[i] = lines[i].replace(old, new)
                cnt += 1
        if cnt != expect:
            print('[hs_irfix] function_40b3f0 置換数不一致 (%d != %d): %s' % (cnt, expect, old[:80])); sys.exit(1)
    rest = '\n'.join(lines[lo:hi + 1])
    if re.search(r'ptr @59[234]\b', rest):
        print('[hs_irfix] function_40b3f0 に定数 (@592/@593/@594) が残存'); sys.exit(1)
    print('[hs_irfix] function_40b3f0 patched: this を BLK+0x08、flag を BLK+0x10 (entry 1 回) から読む')


def _fix_body(lines, fn, rules, tag):
    lo = hi = None
    for i, l in enumerate(lines):
        if l.startswith('define ') and ('@%s(' % fn) in l:
            lo = i
        elif lo is not None and l == '}':
            hi = i
            break
    if lo is None:
        print('[hs_irfix] %s が見つからない' % fn); sys.exit(1)
    for old, expect, new in rules:
        cnt = 0
        for i in range(lo, hi + 1):
            if old in lines[i]:
                lines[i] = lines[i].replace(old, new)
                cnt += 1
        if cnt != expect:
            print('[hs_irfix] %s 置換数不一致 (%d != %d): %s' % (fn, cnt, expect, old[:80])); sys.exit(1)
    print('[hs_irfix] %s patched: %s' % (fn, tag))


def fix_40b370(lines):
    # #3355: native 0x40b370 は rcx=this を rbx に保持し、40b550(this, 407010 の戻り値) を呼ぶ。
    # lift 版は this を "$" 定数 @153 に畳む。this は entry で BLK+0x08 から 1 回読む (407010 が BLK+0x08 を上書きするため)。
    _fix_body(lines, 'function_40b370', [
        ('%ce5n11_function_40b370 = ptrtoint ptr @153 to i64', 1,
         '%hs370_this = load i64, ptr inttoptr (i64 9048072 to ptr), align 8\n'
         '  %ce5n11_function_40b370 = add i64 %hs370_this, 0'),
        ('store ptr getelementptr inbounds ([2 x i8], ptr @153, i64 0, i64 0), ptr inttoptr (i64 9048072 to ptr), align 8', 1,
         'store i64 %hs370_this, ptr inttoptr (i64 9048072 to ptr), align 8'),
    ], 'this を BLK+0x08 から読み、40b550 への第 1 引数に渡す')


def fix_40b550(lines):
    # #3355: native 0x40b550 は rcx=this (rbx)・rdx=確保先 (rsi) を取る。40a5a0(確保先, [this-0x80], 0) の後に
    # [確保先] = this (`mov [rsi], rdi` 0x40b576)。lift 版は this を @381、確保先を @382 の定数に畳み、
    # 40a5a0 の第 1 引数と [rsi]=rdi の store が欠落する。this は BLK+0x08、確保先は BLK+0x10 から entry で読む。
    _fix_body(lines, 'function_40b550', [
        ('%ce5n11_function_40b550 = ptrtoint ptr @381 to i64', 1,
         '%hs550_this = load i64, ptr inttoptr (i64 9048072 to ptr), align 8\n'
         '  %hs550_dst = load i64, ptr inttoptr (i64 9048080 to ptr), align 8\n'
         '  %ce5n11_function_40b550 = add i64 %hs550_this, 0'),
        ('store ptr getelementptr inbounds ([2 x i8], ptr @382, i64 0, i64 0), ptr inttoptr (i64 9048072 to ptr), align 8', 1,
         'store i64 %hs550_dst, ptr inttoptr (i64 9048072 to ptr), align 8'),
        ('%ce13n11_function_40b550 = ptrtoint ptr @381 to i64', 1,
         '%ce13n11_function_40b550 = add i64 %hs550_this, 0'),
        ('store i64 %ce12n11_function_40b550, ptr @382, align 8', 1,
         'store i64 %hs550_this, ptr %sf223, align 8'),
    ], '確保先を BLK+0x08 (40a5a0 の第 1 引数)、this を BLK+0x08 entry から読み [確保先]=this を書く')


if __name__ == '__main__':
    main()
