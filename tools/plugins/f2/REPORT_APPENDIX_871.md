# PLG-F2 #871 付録: 0x6f1650 の原因切り分け (REPORT §10.1 の全文)

## 10.1 (#871 部分) 0x6f1650 の原因切り分け

- 検証 HEAD: `9c6f8c91` (`871-plg-f2-leaf-residual` 上、origin/main be9bb7c1 基点)。本付録の測定値はすべてこの commit で取得。`PLUG_XMMARG=1 PLUG_ICALL=0` の 6 block lift・`leaf_diff.sh` は一致 15 / 不一致 8 を再現 (139 秒、lift 19 秒)。
- **0x6f1650 (19059, `ret_only`) の原因: image 配置と IR 絶対 VA 定数のずれ (確定)**。機械語 `movaps/mulss/addss/divss` は定数 3 個 (0x6f166c・0x6f1670・0x6f1674) を rip 相対で読む。IR はこれを `inttoptr i64 <絶対 VA>` で持つが、`image/19059.bin` は RVA 配置で末尾が 0x3efa00 のため、絶対 VA 0x6f166c は image 外 (ゼロ埋め)。結果 `0 * m + a` の除算 `0/0` で NaN (0xffc00000) になり、native は 0x3f11c71c。引数 (xmm1=0x40200000) は wasm の trace で届いていることを確認済み。
- 同型の絶対 VA 定数は 30 関数 (317 箇所) にあり、`mk_targets.py` の image 配置 (RVA) と `inttoptr` の絶対 VA 規約が不整合。修正 (定数位置の再配置 or wasm_origin 規約の見直し) は 6 block 全体に効くため、回帰込みで #871 に残す (下記 未解決)。
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
- 未実施: 30 関数 (317 箇所) 全体への影響表、`nc_leaf.py` ネガコン、修正前からの未解決 6 関数の切り分け (上の件数定義の「残 6」)。

## 10.3 (#871 fix モード) 0x5de250 回帰の静的確認と未実施項目

- 素材: `fl-win64` のみ実在 (`$HOME/artifacts`)。`toolchain-retdec`・`toolchain-emsdk` は無く、`/opt` に `retdec`・`emsdk` も無い。RetDec の既定配布 URL (`retdec-v5.0-ubuntu-64b.tar.xz`) は 404。よって `f2_step1.sh` (IR 再生成)・`leaf_diff.sh`・`nc_leaf.py` は本 run では未実施。
- block19006 (`extracted/block19006_PE.bin`): ImageBase `0x400000`、SizeOfImage `0x3b2000`。IR の絶対 VA `0x30D0F4` は ImageBase より下 (image 外) だが、RVA `0x30D0F4` は `.data` (VA 0x2e0000、サイズ 0x3ca00) の内側。RVA `0x30D0F4` の先頭 16 byte は `01120805126800000d79100000000803`。
- 機序は未確定のまま。native 側の `/proc/<pid>/maps` 実測は未実施。この静的事実だけでは「回帰を期待される差分として許容する」根拠にならない。
- 未実施 (次の run で `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk` を指定して実施): f2_step1 → leaf_diff (修正前後) → nc_leaf.py ネガティブコントロール → 影響表 (30 関数 / 317 箇所)。
