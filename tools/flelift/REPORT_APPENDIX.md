

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

## 11. #3603 (CI-169): 直下 3 本の VM 既定の絶対パス ([ANALYSIS-DIR]) を `tools/shared/paths.py` 経由へ置換

検証起点 (before): `origin/main` 4517825a2。測定 commit (コードを変えた最後): `fcc0ea6b5`。
既知類型との関係 (DEFECTS.md): 該当なし (パス解決のみの変更。lift 欠陥の類型に当たらない)。
環境: Actions runner (4 vCPU)、素材 `fl-win64` + `toolchain-emsdk`。`fl-win64` は `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (5.4 秒) し `FL_WIN64_DIR` で指定。`toolchain-emsdk` は agent-setup が [EMSDK] に展開済み。

変更: `fle_nat.py`・`fle_diff.py`・`probe_d9_disp.py` の PE 既定を `tools/shared/paths.py` の `FL_WIN64_DIR` 経由にした (`tools/shared/scripts/*.py` と同じ `sys.path.insert` の形)。`FLE_PE` → `FL_WIN64_DIR` の優先順は変えない。VM 既定の絶対パス (`[ANALYSIS-DIR]` の既定値) は 3 本で 1 → 0 件 (`grep -c`)。その既定値は `paths.py` の `ANALYSIS_DIR` 既定に 1 箇所だけ残る。

e2e 実測 (`bash tools/flelift/fle_e2e.sh`、各版 n=1):

| 版 | commit | 総所要 (real) | lift | spot diff | D9 | 判定 |
|---|---|--:|---|---|---|---|
| before | 4517825a2 (origin/main) | 2 分 32.7 秒 | 7,018 関数 / 340,761 命令 / unsup 0 | 16/16 equal | 不一致 0 / 136,333 site | PASS |
| after (作業ツリー) | 未 commit | 2 分 32.6 秒 | 同左 | 16/16 equal | 不一致 0 / 136,333 site | PASS |
| after (コミット済み HEAD) | fcc0ea6b5 | 2 分 32.0 秒 | 同左 | 16/16 equal | 不一致 0 / 136,333 site | PASS |

load average: after 完了時 0.97、HEAD 完了時 1.00 (before は未採取)。

同一性: `results/verdict_flelift.jsonl` (7 行) は before・after・HEAD の 3 版で `cmp` 一致。`lift_meta.json` は before と after で `cmp` 一致。e2e ログは時間の行 (`done in`・`emcc`・`real/user/sys`) を除いて一致。

既定解決 (`import fle_diff` で `PE` を出力して確認。旧列はコードの直読):

| 環境変数の設定 | 変更後の解決先 | 旧 |
|---|---|---|
| `FLE_PE=X` | `X` | `X` |
| `FL_WIN64_DIR=Y` のみ | `Y/extracted/block00031_PE.bin` | 同左 |
| `ANALYSIS_DIR=A` のみ | `A/win64/extracted/block00031_PE.bin` | `[ANALYSIS-DIR]/win64/...` (VM 既定に固定) |
| 何も無し | `[ANALYSIS-DIR]/win64/...` | 同左 |

差は `ANALYSIS_DIR` だけを設定した行のみ (旧は `FL_WIN64_DIR` の既定を固定していた)。Actions で `analysis-*` を展開した run は、今後 `ANALYSIS_DIR` 配下の `win64` を見る。

ネガティブコントロール: `FL_WIN64_DIR` に存在しない dir を指定して `probe_d9_disp.py` を実行 → rc=1 (指定 dir の PE を開けず `FileNotFoundError`)。変数が経路に効いていることの確認。

差分 0 の証跡: `git diff fcc0ea6b5 HEAD -- tools/flelift/fle_nat.py tools/flelift/fle_diff.py tools/flelift/probe_d9_disp.py tools/flelift/fle_e2e.sh tools/flelift/fle_lift.sh` の出力は 0 行 (測定 commit = HEAD 時点)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `tools/flelift/boot/` の VM 既定の絶対パス ([ANALYSIS-DIR]) | boot 系の CI 再現性 (3 本の外) | #348 (既存) |
