# reverb_delay REPORT 付録 (#523 PLG-F4-2 追補)

本体 `REPORT.md` の §12 に続く節。 250 行上限のため分割して置く。

## 13. #523 追補 (2026-10-13 · 測定起点 HEAD 986e7415 · 再測定)

- **測定起点**: main **986e7415** (§13 の測定はこの HEAD で行った。 本 PR は docs のみで engine コードは変更していない)。 `REPORT.md` §12 の起点 97f28539 は E6 修正 (b5372ec3) の親で、作業ブランチ `523-plg-f4-2-engine-lift` の起点。 両者は祖先関係 (97f28539 → 986e7415) にある。
- **素材の確認 (本 PR の fix run、2026-10-13 17:54 UTC)**: `$HOME/artifacts` には `fl-win64.tar.zst` (2.3 GB) のみ実在。 `toolchain-retdec` / `toolchain-emsdk` / `work-*` / `plugins-ott` は確認時点で不在。 したがって本 run では e2e・engine lift を再実行できず、 下表の数値は再現していない。 §13 の測定時に上記素材が揃っていたかは、 PR 本文の記録以外に確認できない。
- **run の別**: 19165 の測定は §12 (15:37:59–15:48:22 UTC、wall 10 分 23 秒、summary.csv 行あり) と §13 (wall 6 分 42 秒) の 2 回として記録されている。 条件 (IPPCODE 除外 + AVX 系 78 除外) は同じで、 wall が一致しないため同一 run の再掲ではないと判断した。 §13 の run の開始時刻は記録していない。 各 run は 1 回のみ。
- engine の正しさは示さない (到達性のみ)。 負荷 (load) は測定していない。

| engine | 条件 | lift rc | define | f80 関数 | `emcc -c` rc | lift 秒 (PR 本文) | wall (PR 本文) |
|---|---|--:|--:|--:|--:|--:|--:|
| 19165 Multiband Delay | IPPCODE 除外 + AVX 系 78 除外 (`avx_bad_ranges.py`) | 0 | 2,608 | 6 | **139 (segfault)** | 391 | 6 分 42 秒 |
| 19165 同上 | 同 + `PLUG_F80_LOWER=1` | 0 | 2,608 | 0 | **1** | 416 | 6 分 57 秒 |
| 19000 Delay 3 | `PLUG_F80_LOWER=1` (全 3,632 関数) | 0 | 4,107 | 0 | **0** | 未記録 | 2 分 7 秒 |

- 秒の列は PR 本文の値のみ。 旧版の付録は表見出しを「秒 (lift+emcc)」としていたが、本文の lift 時間 (391 s) と wall の内訳は記録になく、wall を正とする。

- **19165 segfault の位置**: `emcc` は `function_1800ceec0` の WebAssembly 命令選択 (DAG combine の `visitSTORE`) で落ちる。 同関数は x86_fp80 を含む (`final.ll` の f80 関数 6 本のうち 1 本)。 `PLUG_F80_LOWER=1` で f80 を外すと segfault は消える。
- **19165 の次の類型 (f80 lowering 後)**: `e.final.ll:273362: invalid cast opcode for cast from 'double' to 'i80'`。 `p0c/f80_lower.py` は `bitcast x86_fp80 to i80` (f80 のビット列を読む命令) を double に置換するが、`bitcast double to i80` を残す。 f80 のビット操作を扱えないことが原因と推定。 この類型は共有鎖 (`p0c/f80_lower.py`) の修正が必要で、T0/T1 の退行確認 (#523 受入条件 2) を伴うため、本 run では未修正。 **新類型 E7 (f80 ビット操作の lowering 漏れ)** として記録。
- **19000 の f80 lowering**: `PLUG_F80_LOWER=1` は f64 化で精度を落とす (53 bit 仮数)。 19000 の f80 関数 (`function_1800bcb00` ほか) の精度影響は未検証。 既定 (`PLUG_F80_LOWER=0`) では `emcc -c` が rc 1 のまま (REPORT §12 の既存結果)。
- 19165 の segfault の起点 (`function_1800ceec0`) と f80 6 本の内訳は測定時の `work/reverb_delay/engine19165_noipp_nobad/` (gitignore) に残したが、 本 runner の `work/` には存在しない。 再現手順は下記。

### 再現手順

```
source tools/plugins/reverb_delay/env.sh
python3 tools/plugins/reverb_delay/avx_bad_ranges.py 19165 > work/reverb_delay/bad19165.out
ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges $PWD/work/reverb_delay/bad19165.out" \
  ENGINE_TAG=_noipp_nobad bash tools/plugins/reverb_delay/engine_lift.sh 19165 1200
PLUG_F80_LOWER=1 bash tools/plugins/reverb_delay/engine_lift.sh 19000 800
```

注: `--exclude-ranges` には絶対パスを渡す (`engine_lift.sh` が `tools/plugins` へ cd するため相対パスは解決されない)。 再現には `fl-win64` に加えて `toolchain-retdec` / `toolchain-emsdk` が要る。

### 受入条件への対応 (#523)

1. 19000 は `PLUG_F80_LOWER=1` で `emcc -c` rc 0 (到達性のみ・精度未検証)。 19165 は未達 (E7)。 既定 (f80 lowering 無し) では両方未達。
2. 共有鎖 (`p0c/f80_lower.py`) は未変更のため退行確認は不要だが、E7 の修正時に必要。 未実施。
3. IPPCODE の扱い: 未決 (#38 [IPP-10] と PM 判断)。
4. LoadLibrary 結合解析: 未実施。

## 14. #523 E7 の切り分け (2026-10-13 · 測定起点 main dc7c11df · コード変更なし)

- **再測定** (engine 19165, IPPCODE 除外 + AVX 系 78 除外, 同一条件): lift rc 0 / define 2,608 / f80 6 / unimpl 241 / `emcc -c` rc 139 (segfault) / `emcc -c` (fixcmp) rc 139。 lift 時間 615 秒 (`summary.csv` の `lift_s`。 wall は未計測)。 §13 と同値。
- **E7 の IR 上の位置**: `e.final.ll` の `function_1800ceec0` (行 273038〜) で `bitcast x86_fp80 %12 to i80` → `trunc i80 to i64` → `inttoptr` の列が 2 箇所 (行 273381・273392 付近、 ブロック `dec_label_pc_1800ceffe` 内)、 `sext i32 to i80` → `bitcast i80 to x86_fp80` が 2 箇所 (行 273480・273633 付近)。 (f80 lowering 前の `e.final.ll` の行番号。 別経路の同型 4 箇所は行 348058 以降)。 `%12` は `load x86_fp80, x86_fp80* %11` で、 `%11 = bitcast ptr %rcx to x86_fp80*`。 つまり **整数のポインタ値を格納したメモリを x87 (f80) として読んでいる**。
- **推定原因**: RetDec のメモリ型推定が、 整数スロットを f80 として扱ったことによる lift 側の型誤り。 `p0c/f80_lower.py` は型名を `double` に置換するだけなので、 この bit 列の意味 (80 bit の下位 64 bit をアドレスとして使う) は保存されず、 `bitcast double to i80` が残る。 「`bitcast` の lowering 漏れ」より上流の型誤りが本体と見てよい。
- **対処方針 (未実施)**: (a) lift 側 (RetDec 出力後の型修復 pass) で `%11` の load を `i64` に差し替える engine-local 修復を入れる。 (b) `f80_lower.py` で i80 ビット列を扱う規則を足す (共有鎖・T0/T1 退行確認が必要)。 (a) を先に試す。 本 run では実装していない。
- **残りの類型**: 同じ IR に `error: do not know how to soften fp_extend` と `no libcall available for fp_round with type f80` が出る (`f80_lower` 無し時)。 E7 を消しても f80 libcall が残るため、 19165 が `emcc -c` rc 0 になるには E7 修正に加えて f80 の扱いを決める必要がある。
