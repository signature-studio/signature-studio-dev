# tools/shared/elastique REPORT — élastique `.text` pdata 関数の RetDec lift (T-SH-110 / #4284)

既知の類型との関係: 本件の lift 結果の欠陥類型の判定は未実施 (lift 出力の意味検証は子 issue に移す)。

## 0. 結論

| 項目 | 結論 (実測) |
|---|---|
| 対象件数の定義 | `.text` 内の pdata 関数 **4,556 件**。`.pdata` の生スロット 5,475 件 (`.text` 4,556 / IPPCODE 919) を RVA で直接読んだ値。REPORT_152 §1.1・REPORT_2614 §1 と一致 |
| `tools/shared/elastique/REPORT.md` の 1,956 | `ipp_entries.py` が pefile の `DIRECTORY_ENTRY_EXCEPTION` で数えた値 (1,956 件しか返らない)。生の `.pdata` (5,475 スロット) と食い違う。pefile は `Unknown UNWIND_CODE` で 1,956 件目で打ち切る (§5)。以後の lift は生 `.pdata` の 4,556 件を正とする |
| RetDec 一括 lift | **失敗**。4,556 件を 1 回で `--select-ranges` に渡すと `[capstone2llvmir]: Should not be possible.` で落ちる |
| 1 関数ずつの lift | **1,146 件 成功 / 18 件 失敗 / 3,392 件 未実施** (実測・§2) |
| 受入条件 (4,556 件全件) | **未達**。残りは子 issue に移す (§4) |

## 1. 対象・素材・測定 commit

- 素材: `fl-win64` の `extracted/block24357_PE.bin` (4,997,632 B) を `tools/shared/work/win/elastique_x64.dll` に複製 (gitignore)。RetDec: `toolchain-retdec` (RetDec v5.0・`retdec-decompiler --version` で確認)。
- 測定 commit (コードと CSV を変えた最後の commit): `e068b5dea`。差分は `git diff 7274516e3 e068b5dea -- tools/shared/elastique`。`e068b5dea` から HEAD までのコード差分: `git diff e068b5dea HEAD -- tools/shared/elastique/scripts tools/shared/elastique/data` (REPORT・DOC_MAP の文書修正のみ)。
- 件数の確認は `pdata_funcs` (`scripts/elastique_facts.py`) で行った: 生スロット 5,475・`.text` 内 4,556。

## 2. 再現と実測

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
mkdir -p tools/shared/work/win tools/shared/work/elastique && cp "$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" tools/shared/work/win/elastique_x64.dll
# 範囲表 (begin end の 1 行 1 関数・4,556 行)。生成は scripts/elastique_pdata_ranges.py (elastique_facts.py の pdata_funcs を使う)
python3 tools/shared/elastique/scripts/elastique_pdata_ranges.py tools/shared/work/win/elastique_x64.dll > tools/shared/work/elastique/pdata_text_ranges.txt
RETDEC=<retdec-decompiler> bash tools/shared/elastique/scripts/elastique_retdec_lift.sh tools/shared/work/win/elastique_x64.dll tools/shared/work/elastique/pdata_text_ranges.txt tools/shared/work/elastique/lift_fn 4
```

- 一括 (4,556 件を 1 回で `--select-ranges` に渡す・`--select-decode-only` あり): 1.1 秒で `[capstone2llvmir]: Should not be possible.` で失敗 (rc=1)。入力は範囲表から `SEL=$(awk '{printf "%s-%s,", $1, $2}' pdata_text_ranges.txt | sed 's/,$//')` で作った `--select-ranges "$SEL"`。
- 1 回目: 1 関数ずつ・並列 4・`timeout 60` で 540 秒 (`timeout` で打ち切り) 実行。結果行 651 件 (ok 647・fail 4)。
- 2 回目: 1 回目で結果行が無かった 3,905 件 (= 4,556 − 651 結果行) を入力とした。入力リストは保存していないため、件数は 1 回目の結果行数からの算出 (実測ではない)。420 秒 (`timeout` で打ち切り) で実行。結果行 514 件 (ok 499・fail 15)。
- 合計: 結果行 1,165 件 (`0x18002dac0` は両回で fail のため 1 件重複)。一意の 1,164 件のうち **成功 1,146・失敗 18** (`data/retdec_lift_4284.csv`)。
- 失敗 18 件の再実行 (並列 4・`RETDEC` を指定): 61 秒 (旧記載。本 run では未再現・再測定できず、時間は §5 で「未計測」)。内訳は rc=1 14 件・rc=124 (60 秒 timeout) 1 件・rc=137 (SIGKILL・原因未確認) 3 件。CSV の status には `fail rc=N` を記録した (旧記載の rc=124 2 件は、この再実行と一致しなかったため訂正)。
- 実測の load average は 4 並列で 3.9〜4.1 (4 コア・`uptime`)。1 関数あたりの時間は計測していない (合計の所要時間のみ)。

## 2.5 D5 (x64c 主役) との比較

`docs/DECISIONS.md` D5 は主力 lifter を x64c (`tools/flelift`・`tools/liftlib`) とし、RetDec は過去の試験的手段と位置づける。issue #4284 は本件を RetDec のまま進め、D5 との比較を本 REPORT に記録するよう指定している。

- RetDec を採る理由: 親 #3332 の受入 1 と本 issue の本文が RetDec lift を指定している (採用の根拠は issue 側の指定。x64c との比較は本件では測っていない)。
- RetDec の制約 (実測): 一括 lift は不可 (4,556 件を 1 回で渡すと 1.1 秒で `Should not be possible.`・§2)。1 関数 = 1 プロセスが必要で、1 関数あたり 60 秒の上限 (`timeout 60`)。失敗 18 件 (§2)。D5 が挙げる RetDec 路線の構造欠陥 (間接 call 脱落・小さすぎる global 宣言・stack 引数脱落・証明不能な lift) は本件では未確認 (lift 出力の意味検証は子 #4363 の受入)。
- x64c 側の本件の測定: 未実施。D5 の推奨との差は、本 PR では測らない。
- 扱い: D5 の例外承認は本 PR に無い。本件の RetDec 継続は issue 指定に基づく。x64c との比較 (同じ関数の lift) は子 #4363 で行う。

## 3. 成果物

- `scripts/elastique_retdec_lift.sh`: 1 関数 = 1 プロセスの lift 駆動 (一括が落ちるため)。
- `scripts/elastique_pdata_ranges.py`: .pdata の `.text` 内の関数範囲を 1 行 1 関数で出す (4,556 行・§2)。
- `data/retdec_lift_4284.csv`: 1,164 件の `begin,status` (ok 1,146・fail 18)。fail は `fail rc=N` (rc=1 14・rc=124 1・rc=137 3・§2 の再実行で取得)。
- lift 出力 (`.ll`) は `tools/shared/work/` (gitignore)。commit しない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未実施 3,392 件 (4,556 − 1,164) の lift | 受入条件 (4,556 件) 未達。RetDec の 1 プロセス 60 秒上限と 1 run の時間内では完了不可 | 親 #4363 (open・既存) |
| 失敗 18 件 (decoder の `Should not be possible.`・メモリ・timeout) | 完全な lift にならない | 親 #4363 (open・既存)。§5 の分類を参照 |
| `ipp_entries.py` の 1,956 (pefile) と生 `.pdata` の 5,475 の差 | REPORT.md の件数が生 PE と合わない | 出典は §5 で確定済み (`REPORT.md` の件数修正は本 PR の REPORT.md 1 行) |
| lift 出力の意味検証 (D15 `jmp [mem]`・D11・D14) | lift の正しさは未確認 | 親 #4363 (open・既存) |
| rc=1 の因果 (EVEX マスク付き `vpshufd`・`vshufi32x4` の切り分け) | 原因未確定 (相関のみ) | 親 #4363 へのコメント (追跡のみ・子は起票しない) |
| rc=124 / rc=137 の原因 (メモリ・時間) | 原因未確定 | 親 #4363 へのコメント (追跡のみ・子は起票しない) |
| pefile の `Unknown UNWIND_CODE` の原因 | pefile 側の原因は未調査 (件数の出典は確定) | 親 #4363 へのコメント (追跡のみ・子は起票しない) |

## 5. 失敗 18 件の分類・件数の出典 (T-SH-141 / #5179)

測定 commit: `cddf68a89` (`scripts/elastique_fail_classify.py` を追加した commit。計測のコードは同一で、後続の fix commit は docstring の ID 修正と REPORT の文言修正のみ)。
再現: `python3 tools/shared/elastique/scripts/elastique_fail_classify.py tools/shared/work/win/elastique_x64.dll tools/shared/elastique/data/retdec_lift_4284.csv`
(入力 DLL は `fl-win64` の `block24357_PE.bin` を `tools/shared/work/win/elastique_x64.dll` に複製。sha256 先頭 16 桁 `8551e92209cdd2ce`)。

| 項目 | 実測 |
|---|---|
| 件数 (本 run で `cddf68a89` のスクリプトを実行) | 生 `.pdata` 5,475・`.text` 内 4,556・pefile 1,956 |
| fail 行の内訳 (CSV の `status`) | 計 18 件・互いに素: rc=1 14 件・rc=124 1 件 (`0x18001fb40`)・rc=137 3 件 (`0x180018fe0`・`0x180026520`・`0x18002dac0`) |
| rc=1 14 件と EVEX マスク付き命令 | 14 件全件に `vpshufd` / `vshufi32x4` (`{k}`) がある。ok 1,146 件のうち同命令を含むものは 0 件。因果は未切り分け (capstone2llvmir の入力を絞る実験は未実施) |
| rc=124・137 の 4 件と EVEX マスク付き命令 | 4 件とも同命令は無い (スクリプトで確認)。原因は未確認 |
| 再実行の時間・load・RSS (並列 4・`timeout 60`、単独実行) | **未計測**。本 run の環境に RetDec 本体が無く、`toolchain-retdec` も素材 `fl-win64` の取得に含まれていないため再実行できなかった。§2 の旧記載の時間は本節では再現していない |
| rc=137 の原因 | 未確認 (OOM と断定しない。dmesg 不可) |
| 件数の出典 | 生 `.pdata` 5,475 スロット・`.text` 内 4,556・pefile 1,956。pefile の 1,956 は生スロットの先頭 1,956 件 (file 順) の接頭辞。pefile に無い 3,519 件 = `.text` 内 2,600 件 + IPPCODE 919 件 |
| pefile が 1,956 で止まる原因 | pefile の `parse_exceptions_directory` が `Unknown UNWIND_CODE at 0x4a6038` の警告で打ち切る。以後の RUNTIME_FUNCTION は読まれない。確認 (本 run で実行): `pe = pefile.PE(dll, fast_load=True)`・`pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])`・`pe._PE__warnings` → `['Unknown UNWIND_CODE at 0x4a6038']`、`len(pe.DIRECTORY_ENTRY_EXCEPTION)` → 1956 (pefile 2024.8.26) |

注: 本節の CSV は `main` の `data/retdec_lift_4284.csv` (1,164 件・fail 18)。`origin/4363-retdec-pdata-rest` は未 merge で 3,364 件・fail 89 (rc=1 85・124 1・137 3) まで進んでいる。その 89 件は本節の対象外 (未確認)。
