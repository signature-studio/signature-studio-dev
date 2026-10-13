# tools/python REPORT 付録: PY-12 (#587) `_flhost` per-module state 化

`REPORT.md` の行数上限 (250 行) のため PY-12 節を分離 (内容は REPORT.md の PY-12 節として書いたもの)。

## PY-12 (#587): `_flhost` の per-module state 化

既知類型との関係: 該当なし (lift / 逆アセではない。`docs/DEFECTS.md` 対象外)。検証起点 commit `8f55002` (着手時の main)。

**結論**: 受入条件 3 件とも達成。`src/flpy.c` の `_flhost` を static 変数 (`json_loads`/`HostError`/`g_cbs`/`g_cb_counter`) から **module state 構造体** (`m_size` + traverse/clear/free) に変更し、`Py_mod_multiple_interpreters = Py_MOD_PER_INTERPRETER_GIL_SUPPORTED` を宣言。`g_last_error` はホスト向け診断バッファ (インタプリタ非依存) で static のまま。**採用判断: 現時点では採用しない** (device script は module namespace 分離のまま。下表)。

| 受入条件 | 結果 | 検証 (`tools/python/` から。`build_cpython_wasm.sh` → `FLPY_SKIP_TABLE=1 bash build_flpy.sh` 後 (表の再生成を省き追跡済み `flapi_table.json` を使う)) |
|---|---|---|
| per-module state + 宣言 | 達成 | isolated の拒否 builtin は 5/66 → 4/66 (`_flhost` が消え `_elementtree _lsprof faulthandler pyexpat` のみ) |
| isolated で import でき、破棄後も main が壊れない | 達成 | `node tests/subinterp_probe.mjs`: 19 check PASS (exit 0)。3 構成 (isolated+OWN_GIL / SHARED_GIL / legacy) 全てで、sub 内の `_flhost.call` (J 戻り値) / callable 登録 / `HostError(3,"boom")` が動き、sub の `_cbs` は `{1}` から採番 (main と独立)。破棄後の main の `call` / `HostError` / `_cbs` は無傷 (main 側 `{1}`→自身の登録で `{1,2}`)。legacy で sub が 5 個登録しても main の `_cbs` は 3 のまま |
| 採用判断の材料 | 下表 | 同 probe の `detail.create_run_destroy_ms_per_interp` / `module_namespace_exec_ms` |

**採用判断の材料** (n=50 個を 1 batch の平均 ms、3 batch の min–max。`import json, re` +`_flhost.call` 1 回 +破棄まで):

| 方式 | ms/個 |
|---|---|
| サブインタプリタ isolated (`json, re` のみ) | 33.71〜34.41 |
| サブインタプリタ isolated (+`_flhost`) | 34.80〜35.30 |
| サブインタプリタ legacy (+`_flhost`) | 32.30〜33.82 |
| main 内で module namespace を新規作成して exec (PY-6 の device script 方式) | 0.061〜0.091 |

PY-6 §11 の 26.74〜28.21 ms (別 run・同一コード系列) より本 run は 32.30〜35.30 ms と遅いが、同一 run 内の相対比は上表のとおり (run 間差の原因は未切り分け。load average 0.98〜1.04 の runner 差の可能性、推定)。**隔離の代償は 1 個あたり 370〜564 倍** (isolated `json, re` の min 33.71 ÷ module namespace の max 0.091 = 370、max 34.41 ÷ min 0.061 = 564)。isolated で `_flhost` を import して 1 回 call する分の増分は +0.89〜+1.09 ms (max 同士 / min 同士の差)。device script が `sys.modules` 共有 (script 間で `utils` を共有) で足りる限り、サブインタプリタを採る理由は無い。FL 側が script 単位で分けているかの証拠は無く未確認 (§11 と同じ)。

- **メモリ**: 各系列 150 個の間は線形メモリ 33,554,432B のまま増えない。ただし 201〜250 個目の間で増加 (isolated `json, re` のみ、50 個ごとの線形メモリ B: 33,554,432 ×5 → 40,304,640 → 48,365,568)。**`_flhost` を import しない系列・修正前 flpy.c の同系列でも同じ値列で再現** (`work/memprobe*.mjs` の一時計測。コミット対象外。1 run) = 本変更起因ではない既存挙動。修正前の isolated+`_flhost` は 151〜200 個目の間で増加 (修正後 201〜250 個目より早い。1 run のみで差の有意性は未確認)。PY-6 §11 の「150 回後も増加なし」は 150 回までの範囲でのみ正しい。修正前の legacy+`_flhost` は 51〜100 個目の間から増加し 300 個で 144,703,488B (static 状態の上書きと整合するが因果は未切り分け)。修正後の legacy+`_flhost` は上記 `json, re` のみと同じ値列。
- **PY-6 までの check の更新**: `subinterp_probe.mjs` の「`_flhost` は isolated で拒否」「legacy の既知の危険」の 2 check は、修正を固定する check に置換 (前者の期待が実装の変更で反転したため。通過条件を緩めたのではなく、反対側を厳格化)。

### 検証 (Actions runner 4 core, node 26, emsdk /opt/emsdk, CPython 3.12.1。load average 0.98〜1.04、直列 1 本)

実測: `subinterp_probe.mjs` wall 26.711 秒 (1 回目の誤 FAIL を直した後の 1 run)、`tests/subinterp_negcontrol_old.sh` wall 28.279 秒 (リンク 6 秒+probe)。CPython クリーンビルド (tgz 取得+native+wasm+記録) は `build_cpython_wasm.sh` が 06:29〜06:33 (uptime 時刻の区間。秒単位の計測はしていない)。`flpy.wasm` 5,924,633B (修正前 `8f55002` 5,923,834B、差 +799B)。

再検証 (main の #588 を merge した後・Actions runner 4 core): `build_cpython_wasm.sh` wall 3 分 33.8 秒 (load average 0.48 開始)、`FLPY_SKIP_TABLE=1 bash build_flpy.sh` 5.3 秒、`subinterp_probe.mjs` 19 check PASS・wall 23.02 / 22.93 秒 (n=2、exit 0)、`subinterp_negcontrol_old.sh` exit 0 (修正前 flpy.c で probe exit 2・FAIL 8 件、wall 23.61 秒)、`subinterp_probe.mjs --neg` exit 1、`smoke_direct.mjs` exit 0、`midi_script.mjs` 23 check PASS・`--neg` exit 1。`FLPY_SKIP_TABLE` 無しの `build_flpy.sh` は win PE 無しで exit 2 (#588 の仕様どおり)。

ネガティブコントロール (どちらも「検出できた」のとき緑):
- `node tests/subinterp_probe.mjs --neg` → exit 1 (拒否 builtin の期待に `pyexpat` を欠く → その 1 check だけが FAIL)。
- **`bash tests/subinterp_negcontrol_old.sh`** → exit 0: 修正前 `flpy.c` (`8f55002`) を `FLPY_C`/`FLPY_OUT` で別 dir にビルドし同じ probe を実行 → **exit 2・FAIL 8 件** (isolated は `_flhost` import 不可、SHARED_GIL/legacy は callback 表が main と共有 (`{1}` にならず)、破棄後の main が壊れる、メモリ check)。修正前でも probe が緑なら exit 1 で落ちる。
- 通常実行の FAIL は exit 2、`--neg` が検出できなければ exit 2 (緑にならない)。

回帰: `node tests/smoke_direct.mjs` exit 0 (0.30 秒)、`node tests/midi_script.mjs` 23 check PASS (0.66 秒)・`--neg` exit 1。`provider_check`/`all_tools`/`poc_mcp`/`browser_check`/`mcp_ui_check`/`midi_ui_check`/`midi_bundled_device` は本 run で**未実行** (MCPTools.pyc / fl-win64 / Chrome が無い。`_flhost` の ABI は変えていない)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 201〜250 個目付近からの線形メモリ増加の原因 (リーク / 断片化 / 成長のみ) が未切り分け | サブインタプリタを大量に作る運用では上限が要る (現行は不採用なので影響なし) | 採用検討時に新規 `[PY-n]` (PM 起票)。#587 にコメント |
| 実 FL がサブインタプリタを使うかは未確認 | 採用判断は性能のみに基づく | #76 (実機バイナリ解析の再実行時) |
| (解消) `build_flpy.sh` の `flapi_table.py` 再生成が win PE 無しで表を劣化させる | #588 (PY-13) で入力欠落は exit 2。`FLPY_SKIP_TABLE=1` は「再生成せず追跡済みの表をそのまま使う」明示オプションとして残した (negcontrol が win PE 無しの runner で link だけ行うため) | `REPORT_PY13.md` |
