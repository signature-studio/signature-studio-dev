# ildsp REPORT 付録: PSOLA closure の native 差分 harness の HEAD 再実行記録 (#3469・T-SH-86)

親: #3428 (T-SH-82)。本 issue: #3469 (T-SH-86)。`REPORT.md` §8・`REPORT_APPENDIX_3401.md` の続き。
harness `lift_psola.sh` は #3401 で main に入っている (コードは変えていない)。本付録は、受入条件に挙げられた
「ケース数と PASS/FAIL の記録」を HEAD で取った結果の正本。

## 結論 (1 行)
`lift_psola.sh` は HEAD `8ea8d42b8` で再現する。CreateInstance → slot 0 → slot 4 → slot 5 の native 対 wasm は 64 case 全一致 (PASS 64 / FAIL 0)、ネガティブコントロール (arena 先頭 1 バイト反転) は FAIL 64 / 64、回帰 `lift_wc.sh ok` は PASS 64 / 64。

既知類型との関係: 該当なし (`docs/DEFECTS.md` に VEX・ymm・unsup の類型記述は無い。差分は 0 件)。

測定 commit: `8ea8d42b8` (origin/main・検証起点も同じ)。clean worktree (`../ws-3469`) で測定した。
本付録の commit 以降のコード差分: `git diff 8ea8d42b8 HEAD -- tools/shared/lift/ildsp tools/flelift tools/shared/env.sh tools/shared/scripts ':!*.md'` の出力は空 (差分 0)。

## 受入条件の対応
| 受入 (#3469) | 結果 |
|---|---|
| 1. `lift_psola.sh` を作る (`lift_wc.sh` と同じ流れ) | 作成済み (#3401。`lift_wc.sh` の harness を環境変数で差し替えて `exec` する)。HEAD で再実行: PASS 64 / FAIL 0 |
| 2. 比較器のネガティブコントロール (`lift_psola.sh neg-cmp`) | FAIL 64 / 64 (rc 1・期待どおり) |
| 3. 回帰 `lift_wc.sh ok` が PASS 64/64 のまま | PASS 64 / FAIL 0 (rc 0) |

## 対象と規模 (HEAD・`x64c.py --closure 99`)
| 項目 | 値 |
|---|---|
| root (RVA) | `0x1ab540` (CreateInstance)・`0x1ab590` (slot 0)・`0x1ab6b0` (slot 4)・`0x1ab800` (slot 5) (`WC_ROOTS`) |
| 呼出順 | CreateInstance → slot 0 → slot 4 → slot 5 (`WC_CALL_IDX="0 4 5"`) |
| 戻り値の畳み込み | slot 5 のみ (`WC_RET_IDX="5"`)。slot 4 の戻り値は ABI 上未定義 (`REPORT_APPENDIX_3401.md` §8-4) |
| x64c | 36 関数・1,046 命令・unsup 0・unlifted callees 0・traps 0・imports 10 |
| wasm | 80,737 B (emcc `-O1`) |
| 比較 case | 64 (case 0 = 元の .data。`wc_cases.py`) |

参考 (`lift_wc.sh`・WaveformColouring): 60 関数・2,656 命令・unsup 3 (`vcvtss2sd` 1・`vpmovsxdq` 1・`vshufps` 1)・wasm 138,754 B。

## 比較の中身
- native 側: `wc_native_ref.c` を gcc で実行 (元の機械語)。wasm 側: x64c lift → emcc → `wc_run_wasm.mjs`。
- 比較: `wc_diff_test.py` が rax・import stub の呼出回数・heap (arena 64 KiB)・.data 全体を全バイトで比べる。
- 素材: `fl-win64.tar.zst` (2,324,302,252 B) と `toolchain-emsdk.tar.zst` (532,513,899 B) を `tar --zstd -xf` で `$RUNNER_TEMP` 配下に展開 (5.5 s・4.4 s)。`extracted/block24360_PE.bin` の実在を確認してから実行した。

## 実測 (HEAD `8ea8d42b8`・clean worktree・4 core・各 3 回)
| コマンド | 差分 (3 回共通) | elapsed (s) | load 1 分 (開始 → 終了) |
|---|---|---|---|
| `lift_psola.sh ok` | PASS 64 / FAIL 0 / wasm trap 0 | 1.71–1.73 | 0.39 → 0.39–0.44 |
| `lift_psola.sh neg-cmp` | FAIL 64 / 64 (rc 1) | 1.72–1.75 | 0.44 → 0.44–0.49 |
| `lift_wc.sh ok` | PASS 64 / FAIL 0 | 2.15–2.16 | 0.49–0.53 → 0.49–0.53 |

- 検証コマンド `lift_psola.sh all` (本 issue の検証方法) も 1 回実行: rc 0・`ALL OK` (ok 1.74 s・neg-cmp 1.77 s)。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash tools/shared/lift/ildsp/lift_psola.sh all`

## ネガティブコントロール
- `neg-cmp` は wasm 結果の arena 先頭 1 バイトを反転する (`WC_NEG=arena`)。`wc diff` は 64 case すべてで FAIL (`arena@+0x0`)。比較器が 1 バイトの差を検出することを確認した。

## 観測の範囲と限界
- 64 case は 1 経路の一致。`REPORT_APPENDIX_3401.md` §8-4 と同じ制限で、分岐の網羅ではない。.data は run で変化しない。
- 閉包は CreateInstance と slot 0・4・5 の 4 root。slot 1–3 (DSP 本体) を含む閉包の差分は未実施。
- ymm・VEX-128 の unsup は slot 1・3 から呼ばれる helper 側にあり、この 4 root には無い (unsup 0)。よって本付録の結果は PR #3471 (ymm lift) に依存しない。

## 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 1–3 (DSP 本体 0x17f700・0x180830 と、そこから呼ばれる helper) を含む閉包の native 差分 | 閉包全体の全バイト差分は未達 | 子 [T-SH-81] #3427 |
| slot 2 (0x1ab690 → 0x1804b0) の差分未実施 (閉包は unsup 0) | 閉包の差分の範囲 | 子 [T-SH-81] #3427 の受入に含める |
| 閉包全体の ymm 語・VEX-128 の unsup (7 root の数値は `REPORT_APPENDIX_3401.md` §8-3) | 閉包全体の lift の前提 | 親 [T-SH-82] #3428 (実装は PR #3471) |
| 64 case が 1 経路のみ (分岐網羅なし) | PASS の強さ | 子 [T-SH-81] #3427 の受入に含める |
