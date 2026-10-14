# 付録: icall #2310 (ICALL-72) — BLK+0 (0x36319008) 書込み store の wasm オフセット対応

> 親: #1998 (ICALL-54) の付録 `REPORT_APPENDIX_1998.md` §1 の未達 (IR 行 19132 → wasm オフセット)。本付録は子 issue #2310 の測定結果を記録する。

## 1. 結論

- **受入条件 1 (wasm オフセットまで特定): 達成**。`0x36319008` に "emsc" (`0x63736d65`) を書く store (IR 行 19132) は、wasm の関数 `function_181057d20` 内の **`i64.store offset=909217800` (wasm ファイル内オフセット `0x427be`)** に対応する。
- **受入条件 2 (route 側 / lift 側の分類): 未完 (暫定のまま)**。store 命令自体は lift が生成した関数本体 (`function_181057d20`) の中にある。route 側 (data 敷設) は 1998 付録 §3 で否定済み。ただし値 `%1` の出所 (null ページを指すポインタ `0x400000004` の生成元) が未特定のため、最終分類は #2311 (ICALL-73) の結果を待つ。
- **受入条件 3 (`fa_sweep.sh 8 60` の wasm のみ err 件数): 達成**。wasm のみ err は 9 件で、現状の件数と一致 (実測は §3)。

## 2. 対応の詳細 (実測)

測定: `fa_wc_build.sh` で監視付き wasm (`work/fa_wc/fa_wc.cjs`) を作り、`fa_wc_drv.cjs` で `181057b38` を 8 入力で実行。

| 段階 | 観測 |
|---|---|
| 監視付き IR の挿入 | `fa_wc.py instr`: `store total=5526 instrumented=5526 unhandled=0` |
| 実行 (8 入力) | 全入力で `memory access out of bounds`。`WC line=` 168 行 (1998 §2 と一致)。`WC line=19132 addr=36319008 sz=8 val=63736d65` が 8 件 |
| `__wchk` の第 4 引数 | IN 側 (`work/fa_route/oi.flat.ll`) の行番号。OUT 側 (`oi.wc.ll`) の行番号ではない。`oi.flat.ll` 19132 行 = `store i64 %1, ptr %ce31n11_function_181057d20` |
| wasm 側の位置 | `wasm-dis` で `$function_181057d20` (wat 140562 行〜)。wat 141476 行の `i64.const 19132` → `i64.store offset=909217800` (wat 141490 行) |
| バイナリオフセット | `llvm-objdump -d fa_wc.wasm`: `i64.const 19132` が `0x4279a`、直後の `i64.store offset=909217800` が **`0x427be`** |

対応の読み方: wasm 内の `i64.const 19132` は `__wchk` に渡す IR 行番号 (計装用の定数)。その直後に、同じ IR 行の本体 store (`909217800` = `0x36319008`) が続く。

DWARF の行表 (`llvm-dwarfdump --debug-line`) には `.ll` の行情報が無い (`-g` を付けても lift IR は `!dbg` を持たない)。そのため、対応は `__wchk` の定数を介して取った。

## 3. 測定 (`tools/icall/diff/fa_sweep.sh 8 60`)

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `586c8b0c` (origin/main 取り込み時点の HEAD。本 PR はコード変更なし) |
| 素材 | `fl-win64`・`plugins-freshair` (`fetch.sh`: win 17 files, factory .epf 8)・`toolchain-emsdk` (`/opt/emsdk`)・`toolchain-retdec` (`/opt/retdec`)・`work-icall`・`work-liftlib` |
| `tools/ott/native/build.sh` | OK |
| `tools/icall/fa_route_build.sh` | OK、11.5 s |
| `tools/icall/diff/fa_wc_build.sh` | OK、3.2 s (`store total=5526 instrumented=5526 unhandled=0`) |
| `tools/icall/diff/fa_sweep.sh 8 60` | 131 関数、73.1 s (real 1m13.145s)、開始 load 0.58・終了 0.95 (4 vCPU) |
| 区分 | **bit 一致 46 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 10** (合計 131) |

- wasm のみ err は 9 件で、1998 §4 と一致。
- bit 一致 / 値の不一致 は 1998 §4 (47 / 9) と 1 件ずれた。`fa_sweep` の bit 一致が ±1 揺れる件は #2302 (ICALL-71) で追跡中。本付録では再現判定を行わず、この実測値をそのまま記録する。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| route 側 / lift 側の最終分類 (値 `0x400000004` を作る store の特定に依存) | 受入条件 2 | #2311 (ICALL-73) |
| `fa_sweep` の bit 一致の ±1 揺れ (本 run 46、1998 は 47) | sweep 件数の判定精度 | #2302 (ICALL-71) |

## 5. 再現

```
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FA_DL=$RUNNER_TEMP/plugins-freshair RETDEC_ROOT=$HOME/retdec TMPDIR=$RUNNER_TEMP
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .
mkdir -p "$FL_WIN64_DIR" "$FA_DL" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$FL_WIN64_DIR"
tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$FA_DL"
bash tools/targets/freshair/fetch.sh
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_wc_build.sh
node tools/icall/diff/fa_wc_drv.cjs $PWD/tools/icall/work/fa_wc/fa_wc.cjs 181057b38 2>err.txt
grep -c '^WC line=' err.txt                       # 168
grep '^WC line=19132' err.txt | head -1           # addr=36319008 val=63736d65
/opt/emsdk/upstream/bin/llvm-objdump -d tools/icall/work/fa_wc/fa_wc.wasm | grep -A1 'i64.const.*19132' # 直後の store (0x427be)
bash tools/icall/diff/fa_sweep.sh 8 60
```
