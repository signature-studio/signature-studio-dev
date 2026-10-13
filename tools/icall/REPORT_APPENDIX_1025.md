# tools/icall 付録: #1025 (ICALL-17) Kilohearts Gain の icall 経路 wasm 化と native 差分

REPORT.md §15 相当。REPORT.md の 250 行上限のため別置き。親 #853 (ICALL-12)。

## 結論

**未達 (部分達成)**。icall 経路の復元後 IR から wasm ビルドまで成立したが、wasm 実行は未達 (前回 run で 61/61 シナリオが trap)。native 差分は未取得。

## 実測 (HEAD `a42f84e1`・`ws-1025` worktree・2026-10-13 21:36 UTC)

測定 run: PR #1247 の fix モード (レビュー指摘への対応)。HEAD `a42f84e1` を `ws-1025` worktree で実行。2 回 build して sha256 一致。

素材: `work-icall` を `tools/icall/work/` に展開 (`tar --zstd -xf`)。`plugins-kilohearts` / `toolchain-*` は `$ARTIFACTS_DIR` に実在を確認したが、本 build 経路では展開していない (emsdk は [EMSDK] を使用)。

| 項目 | 結果 | 実測 |
|---|---|---|
| 復元後 IR の後処理 (fix_mask / fix_vstore) | 成功 | `fix_mask` hi32_mask_fixed 2 / `fix_vstore` vstore_fixed 1, unresolved 83 |
| ir_flatten | 成功 | global defs removed 485, refs 300, i64 consts shifted 202, dispatch 表 164 entries (non-i64 ret wrapped 7) |
| m11_simd2 + vex_gen + simd_merge | 成功 | vex_generated 61 (unresolved 3: `__asm_vandnpd`・`__asm_vmovsd__27`・`__asm_vpcmpeqq`) / merge: extra_names 66, stubs_replaced_by_extra 63, fail_fast_installed 1, remaining_unimpl_stubs 13 |
| map.json | `blk` = `0x18a25c000`、`cfg_thunks` = `[]` | `python3` で読んだ値。`ncfg` 0 のため `ir_flatten.py --cfg ""` は正しい |
| emcc (-O0, メモリ 0x3c000000, BLK は map.json の `blk`) | 成功 | `kh_route.cjs` 107,844 B / `kh_route.wasm` 生成 (rc 0) |
| 再現 | 1 本 (rc 0) | `bash tools/icall/kh_route_build.sh` → rc 0。同一 worktree で 2 回 build し、`kh_route.cjs` / `kh_route.wasm` の sha256 が一致 |

**wasm のバイト数・sha256 はチェックアウトのパスに依存する**: `-g` のデバッグ情報に絶対パスが埋まるため、worktree が違うと値が変わる。受入値として使うのは「同一 worktree 内で 2 回 build して sha256 が一致すること」のみ。バイト数と build 時間は受入値にしない。

## 鮮度 (測定 commit から現 HEAD まで)

測定 commit `a42f84e1` (コードを変えた最後の commit。`kh_route_build.sh` のコメント修正と REPORT.md の空行削除)。上表は `a42f84e1` の worktree で実測した。`a42f84e1` から現 HEAD までのコード差分は 0 行。

```
$ git diff 44d70d74 a42f84e1 -- tools/icall/kh_route_build.sh tools/icall/ir_*.py tools/icall/rt tools/m2 tools/m5 tools/m11
diff --git a/tools/icall/kh_route_build.sh b/tools/icall/kh_route_build.sh
-# 1. 復元後 IR の後処理 (ICALL_FIX_MASK / ICALL_FIX_VSTORE は OTT と同じ既定 1)
+# 1. 復元後 IR の後処理 (fix_mask / fix_vstore を無条件に実行)
$ git diff a42f84e1 HEAD -- tools/icall/kh_route_build.sh tools/icall/ir_*.py tools/icall/rt tools/m*
(出力 0 行・exit 0)
```

`44d70d74..a42f84e1` の差分はコメント 1 行のみ (実行される行は不変)。`a42f84e1..HEAD` は 0 行。よって上表の数値は現 HEAD のコードに対しても有効 (再測定は不要, WORKFLOW §6)。

fix の内容: BLK を `map.json` の `blk` から取得 (旧 `0x3a25c000` は出典不明のハードコードだったため削除)、`ir_flatten.py --cfg` に `map.json` の `cfg_thunks` を渡す (OTT `ott_route.sh` と同じ生成式)。
`cfg_thunks` が空であることは上表の `map.json` の値で確認済み。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| PE の .rdata/.data 敷設 (`ott_data_install` が空定義) | wasm 実行の memory access out of bounds の直接原因の候補 (未切り分け) | #1025 (本 issue) |
| wasm 実行と native (`liftlib/work/kh_gain/diff` 61 シナリオ) の差分 | 受入条件 1・2 が未達 | #1025 |
| 再現コマンド 1 本化 (実行・差分込み) | 受入条件 3 が未達 (現状は build のみ) | #1025 |

## 実行段 (本 run・2026-10-13 23:44〜00:00 UTC)

測定 commit: 本 PR の HEAD (`tools/icall/kh_route_build.sh` と `tools/icall/kh_route_run.sh` を変えた最後の commit)。
再現: `bash tools/icall/kh_route_build.sh && bash tools/icall/kh_route_run.sh` (素材 `fl-win64 plugins-kilohearts toolchain-retdec toolchain-emsdk work-icall work-liftlib`)。

| 項目 | 実測 |
|---|---|
| BLK | map.json `blk` (0x18a25c000) − 0x150000000 = `0x3a25c000` (前回の 0x18a25c000 は wasm32 の範囲外) |
| flatten 窓 | `--limit 0x0c000000`。既定 0x4800000 では icall section (0x18625c000) と BLK が窓外で shift されず、`memory access out of bounds` の原因だった |
| PE data | `data_gen.py` で `.rdata/.data/_RDATA` 敷設 (空定義を廃止)。`i64 consts shifted` 202 → 8123 |
| wasm | `kh_route.wasm` 50,762,457 B (PE data 込み) |
| wasm 実行 (61 シナリオ, native と同じ scen.txt) | trap 0 / 366 steps。`rax` 一致 173/366 |
| native との比較 | **bit 一致 61/366 steps**。不一致バッファ: self 305・P 293・L 291・R 290 (step 数) |

判定: **受入 1・2 は未達**。wasm が trap せず 366 step を返すところまで成立した。残る差分は float 系バッファ (`self` の f32 フィールド・`L`/`R` 出力) と `rax` の不一致で、原因は未切り分け (候補: `__asm_movss` 系 SIMD helper の lane 扱い、`__icall_comis` のフラグ、`ott_run` の引数 ABI)。
