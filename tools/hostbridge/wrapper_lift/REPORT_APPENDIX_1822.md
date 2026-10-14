# REPORT 付録 — #1822 (HB-H39): emcc exit 0 ファイルの wasm link と採用方式の比較

> **正本 (測定値)**: 本付録。`tools/hostbridge/wrapper_lift/REPORT.md` §13 は結論 1 行とリンクのみ。

測定 commit: `7d15ceab` (`origin/main` 取り込み時点の HEAD。作業 HEAD はこの commit に本付録と REPORT の文言のみを足す)。
`git diff 7d15ceab HEAD -- tools/hostbridge/wrapper_lift` の `.py` 差分は 0 件 (測定経路のコードは変えていない)。
環境: `[RETDEC]` v5.0 (`toolchain-retdec`)・`[EMSDK]` 6.0.12 (`toolchain-emsdk`)・`fl-win64` (`$RUNNER_TEMP/r1822/extracted`)。
load average (1 分値) は測定中 0.8–1.1。4 vCPU。

## 1. RetDec 経路 (受入条件 1)

手順 (REPORT §12 と同じ): `retdec_batch.py` → `retdec_repair.py --wide --int-ptr` → `retdec_gotofix.py` → `emcc_per_function.py`。

| 項目 | 実測 |
|---|---|
| RetDec batch (block19091, BATCH=500) | 19,816 / 19,816 ok・fail 0・呼び出し 41 回・所要 317.79 s (wall 318.07 s) |
| 同 block23676 | 19,826 / 19,826 ok・fail 0・呼び出し 41 回・所要 310.87 s。repair: `declared_helpers` 924・`int_ptr_wrapped` 1,986・`wide_widened` 1,251。gotofix: `notloop` 78・`goto_replaced` 51・`skip` 27・`label_inserted` 41。emcc: `emcc_exit` `{"0": 17, "1": 24}`・`functions_pass` 19,768 / 19,826・error 行 81・所要 9.5 s |
| repair (`--wide --int-ptr`) | `declared_helpers` 921・`int_ptr_wrapped` 1,993・`wide_widened` 1,245・`wide_skipped` 0・所要 13.5 s |
| gotofix | `notloop` 78・`goto_replaced` 51・`skip_no_addr_in_func` 27・`label_inserted` 41・所要 6.2 s |
| emcc (関数単位) | `emcc_exit` `{"0": 17, "1": 24}`・`functions_pass` 19,758 / 19,816・`functions_with_error` 55・error 行 81・`unattributed` 0・`failclosed` 0・所要 9.6 s |

**REPORT §12 との差**: §12 の表は「修復 + goto 化」の exit 0 を 3 / 41 とし、error 行 1,326 とする。本 run の実測は exit 0 が 17 / 41、error 行 81。
差の原因 (推定・未検証): §12 の error 行 1,326 は `incompatible pointer types passing` 1,245 件を含む。§12 の手順は `retdec_repair.py --int-ptr` のみで `--wide` を含まないため、この 1,245 件が残っていたと推定される。本 run は §11 の `--wide` を含む手順で再現した。同じ手順 (`--wide --int-ptr` → gotofix) を §12 の条件で再実行して差を確かめてはいない。本 run の値を「修復 + goto 化」の値として採る。

exit 0 の 17 ファイル (block19091): `10500, 12000, 12500, 14000, 15000, 15500, 16500, 17000, 17500, 18000, 2500, 3500, 4500, 5500, 6000, 6500m, 9000`。

残り error (block19091_0.c 単体): `'break' statement not in loop or switch statement` 6 件 (単体ファイル)・`assigning to 'struct struct1' from incompatible type 'int64_t'` 1 件。ファイル全体の error 81 行の内訳は未集計。

### 1.1 wasm link (RetDec 経路)

exit 0 の 17 `.o` を `emcc ... -Wl,--export-all -Wl,--allow-undefined` で link した。

- 結果: **rc 1 で失敗**。`wasm-ld: error: duplicate symbol: g*`。
- 重複数: block19091 1,546 件・block23676 1,545 件 (`--error-limit=0` の全件集計)。`undefined symbol` は 0 件 (両 block)。
- 原因: RetDec の各 batch 出力は、ファイルごとに同名のグローバル `g1`・`g2`… を**別の値で**定義する (例: `g1 = 0x646e756f42540b11` と `g9 = 0x8fe298` が別 batch に現れる)。ファイルを名前のまま結合すると衝突し、`--allow-multiple-definition` で潰せば別 batch の変数を取り違える。よって RetDec batch 出力を単純結合する経路は、link 段で止まる。
- 解消には、グローバル名を batch ごとに改名する (または同一 `g*` の定義元を一意化する) 修復が要る。これは未実施 (本 issue の範囲外、後述)。
- 所要・サイズ: 未取得 (link が成立しないため)。

## 2. x64c 経路 (受入条件 1・2)

手順: `x64c_wrapper.py block19091_PE.bin <out>` → `emcc -c -I tools/ott/rt` → `emcc -Wl,--export-all -Wl,--allow-undefined`。

| 項目 | 実測 |
|---|---|
| 生成 (`x64c_wrapper.py`) | `ott_lifted.c` 66,774,883 B・所要 69.1 s (unsup の内訳は `lift_meta.json`) |
| `ULLULL` 行数 | 0 (`x64c_wrapper.py` の後処理で吸収済み) |
| `emcc -c` | **exit 0**・error 0・所要 51.2 s・`ott.o` 57,837,396 B |
| wasm link (`--export-all --allow-undefined`) | **exit 0**・所要 1.678 s・`link/x64c19091.wasm` 43,828,879 B |

block23676 (同手順): 生成 exit 0・所要 68.5 s / `emcc -c` exit 0・所要 50.8 s / wasm link **exit 0**・所要 0.637 s・43,833,146 B。

wasm サイズは REPORT §7 の旧計測 (block19091 43,828,879 B・block23676 43,833,146 B) と一致した。link 所要は §7 の 0.66 s / 0.47 s と同程度 (0.64–1.68 s。load により変動)。

## 3. 比較 (受入条件 2)

| 項目 | RetDec 分割 lift → 修復 → goto 化 | x64c (`x64c_wrapper.py`) |
|---|---|---|
| block19091 lift | 19,816 / 19,816 ok (318 s) | 全 19,816 関数を生成 (69 s) |
| emcc `-c` 通過 | 関数単位 19,758 / 19,816。ファイル単位 exit 0 は 17 / 41 | ファイル単位 exit 0 (1 / 1) |
| wasm link | **失敗** (`duplicate symbol: g*` 1,546 件 / block23676 は 1,545 件) | **成功** (43,828,879 B / 43,833,146 B) |
| 未解決 | goto/break 残り・グローバル名の衝突・引数型 | `ULLULL` の吸収 (生成後の置換)・実行検証 |
| 実行検証 (bit 一致) | 未実施 | 未実施 |

**採用方式: x64c (Wrapper 経由)**。理由: 両 block とも x64c 経路だけが `emcc -c` と wasm link を通る。RetDec 経路は batch を結合すると、link 段でグローバル名 `g*` が衝突する (両 block で約 1,500 件)。RetDec 経路を通すには、batch ごとのグローバル改名と残り error の制御構造復元が要る。これは未実施で、工数は未見積もり。
本判定は**build 経路の判定**であり、wasm の実行結果 (bit 一致) と CreatePlugInstance 到達 (#829) は未検証。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec batch 出力のグローバル `g*` 衝突 (1,546 件) | RetDec 経路の wasm link が不能 | 本 PR では起票しない (採用方式に x64c を選んだため、RetDec 経路の修復は後続判断)。REPORT 付録に残す |
| wasm 実行 (bit 一致)・CreatePlugInstance 到達 | 採用方式の実行検証 | #829 |
| §12 の exit 0 値 (3 / 41) と本 run (17 / 41) の不一致 (§1 の差の原因は推定・未検証) | 手順の記述の差 | 本付録 §1 に明記 (再実行での確定は未実施) |

## 5. 再現手順

```sh
export RETDEC=$RUNNER_TEMP/r1822/retdec/bin/retdec-decompiler FL_WIN64_DIR=$RUNNER_TEMP/r1822/extracted
export EM_CONFIG=$RUNNER_TEMP/r1822/emsdk/.emscripten PATH=$RUNNER_TEMP/r1822/emsdk/upstream/emscripten:$PATH
KEEP_DIR=$RUNNER_TEMP/r1822/raw19091 python3 tools/hostbridge/wrapper_lift/retdec_batch.py block19091_PE.bin
python3 tools/hostbridge/wrapper_lift/retdec_repair.py --wide --int-ptr $RUNNER_TEMP/r1822/raw19091 $RUNNER_TEMP/r1822/rep19091
python3 tools/hostbridge/wrapper_lift/retdec_gotofix.py $RUNNER_TEMP/r1822/rep19091 $RUNNER_TEMP/r1822/fix19091
python3 tools/hostbridge/wrapper_lift/emcc_per_function.py $RUNNER_TEMP/r1822/fix19091 --targets $FL_WIN64_DIR/block19091_PE.bin --out $RUNNER_TEMP/r1822/fix19091.json
FL_WIN64_DIR=$FL_WIN64_DIR python3 tools/hostbridge/wrapper_lift/x64c_wrapper.py $FL_WIN64_DIR/block19091_PE.bin $RUNNER_TEMP/r1822/x64c19091.c
emcc -c -I tools/ott/rt $RUNNER_TEMP/r1822/x64c19091.c/ott_lifted.c -o $RUNNER_TEMP/r1822/x64c19091.c/ott.o
emcc $RUNNER_TEMP/r1822/x64c19091.c/ott.o -Wl,--export-all -Wl,--allow-undefined -o $RUNNER_TEMP/r1822/link/x64c19091.wasm
```

## 6. 未検証・注意

- wasm の実行 (bit 一致)・CreatePlugInstance 到達は未検証。`--allow-undefined` のため未解決シンボルの有無は未検証。
- 生成物 (raw C・修復後 C・`.o`・wasm) は `$RUNNER_TEMP` に置き、commit しない。
