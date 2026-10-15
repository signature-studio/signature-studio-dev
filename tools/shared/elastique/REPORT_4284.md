# tools/shared/elastique REPORT — élastique `.text` pdata 関数の RetDec lift (T-SH-110 / #4284)

既知の類型との関係: 本件の lift 結果の欠陥類型の判定は未実施 (lift 出力の意味検証は子 issue に移す)。

## 0. 結論

| 項目 | 結論 (実測) |
|---|---|
| 対象件数の定義 | `.text` 内の pdata 関数 **4,556 件**。`.pdata` の生スロット 5,475 件 (`.text` 4,556 / IPPCODE 919) を RVA で直接読んだ値。REPORT_152 §1.1・REPORT_2614 §1 と一致 |
| `tools/shared/elastique/REPORT.md` の 1,956 | `ipp_entries.py` が pefile の `DIRECTORY_ENTRY_EXCEPTION` で数えた値 (1,956 件しか返らない)。生の `.pdata` (5,475 スロット) と食い違う。pefile が返す件数が少ない原因は未確定 (本 PR では未調査)。以後の lift は生 `.pdata` の 4,556 件を正とする |
| RetDec 一括 lift | **失敗**。4,556 件を 1 回で `--select-ranges` に渡すと `[capstone2llvmir]: Should not be possible.` で落ちる |
| 1 関数ずつの lift | **1,146 件 成功 / 18 件 失敗 / 3,392 件 未実施** (実測・§2) |
| 受入条件 (4,556 件全件) | **未達**。残りは子 issue に移す (§4) |

## 1. 対象・素材・測定 commit

- 素材: `fl-win64` の `extracted/block24357_PE.bin` (4,997,632 B) を `tools/shared/work/win/elastique_x64.dll` に複製 (gitignore)。RetDec: `toolchain-retdec` (RetDec v5.0・`retdec-decompiler --version` で確認)。
- 測定 commit: 本 PR の HEAD。コードを変えた最後の commit は本 PR の最初のコミット。差分は `git diff 7274516e3 HEAD -- tools/shared/elastique`。
- 件数の確認は `pdata_funcs` (`scripts/elastique_facts.py`) で行った: 生スロット 5,475・`.text` 内 4,556。

## 2. 再現と実測

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
mkdir -p tools/shared/work/win && cp "$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" tools/shared/work/win/elastique_x64.dll
# 範囲表 (begin end の 1 行 1 関数) は pdata_funcs から作る (4,556 行)
RETDEC=<retdec-decompiler> bash tools/shared/elastique/scripts/elastique_retdec_lift.sh tools/shared/work/win/elastique_x64.dll tools/shared/work/elastique/pdata_text_ranges.txt tools/shared/work/elastique/lift_fn 4
```

- 一括 (4,556 件を 1 回で `--select-ranges` に渡す・`--select-decode-only` あり): 1 秒で `Should not be possible.` で失敗 (rc=1)。
- 1 回目: 1 関数ずつ・並列 4・`timeout 60` で 540 秒 (`timeout` で打ち切り) 実行。結果行 651 件 (ok 647・fail 4)。
- 2 回目: 1 回目で未処理の 3,902 件を 420 秒 (`timeout` で打ち切り) 実行。結果行 514 件 (ok 499・fail 15)。
- 合計: 結果行 1,165 件 (`0x18002dac0` は両回で fail のため 1 件重複)。一意の 1,164 件のうち **成功 1,146・失敗 18** (`data/retdec_lift_4284.csv`)。
- 失敗の内訳 (fail 行 19 件・一意 18 件): rc=1 (`capstone2llvmir: Should not be possible.`) 14 件・rc=124 (60 秒 timeout) 2 件・rc=137 (kill) 3 件。
- 実測の load average は 4 並列で 3.9〜4.1 (4 コア・`uptime`)。1 関数あたりの時間は計測していない (合計の所要時間のみ)。

## 3. 成果物

- `scripts/elastique_retdec_lift.sh`: 1 関数 = 1 プロセスの lift 駆動 (一括が落ちるため)。
- `data/retdec_lift_4284.csv`: 1,164 件の `begin,status` (ok 1,146・fail 18)。
- lift 出力 (`.ll`) は `tools/shared/work/` (gitignore)。commit しない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未実施 3,392 件 (4,556 − 1,164) の lift | 受入条件 (4,556 件) 未達。RetDec の 1 プロセス 60 秒上限と 1 run の時間内では完了不可 | 子 issue (本 PR の issue 内に記載) |
| 失敗 18 件 (decoder の `Should not be possible.`・メモリ・timeout) | 完全な lift にならない | 子 issue |
| `ipp_entries.py` の 1,956 (pefile) と生 `.pdata` の 5,475 の差 | REPORT.md の件数が生 PE と合わない | 子 issue (件数の出典修正) |
| lift 出力の意味検証 (D15 `jmp [mem]`・D11・D14) | lift の正しさは未確認 | 子 issue |
