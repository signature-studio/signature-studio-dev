## #3122: 基準 (7e149974 全再生成 IR) の unit 別 survey と本 A/B (main) の対応付け

測定 commit: 基準 `7e149974` (全再生成)・本 A/B `40d3a788d` (origin/main、本 branch の起点)。
前提 PR #3100 は 2026-10-14T22:38:40Z に merge 済み (前回の停止理由は解消)。

### 実測

| 項目 | 実測 |
|---|---|
| 基準の functions_dll.csv (7e149974 には `m11_ghidra_dll.sh` が無いため main の script を基準 worktree にコピーして実行) | 10 分 36 秒, 59,010 行, rc 0 |
| 基準 `m11_e2e.sh --full` (7e149974) | 10 分 26 秒, rc 0, 到達 stage 4/6, 期待値ゲート PASS |
| 基準 unit 別 survey (`M11_SURVEY_UNITS` 指定) | 16.2 秒, 942 本: ok 872 / trap 23 / miss 46 / noproc 1 |
| 本 A/B 用 IR: main の `m11_gen_ir2.sh` を基準の lift 成果物 (boot0〜5.lift.ll) に適用 | 50.99 秒, rc 0, ldfix・ld108・ld115・r8b applied (qstore は build 内で適用) |
| 本 A/B `m11_xmm_ab.sh` (main、既定 0 / opt-in 1) | 1 分 59 秒, rc 0, verdict OK (退行 0) |
| load | 終了後の `uptime` の 1 分平均 0.41 (実行中の load は未採取) |

IR の指紋: 基準 `boot_final.ll` `7e66d79d…`、main の IR `64812d03…`。A/B の `boot_final3.ll` は arm 0 `deb39c96…`・arm 1 `47d795c6…` で不一致 (opt-in で IR は変わる)。

### 対応付け (unit 別, 942 本)

| 比較 | ok | trap | miss | noproc | unit 別の差 |
|---|---:|---:|---:|---:|---|
| 基準 (7e149974 全再生成) | 872 | 23 | 46 | 1 | — |
| 本 A/B 既定 (main, arm 0) | 873 | 22 | 46 | 1 | 基準と 1 件: unit 56 `trap→ok` |
| 本 A/B opt-in (main, arm 1) | 873 | 22 | 46 | 1 | arm 0 と 0 件 |

* unit 838 / 882 / 885 は全 arm で ok。ok 喪失 0 件。
* unit 別 JSON: `tools/m11/xmm_unit_3122/` (base_7e149974.json・main_arm0.json・main_arm1.json)。sha256 は base `22fed888…`・arm 0 と arm 1 `aeb56cd9…` (同一)。
* 対応付けの再現: `python3 tools/m11/m11_unit_map.py tools/m11/xmm_unit_3122/base_7e149974.json tools/m11/xmm_unit_3122/main_arm0.json tools/m11/xmm_unit_3122/main_arm1.json` (rc 0)。

### 注意: 基準と本 A/B は同一 IR ではない

* main の生成パイプラインは、7e149974 に無い pass (ld108・ld115・r8b) を適用する。基準の `ir_conditions.json` にはこれらの記録が無い。
* 基準の IR を main の `m11_build.sh` にそのまま渡すと、`guard699` で止まった (末尾 terminator が想定形でない)。このため本 A/B の IR は、基準と同じ lift 成果物から main の `m11_gen_ir2.sh` で作り直した。
* 従って unit 56 の差は、IR の差 (ld108・ld115・r8b の影響) と build の差 (7e149974 以後の build 変更) のどちらか、または両方による。切り分けは未実施。
* 同一 IR 内の既定 (0) と opt-in (1) の unit 別差は 0 件 (survey JSON が一致)。

### 検証

| 検証 | 結果 |
|---|---|
| `m11_e2e.sh --full` (7e149974) の期待値ゲート | rc 0 |
| 基準 unit 別 survey の件数 | 872 / 23 / 46 / 1 (期待値と一致) |
| `m11_xmm_ab.sh` (main) | rc 0, 退行 0, 負の対照 (unit 838 を ok→trap に改変) で検出 |
| `m11_unit_map.py` | rc 0 (基準の件数 OK・arm 0 と arm 1 の差 0) |
