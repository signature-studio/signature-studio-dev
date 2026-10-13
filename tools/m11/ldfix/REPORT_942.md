# #942 (CI-22) m11 ldfix stage4 の memory access out of bounds — 切り分け (部分達成)

親 #757。受入条件の進捗: 1 = 部分 / 2 = 部分 / 3 = 部分 (snapshot 限定の判定。現 main 生成素材での判定は未実施)。

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

`work/trap_units.mjs` (survey と同じ呼び出しで unit ごとに trap を取得) の結果 (base/fix とも同一 VA 9 件):

| unit VA (RVA) | 種別 | IR 入口 | 閉包サイズ | 修復関数との交差 |
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
- **再現不可 (本 run で確認)**: 上表の閉包サイズ・交差は前 run の `work/trap_units.mjs` / `reach_units.py` の出力であり、
  両スクリプトはリポジトリにも作業環境にも存在しない (未 commit・消失)。本 run ではこの表を再算出できず、検証済みとは扱わない。
  表の値は「前 run の出力の転記」として読むこと。
- unit VA は `m11_unit_va` の RVA。IR 関数名は `+0x400000` (m11_ov.c のアドレス規約) で対応する。全 8 件で定義あり。
- 閉包は IR の直接 call のみ (間接 call トランポリン経由は含まない)。
- **未達**: wasm の name section が無い (リンクは `-g1` だが wasm に名前が残っていない) ため、trap の最上位
  wasm frame (wasm-function[N]) を IR 関数名へ直接対応させられなかった。よって「どの関数の、どの load で trap したか」は未特定。
- base/fix で trap の最上位 frame の関数 index は全 9 件で同一 (14873 ×3・14871・14875・5263・1875・75・725)。
  wasm offset のみ fix 側で増える (修復で命令が増えた分)。修復は trap の発生関数を変えていない。

## 3. 受入 2: boot の threw の原因 (base/fix 区別) — 部分

- base = fix で `memory access out of bounds` (units_run 17 / boot_stage 1 / dllmain_done false)。区別はできない。
- 修復前後で boot の trap 位置・件数は同一。修復 (F3a 2 関数 / F3c 33 関数) は boot の trap を解消も新規発生もさせない。
- 「ldfix 起因か既存か」: base (修復前) で既に同じ trap が起きているため、**修復が trap を新規に作っていないこと**は確定。
  trap の原因が修復前の IR のどこにあるか (既存欠陥か、ldfix が見逃した欠陥か) は、§2 の wasm frame → IR 関数対応が要るため未確定。

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
| trap の wasm frame (wasm-function[N]) → IR 関数名 (VA) の対応 (name section 無し) | 9 件の原因関数が未特定 | #942 (本 issue。次 run) |
| 「memory access out of bounds」の発生 load の特定 (linear memory 外アクセスの address 値) | 修復の効く経路の特定 | #942 |
| work-m11 の IR が現 main 生成と不一致 (ir_conditions.json 無し) | 修復件数が REPORT.md と一致しない | 既存 #680 |

## 6. 再現

```
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/work/trap_units.mjs
python3 tools/m11/ldfix/work/reach_units.py <trap_units の出力>
```

`work/` 配下の調査スクリプト (trap_units.mjs / reach_units.py) は gitignore 対象で、commit されていない。
本 run ではどちらも存在せず、§2 の閉包表は再実行できない。再現には両スクリプトを `tools/m11/ldfix/` 直下へ復元して
commit する必要がある (未起票の作業。起票先は #942)。
