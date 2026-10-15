# 付録: liftdiff LD-243 (#4887): case 単位の揺れの V8 階層化 (C) の切り分け

親: #3935 (LD-183)。前段: `REPORT_APPENDIX_LD183.md`。本付録は `Refs #4887` (受入 3 の (C) を部分達成)。

## 結論

- **V8 の tier-up を止める (`--liftoff-only`) と、case 単位の揺れは default の 38〜43 case から出る** (同じ条件の反復は 2〜3 case)。関数判定の変化は 0。つまり V8 の階層化 (TurboFan への tier-up) は case 単位の揺れに寄与している。
- **ただし (C) は単独で確定していない**: `--liftoff-only` は TurboFan を外すだけで、並び・process の履歴は動かしていない。liftoff の揺れ (lo r1 vs r2 で 3 case) は default の反復 (2 case) と同程度で、liftoff 自体は安定している。
- **件数・関数判定は 4 本とも一致** (359/233/209)。LD-183 の sorted (360/234/206) とは 1 件ずつ違うが、測定 commit が違う (§1) ため、この差は今回の切り分けの対象外。
- 残りの切り分け (B: process 内の履歴 と C: JIT の温まり を分ける) は未解決 (§6)。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `16d1cc7ef` (`origin/main`)。harness `tests/ld183_order_load.py` に `--v8 liftoff` を足す変更 (17 行) を積んだ作業 commit で測定 |
| 測定後のコード差分 | `git diff 16d1cc7ef HEAD -- tools/liftdiff` は本 commit の harness 変更と REPORT のみ (§8) |
| 入力 | `targets/m11.json`・`--set sample:800`・`--shards 12`・`--state auto` (`work/m11/boot_state.json`)・`--order sorted` |
| build | `liftdiff.py build targets/m11.json` (`[build] OK`・`wasm_size` 4464620)。前の `ld_wasm.cjs` (10-12 生成) は `ld_w_snapshot` の引数が現在の runner と合わず、SNAPSHOT で落ちたため作り直した |
| 素材 | `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`・`extracted/block00031_PE.bin` 実在)。`work-m11` → `tools/m11/work/`・`work-liftdiff` → `tools/liftdiff/work/` (worktree は symlink)。`toolchain-emsdk` は `[EMSDK]` |
| 機 | 4 vCPU・15 GiB。run は直列 |
| V8 の条件 | `default` = 既定の V8 (Liftoff → TurboFan の tier-up)。`liftoff` = wasm 側 `node` に `--liftoff-only` を付ける (`harness` の `_patch_liftoff`・判定経路は変えない) |
| 負荷 | 0 (追加 busy なし) |

`--liftoff-only` は `NODE_OPTIONS` では受け付けられない (`not allowed in NODE_OPTIONS`) ため、harness で wasm 側の node コマンドに直接挿した。

## 2. 各 run の結果

| run | V8 | 並び | 一致 / 不一致 / 実行不能 | 所要 | load 開始 |
|---|---|---|---|---|---|
| def_r1 | default | sorted | 359 / 233 / 209 | 127 s | 6.24 |
| def_r2 | default | sorted | 359 / 233 / 209 | 125 s | 5.29 |
| lo_r1 | liftoff | sorted | 359 / 233 / 209 | 132 s | 5.72 |
| lo_r2 | liftoff | sorted | 359 / 233 / 209 | 132 s | 5.72 |

件数は 4 本とも一致。LD-183 の sorted (360/234/206) とは 1 件ずつずれる (測定 commit の違い。§6)。

## 3. case 単位の突合 (`tests/ld182_casediff.py`・共通 8,853〜8,854 case)

| 比較 | 変えた条件 | case 差 | 差のある関数 | 関数判定変化 |
|---|---|---|---|---|
| def_r1 vs def_r2 | 反復 (default) | 2 | 2 | 0 |
| lo_r1 vs lo_r2 | 反復 (liftoff) | 3 | 2 | 0 |
| def_r1 vs lo_r1 | V8: default → liftoff | 43 | 12 | 0 |
| def_r1 vs lo_r2 | V8: default → liftoff | 40 | 11 | 0 |
| def_r2 vs lo_r2 | V8: default → liftoff | 38 | 10 | 0 |

関数判定の変化は全比較で 0 (`tests/ld154_repeat.py` def_r1 vs lo_r1)。

## 4. 切り分けの判定

| 候補 | 判定 | 根拠 |
|---|---|---|
| (A) 追加の CPU 競合 | LD-183 で動かさなかった (`REPORT_APPENDIX_LD183.md` §4) | 本付録では負荷 0 のみ |
| (B) runner 履歴 (case の並び) | LD-183 で揺れを作ると判定。本付録では未分離 | (B) の並び変更は同時に C を動かす |
| (C) V8 階層化 | **揺れを作る方向** (case 差 38〜43 vs 反復 2〜3) | V8 を liftoff に固定すると揺れが大きく減る (反復並み) ではない。liftoff 側も反復で 3 case 揺れるため、残りは他の要因 |
| (D) native ms の 50 ms 閾値 | 未検証 | 本付録の対象外 |

受入 3 の (C) について: 「V8 の tier-up は揺れの一因」までが言える。「liftoff に固定すれば揺れが消える」とは言えない (liftoff 側も 3 case 揺れる)。

## 5. 受入条件の判定 (#4887)

| # | 受入条件 (#3935 の残り) | 判定 | 根拠 |
|---|---|---|---|
| 1 | 上の結果から (A)(B)(C) のどれが揺れを作るかを REPORT に書く | **部分達成** | (A) は LD-183 で外れ、(B) は LD-183 で揺れを作る。(C) は本付録で「揺れの一因」まで。(B) と (C) の分離は未達 (§6) |
| 2 | 判定ロジック (`ldlib/classify.py`・`ldlib/compare.py`) と timeout 既定値は変えない | **達成** | `ldlib`・`rt`・`liftdiff.py`・`targets` は無変更 (§8) |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (B) process 内の履歴と (C) JIT の温まりを分ける。例: shards 1 で並びだけ変える、または case ごとに process を作り直す | 受入 1 の残り。揺れの修復方針が決まらない | #4887 (部分達成で open のまま) |
| `--liftoff-only` 下でも 3 case 揺れる (反復)。この残りの要因は未特定 | 「V8 階層化だけが揺れの原因」とは言えない | #4887 |
| LD-183 sorted (360/234/206) と本付録の sorted (359/233/209) の 1 件差。測定 commit が違う (`2b2c59bea` vs `16d1cc7ef`)・build も作り直し | 件数の前後比較は同じ commit でないと言えない | #4887 |
| (D) native ms の 50 ms 閾値 | 揺れの候補として未検証 | #4887 |

## 7. 検証

- case 単位: `python3 tests/ld182_casediff.py work/m11/ld243_units_def_sorted_r1.jsonl work/m11/ld243_units_lo_sorted_r1.jsonl` (§3)。
- 関数単位: `python3 tests/ld154_repeat.py <def_r1> <lo_r1>` (verdict 変化 0 関数)。
- 再現: `FL_WIN64_DIR=<fl-win64> python3 tests/ld183_order_load.py targets/m11.json --state auto --order sorted --v8 liftoff --out work/m11/ld243_units_lo_sorted_r1.jsonl`。`--v8 default` で対照。

## 8. git diff (測定 commit → HEAD)

`git diff --stat 16d1cc7ef HEAD -- tools/liftdiff` (本 commit の harness 変更と REPORT のみ):

判定の経路 (`ldlib`・`rt`・`liftdiff.py`・`targets`) の差は 0 行。

## 9. 追記: (B) 並び・process 履歴と (C) V8 階層化の分離 (LD-243 2 段目)

- 測定 commit: `3da603ce6` (`origin/main`)。harness `tests/ld183_order_load.py` は本 HEAD に既に `--v8` を持つため変更なし。build `[build] OK`・`wasm_size` 4464620 (同一 HEAD で作り直し)。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-m11` / `work-liftdiff` → worktree の `tools/*/work/` (アーカイブ内のパスは repo 相対のため、展開先は repo ルート)、`toolchain-emsdk` → `$RUNNER_TEMP/emsdk-root/emsdk` (build は `/opt/emsdk` を参照し、runner に既存)。
- 機: 4 vCPU・15 GiB。run は直列。負荷 0。`--state auto --shards 12` (shards 1 のみ例外)。

### 9.1 各 run の件数 (一致 / 不一致 / 実行不能, 関数 801)

| 並び | shards | V8 | r1 | r2 |
|---|---|---|---|---|
| sorted | 12 | default | 359 / 233 / 209 | 359 / 233 / 209 |
| sorted | 12 | liftoff | 359 / 233 / 209 | 359 / 233 / 209 |
| shuffle:1 | 12 | default | 351 / 241 / 209 | 351 / 241 / 209 |
| shuffle:1 | 12 | liftoff | 351 / 241 / 209 | 351 / 241 / 209 |
| sorted | 1 | default | 343 / 249 / 209 | (未取得) |

### 9.2 case 単位・関数単位の突合 (`tests/ld182_casediff.py`・`tests/ld154_repeat.py`)

| 比較 | 変えた条件 | case 差 | 差のある関数 | 関数判定変化 |
|---|---|---|---|---|
| sorted default r1 vs r2 | 反復 | 7 | 3 | 0 |
| sorted liftoff r1 vs r2 | 反復 | 2 | 2 | 0 |
| sh1 default r1 vs r2 | 反復 | 2 | 2 | 0 |
| sh1 liftoff r1 vs r2 | 反復 | 4 | 3 | 0 |
| sorted default vs liftoff (r1 / r2 それぞれ) | (C) V8 | 54 (r1) / 55 (r2) | 14 | **0** |
| sh1 default r1 vs liftoff r1 | (C) V8 | 18 | 6 | 0 |
| sorted default r1 vs sh1 default r1 | (B) 並び | 515 | 119 | **16** (12: match→mismatch, 4: mismatch→match) |
| sorted liftoff r1 vs sh1 liftoff r1 | (B) 並び (V8 固定) | 514 | 117 | **16** |
| sorted default r1 vs shards 1 sorted | (B') process 履歴 (shards 12 → 1) | 701 | 150 | **16** |

### 9.3 判定

| 候補 | 判定 | 根拠 |
|---|---|---|
| (A) 追加の CPU 競合 | 本 2×2 では未測定 | LD-183 で件数・関数判定は動かなかった (§1 の注は LD-183 付録) |
| (B) 並び・process 履歴 | **揺れの主因** | 並びを変えると V8 を liftoff に固定しても 514 case・16 関数の判定が変わる。process を 12 → 1 に変えても 701 case・16 関数が変わる |
| (C) V8 階層化 | **揺れの小さい一因** | V8 の固定で 54〜55 case が動くが、関数判定は 0 件変化。反復の差 (2〜7 case) より大きいが、判定には効かない |

(B) と (C) は今回の 2×2 で分離できた。(B) は V8 の有無に依らず効く。(C) は効くが判定変化 0。

### 9.4 受入条件への対応 (#4887)

| # | 受入条件 | 判定 | 根拠 |
|---|---|---|---|
| 1 | (A)(B)(C) のどれが揺れを作るかを REPORT に書く | 達成 (A は未測定) | §9.3。(A) は LD-183 で判定に効かなかったことに依る |
| 2 | 判定ロジック・timeout 既定値は変えない | 達成 | 本 PR は REPORT のみ。`ldlib`・`rt`・`liftdiff.py`・`targets` は無変更 |

### 9.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (B) の機構: 並びや process 履歴で、どの case がどう変わるか (例: 先行 case が残す状態) | 揺れの修復方針が決まらない | #4887 (修復は別起票) |
| shards 1 の sorted の反復 (r2) が未取得 | (B') の反復の幅が未確定 | #4887 |
| (A) 追加 CPU 競合の 2×2 への組み込み | 揺れ要因 (A) の再確認 | #4887 |
