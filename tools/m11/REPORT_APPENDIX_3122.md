## #3122: 基準 (7e149974 全再生成 IR) の unit 別 survey と本 A/B (main) の対応付け

測定 commit: 基準 `7e149974` (全再生成)・本 A/B `40d3a788d` (origin/main、本 branch の起点)。
前提 PR #3100 は 2026-10-14T22:38:40Z に merge 済み (前回の停止理由は解消)。

### 表記の約束

* unit 番号は 0 始まりの添字 (`m11_unit_map.py` が `range(942)` の添字をそのまま出力する)。添字の範囲は 0〜941。
* 所要時間は各 1 回 (n=1)。実行中の load は未採取で、終了後の `uptime` の 1 分平均 (0.41) だけがある。単発・load 未採取のため、WORKFLOW §5 の load average と n≥3 のレンジは満たさない。

### 実測 (単発・n=1・load 未採取)

| 項目 | 実測 |
|---|---|
| 基準の functions_dll.csv (7e149974 には `m11_ghidra_dll.sh` が無いため main の script を基準 worktree にコピーして実行。Ghidra 12.1.4 headless) | 10 分 36 秒, 59,010 行, rc 0 (完了時刻と sha256 は未記録。下の「基準 CSV の provenance」) |
| 基準 `m11_e2e.sh --full` (7e149974) | 10 分 26 秒, rc 0, 到達 stage 4/6, 期待値ゲート PASS (期待値は下の「期待値ゲートの基準」) |
| 基準 unit 別 survey (`M11_SURVEY_UNITS` 指定) | 16.2 秒, 942 本: ok 872 / trap 23 / miss 46 / noproc 1 |
| 本 A/B 用 IR: main の `m11_gen_ir2.sh` を基準の lift 成果物 (boot0〜5.lift.ll) に適用 | 50.99 秒, rc 0, ldfix・ld108・ld115・r8b applied (qstore は build 内で適用) |
| 本 A/B `m11_xmm_ab.sh` (main、既定 0 / opt-in 1) | 1 分 59 秒, rc 0, verdict OK (退行 0) |

IR の指紋 (記録値。本 run では再計算していない): 基準 `boot_final.ll` `7e66d79d…`、main の IR `64812d03…`。本 A/B の `boot_final3.ll` は arm 0 `deb39c96…`・arm 1 `47d795c6…` で不一致。opt-in で IR は変わる。

### 対応付け (unit 別, 942 本)

| 比較 | ok | trap | miss | noproc | unit 別の差 |
|---|---:|---:|---:|---:|---|
| 基準 (7e149974 全再生成) | 872 | 23 | 46 | 1 | — |
| 本 A/B 既定 (main, arm 0) | 873 | 22 | 46 | 1 | 基準と 1 件: unit 56 `trap→ok` |
| 本 A/B opt-in (main, arm 1) | 873 | 22 | 46 | 1 | arm 0 と 0 件 |

* unit 838 / 882 / 885 は全 arm で ok。ok 喪失 0 件。
* unit 別 JSON: `tools/m11/xmm_unit_3122/` (base_7e149974.json・main_arm0.json・main_arm1.json)。sha256 は base `22fed888…`、arm 0 と arm 1 は `aeb56cd9…` (同一)。
* 対応付けの再現 (3 引数が必要): `python3 tools/m11/m11_unit_map.py tools/m11/xmm_unit_3122/base_7e149974.json tools/m11/xmm_unit_3122/main_arm0.json tools/m11/xmm_unit_3122/main_arm1.json` → rc 0。引数なしは rc 1。

### 注意: 基準と本 A/B は同一 IR ではない

* 本 A/B は「同一 lift 入力・同一 pipeline の opt-in 0/1」の比較である (IR は別 sha)。既定 (0) と opt-in (1) の unit 別差は 0 件 (survey JSON の sha256 が一致)。
* main の生成パイプラインは、7e149974 に無い pass (ld108・ld115・r8b) を適用する。基準の `ir_conditions.json` にはこれらの記録が無い。
* 基準の IR を main の `m11_build.sh` にそのまま渡すと、`guard699` で止まった (末尾 terminator が想定形でない)。このため本 A/B の IR は、基準と同じ lift 成果物から main の `m11_gen_ir2.sh` で作り直した。
* 基準の functions_dll.csv は main の `m11_ghidra_dll.sh` (7e149974 には無い script) で作った。CSV を作った script が main 版である点も、unit 56 の差の候補に含める。
* 従って unit 56 の差は、IR の差 (ld108・ld115・r8b の影響)、build の差 (7e149974 以後の build 変更)、CSV 生成 script の差のいずれか、またはその組み合わせによる。切り分けは未実施。
* コード差分 (7e149974 から 40d3a788d まで): `git diff --stat 7e149974 40d3a788d -- 'tools/m11/*.sh' 'tools/m11/*.mjs'` は 104 files, 4985 insertions, 134 deletions。unit 56 の差の候補はここに含まれる。

### 基準 CSV の provenance (記録の範囲)

基準の survey JSON がどの functions_dll.csv から作られたかを示す。7e149974 の `m11_e2e.sh --full` は Ghidra を呼ばず、`m11_bounds.py`・`m11_tail.py` が `tools/m2/work/ghidra_dll/functions_dll.csv` を読むだけである。CSV が無いと `m11_bounds` は fail-closed で rc 1 になる (REPORT_N1165・REPORT_N1176 の実測)。

| 項目 | 記録 |
|---|---|
| (i) e2e と survey が読んだ CSV の sha256 | 未記録 (この run の CSV は保存していない) |
| (i) 再生成後の CSV の sha256 | 未記録。同じ行数 (59,010) の CSV の記録値が REPORT_N1042 にあるが、本 run の値ではない |
| (ii) 再生成の完了時刻と e2e 開始時刻の前後 | 未記録。記録に残るのは所要時間 (10 分 36 秒・10 分 26 秒) と、本表の記載順 (再生成 → e2e → survey → A/B) だけ |
| 前後関係の根拠 | e2e が rc 0 で stage 4/6 に到達した事実から、e2e の実行時点で `functions_dll.csv` は存在した。記録上、基準 worktree の CSV を作った手段は再生成だけである。ただし、再生成より前に別の CSV が存在した可能性は記録からは否定できない |
| (iii) 基準 JSON の生成コマンド | 下の「再現手順」。実行ログは保存していない |

### 再現手順 (WORKFLOW §5 の 1 コマンド形。この run では未再実行)

前提: [RETDEC] (`toolchain-retdec`)・[EMSDK] (`toolchain-emsdk`)・[GHIDRA] (docs/REFERENCES.md)・FL_WIN64_DIR (素材 `fl-win64`)。

基準側 (7e149974 の worktree):

1. `bash tools/m11/m11_ghidra_dll.sh` (main 版の script を基準 worktree にコピーして実行し、`tools/m2/work/ghidra_dll/functions_dll.csv` を作る)
2. `sha256sum tools/m2/work/ghidra_dll/functions_dll.csv` (CSV の sha256 を記録する)
3. `bash tools/m11/m11_e2e.sh --full`
4. `cd tools/m11 && M11_SURVEY_UNITS=<出力先>/base_7e149974.json node m11_survey.mjs` (出力を `xmm_unit_3122/base_7e149974.json` に複写)

本 A/B 側 (main):

5. `cd tools/m11 && bash m11_gen_ir2.sh` (基準の lift 成果物 boot0〜5.lift.ll を `tools/m11/work/` に置いてから実行)
6. `bash tools/m11/m11_xmm_ab.sh` (`work/xmm_ab/survey_0.json`・`survey_1.json` を、それぞれ `xmm_unit_3122/main_arm0.json`・`main_arm1.json` に複写)
7. `python3 tools/m11/m11_unit_map.py tools/m11/xmm_unit_3122/base_7e149974.json tools/m11/xmm_unit_3122/main_arm0.json tools/m11/xmm_unit_3122/main_arm1.json`

### 再測定 (指摘 3 の条件付き再測定): 未実施

前後関係を確定するには、基準の CSV 再生成 → e2e --full → 基準 survey を実行し直す必要がある。この run では実施できなかった。

* runner に [RETDEC] (`toolchain-retdec`) と [EMSDK] (`toolchain-emsdk`) が無い。`$ARTIFACTS_DIR` は `fl-win64` のみ。issue #3122 の oc_artifacts は `fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff` を要求している。
* [RETDEC] の取得元は docs/REFERENCES.md で `[未確認]`。
* 本 run の残り時間 (fix モード 40 分) では、基準の CSV 再生成 (10 分 36 秒) と e2e --full (10 分 26 秒) を、survey と A/B を含めて収められない。

### 判定器のネガティブコントロール

* 基準の unit 0 を trap に改変した写し (`$RUNNER_TEMP` 下、リポジトリ外): base は 871 / 24 / 46 / 1 になり、件数ゲートの判定は NG。基準と arm 0 の unit 別差は 2 件 (`0:trap->ok 56:trap->ok`)。`m11_unit_map.py` は rc 1 で終了した (期待どおり)。
* 改変しない基準の場合: rc 0 (件数 OK)。

### 期待値ゲートの基準

* 「期待値ゲート PASS」は、基準 7e149974 の `e2e_expect.env` での判定である (`M11_EXPECT_STAGE=4`・`M11_EXPECT_SURVEY_OK=800`・exact pin なし)。
* main の `e2e_expect.env` にある exact pin (`M11_EXPECT_SURVEY_OK_EXACT=873`・`M11_EXPECT_STRICT_DONE=101`) とは別物で、基準の判定には使っていない。

### コード差分 (測定 commit 40d3a788d から HEAD まで)

`git diff --stat 40d3a788d HEAD -- 'tools/m11/*.py' 'tools/m11/*.sh' 'tools/m11/*.mjs' 'tools/m11/*.c' 'tools/m11/*.h' 'tools/m11/*.env'` の出力:

```
 tools/m11/m11_unit_map.py | 29 +++++++++++++++++++++++++++++
 1 file changed, 29 insertions(+)
```

対応付けスクリプト (新規・測定経路の外) のみ。測定に使った build・survey・IR のコードは変更していない。HEAD は本 REPORT を含む fix commit で、その commit も測定コードを変えていない。このため測定値の再測定は要らない (WORKFLOW §6)。ただし、基準 CSV の前後関係の再測定 (上の「再測定」節) は、コード差分とは別の未解決事項である。

### 検証

| 検証 | 結果 |
|---|---|
| `m11_e2e.sh --full` (7e149974) の期待値ゲート | rc 0 (基準の `e2e_expect.env` による) |
| 基準 unit 別 survey の件数 | 872 / 23 / 46 / 1 (期待値と一致) |
| `m11_xmm_ab.sh` (main) | rc 0, 退行 0, 負の対照 (unit 838 を ok→trap に改変) で検出 |
| `m11_unit_map.py` 3 引数 (本 branch の HEAD で再実行) | rc 0 (基準の件数 OK・基準と arm 0 の差 1 件 (56)・arm 0 と arm 1 の差 0) |
| `m11_unit_map.py` 引数なし | rc 1 (ValueError・3 引数が必要) |
| `m11_unit_map.py` ネガティブコントロール (基準の unit 0 を trap に改変) | rc 1 (件数 NG) |
