# tools/icall 付録: #1025 (ICALL-17) Kilohearts Gain の icall 経路 wasm 化と native 差分

REPORT.md §15 相当。REPORT.md の 250 行上限のため別置き。親 #853 (ICALL-12)。

## 結論

**未達 (部分達成)**。icall 経路の復元後 IR から wasm ビルドまで成立したが、wasm 実行は未達 (前回 run で 61/61 シナリオが trap)。native 差分は未取得。

## 実測 (HEAD `cd2202c9` ベースの `ws-1025`, 2026-10-13 UTC)

| 項目 | 結果 | 実測 |
|---|---|---|
| 復元後 IR の後処理 (fix_mask / fix_vstore) | 成功 | `fix_mask` hi32_mask_fixed 2 / `fix_vstore` vstore_fixed 1, unresolved 83 |
| ir_flatten | 成功 | global defs removed 485, refs 300, dispatch 表 164 entries (non-i64 ret wrapped 7) |
| m11_simd2 + vex_gen + simd_merge | 成功 | merge: extra_names 66, stubs_replaced_by_extra 63, remaining_unimpl_stubs 13 |
| emcc (-O0, メモリ 0x3c000000, BLK は map.json の `blk`) | 成功 (前回 run 実測・未再現) | `kh_route.cjs` 107,844 B / `kh_route.wasm` 628,625 B |
| 再現 | 1 本 (未再実行) | `bash tools/icall/kh_route_build.sh` (前回 run: rc 0, build 段 7 秒 = 19:47:21〜19:47:28 UTC) |

**注 (fix 版 `1247/merge` 時点)**: 上表の数値は HEAD `cd2202c9` の前回 run で取得したもので、本 PR の fix commit では再実行していない。
fix の内容: BLK を `map.json` の `blk` から取得 (旧 `0x3a25c000` は出典不明のハードコードだったため削除)、`ir_flatten.py --cfg` に `map.json` の `cfg_thunks` を渡す (OTT `ott_route.sh` と同じ生成式)。
素材 `work-icall` (`after.0.restored.ll`・`map.json`) と `plugins-kilohearts` (`HeartCore.core_64`) は再実行 run では未展開のため、fix 後の build 実測は未取得。



## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| PE の .rdata/.data 敷設 (`ott_data_install` が空定義) | wasm 実行の memory access out of bounds の直接原因の候補 (未切り分け) | #1025 (本 issue) |
| wasm 実行と native (`liftlib/work/kh_gain/diff` 61 シナリオ) の差分 | 受入条件 1・2 が未達 | #1025 |
| 再現コマンド 1 本化 (実行・差分込み) | 受入条件 3 が未達 (現状は build のみ) | #1025 |
