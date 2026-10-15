# 付録: liftdiff LD-182 (#3881): batch の case 単位の揺れの測定と切り分けの結果

親: #3585 (LD-165)。前段: `REPORT_APPENDIX_LD154.md` (#3350)・`REPORT_APPENDIX_LD165.md` (#3585)。
本 PR の受入 (`Refs #3881`): units・hybrid の 2 回連続の件数・関数単位の判定は一致した。case 単位の揺れは残った (受入 3 は未達)。切り分け (A/B/C) は未完で、残りは子 #3935 [LD-183] へ移す (§6)。

## 結論

- **件数・関数単位の判定は 4 回とも一致した** (測定 commit `34f1bb26e`: units 360/230/210 ×2、hybrid 352/258/190 ×2)。関数単位の判定変化は 0 件 (`tests/ld154_repeat.py`)。
- **case 単位の揺れは units 6 case (5 関数)、hybrid 5 case (4 関数) 残った**。wasm の status の反転 (timeout ↔ trap、hang ↔ crash) が中心。原因は未切り分け。
- **前回測定 (`ac7ca0637`、§8) から件数が変わった**: units 360/234/206 → 360/230/210、hybrid 352/271/177 → 352/258/190。`ac7ca0637` 以降の変更は `ldlib/pe.py` (既定 off の引数) と main の `19a314897` (LD-161・`rt/ld_native.c`)。どちらが件数を変えたかは未切り分け。
- 候補の確からしさ (未検証を含む): (A) 1.0 s 境界 — 弱く支持 (§4)。(B) 履歴依存 — 前回の shards 4 の結果と整合するが未検証。(C) V8 階層化 — 未検証。(D) native ms の 50 ms 閾値 — 前回は hybrid の 3 case で確認したが、今回の組では該当 case に差が出なかった (§4)。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `34f1bb26e` (`origin/main` (`abf0981f7`) を merge した `570dc4273` の上に、ld182 の修正を積んだ commit)。build・bootstate・batch は全てこの commit のコードで行った |
| 測定後のコード差分 | `git diff 34f1bb26e HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/targets` = 出力なし (0 行)。確認時の HEAD は `34f1bb26e` (本 REPORT の更新 commit の直前) |
| 前回測定 (`ac7ca0637`) との差 | `git diff --stat ac7ca0637 34f1bb26e -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/targets` = `ldlib/pe.py` 10 行・`rt/ld_native.c` 8 行 |
| 入力 | `targets/m11.json`・`--set sample:800`・`--nobuild` (build は `liftdiff.py build targets/m11.json` を先に実行: `[build] OK`・`wasm_size` 4463122・10 s) |
| units state | `--state auto` (`bootstate targets/m11.json --nobuild`: `units_run=22/942`・precondition ok=False。LD-42 の既存状態) |
| hybrid state | `--state work/m11/boot_state_hybrid.json` (`bootstate --mode hybrid --nobuild`: `units_run=928/942`・`first_fail=830`・precondition ok=True) |
| 素材 | `fl-win64` を展開して `FL_WIN64_DIR` に指定 (`[WIN64]`・展開手順は `docs/WORKFLOW.md` §11)。`work-m11` は `tools/m11/work/`、`work-liftdiff` は `tools/liftdiff/work/` へ展開。`[EMSDK]` (`docs/REFERENCES.md` §4) |
| 機 | 4 vCPU・15 GiB。run は直列 |
| limits | native ITIMER 1.5 s (recv 10.0 s)・wasm vm 1.000 s (recv 10.0 s) (`[batch] limits` 行) |

## 2. 各 run の結果 (測定 commit `34f1bb26e`)

load は `/proc/loadavg` の 1 分値 (開始 → 終了)。所要は batch ログの `done`。n=2 (min–max は未取得のため参考値)。

| run | state | shards | 一致 / 不一致 / 実行不能 | batch 所要 | load |
|---|---|---|---|---|---|
| units r1 | units | 12 | 360 / 230 / 210 | 108 s | 0.33 → 6.44 |
| units r2 | units | 12 | 360 / 230 / 210 | 107 s | 5.45 → 6.59 |
| hybrid h1 | hybrid | 12 | 352 / 258 / 190 | 225 s | 6.06 → 8.47 |
| hybrid h2 | hybrid | 12 | 352 / 258 / 190 | 221 s | 7.79 → 8.18 |

- 再現コマンド: `python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state <state> --out work/m11/ld182_<run>.jsonl` (state は units が `auto`、hybrid が `work/m11/boot_state_hybrid.json`。ログは `work/m11/ld182_<run>.log`。JSONL は gitignore の `work/` にあり commit しない)。
- 前回の shards 4 の参考 run は今回の commit では測っていない (§8 に前回の値を残す)。

## 3. 突合 (case 単位・関数単位)

関数単位: `tests/ld154_repeat.py`。case 単位: `tests/ld182_casediff.py` (両 run の共通 case で `(outcome, native_status, wasm_status)` が異なるものを数える。値は batch JSONL の cases だけを読む)。

| 比較 | 共通 case | 関数の判定変化 | case の差 | 差の内訳 (wasm の status) |
|---|---|---|---|---|
| units r1 vs r2 | 9,226 | 0 | 6 (5 関数) | timeout → trap 5、hang → crash 1 |
| hybrid h1 vs h2 | 9,154 | 0 | 5 (4 関数) | trap → timeout 3、crash → hang 1、hang → crash 1 |

差の case (`wasm_s` = wasm 側の実測秒、`-` は timing 無し。§4 参照):

- units r1 vs r2:
  - `0x4630d0 z`: r1 `hang/segv/timeout` (1.031 s) → r2 `both_fault/segv/trap` (-)
  - `0x5c5500 pall`: r1 `hang/segv/timeout` (1.032 s) → r2 `both_fault/segv/trap` (-)
  - `0x5c5500 u16`: r1 `hang/segv/timeout` (1.026 s) → r2 `both_fault/segv/trap` (-)
  - `0x67e2b0 p1`: r1 `hang/segv/timeout` (1.018 s) → r2 `both_fault/segv/trap` (-)
  - `0xde10c0 z`: r1 `hang/segv/timeout` (1.033 s) → r2 `both_fault/segv/trap` (-)
  - `0xa9ece0 pall2`: r1 `hang/segv/hang` (1.205 s) → r2 `hang/segv/crash` (1.205 s)
- hybrid h1 vs h2:
  - `0x1060950 s`: h1 `both_fault/segv/trap` (-) → h2 `hang/segv/timeout` (1.365 s)
  - `0x4630d0 z`: h1 `both_fault/segv/trap` (-) → h2 `hang/segv/timeout` (1.070 s)
  - `0x67e2b0 p1`: h1 `both_fault/segv/trap` (-) → h2 `hang/segv/timeout` (1.098 s)
  - `0xa9ece0 pall`: h1 `hang/segv/crash` (1.140 s) → h2 `hang/segv/hang` (1.092 s)
  - `0xa9ece0 pall2`: h1 `hang/segv/hang` (3.764 s) → h2 `hang/segv/crash` (3.231 s)

## 4. 切り分けの状況

- **(A) 1.0 s 境界の内外 — 弱く支持**: units の差 6 case のうち 5 case は timeout 側が 1.018〜1.033 s (vm 上限 1.000 s の直後)。ただし wasm の timeout の実測秒 (`timing.wasm.elapsed_s`) の全体は units r1 で 1.002〜2.068 s (281 case)、hybrid h1 で 1.015〜3.421 s (275 case) と幅が広く、上限を大きく超える case の理由は未切り分け。
- **trap 側の実時刻は本測定の JSONL に無い**: `timing` は timeout/hang/crash を含む case にだけ付く。`refine_timing` (refine の再試行で timeout が出た case) は 2 組とも 0 件。従って差の trap 側 (`-`) の秒は測れていない。
- **(B) runner 履歴 — 未切り分け**: 前回 (§8) は shards 12 → 4 で 428 case が変わった。shards は負荷と runner の受け持ちを同時に変えるため A と B を分けられない。今回は shards 12 の 2 組だけ。
- **(C) V8 階層化 — 未検証**。
- **(D) native ms の 50 ms 閾値**: 前回 (§8) は hybrid `0x620cd0` の 3 case で確認した。今回の組では `0x620cd0` に差が出ず、(D) は確認も否定もできない。

## 5. 受入条件の判定

| # | 受入条件 (#3881) | 判定 | 根拠 |
|---|---|---|---|
| 1 | units を 2 回連続で実行し、遷移件数と関数単位の判定が一致する | **達成** (測定 commit `34f1bb26e`) | units r1/r2 の件数 360/230/210 ×2、判定変化 0 (§2・§3) |
| 2 | hybrid を 2 回連続で実行し、同じく一致する | **達成** (同上) | hybrid h1/h2 の件数 352/258/190 ×2、判定変化 0 |
| 3 | case 単位の揺れが 0 件、または残る揺れの起点と原因を説明する | **未達** | units 6 case・hybrid 5 case の揺れが残る。起点は timeout 側の 1.0 s 境界 (§4 A) の弱い支持のみ。原因は未切り分け |
| 4 | 判定ロジック・timeout 既定値を変えない | **達成** | 本 PR の差分は `tests/ld182_casediff.py`・本付録・DOC_MAP の行だけ。`ldlib`・`rt`・`targets` は変えていない (merge で取り込んだ main の `19a314897` は本 PR の差分ではない) |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| case 単位の揺れ (units 6 / hybrid 5 case) の原因 A/B/C/D の切り分け。負荷だけを変える実験と、runner 履歴だけを変える実験が必要 | 受入 3 未達。判定 (件数・関数単位) は今回の 2 組で揺れていない | #3935 [LD-183] (親 #3881) |
| shards 4 で関数の判定が変わる (前回 §8: 7 関数、負荷と履歴の交絡) | 既定の shards 12 の判定を、負荷の違う環境へ移すと変わり得る | #3935 [LD-183] |
| 前回 (`ac7ca0637`) → 今回の件数変化 (units 234→230・206→210、hybrid 271→258・177→190) の原因 (`ldlib/pe.py` と `19a314897` のどちらか) | 件数の前後比較は測定 commit を揃えてからでないと言えない | #3935 [LD-183] |
| 所要・load は n=2 (min–max 未取得) | 変動の幅は不明。上の表は参考値 | #3935 [LD-183] (次回測定を n=3 にする) |

## 7. 検証

- 関数単位: `python3 tests/ld154_repeat.py <A> <B>`。units r1/r2 = 0 件、hybrid h1/h2 = 0 件。
- case 単位: `python3 tests/ld182_casediff.py <A> <B> [--tsv out.tsv]`。units r1 vs r2 = 6 case (5 関数)、hybrid h1 vs h2 = 5 case (4 関数) (§3 の表)。
- 検算 (別アルゴリズム): 辞書の突合ではなく、`(関数 va, case 名, 判定)` の集合で比べた。units 6 case (5 関数)、hybrid 5 case (4 関数) で一致した。
- ネガティブコントロール (実 JSONL):
  - A=A (units r1 vs r1): 共通 9,226 case・差 0 case・差の関数 0。
  - 1 case だけ書き換えた B (units r1 の最初の wasm timeout を trap に変えた): 差 1 case・差の関数 1。ツールは書き換えを検出した。
- 修正の検証 (`wasm_elapsed()`): 合成 JSONL で refine_timing のみの case (元の status は trap、refine の再試行で timeout) を作ると、修正後は `1.200(再試行)` と出る。修正前は `-` (レビュー指摘どおり)。実測 JSONL では refine_timing が 0 件のため、本付録の秒は修正の影響を受けない。
- 範囲外: 主張は測定 commit `34f1bb26e` の 2 組ずつ (units・hybrid)。shards を変えた run は今回測っていない。

## 8. 前回測定 (`ac7ca0637`) の記録 (参考。今回の値の前身)

前回は測定 commit `ac7ca0637` (build・bootstate・batch)。units 2 組・hybrid 2 組・shards 4 の参考 1 回。今回の値と比べるときは §1 の差 (`ldlib/pe.py`・`rt/ld_native.c`) を考慮する。

| run | 一致 / 不一致 / 実行不能 | batch 所要 | load |
|---|---|---|---|
| units r1 / r2 (shards 12) | 360 / 234 / 206 ×2 | 107 s・109 s | 0.78 → 6.38、6.38 → 7.38 |
| units s4 (shards 4、参考) | 353 / 241 / 206 | 152 s | 1.45 → 2.77 |
| hybrid h1 / h2 (shards 12) | 352 / 271 / 177 ×2 | 289 s・290 s | 6.24 → 9.27、9.27 → 10.08 |

前回の突合: units r1/r2 = 9 case (6 関数)、hybrid h1/h2 = 9 case (6 関数)、units r1 vs s4 = 428 case (111 関数)・関数の判定変化 7。前回の hybrid `0x620cd0` の 3 case は、native ms が h1 で 40.5〜42.4 ms、h2 で 51.8〜58.3 ms で、閾値 50 ms (`ldlib/compare.py:197-199`) を跨いだ (D)。
