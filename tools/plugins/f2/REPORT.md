# tools/plugins/f2 REPORT — PLG-F2 eq-filter 11 本: 手順 1 (固有閉包 lift) の再現と、差分試験の前提監査 (#199) / leaf 23 関数の関数単位差分 (#515, §7)

- 検証起点 commit: **09d9fd8** (origin/main 0f22d9c を基点とする `199-plg-f2-eq-filter-step1`)。数値はすべてこの HEAD から `bash tools/plugins/f2/f2_step1.sh` を 3 回実行して取得。
- 日付: 2026-10-13 / 担当 dir: `tools/plugins/f2/` のみ (生成物は `tools/plugins/work/` = gitignore)
- 既知類型との関係: **(icall §4) D1 = 間接 call/jmp 脱落** が 11 閉包すべてで再現 (§3)。(DEFECTS.md) D15 は x64c stage-0 経路の同種事象で、本件は RetDec 経路 (別経路)。新規類型なし。
- 範囲: issue #199 の手順 1 (固有閉包 lift → `emcc -c`) と、手順 3 (差分試験) の実行可否の判定まで。**§7 (#515) で「機械語にも間接 call 無し」の leaf 23 関数だけ関数単位差分を実施**。**手順 2〜4 と出口条件 (差分試験 bit-exact) は未達** (§5)。

## 0. 結論 (先出し)

1. **手順 1 は再現した**: eq-filter の Delphi 殻 11 block (Frequency Splitter の C++ engine block 18980 は T3 別トラックで対象外) を RetDec + pass 鎖で lift し、**11/11 が `lift_rc=0`・`emcc -c` rc=0**。閉包関数数・バイト数・rc は `PLUGIN_MATRIX.json` の記録と **11/11 一致**。1 コマンド 51 秒 (3 回とも 51 秒)。
2. **ただし `emcc -c` 通過は正しさを意味しない**: 11 閉包の機械語には非 IAT の間接 call が **計 550 site** あるが、lift 後 IR (`p.final.ll`) の間接 call は **0**。入口スロット `Eff_Render` も 11/11 が静的に間接 call を 1〜16 件持つのに IR 側は 0 件 (§3)。RetDec が間接 call を decoder 段で捨てる既知欠陥 ((icall §4) D1) で、`batch_lift.sh` 鎖には `tools/icall` の復元 (binary pre-rewrite) が接続されていない。
3. 例: Fruity Bass Boost の入口 `Eff_Render` (閉包 JSON の名前; 0x6c8cb0) は機械語では `this+0x134` と `[this+0x130]` の float を渡して `call qword ptr [0x729560]` (rip 相対の関数ポインタ変数; kernel 表の変数かは未確認) を呼ぶだけの関数。lift 後 IR (`function_6c8cb0`) は call を失い、`this+308` を返すだけの 9 行になっている (callee が使う引数が消えた結果、仮引数も `%arg1` の 1 本のみ)。
4. よって **この鎖の出力に対する差分試験は、実施しても必ず不一致になる**。差分試験の前提は (a) icall 復元の接続、(b) P0a/P0b/P0c (#195/#196/#197、いずれも open) の統合、の 2 段 (§5)。本 PR では出口条件を満たさないため `Refs #199` で、`Closes` は付けない。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 環境 | GitHub Actions runner 4 core (`nproc`=4)。lift は逐次 |
| 素材 | `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk`。`fl-win64` は `extracted/*_PE.bin` 323 本のみ展開 (3.2 秒) |
| 実行 | `f2_step1.sh` ×3: **51 / 51 / 51 秒**。開始時 load average (1 分) 0.22 / 0.66 / 0.86、終了時 0.66 / 0.86 / 0.94。3 回の stdout は md5 一致 (決定的) |
| 前提 work/ の生成 | `win_scan.py` 9.0 秒、`win_funcs.py` **8 分 22 秒** (1 回のみ・load average 13.9・Pool(14) を 4 core で実行)、`win_unique.py` 2.8 秒、`win_abi.py` 0.4 秒。`f2_step1.sh` は work/ が無いときだけ再生成する |
| blockmap | fl-win64 tarball に `block_manifest.json` が無く `nsis_names.py` は動かないため、`f2/mk_blockmap.py` が `PLUGIN_MATRIX.json` の win modules から `work/nsis_blockmap.json` (kind=PE 182 行) を再構成して `win_funcs.py` に渡す |

## 2. 手順 1: 固有閉包 lift の結果 (`work/batch/status.csv`)

閉包 = DSP エントリ (vtable override) から `call/jmp rel32` で到達する固有関数 (framework 共通 13 DLL 以上は frontier として除外; 定義は `lift/plugin_closure.py`)。
`defines` = `p.final.ll` の `^define` 数。`seconds` = `lift_ranges.sh` の実測秒 (合計 35 秒)。f80 / 未実装 helper は全 block 0。

| block | plugin | Tier | 閉包関数 | 閉包 x86 B | defines | lift_rc | emcc -c rc | seconds | matrix 一致 |
|--:|---|---|--:|--:|--:|--:|--:|--:|---|
| 18953 | EQUO | T1 | 39 | 14,834 | 39 | 0 | 0 | 3 | MATCH |
| 18975 | Emphasizer | T1 | 38 | 13,938 | 38 | 0 | 0 | 3 | MATCH |
| 18979 | Frequency Splitter (Delphi 殻) | T3 | 45 | 24,555 | 45 | 0 | 0 | 4 | MATCH (closure のみ; matrix に batch 欄なし) |
| 18982 | Fruity 7 Band EQ | T0 | 14 | 5,660 | 14 | 0 | 0 | 3 | MATCH |
| 18984 | Fruity Bass Boost | T0 | 11 | 3,286 | 11 | 0 | 0 | 2 | MATCH |
| 19005 | Fruity Fast LP | T0 | 14 | 3,560 | 14 | 0 | 0 | 2 | MATCH |
| 19006 | Fruity Filter | T0 | 13 | 6,550 | 13 | 0 | 0 | 3 | MATCH |
| 19013 | Fruity Free Filter | T0 | 14 | 6,337 | 14 | 0 | 0 | 3 | MATCH |
| 19058 | Fruity Parametric EQ | T0 | 17 | 6,380 | 17 | 0 | 0 | 3 | MATCH |
| 19059 | Fruity Parametric EQ 2 | T1 | 73 | 35,342 | 73 | 0 | 0 | 5 | MATCH |
| 19145 | Low Lifter | T1 | 28 | 16,788 | 28 | 0 | 0 | 4 | MATCH |

「matrix 一致」= `status.csv` の closure_funcs / closure_bytes / lift_rc / emcc_c_rc が `PLUGIN_MATRIX.json` の `lift` 欄と等しい (`f2_step1.sh` 内の比較、DIFF count = 0)。

## 3. 間接 call 監査 (`tools/icall/audit_icall.py --funcs <閉包関数 VA> --ir p.final.ll`)

定義: 「静的 site」= 閉包関数範囲を capstone で逆アセンブルした非 IAT の間接 call 命令数 (`call [reg+disp]`・`call [rip+var]` ほか)。「IR」= `p.final.ll` で callee が `@name` でない call の数。
`p.final.ll` は `insn.addr` を持たないため site 単位の dropped / 直接化の区別はできない (関数単位の件数比較)。入口の `Eff_Render` 列は閉包 JSON の `entries` から。

| block | plugin | 静的 site | call あり関数 | IR の間接 call | `Eff_Render` の静的間接 call → IR | IR leaf / うち機械語でも間接 call 無し |
|--:|---|--:|--:|--:|--:|--:|
| 18953 | EQUO | 82 | 20 | 0 | 16 → 0 | 8 / 1 |
| 18975 | Emphasizer | 39 | 15 | 0 | 7 → 0 | 7 / 3 |
| 18979 | Frequency Splitter | 121 | 23 | 0 | 11 → 0 | 10 / 4 |
| 18982 | Fruity 7 Band EQ | 14 | 6 | 0 | 1 → 0 | 1 / 1 |
| 18984 | Fruity Bass Boost | 13 | 6 | 0 | 1 → 0 | 1 / 0 |
| 19005 | Fruity Fast LP | 15 | 6 | 0 | 2 → 0 | 3 / 2 |
| 19006 | Fruity Filter | 17 | 6 | 0 | 2 → 0 | 3 / 2 |
| 19013 | Fruity Free Filter | 17 | 6 | 0 | 2 → 0 | 2 / 1 |
| 19058 | Fruity Parametric EQ | 21 | 7 | 0 | 4 → 0 | 2 / 0 |
| 19059 | Fruity Parametric EQ 2 | 137 | 27 | 0 | 8 → 0 | 17 / 9 |
| 19145 | Low Lifter | 74 | 15 | 0 | 6 → 0 | 1 / 0 |
| 合計 | | **550** | | **0** | 11/11 本で ≥1 → 0 | 55 / 23 |

- 「IR leaf」= 他の `function_*`・外部関数・間接 call を呼ばない `define` (`__asm_*` helper 呼出は許容; `f2/closure_stats.py`)。機械語側にも間接 call が無いものが **23 関数** (関数単位差分試験の候補; ただし浮動小数引数は ARG pass が要る)。
- 全スロットの内訳 (`SaveRestoreState`・`ProcessParam` など) は `f2_step1.sh` の出力表にある。静的に間接 call を持つ入口スロットは `Eff_Render` に限らず、すべて IR 側 0 件 (表の「入口の IR 間接 call 合計」= 11/11 本で 0)。
- 入口 `Eff_Render` の ABI は `ABI.md` §3.1 (rcx=this, rdx=Source, r8=Dest, r9d=Length)。Parametric EQ (0x6d0350) は IR 側が 7 要素の counter 減算ループ (72 行) のみで、静的 4 site の間接 call (実際の処理) は消えている。

## 4. 検算とネガティブコントロール

別算法の検算 (`f2/xcheck_icall.py`): `audit_icall.py` (recursive descent + jump table 解決) とは独立に、閉包 ranges を capstone の線形 sweep で数えた非 IAT 間接 call は **11 block 全てで audit と一致、合計 550 = 550**。

ネガティブコントロール (`bash tools/plugins/f2/nc_f2.sh`、3.8 秒、3 件とも DETECTED):

| 検査 | 壊し方 | 結果 |
|---|---|---|
| NC1 閉包 define 数 = closure JSON の unique_funcs | Bass Boost の ranges を 1 本欠かして lift | defines=10、closure=11 → 不一致 (`closure_stats.py` の assert が FAIL する条件) |
| NC2 `emcc -c` rc | 正常 IR (rc=0) に不正行を 1 行追加 | rc=1 |
| NC3 間接 call 監査の識別力 | Parametric EQ `function_6d0350` に間接 call を 1 本注入した IR | `ir_call_ind_total` 0 → 1、`0x6d0350` の `ir_call_ind` = 1 |

## 5. 範囲外・未解決

検証範囲: 手順 1 の再現と、IR の間接 call 件数 (関数単位) の静的比較のみ。**native との出力比較は 1 件も実施していない**。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `batch_lift.sh` の鎖に `tools/icall` の間接 call 復元 (binary pre-rewrite + `__icall_dispatch`) が無く、550 site 脱落 | 11 本すべて。接続しない限り差分試験は必ず不一致 | **新規子チケット案** `[PLG-F2-2]` (親 #199): batch_lift への icall 接続と、本 REPORT の §3 表を 0 にする回帰ゲート化 (`emcc -c` 通過だけでは gate にならない) |
| 手順 2〜4: 共有 framework wasm とのリンク・Host shim・kernel 表・`Eff_Render` 差分試験・Render test .flp E2E | 出口条件 (差分試験 bit-exact) | 既存 #195 (P0a) / #196 (P0b) / #197 (P0c) が完了待ち。`framework/REPORT.md` §0 は `TFruityPlug*` 実体生成が未達と記録。本 issue (#199) に残す |
| 23 個の「機械語でも間接 call 無し」leaf の関数単位差分 (native ms_abi と wasm; `lift/t0_balance` 方式の一般化) | 部分的な bit-exact 実績。浮動小数引数には ARG pass 再適用が必要 | **新規子チケット案** `[PLG-F2-3]` (親 #199)。ARG pass は #197 | → **#515 で実施 (§7): 一致 15 / 不一致 8。不一致は ARG pass 未接続 (#547)**
| Frequency Splitter の engine DLL (block 18980、MSVC C++ 3.35 MB、T3) | 1 plugin。本 PR では Delphi 殻 18979 のみ | 既存 #28 ([PLG-E1]、タイトルに Frequency Splitter を含む) にコメントし別トラック化を PM が判断 |
| `win_funcs.py` が 4 core で 8 分 22 秒かかり、Actions の 60 分枠を圧迫 | 再実行コスト | `work-plugins-f2` のような素材 (`tools/plugins/work/` の winfuncs) 化は #293 (allowlist 追加) で PM 判断 |

DEFECTS.md 行案: なし (既存 (icall §4) D1 の再確認。新しい検出信号として「`p.final.ll` の間接 call 件数 vs 閉包範囲の静的間接 call 件数」を `audit_icall.py --funcs` で機械化できることを確認した)。

## 6. 再現

```sh
source tools/shared/env.sh && source tools/plugins/f2/env.sh   # fl-win64 の PE 展開 (Actions) と pefile+capstone の venv
bash tools/plugins/f2/f2_step1.sh      # 手順 1 の全再現 (work/ があれば 51 秒; matrix 突合 DIFF count=0 で exit 0)
bash tools/plugins/f2/nc_f2.sh         # ネガティブコントロール 3 件
python3 tools/plugins/f2/xcheck_icall.py 18953 18975 18979 18982 18984 19005 19006 19013 19058 19059 19145   # 別算法検算
```

| ファイル | 役割 |
|---|---|
| `f2_step1.sh` | 前提 work/ 生成 → `batch_lift.sh` (11 block) → matrix 突合 → `closure_stats.py` → `audit_icall.py` → `icall_summary.py` |
| `mk_blockmap.py` | `PLUGIN_MATRIX.json` から `work/nsis_blockmap.json` を再構成 |
| `closure_stats.py` / `icall_summary.py` | 閉包統計 / 間接 call 監査の集計表 |
| `nc_f2.sh` / `xcheck_icall.py` | ネガティブコントロール / 別算法検算 |
| `env.sh` | `FL_WIN64_DIR` と python 依存 (pefile, capstone) の準備 |

## 7. PLG-F2-3 (#515): 「IR leaf かつ機械語に間接 call 無し」23 関数の関数単位差分試験

- 検証起点 commit: **cb70945** (origin/main 6a0a8c8 を基点とする `515-plg-f2-3-leaf-diff`)。数値は §7 の再現コマンドをこの HEAD (`git status --porcelain=v1 -- tools/plugins/f2` クリーン) で実行して取得。前提 `f2_step1.sh` の work/ は同 run 内で再生成 (§1 と同条件)。
- 既知類型との関係: 不一致 8 関数は全て **(DEFECTS.md) D5** (xmm 引数脱落、`xmm_arg_drop` 8)。重なる類型は **(DEFECTS.md) D4** 系 (`spill_slot_deref` 4)・**(DEFECTS.md) D1a** (`fp_flag_unreflected` 4)。比較系の偽陽性 2 類型は新規 (§7.5 の DEFECTS.md 行案)。
- 範囲: 23 関数の関数単位差分とそのネガティブコントロール。native 参照は FL Studio 実機ではなく **Linux x86-64 上で PE の機械語を ImageBase に mmap して MS x64 ABI で直接実行**した値 (`tools/liftdiff/rt/ld_native.c`)。ホスト・framework・TFruityPlug 実体とのリンク (#195〜#197) は範囲外。

### 7.0 結論 (先出し)

1. 対象 23 関数 = §3 の「IR leaf 55」のうち機械語にも非 IAT 間接 call が無いもの。別算法 (`xcheck_leaf.py`) で **同じ 23 関数を再導出** (集合一致 EQ)。23 関数は位置非依存ハッシュで **18 種類のコード**(5 組が別 block と同一コード)。
2. **最終判定: 一致 15 / 不一致 8 / 実行不能 0**(23 関数)。主採点(9 パターン)だけだと 一致 9 / 不一致 9 / 実行不能 5 で、補助 case(§7.2)を足して 12 関数の判定が確定した。うち主採点の「一致」2 関数 (0x6bfec0・0x6c9b60) は補助 case で不一致に覆った = **9 パターンの一致は検出力が弱い関数がある**。
3. 不一致 8 関数は **全て「機械語が xmm 入力を読むのに IR 署名に float 引数が無い」(D5)**。`batch_lift.sh` → `lift_ranges.sh` の鎖に ARG pass (`lift/passes/ir7_argpass.py` は取り込み済みで未接続) が無いことが共通原因。→ [PLG-F2-4] #547。
4. 一致 15 関数は 9 パターン+補助 case の範囲で戻り値・書換えメモリ・entry 列が bit 一致。**入力空間全体の等価性は主張しない**(§7.4 の限界)。
5. ネガティブコントロール (§7.3): 既知の脱落を 1 箇所入れた IR で、一致 15 関数のうち変異できた分の不一致検出を実測。

### 7.1 方式 (1 コマンド再現は §7.6)

`tools/liftdiff` の target 記述 (`docs/FORMAT.md` §1) を block ごとに `mk_targets.py` が生成する。**IR は `batch_lift.sh` の `p.final.ll` そのまま**(下記 ABI アダプタを除き無改変)。

| 項目 | 内容 |
|---|---|
| native | block の PE を ImageBase 0x400000 に mmap、`setarch -R`、MS x64 ABI で `function_<VA>` の機械語を直接実行 (`ld_native`) |
| wasm | `p.final.ll` を entry 計装して `emcc -O0` + `p_simd.c` (SIMD helper) + スタブと link。PE を RVA 配置した image (DIR64 reloc を VA→RVA 補正; 8 block とも reloc 件数 = 補正件数) を線形メモリ 0 番地に載せる (`wasm_origin=0`、delta=0x400000) |
| 比較 | 戻り値 (rax / xmm0 bit)・書換えメモリ (image 書込み可能 section + arena + heap の 8B ブロック)・import 呼出列・関数 entry 列。ptr は delta を許容 |
| 主採点 | 1 関数 9 case (引数パターン z,s,p0,p1,p01,pall,pall2,q0,qall。ptr-rich random の arena) |
| 補助採点 | 主採点が unexec / 時間切れ / 偽陽性 / 検出力不足の 12 関数に、機械語の意味に合わせた手作り case を追加 (`leaf_custom.py`、66 case)。ptr 鎖・count・float 配列・xmm 入力 (native にだけ `f:<bits>` を渡す) |
| ABI アダプタ | IR が `i128` を返す 4 関数 (0x6c8fc0・0x6c9b60・0x6f1650・0x6f23b0。機械語は xmm0 に float を返す) は liftdiff の JS ランナが呼べない。元関数を `.i128` に改名し、同名の `trunc i128→i32; bitcast float` だけのラッパを足した (`mk_targets.py`)。機械語の最後の xmm0 書込み命令の型 (`ss`) で float と決定 |

**採点の定義**(`leaf_report.py` 冒頭と同文): 関数 verdict は match = native 完走 case ≥1 かつ完走した全 case 一致 / mismatch = 完走 case のどれかに差分、または native 完走 + wasm trap / unexec = native 完走 case 0。最終判定は、補助が mismatch なら mismatch、補助が match で主採点が match/unexec なら match、補助が match で主採点が mismatch の場合のみ `leaf_custom.ARTIFACT` に根拠のある偽陽性 3 関数 (§7.5) を match に上書き。数え方: 関数 = 23 (closure_stats の leaf ∩ audit_icall の静的間接 call 0)、case = 主採点 23×9 = 207 + 補助 66。

### 7.2 結果 (`work/f2/leaf_report.md`)

| # | block | plugin | VA | 機械語 B | IR 署名 | 主採点 (9 パターン) | 補助 case | **最終** | タグ |
|--:|--:|---|---|--:|---|---|---|---|---|
| 1 | 18953 | EQUO | 0x6cd8a0 | 8 | `i64(i64)` | mismatch 4/6/9 | match 2/2 | **match** (偽陽性確定) | memory_semantics |
| 2 | 18975 | Emphasizer | 0x6bfec0 | 56 | `i64(i64)` | match 6/6/9 | mismatch 1/5 | **mismatch** | fp_flag_unreflected,xmm_arg_drop |
| 3 | 18975 | Emphasizer | 0x6c8fc0 | 63 | `float(i64)` | mismatch 0/6/9 | - | **mismatch** | xmm_arg_drop |
| 4 | 18975 | Emphasizer | 0x6c9b60 | 83 | `float(i64,i64)` | match 2/2/9 | mismatch 2/4 | **mismatch** | fp_flag_unreflected,xmm_arg_drop |
| 5 | 18979 | Frequency Splitter | 0x662fc0 | 15 | `i64(i64)` | match 6/6/9 | - | **match** | - |
| 6 | 18979 | Frequency Splitter | 0x73e640 | 29 | `i64(i64)` | unexec(native_fault_all_patterns) 0/0/9 | match 7/7 | **match** | - |
| 7 | 18979 | Frequency Splitter | 0x73fa20 | 65 | `i64(i64,i64,i64)` | mismatch 4/5/9 | match 7/7 | **match** (偽陽性確定) | wasm_trap |
| 8 | 18979 | Frequency Splitter | 0x73fa70 | 73 | `i64(i64,i32,i64,i64)` | unexec(hang) 0/0/9 | match 7/7 | **match** | - |
| 9 | 18982 | Fruity 7 Band EQ | 0x6b0ef0 | 1554 | `i64(i64,i64)` | mismatch 0/6/9 | - | **mismatch** | arg_drop,spill_slot_deref,xmm_arg_drop |
| 10 | 19005 | Fruity Fast LP | 0x5de300 | 31 | `i64(i64,i64,i64)` | match 1/1/9 | match 4/4 | **match** | - |
| 11 | 19005 | Fruity Fast LP | 0x6c8c90 | 171 | `i64(i64,i64,i64,i64)` | mismatch 0/3/9 | - | **mismatch** | arg_drop,fp_flag_unreflected,spill_slot_deref,xmm_arg_drop |
| 12 | 19006 | Fruity Filter | 0x5de250 | 23 | `i64(i64)` | match 6/6/9 | - | **match** | - |
| 13 | 19006 | Fruity Filter | 0x6cc2e0 | 171 | `i64(i64,i64,i64,i64)` | mismatch 0/3/9 | - | **mismatch** | arg_drop,fp_flag_unreflected,spill_slot_deref,xmm_arg_drop |
| 14 | 19013 | Fruity Free Filter | 0x6ca5c0 | 1554 | `i64(i64,i64)` | mismatch 0/6/9 | - | **mismatch** | arg_drop,spill_slot_deref,xmm_arg_drop |
| 15 | 19059 | Fruity Parametric EQ 2 | 0x6e9440 | 29 | `i64(i64)` | unexec(native_fault_all_patterns) 0/0/9 | match 7/7 | **match** | - |
| 16 | 19059 | Fruity Parametric EQ 2 | 0x6ec2a0 | 65 | `i64(i64,i64,i64)` | mismatch 4/5/9 | match 7/7 | **match** (偽陽性確定) | wasm_trap |
| 17 | 19059 | Fruity Parametric EQ 2 | 0x6ec2f0 | 73 | `i64(i64,i32,i64,i64)` | unexec(hang) 0/0/9 | match 7/7 | **match** | - |
| 18 | 19059 | Fruity Parametric EQ 2 | 0x6f1650 | 28 | `float()` | mismatch 0/9/9 | - | **mismatch** | xmm_arg_drop |
| 19 | 19059 | Fruity Parametric EQ 2 | 0x6f1c40 | 29 | `i64(i64)` | match 6/6/9 | - | **match** | - |
| 20 | 19059 | Fruity Parametric EQ 2 | 0x6f1c60 | 25 | `i64(i64)` | match 6/6/9 | match 5/5 | **match** | - |
| 21 | 19059 | Fruity Parametric EQ 2 | 0x6f2320 | 20 | `i64(i64)` | match 5/5/9 | - | **match** | - |
| 22 | 19059 | Fruity Parametric EQ 2 | 0x6f2370 | 55 | `i64(i64,i64)` | match 6/6/9 | - | **match** | - |
| 23 | 19059 | Fruity Parametric EQ 2 | 0x6f23b0 | 17 | `float(i64,i64)` | unexec(native_fault_all_patterns) 0/0/9 | match 4/4 | **match** | - |

最終判定 23 関数: **一致 15 / 不一致 8 / 実行不能 0**
主採点のみ: 一致 9 / 不一致 9 / 実行不能 5。 case 207: native 完走 93 (equal 56 / diff 35 / wasm_trap 2)、比較不能 114
補助採点 12 関数: case 66 (equal 60 / diff 6 / wasm_trap 0 / 比較不能 0)
最終 mismatch のタグ (該当関数数): xmm_arg_drop 8, fp_flag_unreflected 4, arg_drop 4, spill_slot_deref 4
最終 mismatch のうち callee 無しで差分 (自己欠陥確定): 8
比較に使った equal case 数が 3 未満の match (検出力弱): なし

- 列「主採点」= `verdict equal/native完走/全case`、「補助 case」= `verdict equal/全case`。
- 最終 mismatch の機械語側の所見(全て `xmm_arg_drop`):入力の float を IR が持たない。0x6f1650 は機械語 `movaps xmm0,xmm1` が IR で `__asm_movaps(0)` (xmm1 の代わりに 0) になる。0x6bfec0 は補助 case 5 のうち 4 で不一致、0x6c9b60 は 4 のうち 2 で不一致 (xmm 入力の値次第で結果が変わる経路)。
- 0x6c9b60 (native 完走 2/9 case で一致)・0x6bfec0 (完走 6/9 case で一致) の主採点「一致」は、xmm 入力が `xfill` の固定値のままの 9 パターンでは差が出なかっただけで、補助 case (xmm 入力を振る) で初めて不一致を検出した(差が出なかった理由の詳細解析は未実施)。他の match 関数は §7.3 のネガコンで検出力を確認した。
- **一致 15 関数は全て `arity_x`=0 (機械語が xmm0..3 を入力に読まない)、不一致 8 関数は全て `arity_x`≥2**(liftdiff の機械語静的解析: 命令の read-before-write)。「xmm 入力を取る関数 = 不一致」と完全に分かれる。
- 同一コードの組は同じ結果: 0x73e640=0x6e9440・0x73fa20=0x6ec2a0・0x73fa70=0x6ec2f0・0x6b0ef0=0x6ca5c0・0x6c8c90=0x6cc2e0。

### 7.3 ネガティブコントロール (`nc_leaf.py`)

ベースライン最終 match の関数だけを対象に、block・kind ごとに IR を複製して**対象関数にだけ変異を 1 箇所**入れ、同じ主採点+補助採点で再採点する。

| 変異 (kind) | 一致 15 関数のうち変異箇所がある関数 | 変異後 mismatch (検出) | match のまま (未検出) |
|---|--:|--:|--:|
| `store_drop`: alloca 以外へ書く最初の `store` を削除 (D3 (DEFECTS.md) 型) | 6 | **6** | 0 |
| `load_drop`: alloca 以外から読む最初の整数/float `load` を 0 に置換 (D4 (DEFECTS.md) 型) | 11 | **11** | 0 |
| `offset_shift`: 最初の `add i64 %v, N` (N>0) を N+8 に (フィールド/配列オフセット誤り) | 13 | **13** | 0 |

- 合計 30 変異 / 30 検出。ベースライン (無変異) の同関数は全て match なので、不一致は変異に帰属する。変異箇所の行番号・変異前後は `work/f2/nc/nc_result_*.json`。
- **選択バイアスの開示**: 最初の実行 (補助 case 追加前) は 3 変異が未検出だった (`load_drop`: 0x6bfec0・0x6f1c60、`offset_shift`: 0x6f1c60)。0x6bfec0 は補助 case で不一致に覆り対象外になり、0x6f1c60 (`[this+0x360]==1 && [this+0x361]!=0` 型) は 2 byte を振る補助 case を足して検出した。上表は追加後の再実行値で、**ネガコンを見て case を足した分、検出力の評価としては楽観的**。
- 変異の検出信号は戻り値・書換えメモリの差分 (`ret` / `mem`)。変異ごとの主採点だけの検出か補助 case での検出かは区別していない。

### 7.4 限界・範囲外

- native 参照は Linux 上の機械語直接実行。Windows 実機・FL Studio 内の呼出しとは別 (`PEB/TEB` は ld_core の偽 TEB)。leaf 23 関数は import を呼ばない (強い leaf、`xcheck_leaf.py`)。
- match は「9 パターン + 補助 case で bit 一致」。ネガコンの未検出が示すとおり、真偽フラグ型の関数は random では検出力が弱く補助 case で補った。**全 15 関数について入力空間の網羅は未実施**(一致 15 関数は 8 B〜73 B の小関数。大きい 1554 B の 2 関数 (0x6b0ef0・0x6ca5c0) は不一致)。
- xmm 入力を取る関数は IR 署名に float 引数が無いため、native にだけ `f:<bits>` で渡す補助 case でしか検出できない(0x6bfec0・0x6c9b60 の例)。一致 15 関数は xmm 入力を取らないので、この限界の対象外。float をメモリから読む 0x5de300 (`cvtss2sd` 2 本) と 0x6f23b0 は、補助 case (1.5 / -2.25 / 3 / 1e10 / -0 / NaN / denormal / inf を含む) で全て bit 一致。
- icall 復元 (#514) 後の IR は対象外 (本件の 23 関数は機械語に間接 call が無いので #514 の影響を受けない)。

### 7.5 未解決 (起票先) と DEFECTS.md 行案

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 不一致 8 関数は xmm 引数脱落 (D5)。`lift_ranges.sh` 鎖に ARG pass 未接続。うち 4 は `spill_slot_deref`、4 は `fp_flag_unreflected` | eq-filter の float 入力を取る leaf が全滅。Eff_Render 側も同じ原因を持つ可能性が高い (§3 の入口は間接 call 脱落が先) | **#547 [PLG-F2-4]** (親 #199) |
| liftdiff 比較系の偽陽性 2 類型: (a) 部分上書きされた ptr 入り 8B ブロックを `cmp_mem` が正規化できない (0x6cd8a0)、(b) wasm 1 s 打切りによる偽 `wasm_trap` (0x73fa20・0x6ec2a0) | 主採点だけだと 3 関数が不一致に見える。補助 case と `ARTIFACT` 表で上書きしている | **#548 [LD-11]** (親 #122) |
| 主採点 9 パターンの検出力不足 (真偽フラグ・ptr 鎖・float 入力型の関数で native 全滅/偶然一致) | 補助 case を手で足した。他 block の leaf 拡大時に再発 | #235 ([LD-4], 被覆拡大) にコメント |
| 手順 2〜4 (framework link・Host shim・Render test .flp E2E) と `Eff_Render` の差分 | 出口条件 (差分試験 bit-exact) の残り | 既存 #195 / #196 / #197 完了待ち。#199 に残す |

DEFECTS.md 行案 (PM 判断で追記): `D17 | ours (harness) | 新規 (#515) | 部分上書きされた ptr 入りワードが偽の mem 差分になる | compare.cmp_mem が書込み後の語を ptr と認識できず delta (0x400000) 差を不一致とする | EQUO 0x6cd8a0 (byte 1 を [this+0x35af] へ) 主採点 2/9 case で偽 diff、ptr 無し arena では equal | native−wasm = delta かつ書込み byte 以外同値 | byte 単位比較`、`D18 | ours (harness) | 新規 (#515) | ループ長が引数依存の関数が wasm 1 s 上限で偽 wasm_trap | ld_runner.mjs の vm timeout=1000 ms (native 上限は 10 s) | 0x73fa20 / 0x6ec2a0 (count 下位 32bit ≒ 5.7e8 回) pall | native 完走 + wasm timeout で loop 幅が引数由来 | timeout の target 指定`。

### 7.6 再現

```sh
source tools/shared/env.sh && source tools/plugins/f2/env.sh
bash tools/plugins/f2/f2_step1.sh        # 前提 work/ (§1)。済みなら 51 秒
bash tools/plugins/f2/leaf_diff.sh       # 23 関数の列挙 → target 生成 → liftdiff 主採点 → 補助採点 → 集計 → 別算法検算
python3 tools/plugins/f2/nc_leaf.py      # ネガティブコントロール (kind ごとに並列なら --kinds X --run-only を 3 本 → --reuse)
```

| ファイル | 役割 |
|---|---|
| `leaf_list.py` | 対象 23 関数の列挙 (`--expect 23` で件数を assert) |
| `mk_targets.py` | block ごとの liftdiff target JSON・wasm image・VA 一覧・i128 ABI アダプタ |
| `leaf_diff.sh` | 上記の 1 コマンド駆動 |
| `leaf_custom.py` | 補助採点の手作り case と `ARTIFACT` 表 |
| `leaf_report.py` | 主採点+補助採点の集計 (表・件数) |
| `nc_leaf.py` | ネガティブコントロール (store 脱落 / load 脱落 / オフセット誤り) |
| `xcheck_leaf.py` | 別算法検算 (IR 本文の独立走査 + 機械語の関数別線形 sweep で 23 関数を再導出、同一コード判定) |

### 7.7 実測時間・再現性

測定環境: GitHub Actions runner 4 core (`nproc`=4)、他の重い処理なし。`leaf_diff.sh` = 23 関数の列挙 → target 生成 → 主採点 (block ごとに shard 4) → 補助採点 → 集計 → 別算法検算の全体。

| 実行 | 所要 (秒) | load average (1 分) 開始 → 終了 | `leaf_report.md` md5 先頭 12 桁 |
|---|--:|---|---|
| warm 1 | 129 | 0.27 → 0.31 | 8a33cc049389 |
| warm 2 | 128 | 0.31 → 0.91 | 8a33cc049389 |
| warm 3 | 129 | 0.91 → 0.33 | 8a33cc049389 |
| cold (`tools/liftdiff/work/eqf*` を削除して実行) | 133 | 0.20 → 0.57 | 8a33cc049389 |

- warm 3 回は **128〜129 秒**、cold は **133 秒**。`leaf_report.md` と最終判定 JSON (`functions` の md5) は 3 回とも一致 = 決定的。warm の内訳: liftdiff の wasm ビルドは mtime ガード (`newer(ir, ...)`) で再利用され、`mk_targets.py` が image を毎回再生成する。
- 前提 `f2_step1.sh` を `tools/plugins/work/` 無しで実行した初回 = **6 分 55.8 秒** (`time` 実測、`win_funcs.py` が支配的; load average は Pool(14) で最大 16.3)。work/ があれば §1 のとおり 51 秒。
- `nc_leaf.py`: kind ごとに並列 (3 プロセス) で 55.4 秒 (`store_drop`) / 65.1 秒 (`load_drop`) / 81.3 秒 (`offset_shift`)。
- `find tools/plugins/f2 -type f -size +20M` = 0 件、`git status --porcelain=v1 -- tools/plugins/f2` はコミット前にクリーン。
