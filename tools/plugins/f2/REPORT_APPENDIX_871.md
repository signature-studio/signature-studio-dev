# PLG-F2 #871 付録: 0x6f1650 の原因切り分け (REPORT §10.1 の全文)

## 10.1 (#871 部分) 0x6f1650 の原因切り分け

- 検証 HEAD: `9c6f8c91` (`871-plg-f2-leaf-residual` 上、origin/main be9bb7c1 基点)。本付録の測定値はすべてこの commit で取得。`PLUG_XMMARG=1 PLUG_ICALL=0` の 6 block lift・`leaf_diff.sh` は一致 15 / 不一致 8 を再現 (139 秒、lift 19 秒)。
- **0x6f1650 (19059, `ret_only`) の原因: image 配置と IR 絶対 VA 定数のずれ (確定)**。機械語 `movaps/mulss/addss/divss` は定数 3 個 (0x6f166c・0x6f1670・0x6f1674) を rip 相対で読む。IR はこれを `inttoptr i64 <絶対 VA>` で持つが、`image/19059.bin` は RVA 配置で末尾が 0x3efa00 のため、絶対 VA 0x6f166c は image 外 (ゼロ埋め)。結果 `0 * m + a` の除算 `0/0` で NaN (0xffc00000) になり、native は 0x3f11c71c。引数 (xmm1=0x40200000) は wasm の trace で届いていることを確認済み。
- 同型の絶対 VA 定数は 30 関数 (317 箇所) にあり、`mk_targets.py` の image 配置 (RVA) と `inttoptr` の絶対 VA 規約が不整合。修正 (定数位置の再配置 or wasm_origin 規約の見直し) は 6 block 全体に効くため、回帰込みで #871 に残す (下記 未解決)。
- 残る 5 関数 (0x6bfec0・0x6c8fc0・0x6c9b60・0x6c8c90・0x6cc2e0 ほか) の原因は本 run では未切り分け。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 絶対 VA 定数の image 配置不整合の修正と 6 block 回帰 (0x6f1650 の値の解消) | 受入条件 1・4 | #871 ([PLG-F2-6]) |
| 残 5 関数 (no_placeholder 3 / slot_occupied 2) の原因切り分け | 受入条件 1・2 | #871 ([PLG-F2-6]) |

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
- 最終判定 (HEAD `9d604905`): 一致 **16** / 不一致 **7** / 実行不能 0 (修正前 15 / 8 / 0)。回帰 1 件を含む。
- 未実施: 30 関数 (317 箇所) 全体への影響表、`nc_leaf.py` ネガコン、残 5 関数の切り分け。
