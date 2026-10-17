# icall #4290 (ICALL-97): リーフ 3 関数の abort 原因と route 入力の統合

測定 commit: `328331860` (コードを変えた最後の commit。main `fe48dca85` の上)。
`git diff 328331860 HEAD -- tools/icall` の出力は 0 行 (本 PR の HEAD で測定した)。

## 1. 結論

- 前回 (`abort`) の原因: `fa_route_build.sh` が `after.0.restored.ll` (chunk 0) だけを入力にしていた。
  3 関数はいずれも chunk 0 に定義が無く、`ir_flatten.py` の入口表 `icall_tbl_va` に入らず `unknown entry` で abort していた。
- 修正: `ir_merge_restored.py` で `after.{0..3}.restored.ll` を統合する (`fa_route_build.sh` の既定経路)。統合後は入口表 164 件 (chunk 0 のみでは 131 件)。
- 結果: `181056a4c` `181056aa0` は native と wasm が 8/8 一致。`18105d9fc` は `unreachable` trap で 0/8 (未解決)。

## 2. 測定

| 手順 | 条件 | 結果 | 所要 (real) |
|---|---|---|---|
| `roundtrip.sh` | `CHUNKS=4`・`fa_ranges_4271.txt`・`freshair-4290` | rc 0・`lost 6` (非IAT) | 50.7 s |
| `fa_route_build.sh` (統合) | `FA_RT=tools/icall/work/rt_freshair-4290` | OK・`[merge] chunks 4, defines 164`・table 164 | 9.7 s |
| `fa_cmp.py 181056a4c --n 8` | `FA_MAP=rt_freshair-4290/map.json` | match 8 / mismatch 0 | — |
| `fa_cmp.py 181056aa0 --n 8` | 同上 | match 8 / mismatch 0 | — |
| `fa_cmp.py 18105d9fc --n 8` | 同上 | match 0 / mismatch 8 (`ERR:RuntimeError: unreachable`) | — |
| `fa_cmp.py 180da6e60 --n 8` | 同上 (回帰確認) | match 8 / mismatch 0 | — |

`missing` は 4 件のまま (`1801a9a6c` `1801a9b38` `1801c8c00` `1801c8cb8`)。前回の仮説「`missing` の override 未適用が原因」は、今回の abort の原因ではなかった。

## 3. 統合で扱った差異

`ir_merge_restored.py` の入力で確認したこと:
- `define` は chunk 間で重複しない (164 件)。
- 同名 global の定義が矛盾するもの 2 件: `@global_var_18125eaa8` (chunk 0 は `i64`、chunk 1〜3 は `i32`) と `@global_var_1813068d8` (`local_unnamed_addr` の有無だけ)。先頭 chunk の定義を採る。cookie 型は `fa_route_build.sh` の `ir_fix_cookie.py` が i64 に直す。
- metadata 番号 (`!N`) は chunk ごとに後ろへずらす。ずらさないと `llvm-link` が衝突で失敗する。
- RetDec 出力 (chunk 0〜3) は `llvm-as` の検証を通らない (`uselistorder` の不整合・`%wide-string` の不正構文)。統合は `uselistorder` を落とし、`%wide-string` は chunk 3 にだけある。route 本体は `ir_flatten` 以降がテキスト処理のため、統合 IR のまま build できた。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `18105d9fc` が `unreachable` で trap (0/8)。`oi.flat.ll` に `unreachable` は無く、wasm 側の trap 位置は未特定 | 3 関数の受入のうち 1 件が未達 | #4290 のまま (次 run) |
| RetDec 出力 (chunk 0〜3) が `llvm-as` 検証を通らない | 統合 IR の検証を route build の外でできない | #4290 のまま (注記のみ) |
| `1803b5500` `180da5f20` の `missing function` | 測定期待値 (`mismatch 8・wasm_err 8`) どおり。本 issue の範囲外 | 既存の記録どおり |
