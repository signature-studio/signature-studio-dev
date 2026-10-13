# M11 実行後の guest ポインタ検査 (#1004, 部分達成)

親: #403 (受入 3 の後半)。素材: fl-win64 (`block00031_PE.bin` 22,227,016 B, sha256 先頭 `b2c64da4…`)・work-m11・work-liftdiff。
toolchain-retdec は `$RUNNER_TEMP/retdec/retdec/` に展開済み (`/opt/retdec` も存在)。

## 1. 実装 (完了)

- `tools/m11/m11_ptrcheck.mjs` — 実行後の guest メモリ全体で、4 バイト整列 word のうち image VA 範囲 `[0x400000, 0x400000+0x1ac0000)` に入り、かつ実行前には無かったものを数える。`M11_PTRCHECK_INJECT=<offset>` で既知の未 remap 値 `0x400000` を書き込めるようにした (ネガティブコントロール用)。
- `tools/m11/m11_run.mjs` / `m11_survey.mjs` — 実行後に `ptrcheck` の結果を JSON に出す (情報出力)。

## 2. 実測 (work-m11 の既存 wasm・image, LB=0 相当)

| 条件 | 所要 | 結果 |
|---|---|---|
| `m11_run.mjs` クリーン | 0.99 s (wall) | `image_va_words_pre=406576`・`image_va_words_new=68938`・`ok=false` |
| `m11_run.mjs` + `M11_PTRCHECK_INJECT=22519877` | — | `image_va_words_new=68939` (+1 を検出) |
| `m11_survey.mjs` | 0.26 s で異常終了 | `_m11_set_va_unit_budget is not a function`。work-m11 の wasm は現行 `m11_rt.c` より古い |

## 3. 未達 (受入条件との対応)

- **受入 1 (実行後検査)**: 実装済み。ただし上記 68,938 語のクリーン実行の「新規」範囲内 word は、正当な LVA の整数値とも未 remap の VA とも値だけでは区別できない。このため不合格ゲートにはしていない (e2e に組み込むと常に失敗する)。
- **受入 2 (不合格で非 0 終了)**: ゲート化を見送ったため未達。判定基準 (どの offset を未 remap とみなすか) を確定させる必要がある。
- **受入 3 (ネガティブコントロール同梱)**: 注入で +1 検出は確認したが、コントロールスクリプトは判定基準が未確定のため同梱していない。
- **受入 4 (`M11_LB_BASE=0` / `0x10000` の e2e 比較)**: 未実施。理由:
  - `m11_e2e.sh` が全再生成モードに入り、`m11_bounds.py` が素材に無い `tools/m2/work/ghidra_dll/functions_dll.csv` を要求して落ちる (fail-closed)。
  - work-m11 に `lift_pe.sha256`・`ir_conditions.json`・`ir_lb_base.stamp` が無く、WORKFLOW §11 のとおり pre-qstore 版。
  - 既存 wasm が現行 `m11_rt.c` と一致しないため、survey を実行できない。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 「未 remap の image VA」を実行後の値だけで判定できない (LB=0 は LVA=RVA で範囲が重なる) | 受入 1・2・3 の判定基準 | 本 issue (#1004) で継続 |
| `m11_e2e.sh` の全再生成が素材に無い `functions_dll.csv` を要求する | e2e 比較 (受入 4) が実行できない | PM 起票を要求 (素材 `work-m11` の再生成手順) |
| work-m11 の wasm が現行ソースより古い (`m11_set_va_unit_budget` 無し) | survey 実測が不可 | PM 起票を要求 (work-m11 の再生成) |
