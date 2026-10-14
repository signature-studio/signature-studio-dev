# #942 (CI-22) m11 ldfix stage4 の memory access out of bounds — 切り分け (部分達成)

親 #757。受入条件の進捗 (本 run 時点): 1 = 部分 (frame → IR 対応で trap の関数 7 種まで特定。発生 load は未特定) / 2 = 部分 (trap chain に修復関数無し = ldfix 起因ではないと確定。trap の load 特定は未了) / 3 = 部分 (snapshot 限定の判定。現 main 生成素材は #1292)。
通常 boot の trap 位置・lift 誤り候補 (最新) は [REPORT_942_APPENDIX.md §14](REPORT_942_APPENDIX.md) を参照。

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
- **注 (現 main の IR での判定は §8-2 を正とする。本節は snapshot 限定の記録)**。
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

## 8. 現 main 生成 IR での再判定 (#1292・受入 1〜4)

測定 commit: `604e900f` (origin/main、PR の親。測定に使った `tools/` はこの commit と同一)。
検証 HEAD: `8702c274` (コード差分 0。`git diff 604e900f 8702c274 -- tools/ ':!*.md'` は 0 行。§8-5)。runner: nproc=4。load average は各回の前後を採取 (§8-1)。
素材: fl-win64 / work-m11 / work-liftdiff / toolchain-emsdk (`[EMSDK]`) / toolchain-retdec (`[RETDEC]`) を展開。
IR は `bash tools/m11/m11_gen_ir2.sh` (現 main の手順) で作り、`ldfix_e2e.sh` の base は `M11_LDFIX=0` の IR から `m11_build.sh` で作った `boot_final3.ll`。

### 8-1. 実測 (n=3)

IR 生成 (現 main の手順、`ir_conditions.json` 付き):

- ldfix 適用: `ir_sha256` 2c68ceae…・490693 行・F1=902 / F2=30 / F3a=3 / F3b=5 / F3c=36 (7421 関数中)。
- ldfix 無し (`M11_LDFIX=0`): `ir_sha256` 25e931f2…・491108 行。ここから `m11_build.sh` (`M11_ALLOW_LDFIX_DISABLED=1`) で base の `boot_final3.ll` を作った。

`bash tools/m11/ldfix/ldfix_e2e.sh` (base = ldfix 無し / fix = ldfix 適用)、n=3:

| 回 | wall (秒) | load (実行前 → 後) | judge |
|---|--:|---|---|
| 1 | 73.3 | 0.74 0.54 0.24 → 1.29 0.72 0.32 | PASS |
| 2 | 62.6 | 1.09 0.69 0.32 → 1.25 0.81 0.38 | PASS |
| 3 | 62.4 | 1.15 0.79 0.38 → 1.21 0.87 0.43 | PASS |

- 並列数: nproc=4。survey は base/fix の 2 並列 (`ldfix_e2e.sh` の `for N in base fix` が `&` で並走)。
- wall の min–max: 62.4–73.3 秒。1 回目は `boot_final3.ll` の build 直後で、2・3 回目は 62.4–62.6 秒。

stage4 (n=3 とも同値):

| 項目 | base (ldfix 無し) | fix (ldfix 適用) |
|---|---|---|
| units_run / units_total | 52 / 942 | 52 / 942 |
| threw | unreachable | unreachable |
| icall_ok / icall_miss | 234 / 5 | 234 / 5 |
| init_count | 54 | 54 |

survey (n=3 とも同値。min–max は全 run で同一):

| | ok | miss | trap | trap の内訳 |
|---|--:|--:|--:|---|
| base | 868 (868–868) | 47 (47–47) | 26 (26–26) | unreachable 1 / halt0 8 / OOB 17 |
| fix | 870 (870–870) | 47 (47–47) | 24 (24–24) | unreachable 1 / halt0 7 / OOB 16 |

- judge: `STAGE4_JUDGE pass: true` (3 回とも)。
- 参考 (手順の訂正): 前 run の 1 回目の e2e は `boot_final3.ll` が ldfix 適用済みのまま base に使われ、ldfix が 2 回掛かった (F3a=2・survey 870/870・trap 24/24)。before/after になっていないため採用しない。以降は上記の手順どおり base を `M11_LDFIX=0` の IR に差し替えて測定。
- 注: boot の threw は snapshot (§1) の `memory access out of bounds` ではなく、現 main では base/fix とも `unreachable`。

### 8-2. 受入 3: 修復件数の反映

- 現 main での survey 件数は trap 26 → 24・ok 868 → 870 (base/fix の差)。
- 修復が trap 件数に反映されたかは、**1 件で確認・1 件は帰属未確認**:
  - 確認: `0x26d1a0` (unit 158) は base OOB → fix ok。base の最上位 frame 707 = `function_413540` (F3a)。
  - 未確認: `0x6d9ba0` (unit 493) は base halt0 → fix ok。halt0 経路のため frame が無く、修復との帰属は確認できない。
- F3a 残存: `0x6d5700` (unit 492) は base・fix とも OOB、最上位 frame 14873 = `function_4133f0` (F3a)。修復後も trap は残る。
- 種別が変わった unit は 2 件 (どちらも依然 trap):
  - `0x25c540` (unit 144): base halt0 → fix OOB。fix の最上位 frame 1875 = `function_407e20__lifted`。因果は未確認。
  - `0xeddfe0` (unit 895): base OOB (frame 2001 = `function_40ff70`) → fix halt0。
- unit の変化は 4 件。ok に入ったのが 2 件 (`0x26d1a0`・`0x6d9ba0`)、種別だけ変わったのが 2 件 (`0x25c540`・`0xeddfe0`、いずれも trap のまま)。この 4 件で trap 26 → 24・ok 868 → 870 の差が説明できる。
- したがって「修復が件数に反映される」は現 main でも**限定的**: 帰属が確認できたのは `0x26d1a0` の 1 件。snapshot 限定の判定を「解消」とは言わない。

### 8-3. 受入 4: trap 最上位 frame と #942 の結論

全 unit の表 (base 26 件・fix 24 件) は `REPORT_942_APPENDIX.md` に分割移動。取得方法は `tools/m11/ldfix/trap_units.mjs` (`S4_NAME=base|fix`)。

- 結論: #942 の「修復対象は function_409c80 の 1 件のみ」は現 main では**一致しない**。`function_409c80` (F2・F3c) は trap の最上位 frame に現れない。最上位 frame に現れる F3a は `function_413540` (base の unit 0x26d1a0 のみ) と `function_4133f0` (unit 0x6d5700。修復後も残る)。
- survey の `top_frame_idx` の `14877` (`function_412770`) は base 8 件・fix 7 件で、halt0 unit 数と一致する。halt0 経路は frame を取れない。
- chain 上の関数 (非最上位) の判定は未確認。

### 8-4. F3a 3 件・F3c 36 件の所在と差分

- F3a 3 件 (`ldfix_report.json` `f3a_vas`): `function_4133f0` / `function_413480` / `function_413540`。
- 旧 snapshot の F3a (413480・413540) との対応: `function_413540` と `function_413480` は新旧で F3a。`function_4133f0` は**現 main で新たに F3a に入った関数**で、旧 snapshot の F3a には無い。
- F3c 36 (`f3c_vas`) は `ldfix_report.json` を参照。`function_409c80` は F3c に含まれる。
- F3c 36 と REPORT.md §1 の F3c 26 の差: **原因は未確認**。REPORT.md §1 の 955 (F1 902 + F3c 26 等) は旧 snapshot 時点の測定値で、旧 snapshot: units_run 17 / survey ok 812。現 main (§8-1): units_run 52/942、ok 868。F1 902 は一致する。

### 8-5. 検証範囲と手順

- 本節の数値は本 fix run (2026-10-13・PR #1469 の差し戻し対応) で実測。素材は `oc_artifacts: fl-win64 work-m11 work-liftdiff toolchain-emsdk toolchain-retdec` で展開。
- 手順 (実行順):
  ```
  M11_LDFIX=0 bash tools/m11/m11_gen_ir2.sh                     # ldfix 無しの IR (ir_conditions.json: ldfix=disabled)
  rm -f tools/m11/work/boot_final3.ll tools/m11/work/obj/*.o     # ldfix 適用済みの boot_final3.ll を消す
  M11_ALLOW_LDFIX_DISABLED=1 bash tools/m11/m11_build.sh        # ldfix 無し IR の build は明示 opt-in (#1165)
  bash tools/m11/ldfix/ldfix_e2e.sh                             # base = 上の boot_final3.ll / fix = ldfix 適用
  S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs   # 全 unit の frame
  S4_NAME=fix  S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs
  ```
  `ldfix_e2e.sh` は `boot_final3.ll` を base として読み、その上に ldfix を掛けて fix を作る (ldfix_e2e.sh:28)。base が ldfix 適用済みだと ldfix が 2 回掛かる (§8-1 の参考)。
- 最後の `work/` の状態: 検証の最後に `M11_LDFIX=0 bash tools/m11/m11_gen_ir2.sh` を実行して戻したため、`ir_conditions.json` は `ldfix=disabled` (`ir_sha256` 25e931f2…)。`boot_final3.ll` は ldfix 無しの base IR から作ったもの。
- 測定基準は `8702c274` に統一 (§8 冒頭の「検証 HEAD」と同じ)。`8702c274` 以降 (`bff2ac54`) の差は REPORT の記述修正のみ。
- 差分 0 の証跡: `git diff 604e900f 8702c274 -- tools/ ':!*.md'` の出力は 0 行 (`bff2ac54` まででも 0 行)。`git diff 604e900f 8702c274 --stat -- tools/` は `tools/m11/ldfix/REPORT_942.md` と `REPORT_942_APPENDIX.md` のみ (本文の記述修正は `*.md` のため上記の差分には含まれない)。
- 未解決 (起票先):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| F3c 36 と REPORT.md §1 の 26 の差の原因 | 修復件数の記録の正確さ | #942 (次 run) |
| `function_4133f0` (unit 0x6d5700) の F3a 修復後も残る trap の発生 load | 受入 1 | #942 (次 run) |
| unit 144 (0x25c540) の halt0 → OOB の因果 (`function_407e20__lifted`) | 受入 2・3 | #942 (次 run) |
| unit 0x6d9ba0 (halt0) の修復との帰属 (frame 無し) | 受入 3 | #942 (次 run) |

## 9. bin 表の boot 前後の状態 (#942 受入 1・2・run 5)

測定 commit: `35e6031e` (origin/main)。素材 fl-win64 / work-m11 / work-liftdiff / toolchain-emsdk / toolchain-retdec を展開。
`bash tools/m11/ldfix/ldfix_e2e.sh` は 36.7 秒・rc 0・judge PASS (units 17/942・icall 24・threw `memory access out of bounds`・survey ok 136 / trap 9、base = fix)。

- 計測: `S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/bin_table_pre_boot.mjs` (commit 済み)。
- PRE (イメージ読込直後・boot 前): k184 P=0x7a50 / k185 P=0x8040 / k186 P=0x8870 / k236 P=0xa027 の F が OOB。k215 P=0xee は F=0。
- 上記 4 つの P は PE `.data` 上の生値 `0x407a50` / `0x408040` / `0x408870` / `0xa027` の上位 `0x40` を落とした値 (`m11_image.bin` は VA→LVA 補正済み) **と推定**。本 run では、生値 `0x407a50` / `0x408040` / `0x408870` / `0xa027` が PE `.data` 内に各 1 箇所 (8 バイト LE) あることだけ照合した。上位 `0x40` 欠けの因果は未確認。PE 上の値は `.text` の関数先頭アドレスに見える。
- POST (boot 後): OOB 47 件 (57 行中。PRE の 4 件を足した全体は 51 件)。boot 中に bin 表スロットの多くが bin 表自身 (`0xfa5xxx`) を指すため、F の読みが OOB 扱いになる。走査が FastMM の正しい空きリストを表しているかは未確認。
- 結論 (受入 1・2 の進捗): 「bin 表の不正値がイメージ段階から存在する」ことは PRE で確認。ただし、これが「書き込み元が boot 前のイメージ」を意味するかは未確認 (P 値の対応先が bin ヘッダか、隣接する別データかを切り分けていない)。ldfix の修復前後で差は無い (base = fix)。
- 未解決 (起票先): P/F の由来 (bin ヘッダか否か) の切り分けと、POST で OOB になるスロットの書き込み元 → #942 (次 run)。

## 10. bin 表 P/F の由来とサイズ→bin 表 (#942 受入 1・2・run 6)

結論 1 行: bin 表 k184〜186・k236 の P 値は PE `.data` に生値として存在することを確認 (5 件のみ。512 スロットの照合は未実施)。k184〜186・k215・k236 の不正値が通常経路 (サイズ ≤ 2600) で読まれるかは未確認 (前回観測では読まれない、HEAD で未再現)。詳細・実測値・未解決 (#942 次 run) は [REPORT_942_APPENDIX.md §10](REPORT_942_APPENDIX.md) を参照。
