# REPORT 付録 (#4955 KH-136): func_0x0001802ecfc0 (tap_add) の宣言型を機械語どおりに直す

親 #4014 の残件 (#4014 の受入 2 と宣言型の修正を引き継ぐ)。

## 結論

- `FUN_1802ecfc0` の `param_3`・`param_4` は、生成 C で `float *` だったが、機械語では 16 byte の `V128` オペランドである。`DELAY_RULES` 4 件 (宣言 1・本体 2・呼出元 1) で `V128 *` に直した。
- emcc の error は 2 件減った (delay の emcc census は、基準 `origin/main` **417** → 本 PR **415**)。消えた 2 件は `delay.c:1271` の 2 件 (`undefined8 *` と `undefined1[11][16]` を `float *` に渡す型不一致。どちらも行番号つきの diff で確認)。内訳は演算・代入・ポインタの型不一致 1 件 (171 → 170)、128bit レーン型 1 件 (167 → 166)。
- 本体の lane 読みは、(float) の数値変換から、ビット列 (`u2f`) へ直した。機械語の `addps` は lane のビットを float として加算するため。
- ホスト gcc で、機械語 (`addps`・`movlps`) と生成 C 本体の突合 200,000 試行 **mismatches 0**。ネガティブコントロール (減算に変えた誤実装) は **117,490 件** で FAIL を検出した。

## 機械語の読み (解消方法の根拠)

`HeartCore.core_64` の `0x1802ecfc0` (objdump -M intel、`work/winpkg` の実物):

```
1802ecfc0: movsxd rax,edx
1802ecfc3: movsd  xmm0,QWORD PTR [rcx+rax*8+0x28]
1802ecfc9: movsd  xmm1,QWORD PTR [rcx+rax*8+0x228]
1802ecfd2: addps  xmm0,XMMWORD PTR [r8]        ; param_3 を 16 byte のメモリオペランドとして読む
1802ecfd6: movlps QWORD PTR [rcx+rax*8+0x28],xmm0   ; 下位 8 byte (2 lane) だけ書く
1802ecfdb: addps  xmm1,XMMWORD PTR [r9]        ; param_4 も 16 byte
1802ecfdf: movlps QWORD PTR [rcx+rax*8+0x228],xmm1
1802ecfe7: ret
```

- r8・r9 (= param_3・param_4) は `addps` の 16 byte メモリオペランド。`float *` の 4 byte 読みでは機械語と一致しない。
- 解消方法: `param_3`・`param_4` を `V128 *` にする (規則 `FUN_1802ecfc0 宣言`)。本体は lane 0・1 を `u2f` で読んで `f2u` で書き戻す (規則 `本体 lane 0・1`)。
- 呼出元 (`delay.c:1271`): `uStack_108` (8 byte) と `uStack_100` (0 を書いた上位 8 byte) を 1 つの `V128` `kh_p108` にまとめて渡す。`aauStack_f8` (`undefined1[11][16]`) は先頭要素を `(V128 *)` で渡す (値は変えない)。規則 `caller FUN_1802ecfc0`。

## 測定

- 測定 commit (コードを変えた最後の commit): `ca1f38304` (`ghidra_to_c.py` の規則追加)。
- 測定 commit から HEAD までの差分: `git diff ca1f38304 HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` は **4 行** (`ghidra_route/patches.py` +4。main 取り込みで入った #4835 の ABI 規則 `delay 2666 FUN_180fbbfb8 rcx=param_1 (FUN_180fbdfcc)`)。`name == 'delay'` の変換に効くため、この差分の分を下表の census は含む。
- 測定 HEAD: `bb49a5ec0` (下表は HEAD で再測定した実測値)。基準: `origin/main` `7103cff33`。
- 測定 commit `ca1f38304` を同じ道具で取り直すと census は 416 (下の参考行を参照)。
- 素材: `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64`、76,642,304 B。sha256 `d55ce8b4…`)。`toolchain-emsdk` (`/opt/emsdk`、emcc 6.0.12)。Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致・JDK 21)。
- decompile: `gtype_census.sh` の lift 集合で DecompEach (151 件 OK)。
- 変換: `ghidra_to_c.py delay … --fix bitcast,intload,stackpair,assoc,concat`。emcc: `emcc -c -ferror-limit=0`。基準は `git archive origin/main` の `ghidra_route`・`snapins/lift`・`snapins/scripts/approx_tables.b64` の変換器 (同じ decompile 出力を入力)。

| 分類 | 基準 (main `7103cff33`) | 本 PR (`bb49a5ec0`) |
|---|---|---|
| 未関数化 callee | 0 | 0 |
| 128bit レーン型 | 167 | 166 |
| 引数数不一致 | 79 | 79 |
| 演算・代入・ポインタの型不一致 | 171 | 170 |
| **合計 (census)** | **417** | **415** |
| emcc error 行 (`error:`) | 417 | 415 |

- 消えた 2 件 (行番号つきの diff で確認): `delay.c:1271:74` (`undefined8 *` を `float *` に渡す・分類は型不一致 171 → 170) と `delay.c:1271:86` (`undefined1[11][16]` を `float *` に渡す・分類は `undefined1[N]` を含むためレーン型 167 → 166)。
- 参考 (同じ道具の測定 commit): `ca1f38304` の census は 416 (レーン 166・引数数不一致 80・型不一致 170)。main 取り込みで入った #4835 の ABI 規則 (`patches.py` `delay 2666`) が引数数不一致を 80 → 79 に変えた。
- Gain/Haas/Gate の `.o` は HEAD と基準で一致 (`gtype_census.sh` の `旧規則と一致` 3 件。gain 1435 B・haas 3217 B・gate 3756 B)。

## 回帰 (Gain/Haas/Gate への影響)

- 規則は `name == 'delay'` のガード内 (`DELAY_RULES`) にだけ入るため、Gain/Haas/Gate の変換は通らない。
- 規則の件数 assert (`delay rule hit … want 1`) は、規則が 1 件ずつ当たることを変換時に検査する (外れると変換が止まる)。
- Gain/Haas/Gate の `.o` は、本 PR (HEAD `bb49a5ec0`) と基準 (main) で `cmp` 一致 (測定節の `旧規則と一致` 3 件)。

## 単体突合 (機械語 vs 生成 C 本体)

- 検証スクリプト: `work/kh136/check.c` (`ghidra_shim.h` + 生成 C の `FUN_1802ecfc0` 本体)。`work/` は gitignore 対象のため repo に無い。突合は repo から再現できない状態で、本 PR の範囲では再現していない (未解決の表を参照)。再現手順は次のとおり: (1) `ghidra_route/ghidra_shim.h` を include し、`ghidra_to_c.py delay` で生成した `FUN_1802ecfc0` 本体を `check.c` に貼る。(2) 入力は乱数で、`param_1` は 1 KB のメモリ、`param_3`・`param_4` は 16 byte。(3) 参照側は `addps`・`movlps` の C 再現 (下位 2 lane の float 加算と 8 byte 書込み)。(4) 200,000 試行で両者の出力 (`param_1` の 1 KB) を比較する。
- 参照: 機械語 `addps`・`movlps` を C で再現 (下位 2 lane の float 加算と 8 byte 書込み)。入力は乱数 (`param_1` の 1 KB メモリ・`param_3`/`param_4` の 16 byte)。
- 結果: **mismatches 0 / 200,000** (rc 0)。
- ネガティブコントロール (`param_3` の lane 0 の加算を減算に変更): **mismatches 117,490 / 200,000** (rc 1)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Delay の native 突合 (1000 trial bit-exact) | 宣言型の正しさは機械語の読みと単体突合で示したが、Delay 全体の出力は未確認 | #3073 [KH-41] |
| 残件 415 (レーン 166・引数数不一致 79・型不一致 170) | Delay の emcc が通らない | #3801 [KH-65]・#3808 [KH-67]・#3809 [KH-68]・#3844 [KH-79]・#3847 [KH-73] (既存の起票先) |
| 突合 `work/kh136/check.c` の repo 外 (gitignore) | 200,000 試行の突合を repo から再現できない | #3073 [KH-41] (Delay の突合を扱う既存 issue。突合スクリプトの追跡化は同 issue の範囲。新規起票はしない。再現手順は上の「単体突合」節) |
