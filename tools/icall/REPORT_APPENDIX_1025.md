# tools/icall 付録: #1025 (ICALL-17) Kilohearts Gain の icall 経路 wasm 化と native 差分

REPORT.md §15 相当。REPORT.md の 250 行上限のため別置き。親 #853 (ICALL-12)。

## 結論

**未達 (部分達成)**。icall 経路の復元後 IR から wasm ビルドまで成立したが、wasm 実行は未達 (前回 run で 61/61 シナリオが trap)。native 差分は未取得。

## 実測 (HEAD `0b761625`・`ws-1025` detached worktree・2026-10-13 20:10 UTC)

素材: `work-icall` を `tools/icall/work/` に展開 (`tar --zstd -xf`・22.9 s)。`plugins-kilohearts` / `toolchain-*` は `$ARTIFACTS_DIR` に実在を確認 (`ls -la`) のみで、本 build 経路では展開していない (emsdk は `/opt/emsdk`)。

| 項目 | 結果 | 実測 |
|---|---|---|
| 復元後 IR の後処理 (fix_mask / fix_vstore) | 成功 | `fix_mask` hi32_mask_fixed 2 / `fix_vstore` vstore_fixed 1, unresolved 83 |
| ir_flatten | 成功 | global defs removed 485, refs 300, i64 consts shifted 202, dispatch 表 164 entries (non-i64 ret wrapped 7) |
| m11_simd2 + vex_gen + simd_merge | 成功 | vex_generated 61 (unresolved 3: `__asm_vandnpd`・`__asm_vmovsd__27`・`__asm_vpcmpeqq`) / merge: extra_names 66, stubs_replaced_by_extra 63, fail_fast_installed 1, remaining_unimpl_stubs 13 |
| map.json | `blk` = `0x18a25c000`、`cfg_thunks` = `[]` | `python3` で読んだ値。`ncfg` 0 のため `ir_flatten.py --cfg ""` は正しい |
| emcc (-O0, メモリ 0x3c000000, BLK は map.json の `blk`) | 成功 | `kh_route.cjs` 107,844 B / `kh_route.wasm` 628,625 B (同一 HEAD の 2 回目 build で sha256 一致) |
| 再現 | 1 本 (実行 rc 0) | `bash tools/icall/kh_route_build.sh` → rc 0、`time` 実測 real 6.317 s (script 全体) |

**wasm サイズはチェックアウトのパスに依存する**: `-g` のデバッグ情報に絶対パスが埋まる (`.../signature-studio-dev/<worktree>/...`)。
同じ HEAD を `ws-1025` (628,625 B) と別名の worktree (628,689 B) で build して確認した。レビュー run の 628,501 B は別パスで build された値と考えられ、本 run では再現していない。

fix の内容: BLK を `map.json` の `blk` から取得 (旧 `0x3a25c000` は出典不明のハードコードだったため削除)、`ir_flatten.py --cfg` に `map.json` の `cfg_thunks` を渡す (OTT `ott_route.sh` と同じ生成式)。
`cfg_thunks` が空であることは上表の `map.json` の値で確認済み。



## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| PE の .rdata/.data 敷設 (`ott_data_install` が空定義) | wasm 実行の memory access out of bounds の直接原因の候補 (未切り分け) | #1025 (本 issue) |
| wasm 実行と native (`liftlib/work/kh_gain/diff` 61 シナリオ) の差分 | 受入条件 1・2 が未達 | #1025 |
| 再現コマンド 1 本化 (実行・差分込み) | 受入条件 3 が未達 (現状は build のみ) | #1025 |
