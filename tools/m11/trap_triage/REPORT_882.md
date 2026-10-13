# #882 unit 95 / 895 の出所調査: 現行 main での再測定

親: #684 (REPORT_684.md §4・§5)。子の依頼元: #684 の受入条件の残り。
検証起点: main `7736a5c5` (PR #1057 取込み後)。素材: fl-win64 / work-m11 / toolchain-emsdk / toolchain-retdec (`$ARTIFACTS_DIR`)。

## 0. 結論

1. **前提が現行 main では成立しない**。REPORT_684 の対象 2 unit は現行 build で挙動が変わっている。
   - unit 95 (`0x1d2680`): OOB → **ok** (survey kind=ok、GDI stub 呼出し 14 件、0 を返して継続)。
   - unit 895 (`0xeddfe0`): OOB → **halt0** (`MessageBoxA` `Runtime error 210 at 0000000010251460`、最上位 frame `function_412770`)。
   よって「unit 95 の OOB の出所」「unit 895 の `p-144` の出所」は、現行 build では観測できる OOB が存在せず、受入条件の対象が消えた。
2. 現行 build の OOB は 16 件 (REPORT_684 §8 `0618c61` 時点 11 件、`e920ac3` 時点 13 件から変化)。単発 OOB 4 unit のうち、**477 と 275 は残存** (`903d20` / `864fe0`)、95 は消えた。
3. **未達**: #882 の受入条件のうち「unit 95 の index・arg1 の出所を実測で特定」「unit 895 のリスト先頭・`p-144` の構造体特定」は、対象の観測が現行 build にないため実測できない。DEFECTS 行案は REPORT_684 §6 に既出 (477 の D11 変種) で、本 run では新規の類型を確定できなかった。

## 1. 再現の条件 (現行 main)

- `m11_e2e.sh` 全体は**未実行**。`m11_bounds.py` が `tools/m2/work/ghidra_dll/functions_dll.csv` を要求し、work-m11 にも fl-win64 にも無いため、全再生成モードで失敗した (fail-closed)。
- `functions_dll.csv` の生成経路 (`docs/WORKFLOW.md` §11: Ghidra 12.1.4 の `support/analyzeHeadless`・JDK 21・`tools/m2/ghidra_scripts/DumpFunctions.java`) は **未試行**。理由: 本 run の runner に Ghidra 12.1.4 が無く (`analyzeHeadless` 不在、`$ARTIFACTS_DIR` は fl-win64 のみ)、JDK は 17.0.20 で 21 ではない。csv の作成には Ghidra 12.1.4 の取得・JDK 21 の導入・`DumpFunctions.java` の実行が必要で、本 run では着手していない。csv が作れれば `m11_e2e.sh` 全体の再現を試せる (素材の追加は §5)。
- 代わりに、既存の lift 成果物 (`work/boot{0..4}.lift.ll`) から `m11_gen_ir2.sh` で IR を再生成 (rc=0、33.5 s、`ldfix` applied)、`m11_build.sh` で build (rc=0、18.8 s)、`survey_units.mjs` を `SV_RAW=1` で実行 (rc=0、9.8 s)。
- 上記の再生成 IR は `work-m11` 素材の IR と同一である保証は無い (provenance stamp が素材に無いため、`ir_conditions.json` の指紋は新規記録)。以降の数値はこの再生成 build の値。

## 2. 実測 (survey、現行 main)

| 構成 | ok | halt0 | miss | oob | other | noproc |
|---|--:|--:|--:|--:|--:|--:|
| REPORT_684 `e920ac3` | 828 | 54 | 46 | 13 | — | 1 |
| REPORT_684 §8 `0618c61` (比較の基準) | 829 | 55 | 46 | 11 | 0 | 1 |
| 本 run `7736a5c5` (再生成 build) | 869 | 8 | 47 | 16 | 1 | 1 |

各行の合計は 942 units (`0618c61` は 829+55+46+11+1 = 942、本 run は 869+8+47+16+1+1 = 942)。

### 2.1 `0618c61` → 本 build の OOB 遷移 (unit 単位)

`0618c61` の OOB 11 件 (56 / 95 / 149 / 275 / 291 / 296 / 304 / 477 / 555 / 895 / 923) と、本 build の OOB 16 件 (144 / 149 / 275 / 280 / 304 / 477 / 484 / 492 / 513 / 520 / 555 / 659 / 745 / 830 / 880 / 923) の差:

| 区分 | unit | `0618c61` | 本 build |
|---|---|---|---|
| OOB → ok | 95 | OOB (`47ad70`) | ok |
| OOB → halt0 | 895 | OOB (`40ff70`) | halt0 (`412770`) |
| OOB → OOB でない | 56 | OOB (`8c6530`) | OOB でない (本 run の survey 出力は 16 件の OOB 一覧のみで、現 ok/halt0/miss の区分は未取得) |
| OOB → OOB でない | 291 / 296 | OOB (`4f9f40`) | OOB でない (同上) |
| halt0 → OOB | 280 / 659 | halt0 (`412770`) | OOB (`6cefb0`) |
| 新たに OOB | 144 / 745 (`407e20`)、484 / 513 / 520 (`903e00`)、492 (`4133f0`)、830 (`10c7cd0`)、880 (`125da90`) | OOB でない (分類は未取得) | OOB |
| OOB のまま (top frame 変化) | 304 / 555 (`4f9f40` → `535bf2`)、923 (`4f9f40` → `410b10`) | OOB | OOB |
| OOB のまま (top frame 同じ) | 149 (`412e40`)、275 (`864fe0`)、477 (`903d20`) | OOB | OOB |

件数: 両方 OOB 6 件、`0618c61` のみ 5 件 (56 / 95 / 291 / 296 / 895)、本 build のみ 10 件 (144 / 280 / 484 / 492 / 513 / 520 / 659 / 745 / 830 / 880)。

主な変化は次のとおり。(a) 95 の OOB が消え、895 は halt0 になった。(b) 280 / 659 が halt0 から OOB に移った。(c) 144 / 484 / 492 / 513 / 520 / 745 / 830 / 880 が新たに OOB になった。(d) 56 / 291 / 296 の OOB が消えた。halt0 の残り (55 → 8) の内訳は、unit 単位の JSON を本 run で取得していないため未切り分け。main 側のどの変更 (#1057 など) に由来するかも未切り分け。

OOB 16 件の最上位 frame (現行 build): 144 `407e20` / 149 `412e40` / 275 `864fe0` / 280 `6cefb0` / 304 `535bf2` / 477 `903d20` / 484 `903e00` / 492 `4133f0` / 513 `903e00` / 520 `903e00` / 555 `535bf2` / 659 `6cefb0` / 745 `407e20` / 830 `10c7cd0` / 880 `125da90` / 923 `410b10`。

**注意**: halt0 が `0618c61` の 55 → 8 に大きく動いた (`e920ac3` からは 54 → 8)。main 側の変更 (#1057 含む) による遷移と推定するが、未検証 (本 run では main の差分を切り分けていない)。

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
| `m11_e2e.sh` 全再生成の `tools/m2/work/ghidra_dll` 素材の欠落 (Ghidra 経路は §1 のとおり未試行) | e2e 全体を再現できない | PM 判断: `prepare-event-context.sh` の allowlist に `work-m2` を追加し、R2 に素材を置く。`docs/WORKFLOW.md` §11 の許可名に `work-m2` は無く、`work-m6-ott` は `tools/m2` を展開しないため、現状の `oc_artifacts` 指定では届かない |

## 6. 検証の記録

- `m11_gen_ir2.sh` (foreground、rc=0、33.5 s): `ldfix` F1=902 F2=30 F3c=36 errors=0。
- `m11_build.sh` (foreground、rc=0、18.8 s): `_m11_icall_cnt_n` 2 件。
- `survey_units.mjs` (`SV_RAW=1`、foreground、rc=0、9.8 s): `SURVEY_UNITS {"ok":869,"miss":47,"other":1,"halt0":8,"oob":16,"noproc":1}`。
- `m11_e2e.sh` 全体: 未達 (§1 参照)。
