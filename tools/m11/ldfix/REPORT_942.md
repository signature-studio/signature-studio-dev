# #942 (CI-22) m11 ldfix stage4 の memory access out of bounds — 切り分け (部分達成)

親 #757。受入条件の進捗 (本 run 時点): 1 = 部分 (frame → IR 対応で trap の関数 7 種まで特定。発生 load は未特定) / 2 = 部分 (trap chain に修復関数無し = ldfix 起因ではないと確定。trap の load 特定は未了) / 3 = 部分 (snapshot 限定の判定。現 main 生成素材は #1292)。

## 1. 実測 (検証起点 origin/main `b4dac086`・runner 1 台)

`bash tools/m11/ldfix/ldfix_e2e.sh` (FL_WIN64_DIR=$RUNNER_TEMP/fl-win64、TMPDIR=$RUNNER_TEMP)
- 所要 56.9 秒 (real)・rc 0・開始 2026-10-13 18:32:34 UTC・load average 1.15 / 1.02 / 0.51
- 素材: fl-win64 / work-m11 / work-liftdiff / toolchain-emsdk (`[EMSDK]`) を展開 (toolchain-retdec は未使用)

| 項目 | base (修復前) | fix (修復後) |
|---|---|---|
| 修復関数数 (ldfix.py) | — | F3a=2 / F3c=33 (F1=0・F2=0・F3b=0) |
| stage4 units_run / units_total | 17 / 942 | 17 / 942 |
| stage4 threw | memory access out of bounds | memory access out of bounds |
| icall_ok / GetMem / FreeMem | 24 / 16 / 6 | 24 / 16 / 6 |
| survey ok / trap / miss | 136 / 9 / 14 | 136 / 9 / 14 |
| trap 種別 | out of bounds 8 ・ halt0 1 | 同左 |

判定 (judge_e2e.py): PASS (stage 4、全 probe・units・icall が base = fix)。

注意: `work-m11` の IR は現 main の生成手順と一致しない古いスナップショット (`ir_conditions.json` 無し、
`ldfix_report.json` の F1=0 / F3c=33 は REPORT.md §1 の 955 関数 (F1 902 / F3c 26) と別物)。
したがって本 REPORT の数値は「この素材の IR での値」であり、REPORT.md の値とは比較しない。

## 2. 受入 1: trap 9 件の unit 別切り分け (部分)

unit ごとの trap 9 件 (base/fix とも同一 VA)。**旧版の閉包表 (下) は前 run の転記で本 run では未検証。参考値として残す。**

| unit VA (RVA) | 種別 | IR 入口 | 閉包サイズ (前 run 転記・未検証) | 修復関数との交差 (前 run 転記・未検証) |
|---|---|---|--:|---|
| 0x55790 | OOB | function_455790 | 271 | 409c80, 413480, 413540, 417b70, 447ee0 |
| 0x158e20 | OOB | function_558e20 | 175 | 409c80, 413480, 413540, 417b70 |
| 0x16fde0 | OOB | function_56fde0 | 211 | 409c80, 413480, 413540, 417b70, 8c7710 |
| 0x19f9a0 | OOB | function_59f9a0 | 105 | 409c80, 413540, 417b70 |
| 0x223840 | halt0 | function_623840 | 510 | 409c80, 40ffe0, 413480, 413540, 417b70, 46b4d0, 5c0270 |
| 0x243270 | OOB | function_643270 | 173 | 409c80, 413480, 413540, 417b70 |
| 0x25c540 | OOB | function_65c540 | 262 | 409c80, 413480, 413540, 417b70, 44f740 |
| 0x264260 | OOB | function_664260 | 258 | 409c80, 413480, 413540, 417b70, 44f740 |
| 0x0 | OOB | (unit VA 0 = 対象外) | — | — |

- survey の trap は 9 件。unit VA を特定できたのは上の 8 件で、残り 1 件 (unit VA 0x0) は帰属不明のため閉包は算出していない。
  上表は実在 unit 8 件の内訳であり、9 件の完全な内訳ではない。
- 上表の閉包サイズ・交差は前 run の `reach_units.py` 出力の転記で、本 run では再算出していない (算出 script は消失)。
  閉包を根拠に原因を断定しないこと。
- unit VA は `m11_unit_va` の RVA。IR 関数名は `+0x400000` (m11_ov.c のアドレス規約)。
- 閉包は IR の直接 call のみ (間接 call トランポリン経由は含まない)。
- **対応 (本 run で解決)**: 前 run の「name section が無い」は誤り。wasm の export section に `--export-all` で全関数名が
  残っており、`tools/m11/m11_wasmnames.py` で wasm 関数 index → IR 関数名を引ける (15674 件)。
  `tools/m11/ldfix/trap_units.mjs` (survey と同じ呼び出し) で unit ごとの最上位 frame を取った結果 (base):

| unit VA | 種別 | 最上位 wasm frame | IR 関数 | 修復対象 (F3a/F3c) |
|---|---|---|---|---|
| 0x55790 | OOB | 14871 | function_4133f0 | 無し |
| 0x158e20 | OOB | 14873 | function_418190 | 無し |
| 0x16fde0 | OOB | 5263 | function_8c6530 | 無し |
| 0x19f9a0 | OOB | 14873 | function_418190 | 無し |
| 0x223840 | halt0 | — (Halt → longjmp) | — | — |
| 0x243270 | OOB | 14873 | function_418190 | 無し |
| 0x25c540 | OOB | 1875 | function_407e20 (`__lifted`) | 無し |
| 0x264260 | OOB | 75 | function_412e40 | 無し |
| 0x0 | OOB | 725 | function_409c80 | **有 (F3c 対象)** |

- 結論: 9 件の最上位 frame の関数は 7 種。修復対象は `function_409c80` (unit 0x0 の frame) の 1 件のみ。
  残りの trap は修復前から、修復と無関係な関数の load で起きている。
  受入 1 は「関数の特定まで」で部分達成 (trap の発生 load の特定は未了 = §5)。
- base/fix の frame 比較 (survey): 9 件の最上位 frame の関数 index は base/fix で同一 (前 run と同じ)。
  wasm offset のみ fix 側で増える。修復は trap の発生関数を変えていない。
  trap の発生 load (address 値) までは未特定。
- 注: 閉包表 (前 run の転記) の関数名 (`function_455790` 等) は、本 run の frame 対応とは別の unit 単位の閉包であり、本表の frame と混同しないこと。

## 3. 受入 2: boot の threw の原因 (base/fix 区別) — 部分

- base = fix で `memory access out of bounds` (units_run 17 / boot_stage 1 / dllmain_done false)。区別はできない。
- 修復前後で boot の trap 位置・件数は同一。修復 (F3a 2 関数 / F3c 33 関数) は boot の trap を解消も新規発生もさせない。
- 本 run で trap の呼び出し chain を取得 (`run_stage4.mjs` の stack、base/fix とも同形):
  trap 点 (内側) から外側へ: **function_4133f0(14871)** ← function_446400(2711) ← function_44bb70(2765)
  ← function_455790(2835) ← m11_tr_function_455790(9725) ← m11_icall(14847) ← function_4120c0(14865)
  ← m11_InitLib(14866) ← function_41d8f0(14869) ← entry_point(26) ← m11_boot_enter(14913)。
  (stack 11 frame 全件取得・base/fix 同一。)
  chain 上の関数 (41d8f0 / 4120c0 / 44bb70 / 446400 / 455790 / 4133f0) は修復対象 (F3a/F3c) に 1 つも含まれない。
- よって **「ldfix 起因か」: 否** (修復の影響を受けない関数の load で trap。base で既に存在)。
  「既存か」: 既存 (base = 修復前で同じ trap)。修復が trap を新規作成していないことも確定。
- 未確定: function_4133f0 のどの load が範囲外か (address 値・linear memory の範囲)。これは次 run の入口。

## 4. 受入 3: ldfix の修復が件数に反映されるか — 部分 (snapshot 限定の判定)

- **判定の範囲**: 本判定は `work-m11` の古い snapshot (§1 注意) の IR でのみ行った。現 main 生成の素材での e2e 再実行は未実施のため、
  現 main での効果は判定できていない。REPORT.md の値 (F1 902 / F3c 26) とも比較していない。
- F3a 2 関数 (413480, 413540) と F3c 33 関数の修復は、stage4 (units_run / probe / icall) と survey (ok / trap / miss) の
  いずれにも**反映されていない** (base = fix)。
- 理由 (推定・未確定): 修復関数は trap 閉包 (§2) に含まれるが、trap の最上位 frame の wasm index (14871 / 14873 / 14875 / 5263 /
  1875 / 75 / 725) が修復関数のどれに当たるかは未確認 (§2 の限界)。確認できているのは「修復後も同じ wasm 関数で同じ種類の trap が起きる」まで。
  修復が効く経路が trap より後にあるため先に止まる、という説明は仮説として残す。
- 件数が base/fix で同じであることは、ldfix が**壊さない** (非劣化) ことの確認にはなるが、**改善の検出**にはならない。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 「memory access out of bounds」の発生 load の特定 (function_4133f0 / 418190 / 8c6530 等の address 値) | trap の根本原因の特定 | #942 (次 run) |
| 現 main 生成 IR での ldfix 効果の再判定 (受入 3 の snapshot 限定を解消) | 修復件数の反映を現 main で未確認 | #1292 (`[CI-25]`・子) |
| 閉包表 (§2 旧版の unit 閉包サイズ・交差) の再算出 | 本 run では再算出していない (前 run の転記) | 不要 (frame 対応で代替。閉包表は参考値) |
| work-m11 の IR が現 main 生成と不一致 (ir_conditions.json 無し) | 修復件数が REPORT.md と一致しない | 既存 #680 |

## 6. 再現

```
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh   # stage4/survey 成果物を作る
S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs       # unit ごとの最上位 frame
S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/run_stage4.mjs      # boot threw の stack (chain)
python3 tools/m11/m11_wasmnames.py tools/m11/ldfix/work/stage4/base/m11_boot.cjs.wasm <idx...>   # index → IR 関数名
```

`trap_units.mjs` は commit 済み (本 run で追加)。閉包表 (§2 旧版) の算出スクリプトは前 run で消失しており、本 run では再算出していない。

## 7. 次 run の追加切り分け (run 3・測定 commit `2b99366a` の worktree `942-m11-trap-load`)

- 実測: `bash tools/m11/ldfix/ldfix_e2e.sh` 61 秒・rc 0・judge PASS (units 17/942・icall 24・survey ok 136 / trap 9、base = fix)。
  修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0 (§1 と同一)。
- **前節 §2 の訂正**: 本 run で `trap_units.mjs` の frame 番号を取り直すと、unit 17 の最上位 frame は `wasm-function[14871]` (function_4133f0) ではなく、
  単独実行 (先行 unit を走らせない) では `wasm-function[1874]` = `function_407a50__lifted` (FastMM_GetMem 実体) の `i64.load` (0x13c488) だった。
  先行 unit の副作用で frame が変わるため、§2 の「unit ごとの最上位 frame」は実行順に依存する。単独 unit で取り直すこと。
- 発生 load: `function_407a50__lifted` の空きリスト走査 (IR の `%26-8` 読み。IR 行 `load i64, ptr %33`)。
  `tools/m11/ldfix/trap_bins.mjs` (commit 済み) で bin 表 (BASE 16404744 + 16k) を走査すると、有効に見える bin ポインタ P のうち
  `F=[P+24]` の `F-8` が線形メモリ外のものが 4 件ある (k184 P=0x7a50 / k185 P=0x8040 / k186 P=0x8870 / k236 P=0xa027)。
  - F の値は機械語らしきバイト列に見える (例: `0x48000000b2850f07`・`0x8b4820ec83485500`)。P は 0x7a50 等の小さい値。
    ただし P の正体 (ヒープか・イメージ内か) と、boot 直後で既に壊れているかは**未確認** (この run では boot 直後の bin 表は scan していない・
    `trap_bins.mjs` の BEFORE 行は unit 17 の直前 = boot 後の状態で、その時点で既に上記 4 件が OOB)。
  - base と fix で同一 (修復前から存在)。ldfix の修復が bin 表を壊していないことは、この観測の範囲で確認。
- 結論 (受入 1・2 の進捗): 「trap の発生 load」は、unit 17 では FastMM の bin 表 (F-8 読み) まで特定。
  bin 表の値がどこから来たか (書き込み元) は未特定。次の入口は、boot 後の bin 表領域への書き込み元と、P/F の値の由来の確認。
- 未解決 (起票先): bin 表の上書き元の特定 → #942 (次 run)。現 main 生成 IR での再判定 → #1292 (`[CI-25]`)。
