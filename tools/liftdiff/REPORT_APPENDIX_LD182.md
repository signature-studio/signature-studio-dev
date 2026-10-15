# 付録: liftdiff LD-182 (#3881): batch の case 単位の揺れの測定と切り分けの結果

親: #3585 (LD-165)。前段: `REPORT_APPENDIX_LD154.md` (#3350)・`REPORT_APPENDIX_LD165.md` (#3585)。
本 PR の受入 (`Refs #3881`): units・hybrid の 2 回連続の件数・関数単位の判定は一致した。case 単位の揺れは残った (受入 3 は未達)。切り分け (A/B/C) は未完で、残りは子 #LD-183 へ移す (§6)。

## 結論

- **件数・関数単位の判定は 4 回とも一致した** (units 360/234/206 ×2、hybrid 352/271/177 ×2)。関数単位の判定変化は 0 件 (`tests/ld154_repeat.py`)。
- **case 単位の揺れは両ペアとも 9 件あった** (units r1/r2: 9 case / 6 関数、hybrid h1/h2: 9 case / 6 関数)。wasm の status の反転 (timeout ↔ trap・ok、hang ↔ crash) が中心で、LD-165 の 16 件 (2 組) と同じ型。
- **負荷を下げる run (shards 4) で判定が変わった** (units: 件数 353/241/206、関数の判定変化 7・case の差 428)。shards は負荷だけでなく、runner ごとに受け持つ case の履歴も変えるため、A (負荷) と B (runner 履歴) は**切り分けられていない**。
- 候補の確からしさ (未検証を含む): (A) 1.0 s 境界の内外 — 支持 (同じ case の ok ↔ timeout 1.045 s、§3)。(B) 履歴依存 — shards 4 の結果と整合するが未検証。(C) V8 階層化 — 未検証。(D) native ms の 50 ms 閾値 — hybrid の 3 case で確認 (§3)。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `ac7ca0637` (測定開始時の main)。build・bootstate・batch は全てこの commit の作業ツリーで行った |
| 測定後のコード差分 | `git diff --stat ac7ca0637 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/targets` = `ldlib/pe.py` 10 行 (`#2850` の `analyze(va, zero_idiom=False)` の新引数。既定 False。`tools/liftdiff` の非テスト呼出元は 0 件)。batch の実行経路は既定で変わらない。**この差分の上の最新 main (`df2f768ea`) では再測定していない** |
| 入力 | `targets/m11.json`・`--set sample:800`・`--nobuild` |
| units state | `--state auto` (`bootstate targets/m11.json --nobuild`: `units_run=22/942`・precondition ok=False。LD-42 の既存状態) |
| hybrid state | `--state work/m11/boot_state_hybrid.json` (`bootstate --mode hybrid --nobuild`: `units_run=928/942`・`first_fail=830`・precondition ok=True) |
| 素材 | `fl-win64` を `$RUNNER_TEMP/fl-win64` へ展開 (`FL_WIN64_DIR`)。`work-m11`・`work-liftdiff` は既存の `work/` を使い、build で作り直した (`[build] OK`・`wasm_size` 4463122・10 s)。`[EMSDK]` (`docs/REFERENCES.md` §4) |
| 機 | 4 vCPU・15 GiB。run は直列 |
| limits | native ITIMER 1.5 s・wasm vm 1.000 s (`[batch] limits` 行) |

## 2. 各 run の結果

load は `/proc/loadavg` の 1 分値 (開始 → 終了)。所要は batch ログの `done`。

| run | state | shards | 一致 / 不一致 / 実行不能 | batch 所要 | load |
|---|---|---|---|---|---|
| units r1 | units | 12 | 360 / 234 / 206 | 107 s | 0.78 → 6.38 |
| units r2 | units | 12 | 360 / 234 / 206 | 109 s | 6.38 → 7.38 |
| units s4 (負荷を下げた参考) | units | 4 | 353 / 241 / 206 | 152 s | 1.45 → 2.77 |
| hybrid h1 | hybrid | 12 | 352 / 271 / 177 | 289 s | 6.24 → 9.27 |
| hybrid h2 | hybrid | 12 | 352 / 271 / 177 | 290 s | 9.27 → 10.08 |

- 再現コマンド: `python3 liftdiff.py batch targets/m11.json --set sample:800 --shards <N> --nobuild --state <state> --out work/m11/ld182_<run>.jsonl` (ログ `work/m11/ld182_<run>.log`。JSONL は gitignore の `work/` にあり commit しない)。
- LD-154 (`38e057dce`) の units 361/233/206・360/234/206 とは一致しない (同じ units でも 1 件の差)。差の原因は未切り分け。

## 3. 突合 (case 単位・関数単位)

関数単位: `tests/ld154_repeat.py`。case 単位: `tests/ld182_casediff.py` (新規。両 run の共通 case で `(outcome, native_status, wasm_status)` が異なるものを数え、TSV を出す)。

| 比較 | 共通 case | 関数の判定変化 | case の差 | 差の内訳 (wasm の status) |
|---|---|---|---|---|
| units r1 vs r2 | 9,226 | 0 | 9 (6 関数) | timeout → trap 6、trap → timeout 2、ok → timeout 1 |
| hybrid h1 vs h2 | 9,152 | 0 | 9 (6 関数) | timeout → timeout 3 (outcome のみ変化)、trap → timeout 2、timeout → trap 2、hang → crash 2 |
| units r1 vs s4 | 9,226 | 7 (match → mismatch) | 428 (111 関数) | trap → ok 149 ほか |

主な case (units r1 vs r2。`wasm_s` = 壁時計の秒、`-` は timing 無し):

- `0x1266e70 p0`: r1 `native_fault/segv/ok` → r2 `hang/segv/timeout` (wasm 1.045 s)。**同じ case が ok と timeout に分かれた**。
- `0x1060950 s`: r1 `both_fault/segv/trap` → r2 `hang/segv/timeout` (wasm 1.241 s)。LD-165 の同じ case と一致。
- `0x4630d0 z`: r1 `hang/segv/timeout` (1.012 s) → r2 `both_fault/segv/trap`。

hybrid の `0x620cd0` (`pall`・`s`・`z`): 3 case とも wasm は両 run `timeout` (1.268〜1.476 s)。outcome だけが `wasm_trap` ↔ `wasm_timeout_native_long` で変わる。native は両 run `ok`。判定は `ldlib/compare.py:197-199` の `native ms × wasm_slowdown_bound (20) ≥ wasm_timeout_ms (1000)` (= native ms ≥ 50 ms) で決まり、JSONL の `native_ms` で確認した: h1 は 40.5〜42.4 ms (`wasm_trap`)、h2 は 51.8〜58.3 ms (`wasm_timeout_native_long`)。native の ms が 50 ms の閾値を跨いだ (D)。

## 4. 切り分けの状況

- **(A) 1.0 s 境界の内外 — 支持 (弱い)**: units r1/r2 の差のある case の wasm の elapsed は 1.012〜1.241 s (timing のある側)。timeout 側は vm 上限 (1.0 s) の直後。ok ↔ timeout の反転 (`0x1266e70 p0`) が 1 件ある。ただし trap 側には timing が無く、trap の実時刻は測れていない。
- **(B) runner 履歴 — 未切り分け**: shards を 12 → 4 に変えると、同じ 800 関数で 428 case が変わった。shards は負荷 (load 6 → 2) と runner の受け持ち (1 runner あたりの case 数 3 倍) を同時に変えるため、A と B を分けられない。
- **(C) V8 階層化 — 未検証**。
- **(D) native ms の 50 ms 閾値 — 確認 (hybrid の 3 case)**: 判定の分岐は native の ms だけで決まり、wasm 側は両 run とも timeout。native の ms は 40〜58 ms で揺れた (§3)。units の 9 case の判定は (D) では説明できない (native は segv)。

## 5. 受入条件の判定

| # | 受入条件 (#3881) | 判定 | 根拠 |
|---|---|---|---|
| 1 | units を 2 回連続で実行し、遷移件数と関数単位の判定が一致する | **達成 (本 run)** | units r1/r2 の件数 360/234/206 ×2、判定変化 0 (§2・§3) |
| 2 | hybrid を 2 回連続で実行し、同じく一致する | **達成 (本 run)** | hybrid h1/h2 の件数 352/271/177 ×2、判定変化 0 |
| 3 | case 単位の揺れが 0 件、または残る揺れの起点と原因を説明する | **未達** | 9 case/組の揺れが残る。起点は wasm の 1.0 s 境界 (§4 A)。原因は未切り分け (A/B/C/D) |
| 4 | 判定ロジック・timeout 既定値を変えない | **達成** | 本 PR は `tests/ld182_casediff.py` と本付録だけ。`ldlib`・`rt`・`targets` は変えていない |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| case 単位の揺れ (units 9 / hybrid 9 case) の原因 A/B/C/D の切り分け。負荷だけを変える実験 (shards 固定・並列の別プロセスで CPU を占有) と、runner 履歴だけを変える実験 (同じ shards で case の並びを変える) が必要 | 受入 3 未達。判定 (件数・関数単位) は本 run で揺れていないが、再現性の根拠が弱い | [LD-183] (本 PR で起票。親 #3881) |
| shards 4 で関数の判定が 7 件変わる (負荷と履歴の交絡) | 既定の shards 12 の判定を、負荷の違う環境に移すと変わり得る | [LD-183] |
| 測定 commit `ac7ca0637` の後の差分 `ldlib/pe.py` (10 行・既定 off) の上での再測定 | 最新 main (`df2f768ea`) での数値は未確認 | 本 PR の範囲外。LD-183 の測定で同時に取る |

## 7. 検証

- 単体: `python3 tests/test_compare_ld11.py` (e2e [0/4] と同じ)。`python3 tests/ld182_casediff.py <A> <B>` は本付録の §3 の表を再現する。
- 関数単位: `python3 tests/ld154_repeat.py <A> <B>`。
- 検算 (別アルゴリズム): 未実施 (時間制限)。case 単位の数値は `ld182_casediff.py` の 1 本だけで出している。
