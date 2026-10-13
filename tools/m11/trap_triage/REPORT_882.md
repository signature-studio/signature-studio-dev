# #882 unit 95 / 895 の出所調査: 現行 main での再測定

親: #684 (REPORT_684.md §4・§5)。子の依頼元: #684 の受入条件の残り。
検証起点: main `7736a5c5` (PR #1057 取込み後)。素材: fl-win64 / work-m11 / toolchain-emsdk / toolchain-retdec (`$ARTIFACTS_DIR`)。

## 0. 結論

1. **前提が現行 main では成立しない**。REPORT_684 の対象 2 unit は現行 build で挙動が変わっている。
   - unit 95 (`0x1d2680`): OOB → **ok** (survey kind=ok、GDI stub 呼出し 14 件、0 を返して継続)。
   - unit 895 (`0xeddfe0`): OOB → **halt0** (`MessageBoxA` `Runtime error 210 at 0000000010251460`、最上位 frame `function_412770`)。
   よって「unit 95 の OOB の出所」「unit 895 の `p-144` の出所」は、現行 build では観測できる OOB が存在せず、受入条件の対象が消えた。
2. 現行 build の OOB は 16 件 (REPORT_684 の e920ac3 時点 13 件から変化)。単発 OOB 4 unit のうち、**477 と 275 は残存** (`903d20` / `864fe0`)、95 は消えた。
3. **未達**: #882 の受入条件のうち「unit 95 の index・arg1 の出所を実測で特定」「unit 895 のリスト先頭・`p-144` の構造体特定」は、対象の観測が現行 build にないため実測できない。DEFECTS 行案は REPORT_684 §6 に既出 (477 の D11 変種) で、本 run では新規の類型を確定できなかった。

## 1. 再現の条件 (現行 main)

- `m11_e2e.sh` 全体は**未実行**。`m11_bounds.py` が `tools/m2/work/ghidra_dll/functions_dll.csv` を要求し、work-m11 にも fl-win64 にも無いため、全再生成モードで失敗した (fail-closed)。
- 代わりに、既存の lift 成果物 (`work/boot{0..4}.lift.ll`) から `m11_gen_ir2.sh` で IR を再生成 (rc=0、33.5 s、`ldfix` applied)、`m11_build.sh` で build (rc=0、18.8 s)、`survey_units.mjs` を `SV_RAW=1` で実行 (rc=0、9.8 s)。
- 上記の再生成 IR は `work-m11` 素材の IR と同一である保証は無い (provenance stamp が素材に無いため、`ir_conditions.json` の指紋は新規記録)。以降の数値はこの再生成 build の値。

## 2. 実測 (survey、現行 main)

| 構成 | ok | halt0 | miss | oob | other | noproc |
|---|--:|--:|--:|--:|--:|--:|
| REPORT_684 `e920ac3` | 828 | 54 | 46 | 13 | — | 1 |
| 本 run `7736a5c5` (再生成 build) | 869 | 8 | 47 | 16 | 1 | 1 |

OOB 16 件の最上位 frame (現行 build): 144 `407e20` / 149 `412e40` / 275 `864fe0` / 280 `6cefb0` / 304 `535bf2` / 477 `903d20` / 484 `903e00` / 492 `4133f0` / 513 `903e00` / 520 `903e00` / 555 `535bf2` / 659 `6cefb0` / 745 `407e20` / 830 `10c7cd0` / 880 `125da90` / 923 `410b10`。

**注意**: halt0 が 54 → 8 に大きく動いた。main 側の変更 (#1057 含む) による遷移と推定するが、未検証 (本 run では main の差分を切り分けていない)。

## 3. unit 95 (現行 ok)

- `function_47ad70` (現行 IR): `[arg1+40] == 0` なら `47ad00`、そうでなければ `[arg1+8]` を長さとする線形探索 (`*(arg1 + 8*i) == arg2` で `i` を返す)。
- REPORT_684 の OOB 経路 (`i64.load` at wasm `0x18f8df`) は、現行 build で unit 95 が通るため**発火しない**。wasm オフセットは再取得していない (現行 wat が無い。`work/m11_boot.wat` は 10/10 の古い生成物)。
- 結論: unit 95 の index `v` と `arg1` の出所は、現行 build では問題の挙動が無いため特定の対象外。

## 4. unit 895 (現行 halt0)

- 最上位 frame `function_412770` (`Runtime error 210` の表示元の前段)。`412770` は `[arg1+56]` から 30 要素、`ptr null` から 37 要素 (i64) を `__asm_rep_movsq_memcpy` で複写し、その後 `function_4126f0` を呼ぶ。
- **観測**: `ptr null` (wasm 上は address 0) からの読み出しを含む。wasm では address 0 は読めるため即 trap はしない。この経路が Runtime error 210 の直接原因かは**未検証**。
- REPORT_684 が述べた `40ffe0` のリスト先頭 (`p-144`) は、現行 build では `40ffe0` まで到達しない (halt0 frame 上では `40ffe0` は `40c820` の caller の一つ)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 現行 main で unit 95 / 895 の trap が消えたことの原因 (main 側のどの変更か) | REPORT_684 の前提の再検証 | PM 判断: #684 へのコメント (main 差分の切り分けを含む) |
| 895 の `412770` の null memcpy が Runtime error 210 の直接原因か | 895 の halt0 原因 | PM 判断: 新規子 issue (親 #684) |
| 477 (`903d20`) / 275 (`864fe0`) の残存 OOB | REPORT_684 §3・§4 の未解決 | 既存: #684 |
| `m11_e2e.sh` 全再生成の `tools/m2/work/ghidra_dll` 素材の欠落 | e2e 全体を再現できない | PM 判断: 素材の `oc_artifacts` 追加依頼 (work-m2 等) |

## 6. 検証の記録

- `m11_gen_ir2.sh` (foreground、rc=0、33.5 s): `ldfix` F1=902 F2=30 F3c=36 errors=0。
- `m11_build.sh` (foreground、rc=0、18.8 s): `_m11_icall_cnt_n` 2 件。
- `survey_units.mjs` (`SV_RAW=1`、foreground、rc=0、9.8 s): `SURVEY_UNITS {"ok":869,"miss":47,"other":1,"halt0":8,"oob":16,"noproc":1}`。
- `m11_e2e.sh` 全体: 未達 (§1 参照)。
