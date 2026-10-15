# REPORT 付録 (#4955 KH-136): func_0x0001802ecfc0 (tap_add) の宣言型を機械語どおりに直す

親 #4014 の残件 (#4014 の受入 2 と宣言型の修正を引き継ぐ)。

## 結論

- `FUN_1802ecfc0` の `param_3`・`param_4` は、生成 C で `float *` だったが、機械語では 16 byte の `V128` オペランドである。`DELAY_RULES` 4 件 (宣言 1・本体 2・呼出元 1) で `V128 *` に直した。
- emcc の error は 2 件減った (delay の emcc census は **418 → 416**)。内訳は表の実測差分のとおり、演算・代入・ポインタの型不一致が 1 件 (171 → 170)、128bit レーン型が 1 件 (167 → 166)。
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
- 測定 commit から現 HEAD (`65cdeaf30`) までの差分: `git diff ca1f38304 HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` は **4 行** (`ghidra_route/patches.py` +4。main 取り込みで入った #4835 の ABI 規則 `delay 2666 FUN_180fbbfb8 rcx=param_1 (FUN_180fbdfcc)`)。本 PR の変更ではないが、`name == 'delay'` の変換に効くため、下表の census は HEAD の実行コードの値ではない。
- **HEAD `65cdeaf30` での再測定は未実施** (本 run に `plugins-kilohearts` (`HeartCore.core_64`) と `toolchain-emsdk` が無かった)。下表は `ca1f38304` 時点の実測値で、現 HEAD の census は未確定。再測定は `oc_artifacts: plugins-kilohearts toolchain-emsdk` を付けた run で行い、結果で下表を置き換える。
- 基準: 同じ素材・同じ道具で、`git archive origin/main` の `ghidra_route`・`snapins/lift`・`snapins/scripts` を使う変換器の出力。
- 素材: `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64`、76,642,304 B)。`toolchain-emsdk` (emcc 6.0.12)。Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致・JDK 21)。
- decompile: 挿入順の lift 集合 (142 件・重複 1 件) で **142/142 OK** (wall 40 s)。
- 変換: `ghidra_to_c.py delay … --fix bitcast,intload,stackpair,assoc,concat`。emcc: `emcc -c -ferror-limit=0`。load: 測定時 0.4〜1.3 (4 vCPU)。

| 分類 | 基準 (main) | 本 PR |
|---|---|---|
| 未関数化 callee | 0 | 0 |
| 128bit レーン型 | 167 | 166 |
| 引数数不一致 | 80 | 80 |
| 演算・代入・ポインタの型不一致 | 171 | 170 |
| **合計 (census)** | **418** | **416** |
| emcc error 行 (`error:`) | 418 | 416 |

- 消えた 2 件の内訳: 演算・代入・ポインタの型不一致 1 件 (171 → 170) と 128bit レーン型 1 件 (167 → 166)。**行番号は未確認**。census の入力 (`plugins-kilohearts` の `HeartCore.core_64`) が本 run の素材に無く、diff 前後の `error:` 行を取り直せなかったため、どの行が消えたかは特定していない。特定は census の再実行 (素材が揃った run) で行う。
- 注: この census は `main` (`0f5bcaa89`) の decompile から作ったもので、#4687 §9 の 441 件とは取り方が違う (decompile の集合・規則が main の進みで変わった)。差分の比較は同じ条件 (本 PR と基準) の値で行った。

## 回帰 (Gain/Haas/Gate への影響)

- 規則は `name == 'delay'` のガード内 (`DELAY_RULES`) にだけ入るため、Gain/Haas/Gate の変換は通らない。
- 規則の件数 assert (`delay rule hit … want 1`) は、規則が 1 件ずつ当たることを変換時に検査する (外れると変換が止まる)。
- Gain/Haas/Gate の `.o` の `cmp` は、本 PR では未実施 (decompile 集合が `work/ghidra/out` 側で別に必要なため)。これは Gain/Haas/Gate の既存測定 (`build_cmp.sh`) の範囲で、本 issue の範囲外。

## 単体突合 (機械語 vs 生成 C 本体)

- 検証スクリプト: `work/kh136/check.c` (`ghidra_shim.h` + 生成 C の `FUN_1802ecfc0` 本体)。`work/` は gitignore 対象のため repo に無い。突合は repo から再現できない状態で、本 PR の範囲では再現していない (未解決の表を参照)。再現手順は次のとおり: (1) `ghidra_route/ghidra_shim.h` を include し、`ghidra_to_c.py delay` で生成した `FUN_1802ecfc0` 本体を `check.c` に貼る。(2) 入力は乱数で、`param_1` は 1 KB のメモリ、`param_3`・`param_4` は 16 byte。(3) 参照側は `addps`・`movlps` の C 再現 (下位 2 lane の float 加算と 8 byte 書込み)。(4) 200,000 試行で両者の出力 (`param_1` の 1 KB) を比較する。
- 参照: 機械語 `addps`・`movlps` を C で再現 (下位 2 lane の float 加算と 8 byte 書込み)。入力は乱数 (`param_1` の 1 KB メモリ・`param_3`/`param_4` の 16 byte)。
- 結果: **mismatches 0 / 200,000** (rc 0)。
- ネガティブコントロール (`param_3` の lane 0 の加算を減算に変更): **mismatches 117,490 / 200,000** (rc 1)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Delay の native 突合 (1000 trial bit-exact) | 宣言型の正しさは機械語の読みと単体突合で示したが、Delay 全体の出力は未確認 | #3073 [KH-41] |
| Gain/Haas/Gate の `.o` の cmp (本 PR の規則の非影響の実測) | 規則のガードで影響しないと判断。実測は未実施 | 本 PR の範囲外 (規則は delay ガード内) |
| 残件 416 (レーン 166・引数数不一致 80・型不一致 170) | Delay の emcc が通らない | #3801 [KH-65]・#3808 [KH-67]・#3809 [KH-68]・#3844 [KH-79]・#3847 [KH-73] (既存の起票先) |
| 消えた 2 件の行番号 (census の diff 前後の `error:` 行) | 内訳は分類差分のみ確認。行の特定は未実施 | 本 PR の範囲外 (census 素材が揃った run で再測定) |
| 突合 `work/kh136/check.c` の repo 外 (gitignore) | 200,000 試行の突合を repo から再現できない | 未起票 (突合スクリプトの追跡化は issue 未作成。再現手順は上の「単体突合」節) |
