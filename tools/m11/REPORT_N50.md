# #928 (M11-N50) m11_e2e.sh の RetDec PATH 解決 — 実測

親: #715。修正本体は `74b365f6` (main 取込済み)。本書は同 issue の受入条件の実測記録。

## 実測 (測定 commit `b34304f2`・2026-10-13・検証 HEAD `b34304f2`)

- 素材: fl-win64 sha256 `b2c64da4…` (展開先 `FL_WIN64_DIR`)・toolchain-retdec (`[RETDEC]`・retdec-decompiler v5.0)・work-m11 (`tools/m11/work/`)。`[EMSDK]` は runner 同梱の 6.0.12 (pin 一致) を使用。Ghidra 12.1.4 (`[GHIDRA]`) を取得し、JDK 21 で `functions_dll.csv` (59 010 行) を生成。
- `RETDEC_ROOT` 未設定・PATH に `retdec-decompiler` 無し。

| 実行 | rc | 所要秒 | 結果 |
|---|---|---|---|
| `m11_lift.sh` 3 range (`boot_ranges_extra.txt` 先頭 3 件) | 0 | 8.0 | RetDec 160 lines / ir5 111 lines |
| Ghidra 12.1.4 headless → `functions_dll.csv` | 0 | 622 | 59 010 行 |
| `m11_e2e.sh --full` 1 回目 (`obj` 未削除) | 0 | 640 | reached_stage 4 / survey_ok 871 / trap 24 (oom 0) / clobber 0 / miss 46 / ir_sha256 `4103911…` |
| `obj/rt.o` `obj/win.o` を削除して `--full` 2 回目 | 0 | 634 | reached_stage 4 / survey_ok 871 / trap 24 (oom 0) / clobber 0 / miss 46 / ir_sha256 `9437864…` |

- 2 回の `ir_sha256` が異なる (未切り分け・既知。IR の指紋は実行ごとに変わる)。
- 2 回目の build は `obj/rt.o`・`obj/win.o` を削除した状態で通過 (`_m11_set_va_bigtrace` の undefined は再現せず)。

## 鮮度

- 測定 commit: `b34304f2` (本表の測定を行った HEAD)。
- `git diff b34304f2 HEAD -- tools/m11 tools/liftlib ':!*.md'` の出力は 0 行 (差分 0)。本表は現 HEAD の根拠として使える。

## 結論

- retdec の PATH 解決に起因する失敗は再現しない (`m11_lift.sh` は既定 [RETDEC] で解決して rc 0)。
- `--full` の再生成経路は現 HEAD で rc 0 (2 回)。受入条件 3 を満たす。
- `--full` の残る trap (`unreachable` @ function_8c5eb0) は reached_stage 4 の既知事象で本 issue の対象外。build 失敗の残件は #1176 (`[M11-N71]`)。

## 測定中の入力変更 (未解決)

- `--full` の `m11_tail.py` (固定点処理) が測定中に `tools/m11/m11_extra_seeds.txt` へ seed `0x4572b0` を 1 行追記した (`git diff` で 1 insertion)。2 回の `--full` の ir_sha256 が異なる原因の候補。
- 本 commit では seed ファイルを戻さず・含めない (測定の入力を変えないため)。次の PR で seed の扱い (コミットするか・測定ごとに固定するか) を決める。
- 起票先: #1176 (`[M11-N71]`)。
