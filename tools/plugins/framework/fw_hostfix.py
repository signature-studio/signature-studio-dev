#!/usr/bin/env python3
"""fw_hostfix.py — CAB-195: plugin 連鎖が通る誤 decode mosaic 領域の targeted override.

背景 (実測):
  * CreatePlugInstance (0x6bdde0) の init (0x6bd210) は続いて文字列割付け
    (NewAnsiString 0x40e5e0 → GetMem 0x407010) を通る。この領域の lift は
    dec_label が定義 VA と無関係な mosaic 状態で、ret や引数が定数折畳み
    (@153 のアドレス = 0x10000710 を「文字列長」に折畳み) されており、
    [buf + 2*len + 16] 系の store が linear memory 外を指して OOB trap する
    (fw_host.mjs / hs_e2e 実測。canon3 でも同じ経路を garbage が偶然 writable
    なアドレスを指しただけで通過した only — CAB-194 REPORT §7.1 の停止位置と同根)。
  * 本 pass は当該 define を「deref/write 安全な scratch を返す 0-arg 関数」で
    置換する (fw_ovpass.py の C override と同方針の IR 版)。正規の plugin 連鎖
    (0x6b8000..0x6c2000, retw 適用済み) は置換対象外。

現時点の対象 (実測の trap 順):
  0x40e5e0 NewAnsiString 相当 → fw_hs_scratch(4096)+16 を返す (BLK+0x80 にも store、
           呼出側の abi_ret_load が読むのは BLK+0x80 のため)
  0x40bd20 TObject.Free 相当 (native: call [rbx-0x50], 0x40bd3d 実測) — mosaic で
           vptr が fold され load [-44] が即 trap → scratch を返す (leak 容認, smoke のみ)
  0x407010 _GetMem 相当 (native: call [rip+0x2ccc64] = FastMM fn ptr, 0x40701e 実測) —
           mosaic では target 計算が誤 slot を読み __icall_dispatch(0x40701e) が無関係
           関数を実行して static 領域を破壊する (dispatch counter 破壊を実測) →
           scratch を返す。TTestPlug instance の正規確保は class VMT 経由の dispatch
           (w_412d60) なので本 override の影響外。
  0x40e650 NewWideString 相当 (native 0x40e67e 実測: 0x407010 経由の alloc + header
           書込み) — 40e5e0 同族。6bd150 (services init) → 40f3b0 → 40ead0 → 40e650
           の経路で到達 (hs_e2e 実測) → scratch を返す。
  0x4076b0 Move 相当 (RTL Move: src rcx / dst rdx / len r8, native 0x4076b0 実測) —
           40ead0 (文字列 assign) が fold 済み garbage src で呼ぶため OOB read →
           no-op (copy しない。dst は scratch のため安全)。
  0x40fff3 (空文字列 default getter — native 0x40ffe0: `return s ? s : [rip+..]+0x10`)
           — .pdata 登録が最終命令 ret のみで decode 漏れ stub 化していた (fw_table
           生成の fail-fast が 6bd150 経路で発火) → zeroed scratch (空文字列相当) を返す。

  python3 fw_hostfix.py in.ll out.ll --blk 0x8A1000 [--report json]
"""
import argparse, re, json

# (define VA, 差し替える body)
OVERRIDES = {
    0x40e5e0: '''define i64 @function_40e5e0() local_unnamed_addr {
  %p = call ptr @fw_hs_scratch(i32 4096)
  %q = getelementptr i8, ptr %p, i64 16
  %r = ptrtoint ptr %q to i64
  store i64 %r, ptr inttoptr (i64 @RETSLOT@ to ptr), align 8
  ret i64 %r
}''',
    0x40bd20: '''define i64 @function_40bd20() local_unnamed_addr {
  %p = call ptr @fw_hs_scratch(i32 4096)
  %r = ptrtoint ptr %p to i64
  store i64 %r, ptr inttoptr (i64 @RETSLOT@ to ptr), align 8
  ret i64 %r
}''',
    0x407010: '''define i64 @function_407010() local_unnamed_addr {
  %p = call ptr @fw_hs_scratch(i32 4096)
  %r = ptrtoint ptr %p to i64
  store i64 %r, ptr inttoptr (i64 @RETSLOT@ to ptr), align 8
  ret i64 %r
}''',
    0x40e650: '''define i64 @function_40e650() local_unnamed_addr {
  %p = call ptr @fw_hs_scratch(i32 4096)
  %r = ptrtoint ptr %p to i64
  store i64 %r, ptr inttoptr (i64 @RETSLOT@ to ptr), align 8
  ret i64 %r
}''',
    0x4076b0: '''define i64 @function_4076b0() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 @RETSLOT@ to ptr), align 8
  ret i64 0
}''',
    0x40fff3: '''define i64 @function_40fff3() local_unnamed_addr {
  %p = call ptr @fw_hs_scratch(i32 64)
  %r = ptrtoint ptr %p to i64
  store i64 %r, ptr inttoptr (i64 @RETSLOT@ to ptr), align 8
  ret i64 %r
}''',
    # ---- CAB-195: RTL ユーティリティ (native 実機対照, REPORT §3.2) ----
    # 0x40e770/0x40e800/0x40e850 = DynArray 参照カウント操作 (native は lock xadd;
    # wasm に AT&T lock xadd は無いため lift IR は load/store に退化)。
    # rcx/rsi = ポインタ配列のアドレス, edx/ebx = 個数 (0x40e770 は 1 個固定)。
    # lift IR 上の呼出は `call @function_XXXX()` の **direct call** なので,
    # 本体を hostshim (hs_utl.c) 委譲に差し替える (BLK は呼出元が設定済み)。
    0x40e770: '''define i64 @function_40e770() local_unnamed_addr {
  %r = call i64 @hs_utl_dec1()
  store i64 %r, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 %r
}''',
    0x40e800: '''define i64 @function_40e800() local_unnamed_addr {
  %r = call i64 @hs_utl_decn()
  store i64 %r, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 %r
}''',
    0x40e850: '''define i64 @function_40e850() local_unnamed_addr {
  %r = call i64 @hs_utl_decn()
  store i64 %r, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 %r
}''',
    0x40e8f0: '''define i64 @function_40e8f0() local_unnamed_addr {
  %r = call i64 @hs_utl_inc()
  store i64 %r, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 %r
}''',
    0x40e910: '''define i64 @function_40e910() local_unnamed_addr {
  %r = call i64 @hs_utl_dec1ref()
  store i64 %r, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 %r
}''',
    0x40e8a0: '''define i64 @function_40e8a0() local_unnamed_addr {
  %r = call i64 @hs_utl_tobjfree()
  store i64 %r, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 %r
}''',
    # 0x40edb0: `SetWideString(var S: WideString; const Value)` (native 0x40edb0 実測)。
    # Value は retw/fold により WASM 定数 @344 に落ち, `[@344-8]` の refcount 読みが
    # linear memory の極低位 (0x1c) に到達して OOB trap する (hs_e2e 実測)。
    # 対処: fold 値は「空 (nil) WideString」相当として扱い, var (BLK+8) に 0 を書く。
    0x40edb0: '''define i64 @function_40edb0() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048064 to ptr), align 8
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    # 0x5c0630: FLE 側 "Register/Get global オブジェクト" (native 0x5c0630 実測:
    #   `[rsi] → vtable slot0` を介した FL 内部 API 参照)。wasm では fold した
    #   global @666 の内容が 0 に近く, `[[@666+856]]` → `[[+40]]` の 2 段 deref が
    #   OOB trap (hs_e2e 実測 → [dbg] -> 0x40edb0 直後に停止)。
    #   呼出元 (0x6bd210) は結果を [[5c1930 結果]+0x14] に store するだけで
    #   deref しないため, fail-soft に 0 を返して連鎖を継続させる (REPORT §3.3)。
    #   signature は i128 (xmm0 経由の戻り値) なので 0 を返す。
    0x5c0630: '''define i128 @function_5c0630() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i128 0
}''',
    # 0x5c1930: FL 側 "TPFruityPluginInfoManager 生成/登録" (native 0x5c1930 実測:
    #   rbx=[BLK+8]; FL object = [rbx+0x358]; 仮想呼出 [[FL]+0xb0] (slot22 相当) →
    #   FL object を介した一連の API 連鎖 (0x5be390 / 0x5bded0 / 0x5bdf50)。
    # headless では FL object ([BLK+8]+0x358) が fold で 0 に近く, 仮想呼出の
    # ターゲット計算が OOB (hs_e2e 実測 → Dispatcher 0x56 直後に停止)。
    # 呼出元 (0x6bd210) は結果を [[自身]+0x14] に store するのみなので 0 で fail-soft。
    0x5c1930: '''define i64 @function_5c1930() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    # 0x40b930 / 0x40b9a0: TComponent 名検索 (native 実測: 0x40b930 は [rcx-0x90] の
    # list を total 探索, 0x40b9a0 は [[rcx]] 経由のラッパ)。ctor 後半 (host object の
    # 名前/component tree 検索) で到達するが, headless では rcx が fold 定数になり
    # [rcx-0x90] の deref が linear memory 外 → OOB trap (hs_e2e 実測, wasm stack 確認)。
    # 「見つからない」= 0 を返す fail-soft で連鎖を継続させる (REPORT §3.4)。
    0x40b930: '''define i64 @function_40b930() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    0x40b9a0: '''define i64 @function_40b9a0() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    # 0x461950: `TStream.Read` ラッパ (native 0x461950 実測: rdx=[rcx+0x10], r8=1,
    # r9=&arg で 0x412fc0 を呼ぶだけの 1 行 wrapper)。0x412fc0 は Delphi RTL の
    # variant/encoding 処理で, fold 定数のストリームを辿って深く再帰し OOB
    # (hs_e2e 実測: function_412fc0 → 自己再帰で trap, wasm stack 確認)。
    # headless では実ストリームが無いので「読めなかった」= 0 を返す (REPORT §3.4)。
    0x461950: '''define i64 @function_461950() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    # 0x52dba0: `TComponent.Find*` (native 実測: dl!=0 で 0x40bce0 → 0x40b3f0(rcx,0) と
    # 辿り, 内部で 0x52cf40 → 0x52ce00 (CRC32(name)) が wide string を読む)。
    # headless では name ポインタが fold 定数で CRC32 のバイト読取が OOB
    # (hs_e2e 実測: function_52ce00 → trap, wasm stack 確認)。
    # 「名前不一致」= 0 を返す fail-soft (REPORT §3.4)。
    0x52dba0: '''define i64 @function_52dba0() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    # 0x52cf40: native では命令境界ではなく, .pdata 関数 [0x52ce50,0x52cf67) の途中
    # (0x52cf3e の mov の内部)。native に 0x52cf40 への直接 call は無く (E8 走査 0 件),
    # 0x52ce00 へ分岐する経路も無い (REPORT_2070.md §3.1)。よって lift の function_52cf40 は
    # 途中から decode された artifact。旧注釈の「CRC32 → 0x52ce00 で OOB」は誤り。
    # 0 を返す fail-soft は呼出元 (0x52d230) の「不一致 = 0」分岐に合わせた stub (意味づけは推定)。
    0x52cf40: '''define i64 @function_52cf40() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    # 0x4e6060: native では関数ではなく RTTI 文字列 "Object>.ParrayofT" の領域 (.text 内・.pdata 外)。
    # 0x4e5f50 (= "tem.Generics.Defaults" の領域) と同様, native に直接 call は無い (E8 走査 0 件)。
    # 旧注釈の「0x4e5fc0 からの自己再帰」も, 0x4e5fc0 が .pdata 外のデータ領域で関数として成立しない
    # (REPORT_2070.md §3.2)。lift の function_4e6060 は文字列を関数として decode した artifact。
    # 「該当なし」= 0 の fail-soft は呼出元の分岐を通すための stub で, native の根拠は無い。
    0x4e6060: '''define i64 @function_4e6060() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    # E3 (診断・未採用): 0x4180d0 を native の意味 (LocalAlloc(0x40, 0x288) → TlsSetValue(idx, blk)) に置換。
    0x4180d0: '''define i64 @function_4180d0() local_unnamed_addr {
  %idx = load i32, ptr inttoptr (i64 7171696 to ptr), align 4
  %blk = call ptr @LocalAlloc(i32 64, i32 648)
  %ok = icmp ne ptr %blk, null
  br i1 %ok, label %set, label %done
set:
  %r = call i1 @TlsSetValue(i32 %idx, ptr %blk)
  br label %done
done:
  ret i64 0
}''',
    # 0x40e720: `ClearWideString(var S)` (native 0x40e720 実測: S[0]!=0 なら refcount--
    # して 0 に達したら FreeMem。rcx は var アドレス)。lift では S が scratch 畳み込みで
    # 内容が非 NULL に見え、`[val-0x10+8]` の refcount 読取 → scratch pool 先頭を
    # refcount と誤認して破損しうる。→ var に 0 を書いて nil 化 (free は走らせない)。
    0x40e720: '''define i64 @function_40e720() local_unnamed_addr {
  store i64 0, ptr inttoptr (i64 9048064 to ptr), align 8
  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8
  ret i64 0
}''',
    # ---- CAB-195: RetDec trap artifact (llvm.trap + unreachable 本体) ----
    # 未実装の __readgsbyte/__writegsbyte/__readfsbyte を呼んだ後 llvm.trap する
    # artifact define が 7 本 (0x4467f5 / 0x573617 / 0x58269f / 0x641ddf /
    # 0x6b5090 / 0x6bf368 / 0x6bf550)。plugin 連鎖では 0x6b5090 (base ctor の
    # artifact) に到達して即 unreachable trap (hs_e2e 実測 → 0x579c20 直後)。
    # どれも RetDec の decoder artifact (native の実態は空 or 別関数) なので,
    # 0 を返す fail-soft 本体に差し替える (signature は i64 3引数で統一)。
    0x4467f5: '__TRAP__', 0x573617: '__TRAP__', 0x58269f: '__TRAP__', 0x641ddf: '__TRAP__',
    0x6b5090: '__TRAP__', 0x6bf368: '__TRAP__', 0x6bf550: '__TRAP__',
}


def trap_body(va):
    """RetDec trap artifact (llvm.trap 本体) の fail-soft 置換本体を返す。"""
    return ('define i64 @function_%x(i64 %%arg1, i64 %%arg2, i64 %%arg3) local_unnamed_addr {\n'
            '  store i64 0, ptr inttoptr (i64 9048192 to ptr), align 8\n'
            '  ret i64 0\n'
            '}' % va)


def body_of(va):
    b = OVERRIDES[va]
    return trap_body(va) if b == '__TRAP__' else b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--blk', type=lambda x: int(x, 0), default=0x8A1000)
    ap.add_argument('--report')
    a = ap.parse_args()
    retslot = a.blk + 0x80

    lines = open(a.src, errors='replace').read().split('\n')
    out = []
    done = {}
    stripped = []
    i = 0
    n = len(lines)
    while i < n:
        l = lines[i]
        m = re.match(r'define \S+ @function_([0-9a-f]+)\(', l)
        if m:
            va = int(m.group(1), 16)
            if va in OVERRIDES:
                j = i
                while lines[j] != '}':
                    j += 1
                out.append(body_of(va).replace('@RETSLOT@', str(retslot)))
                done[va] = j - i + 1
                i = j + 1
                continue
        # declare の strip (override を define として注入するため)
        md = re.match(r'declare \S+ @function_([0-9a-f]+)\(', l)
        if md and int(md.group(1), 16) in OVERRIDES:
            stripped.append(int(md.group(1), 16))
            i += 1
            continue
        out.append(l)
        i += 1

    # define が無かった override (decode 漏れ等) は新たに define として注入する
    # (declare は上で strip 済み。fw_table.py は define 有りなら C fail-fast stub を生成しない)
    injected = []
    if out:
        for va, body in OVERRIDES.items():
            if va not in done:
                injected.append(va)
                done[va] = 0
        first_define = next((k for k, l in enumerate(out) if l.startswith('define ')), None)
        if first_define is None:
            raise SystemExit('[hostfix] define が 1 つも無い IR')
        for k, va in enumerate(injected):
            out.insert(first_define + k, body_of(va).replace('@RETSLOT@', str(retslot)))
    # CAB-195: RetDec の定数折畳み global (@N = internal constant [2 x i8] c"$\00") は
    # plugin 連鎖で **書き込み** を受ける (0x408e80/0x409400 の double 変換 temp として
    # `store i64 %63, ptr @414` 等)。LLVM では constant global への store は UB で,
    # clang は `unreachable` を生成して wasm trap する (hs_e2e 実測: 0x579c20 直後)。
    # → store を受けているものだけ mutable global (zeroinitializer) に落とす。
    # (framework smoke (CAB-194) 経路では store されないので影響なし)
    ncv = 0
    cvre = re.compile(r'^(@[\w.$-]+ = (?:local_unnamed_addr )?(?:internal )?(?:constant|global) \[[0-9]+ x i(?:8|16|32|64)\] )(?:c"[^"]*"|zeroinitializer)[^\n]*$')
    for k, l in enumerate(out):
        m2 = cvre.match(l)
        if not m2:
            continue
        nm0 = l.split(' ')[0]
        pat = re.compile(r'store \S+ [^,]*, ptr ' + re.escape(nm0) + r'\b')
        if any(pat.search(x) for x in out):
            out[k] = m2.group(1) + 'zeroinitializer, align 8'
            ncv += 1

    # CAB-195: `@__asm_*` helper の呼出 signature 不整合を同族 rename で解消する。
    # RetDec IR は declare を 1 本化した (`__asm_mulsd__xxx(i128,i128)`) が, 一部
    # call site は第2引数を GPR (i64) で渡す movq 由来の `(i128,i64)` 形になっている。
    # C 側 (work/fw/fw_simd.c, liftlib simd gen 产出) は mnemonic ごとに
    # `__xxx`(x,x) / `__xxq`(x,q) / `__qx`(q,x) / `__qq`(q,q) / `__xd`(x,d) 等の
    # 別名を定義しているため, 実引数型に一致する別名へ rename すれば C と噛み合う。
    # 不一致のまま放っておくと clang は ABI 調整 thunk `*_bitcast_invalid`
    # (本体 unreachable) を生成し, 呼ばれた時点で wasm trap
    # (hs_e2e 実測: function_6be800 → unreachable, wasm stack で確認)。
    # 対象は CAB-195 host shim 派生ビルドのみ (framework smoke = CAB-194 は元のまま)。
    nfix = 0
    unl = []
    ddecl = {}
    for l in out:
        m = re.match(r'declare (\S+) @(\S+)\((.*?)\)', l)
        if m:
            sig = (m.group(1), tuple(p.strip() for p in m.group(3).split(',') if p.strip()))
            ddecl.setdefault(m.group(2), set()).add(sig)
    fam = {}
    for nm, sigs in ddecl.items():
        mm = re.match(r'^(__asm_[A-Za-z0-9_]+)__([a-z]{1,4})$', nm)
        if not mm:
            continue
        for s1 in sigs:
            fam.setdefault(mm.group(1), {}).setdefault(s1, nm)
    call_re = re.compile(r'call (\S+) @(__asm_[A-Za-z0-9_]+)\(([^)]*)\)')
    for k, l in enumerate(out):
        if ' call ' not in l:
            continue
        m = call_re.search(l)
        if not m:
            continue
        nm = m.group(2)
        if nm not in ddecl:
            continue
        tys = []
        for p in m.group(3).split(','):
            p = p.strip()
            if not p:
                continue
            tys.append(p.split()[0] if ' ' in p else p)
        sig = (m.group(1), tuple(tys))
        if sig in ddecl[nm]:
            continue
        fm = re.match(r'^(__asm_[A-Za-z0-9_]+)__', nm)
        alt = fam.get(fm.group(1), {}).get(sig) if fm else None
        if alt:
            out[k] = l.replace('@' + nm + '(', '@' + alt + '(')
            nfix += 1
        else:
            unl.append((nm, sig))
    if unl:
        print('[hostfix] __asm_* rename 解消不能 %d 件 (%s) — そのまま残す'
              % (len(unl), ', '.join(sorted(set(n for n, _ in unl))[:6])))
    if nfix:
        print('[hostfix] __asm_* 呼出 signature 不整合 → 同族名に rename: %d' % nfix)

    text = '\n'.join(out)
    decl = 'declare ptr @fw_hs_scratch(i32) local_unnamed_addr\n'
    if decl not in text:
        idx = text.index('\ndefine ')
        text = text[:idx + 1] + decl + '\n' + text[idx + 1:]
    # CAB-195: hs_utl_* (hostshim/hs_utl.c) の declare (上記 override が呼ぶ)
    for nm in ('hs_utl_dec1', 'hs_utl_decn', 'hs_utl_inc', 'hs_utl_dec1ref', 'hs_utl_tobjfree'):
        d = 'declare i64 @%s() local_unnamed_addr\n' % nm
        if d not in text:
            idx = text.index('\ndefine ')
            text = text[:idx + 1] + d + '\n' + text[idx + 1:]

    open(a.dst, 'w').write(text)
    rep = {'overrides': {'0x%x' % va: {'old_lines': nl, 'injected': va in injected}
                         for va, nl in done.items()},
           'declares_stripped': ['0x%x' % v for v in stripped],
           'retslot': retslot}
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[hostfix] overrides: %s -> %s' %
          (', '.join('0x%x(%s)' % (va, ('%d lines' % nl) if nl else 'injected')
                     for va, nl in done.items()), a.dst))
    if ncv:
        print('[hostfix] folded constant globals → mutable global (store 先): %d' % ncv)


if __name__ == '__main__':
    main()
