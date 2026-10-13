# PLG-F2 #871 付録: 0x6f1650 の原因切り分け (REPORT §10.1 の全文)

## 10.1 (#871 部分) 0x6f1650 の原因切り分け

- 検証 HEAD: `9c6f8c91` (`871-plg-f2-leaf-residual` 上、origin/main be9bb7c1 基点)。本付録の測定値はすべてこの commit で取得。`PLUG_XMMARG=1 PLUG_ICALL=0` の 6 block lift・`leaf_diff.sh` は一致 15 / 不一致 8 を再現 (139 秒、lift 19 秒)。
- **0x6f1650 (19059, `ret_only`) の原因: image 配置と IR 絶対 VA 定数のずれ (確定)**。機械語 `movaps/mulss/addss/divss` は定数 3 個 (0x6f166c・0x6f1670・0x6f1674) を rip 相対で読む。IR はこれを `inttoptr i64 <絶対 VA>` で持つが、`image/19059.bin` は RVA 配置で末尾が 0x3efa00 のため、絶対 VA 0x6f166c は image 外 (ゼロ埋め)。結果 `0 * m + a` の除算 `0/0` で NaN (0xffc00000) になり、native は 0x3f11c71c。引数 (xmm1=0x40200000) は wasm の trace で届いていることを確認済み。
- 同型の絶対 VA 定数は 30 関数 (317 箇所) にあり、`mk_targets.py` の image 配置 (RVA) と `inttoptr` の絶対 VA 規約が不整合。修正 (定数位置の再配置 or wasm_origin 規約の見直し) の影響は、本付録では leaf 23 関数のみで検証した (§10.5)。残り 7 関数 (非 leaf) の影響は未確認 (下記 未解決)。
- 修正前 (78aa75ad) の mismatch 8 関数のうち、0x6f1650 と 0x6c8fc0 は §10.2 の修正で解消。残り 6 関数 (0x6bfec0・0x6c8c90・0x6cc2e0・0x6c9b60・0x6b0ef0・0x6ca5c0) の原因は本 run では未切り分け。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 絶対 VA 定数の image 配置不整合の修正と 6 block 回帰 (0x6f1650 の値の解消) | 受入条件 1・4 | #871 ([PLG-F2-6]) |
| 修正前の未解決 mismatch 6 関数 (0x6bfec0・0x6c8c90・0x6cc2e0・0x6c9b60・0x6b0ef0・0x6ca5c0) の原因切り分け | 受入条件 1・2 | #871 ([PLG-F2-6]) |

親: #613 (PLG-F2-5)。未解決の追跡先は上表のとおり #871 のみ。

## 10.2 (#871 修正) mk_targets の恒等写像化: 部分達成 (回帰 1 件)

- 変更: `mk_targets.py` を `wasm_origin = ImageBase` (恒等写像) にし、DIR64 reloc の VA→RVA 補正を外した。IR の絶対 VA 定数をそのまま image 内に指せるようにする。
- 測定 HEAD: 修正前は `78aa75ad` (origin/main) で再現 (一致 15 / 不一致 8 / 実行不能 0、leaf_diff 130 秒)。修正後は HEAD `9d604905` で `leaf_diff.sh` を再実行 (一致 16 / 不一致 7 / 実行不能 0、126 秒、load 0.38)。
- 修正前後の差 (23 関数、最終判定):

| VA | block | 修正前 | 修正後 | 備考 |
|---|---|---|---|---|
| 0x6f1650 | 19059 | mismatch (ret_only) | **match** 11/11/11 | 受入の本命が解消 |
| 0x6c8fc0 | 18975 | mismatch (xmm_arg_drop) | **match** | 副次的に解消 |
| 0x5de250 | 19006 | **match** 8/8/11 | **mismatch** (memory_semantics) | **回帰** |

- 回帰の機序 (確定していない・暫定): 0x5de250 は IR で `load i32 @ inttoptr (3198772 = 0x30D0F4)` を読み、その値で分岐する。0x30D0F4 は ImageBase (0x400000) より下で image 外。修正前は wasm 側がこの値を別の内容として読んでいた。修正後は wasm 側の比較が native と一致しなくなり、`arena+0x1000` への store の有無が分かれる。
- 最終判定 (HEAD `9d604905`): 一致 **16** / 不一致 **7** / 実行不能 0 (修正前 15 / 8 / 0)。
- 件数の定義 (本付録・PR 本文で共通): 分母は leaf_diff の対象 23 関数。**残 mismatch 7 = 修正後の不一致全体** (内訳: 修正前からの未解決 6 関数 + 回帰 1 関数 0x5de250)。「残 6」は回帰を除いた数。
- 未実施: 残り 7 関数 (非 leaf、30 − 23) を含む 30 関数 (317 箇所) 全体への影響表、修正前からの未解決 6 関数の切り分け (上の件数定義の「残 6」)。本付録の影響表は leaf 23 関数に限る (§10.4・§10.5)。

## 10.3 (#871 fix モード) 0x5de250 回帰の静的確認と未実施項目

- 素材: `fl-win64` のみ実在。`toolchain-retdec`・`toolchain-emsdk` は無く、`[RETDEC]`・`[EMSDK]` も未導入。よって `f2_step1.sh` (IR 再生成)・`leaf_diff.sh`・`nc_leaf.py` は本 run では未実施。
- block19006 (`extracted/block19006_PE.bin`): ImageBase `0x400000`、SizeOfImage `0x3b2000`。IR の絶対 VA `0x30D0F4` は ImageBase より下 (image 外) だが、RVA `0x30D0F4` は `.data` (VA 0x2e0000、サイズ 0x3ca00) の内側。RVA `0x30D0F4` の先頭 16 byte は `01120805126800000d79100000000803`。
- 機序は未確定のまま。native 側の `/proc/<pid>/maps` 実測は未実施。この静的事実だけでは「回帰を期待される差分として許容する」根拠にならない。
- 未実施 (次の run で `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk` を指定して実施): f2_step1 → leaf_diff (修正前後) → nc_leaf.py ネガティブコントロール → 影響表 (leaf 23 関数)。残り 7 関数は §10.5 のとおり別途。

## 10.4 (#871 fix モード 2) 実測: f2_step1 / leaf_diff (修正前後) / nc_leaf / 修正前後の突き合わせ

前版 (10.3) の「素材なし」は誤り。RetDec 公式 Release (`RetDec-v5.0-Linux-Release.tar.xz`, avast/retdec v5.0, `[RETDEC]`) は取得でき、emsdk 6.0.12 (`tools/m1/flags.sh` の pin, `[EMSDK]`) を導入した。fl-win64 は run 内の一時領域に展開 (13 s, PE 313 本)。実行は run 内で完結。

| 項目 | HEAD (`747c5fe0`, 修正後) | base (`78aa75ad`, 修正前) |
|---|---|---|
| `f2_step1.sh` | rc 0、7 m 04.8 s | rc 0、7 m 07.6 s |
| `leaf_diff.sh` | rc 0、2 m 17.3 s、一致 **16** / 不一致 **7** / 実行不能 0 | rc 0、2 m 15.2 s、一致 **15** / 不一致 **8** / 実行不能 0 |
| `nc_leaf.py` (HEAD) | rc 0、3 m 12.2 s。変異 28 件 (store_drop 5 / load_drop 10 / offset_shift 13) すべて mismatch、未検出 0、unexec 0 | - |

### 修正前後の判定 (leaf_diff の対象 23 関数)
遷移: match→match 14, mismatch→mismatch 6, **match→mismatch 1**, mismatch→match 2。
- 回帰 (match→mismatch): 0x5de250 (19006) のみ。
- 改善 (mismatch→match): 0x6c8fc0 (18975, base は xmm_arg_drop で mismatch→match)、0x6f1650 (19059)。
- 不変の mismatch 6: 0x6bfec0, 0x6c9b60, 0x6b0ef0, 0x6c8c90, 0x6cc2e0, 0x6ca5c0。

集計コマンド: `python3` で `leaf_diff.sh` の stdout 表 (`^| <#> | <block> | ... | **<verdict>**`) を VA で突き合わせ (base = 修正前ログ、head = 修正後ログ。いずれも run の一時領域に置き、repo には残さない)。

### 0x5de250 回帰の切り分け (未解決)
- IR (`tools/plugins/work/batch/19006/p.final.ll`) の `@function_5de250` は `i32 load (inttoptr i64 3198772)` = 絶対 VA `0x30D0F4` を読み、`(arg & 0x7fffffff) < 値` で分岐して `store i32 0, ptr %arg1` する。
- block19006 PE: ImageBase `0x400000`、SizeOfImage `0x3b2000`。絶対 VA `0x30D0F4` は image 外。RVA `0x30D0F4` は `.data` (VA `0x2e0000`、サイズ `0x3c838`) の内側で、先頭 16 byte は `01120805126800000d79100000000803`。
- 修正後の wasm は `wasm_origin = ImageBase` で image を置くため、IR の `0x30D0F4` は image 外を読む。修正前は RVA として image 内を読んでいた。
- **native 側の実測は未完**: 通常プロセス (gcc 製プローブ) の `/proc/self/maps` には `0x30D0F4` が現れなかった (これは `ld_native` の実行環境ではない)。`ld_native` 内で `0x30D0F4` が何を指すか (mapping の有無・読んだ値) は未測定。その実測が無い限り、回帰の意味は決まらない。**機序は未確定のまま**。

### 未実施: 残りの 7 関数 (30 − 23) と 317 箇所の影響表
leaf_diff は IR leaf かつ機械語に間接 call 無しの 23 関数のみを対象とする。残りは非 leaf で、本 run では liftdiff にかけていない。したがって「絶対 VA 定数の修正で壊れていない」根拠は 7 関数分まだ無い。起票先: #923 (子として残す)。

## 10.5 (#871 fix モード 3) 範囲の限定と未解決

- 本 run の素材: `fl-win64` のみ実在。`[RETDEC]`・`[EMSDK]` は未導入で、`f2_step1.sh` (IR 再生成) を実行できない。したがって 10.5 で新たな実測は追加していない。10.4 の数値は前 run (HEAD `747c5fe0`/`3ca876d4`、base `78aa75ad`) の測定値。
- 指摘 1 (回帰 0x5de250): 未解決。`ld_native` 内で絶対 VA `0x30D0F4` が何を指すかは未測定。回帰を「期待される差分」として許容する根拠は無い。本 PR は回帰を残したまま merge しない。
- 指摘 3 (影響表): 範囲を leaf 23 関数に限定して検証した。残り 7 関数 (非 leaf、30 − 23) の liftdiff は未実施。影響の有無は未確認。
- 受入条件「回帰: 一致 15 以上」は件数ではなく「既存 match の維持」で判定する。現時点では 0x5de250 の match 維持に失敗しているため、未達。
- 起票先: 回帰の解消・ld_native 実測・残 7 関数の liftdiff は #923 (子)。修正前からの未解決 mismatch 6 関数は #871 / #613。

## 10.6 (#871 fix モード 4) 最終 head での再測定 (素材付き run)

- 検証 HEAD: `71d6fd68` (コード差分は `9d604905` 以降なし。`git diff 9d604905 HEAD -- tools/plugins/f2/mk_targets.py tools/liftdiff tools/plugins/f2/leaf_diff.sh` が空)。
- 素材: `fl-win64`・`toolchain-retdec`・`toolchain-emsdk` を `$ARTIFACTS_DIR` から展開 (fl-win64 13.8 s、PE 実在を確認)。emcc は `tools/m1/flags.sh` の pin `6.0.12` を確認。
- `f2_step1.sh`: rc 0、558 s。間接 call 監査の IR leaf 55 / うち機械語でも間接 call 無し 23 (leaf_diff の対象 23 関数と一致)。
- `leaf_diff.sh` (HEAD `71d6fd68`): rc 0、148 s、load 1.36。**最終判定 一致 16 / 不一致 7 / 実行不能 0** (10.2・10.4 の前 run 測定値と一致)。集合一致 EQ。IR から call 脱落 0。
- 最終判定 (23 関数、HEAD `71d6fd68`):

| VA | block | 最終判定 | 備考 |
|---|---|---|---|
| 0x6f1650 | 19059 | match | 修正の本命 |
| 0x6c8fc0 | 18975 | match | 副次的に解消 |
| 0x5de250 | 19006 | **mismatch** (memory_semantics) | **回帰** (§10.3 の機序は未確定) |
| 0x6bfec0 | 18975 | mismatch | 修正前から未解決 |
| 0x6c9b60 | 18975 | mismatch | 修正前から未解決 |
| 0x6b0ef0 | 18982 | mismatch | 修正前から未解決 |
| 0x6c8c90 | 19005 | mismatch | 修正前から未解決 |
| 0x6cc2e0 | 19006 | mismatch | 修正前から未解決 |
| 0x6ca5c0 | 19013 | mismatch | 修正前から未解決 |
| 上記以外 14 関数 (match) | - | match | 0x6cd8a0・0x662fc0・0x73e640・0x73fa20・0x73fa70・0x5de300・0x6e9440・0x6ec2a0・0x6ec2f0・0x6f1c40・0x6f1c60・0x6f2320・0x6f2370・0x6f23b0 |

- 最終判定の内訳: match 16 (上の 2 関数 + 14 関数) / mismatch 7 (上の表の 7 関数のうち 0x5de250 以外の 6 関数と回帰 0x5de250)。
- 件数の定義は §10.2 のとおり (残 mismatch 7 = 回帰 1 + 未解決 6)。
- 件数 (一致 16 / 不一致 7 / 実行不能 0) と回帰 0x5de250・改善 0x6f1650・0x6c8fc0 の判定は §10.4 の前 run 測定と一致。
- 本 run の `nc_leaf.py` は再実行していない (§10.4 の HEAD `747c5fe0` 測定を残す。コード差分なし)。修正前 `78aa75ad` との関数単位の突き合わせ (遷移 14/6/1/2) は今回は再計算していない (ログ未保存のため)。
- 範囲は leaf 23 関数のみ (§10.5)。残り 7 関数は未確認。
