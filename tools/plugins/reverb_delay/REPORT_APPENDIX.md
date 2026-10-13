# reverb_delay REPORT 付録 (#523 PLG-F4-2 追補)

本体 `REPORT.md` の §12 に続く節。 250 行上限のため分割して置く。

## 13. #523 追補 (2026-10-13 · HEAD 986e7415 · 再測定)

検証起点 **986e7415** (main、本 PR で変更なし)。 素材 `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` / `work-*` / `plugins-ott` は `$HOME/artifacts` に実在を確認。 各 run は 1 回のみ。 engine の正しさは示さない (到達性のみ)。

| engine | 条件 | lift rc | define | f80 関数 | `emcc -c` | 秒 (lift+emcc) |
|---|---|--:|--:|--:|--:|--:|
| 19165 Multiband Delay | IPPCODE 除外 + AVX 系 78 除外 (`avx_bad_ranges.py`) | 0 | 2,608 | 6 | **139 (segfault)** | 391 |
| 19165 同上 | 同 + `PLUG_F80_LOWER=1` | 0 | 2,608 | 0 | **1** | 416 |
| 19000 Delay 3 | `PLUG_F80_LOWER=1` (全 3,632 関数) | 0 | 4,107 | 0 | **0** | 124 |

- **19165 segfault の位置**: `emcc` は `function_1800ceec0` の WebAssembly 命令選択 (DAG combine の `visitSTORE`) で落ちる。 同関数は x86_fp80 を含む (`final.ll` の f80 関数 6 本のうち 1 本)。 `PLUG_F80_LOWER=1` で f80 を外すと segfault は消える。
- **19165 の次の類型 (f80 lowering 後)**: `e.final.ll:273362: invalid cast opcode for cast from 'double' to 'i80'`。 `p0c/f80_lower.py` は `bitcast x86_fp80 to i80` (f80 のビット列を読む命令) を double に置換するが、`bitcast double to i80` を残す。 f80 のビット操作を扱えないことが原因と推定。 この類型は共有鎖 (`p0c/f80_lower.py`) の修正が必要で、T0/T1 の退行確認 (#523 受入条件 2) を伴うため、本 run では未修正。 **新類型 E7 (f80 ビット操作の lowering 漏れ)** として記録。
- **19000 の f80 lowering**: `PLUG_F80_LOWER=1` は f64 化で精度を落とす (53 bit 仮数)。 19000 の f80 関数 (`function_1800bcb00` ほか) の精度影響は未検証。 既定 (`PLUG_F80_LOWER=0`) では `emcc -c` が rc 1 のまま (REPORT §12 の既存結果)。
- 19165 の segfault の起点 (`function_1800ceec0`) と f80 6 本の内訳は `work/reverb_delay/engine19165_noipp_nobad/` (gitignore) に残し、再現手順は下記。

### 再現手順

```
source tools/plugins/reverb_delay/env.sh
python3 tools/plugins/reverb_delay/avx_bad_ranges.py 19165 > work/reverb_delay/bad19165.out
ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges $PWD/work/reverb_delay/bad19165.out" \
  ENGINE_TAG=_noipp_nobad bash tools/plugins/reverb_delay/engine_lift.sh 19165 1200
PLUG_F80_LOWER=1 bash tools/plugins/reverb_delay/engine_lift.sh 19000 800
```

注: `--exclude-ranges` には絶対パスを渡す (`engine_lift.sh` が `tools/plugins` へ cd するため相対パスは解決されない)。

### 受入条件への対応 (#523)

1. 19000 は `PLUG_F80_LOWER=1` で `emcc -c` rc 0 (到達性のみ・精度未検証)。 19165 は未達 (E7)。 既定 (f80 lowering 無し) では両方未達。
2. 共有鎖 (`p0c/f80_lower.py`) は未変更のため退行確認は不要だが、E7 の修正時に必要。 未実施。
3. IPPCODE の扱い: 未決 (#38 [IPP-10] と PM 判断)。
4. LoadLibrary 結合解析: 未実施。
