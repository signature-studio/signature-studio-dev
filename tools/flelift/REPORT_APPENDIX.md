

## 10. PERF-P9 (#168) ④: closure の最適化 variant 別 build (LTO 効果)

検証起点: `origin/main` 36edc993 + 本節。環境: Actions runner (4 vCPU, load 0.6〜1.3)、素材 `fl-win64` + `toolchain-emsdk`。
同一 lift 産物 (`fle_lift.sh`: 7,018 関数 / 340,761 命令 / unsup 0) を variant 別に emcc link (`fle_lto.sh`)。

| variant | wasm (B) | emcc 所要 (s) |
|---|--:|--:|
| -O0 (既定) | 27,639,303 | 19.1 |
| -O2 | 13,705,498 | 87.4 |
| -O2 -flto | 11,122,894 | 108.8 |

実行確認 (`fle_lto_bench.mjs`: _UStrAsg 0x4133f0 + Move 0x409c80 の 2 関数を 7 種の n で反復、出力メモリの SHA-256 を取る):
20,000 反復 × 3 回の p50 (µs)。署名は 3 variant・3 回すべて一致 (`533e70fd7efebaa0`)。

| variant | 1 回目 | 2 回目 | 3 回目 |
|---|--:|--:|--:|
| -O0 | 0.450 | 0.341 | 0.290 |
| -O2 | 0.091 | 0.131 | 0.141 |
| -O2 -flto | 0.140 | 0.121 | 0.100 |

判定: **サイズと build 時間は実測で確定、実行時間は 2 関数の微小測定のみ**。-O2 系は -O0 の約 1/3〜1/4 の時間を示すが、
-O2 と -O2 -flto の差は回ごとに入れ替わり、LTO の効果は本測定では判定できない。
M11 級 (boot 連鎖) の closure 全体での実行時間は未測: boot closure の lift は RAM 上限で完走しない (`boot/REPORT_APPENDIX.md`, #918 = FLE-7)。

## 11. 環境パス置換 (#294 / #3603) の実測詳細

REPORT §11 の付録。指定の見出しは `## 10.` だが、既存の PERF-P9 節と衝突するため §11 とした。

検証起点: `origin/main` 03df83be4。測定 commit (コード): C1 `b5c49356c`。本節は別 commit (REPORT)。
環境: Actions runner (4 vCPU)。素材 `fl-win64` は展開して `FL_WIN64_DIR` で指定。`toolchain-emsdk` は成果物を展開せず、`fle_e2e.sh`・`fle_lift.sh` が直接 source する runner 既設の emsdk を使用 (emscripten 6.0.12。成果物・`tools/m1/flags.sh` の pin と同版を確認)。

### 11.1 変更

| ファイル | 置換内容 |
|---|---|
| `fle_nat.py` | `DLL` の既定を `FL_WIN64_DIR` 経由に。`sys.path` 追加と import は HERE の直後 (冒頭の ASLR 用 `setarch` 再実行より後) |
| `fle_diff.py` | `PE` の既定を同上 (`sys` は import 済み) |
| `probe_d9_disp.py` | `PE` の既定を同上。`sys` を import に追加し `HERE` を定義 |

`FLE_PE` → `FL_WIN64_DIR` → 既定、の優先順は不変。`fle_e2e.sh` は変更なし (既に `tools/shared/env.sh` を source)。
`git diff C1 HEAD -- tools/flelift/fle_nat.py tools/flelift/fle_diff.py tools/flelift/probe_d9_disp.py` は空 (本 commit までに変更なし)。

### 11.2 静的検証

| 検査 | 結果 |
|---|---|
| `python3 -m py_compile` (3 本) | OK |
| 旧既定値の残存 (3 本) | 0 件 |
| `bash tools/shared/test_paths.sh` | PASS (default / analysis_dir_only / individual_override / negctl) |
| 全変数未設定時の `FL_WIN64_DIR` | 従来の `[WIN64]` 既定と一致 |
| ネガティブ制御: `FL_WIN64_DIR` に存在しないディレクトリを指定し `probe_d9_disp.py` を実行 | `FileNotFoundError` (`<指定dir>/extracted/block00031_PE.bin` を開けず rc=1)。環境変数が効くことを確認 |

### 11.2b フォールバックの実測 (e2e 外、本 fix で追加)

`fle_e2e.sh` は `FLE_PE` を export してから `fle_diff.py`・`probe_d9_disp.py` を呼ぶため、この 2 本の `FL_WIN64_DIR` 式は e2e で評価されない。両スクリプトの先頭から PE 代入行 (`IMG = 0x400000` の直前まで) を exec し、解決先を 4 ケースで確認した (コード HEAD `ec306ec74`、コード変更なし)。

| 設定した環境変数 | PE の解決先 (両スクリプトで同一) |
|---|---|
| なし (すべて未設定) | `ANALYSIS_DIR` 既定 (`tools/shared/env.sh` の値) 配下の `win64/extracted/block00031_PE.bin` |
| `FL_WIN64_DIR=<存在しない dir>` | `<dir>/extracted/block00031_PE.bin` |
| `ANALYSIS_DIR=<存在しない dir>` | `<dir>/win64/extracted/block00031_PE.bin` |
| `FLE_PE=<存在しない file>` + `FL_WIN64_DIR=<存在しない dir>` | `<FLE_PE の値>` (`FLE_PE` 優先) |

4 ケースとも仕様どおり。

### 11.3 e2e before / after (`bash tools/flelift/fle_e2e.sh`、素材 `fl-win64`。`toolchain-emsdk` は展開せず、スクリプトが直接 source する runner 既設の `[EMSDK]` (6.0.12) を使用、`FL_WIN64_DIR` = 同一の展開先)

| 項目 | before (03df83be4) | after (C1 `b5c49356c`) |
|---|--:|--:|
| 所要 (s) | 158 | 157 |
| load average (1 分) 開始 → 終了 | 0.80 → 0.99 | 0.16 → 0.94 |
| 終了コード / 結果行 | rc=0 / `[fle_e2e] PASS` | rc=0 / `[fle_e2e] PASS` |
| lift | 7,018 関数 / 340,761 命令 / unsup 0 / unlifted callee 0 | 同左 |
| lift 所要 (ログ) | lift 19 s、emcc 40 s、合計 59 s | 同左 |
| smoke | UStrAsg case1・case2 OK、Move n=392/64/36/24/3/1/0 すべて OK | 同左 |
| spot diff | 7 関数 / 16 case / equal 16 | 同左 |
| D9 | rip-rel 136,333 site / mismatch 0 | 同左 |

### 11.4 比較

- ログ: 31 行。作業パス (worktree) と所要秒を正規化後に diff して一致。生の diff はパス 4 行のみ。
- 出力物: `work/verdict.jsonl`・`work/verdict_summary.json`・`work/lift/lift_meta.json`・`work/nat_results.jsonl`・`work/wasm_results.json`・`work/nat_cases.txt` と追跡の `results/verdict_flelift.jsonl`・`results/verdict_summary.json` の sha256 が全件一致。`work/lift/` (`flel.cjs`・`flel.wasm`・`fle_lifted.c`・`fle_data.c`・`lift_meta.json`) は `diff -rq` で同一。
- 追跡の `results/` 2 件は e2e がコピーで上書きするが、内容は HEAD と同一 (`git status` は空)。
- 検算 (別アルゴリズム): Python で `verdict.jsonl` の行 (7 行) と各 case の outcome を数え直し、`verdict_summary.json` (cases 16 / equal 16) と一致。`grep -c` でも照合して一致。D9 の prefix 別内訳 (none 10,569 / rex 106,219 / f2 9,049 / 66 2,542 / f3 7,765 / manual-unparsed 189) の合計は 136,333 で総数と一致。`lift_meta.json` の関数数 (7,018) はログと一致。

### 11.5 範囲

- 範囲内: `tools/flelift` 直下の 3 本と `fle_e2e.sh` (素材 `fl-win64` + emsdk 6.0.12)。
- 範囲外 (親 #294 の残り): `tools/flelift/boot`・`tools/icall` (#3604)・`tools/ott`・m11。
- 仕様差: `ANALYSIS_DIR` を設定した場合のみ既定が `$ANALYSIS_DIR/win64` になる (旧 3 本は `ANALYSIS_DIR` を見ていなかった)。両方未設定の既定は従来と同一。
