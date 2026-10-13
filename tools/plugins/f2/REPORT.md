# tools/plugins/f2 REPORT — PLG-F2 eq-filter 11 本: 手順 1 (固有閉包 lift) の再現と、差分試験の前提監査 (#199)

- 検証起点 commit: **09d9fd8** (origin/main 0f22d9c を基点とする `199-plg-f2-eq-filter-step1`)。数値はすべてこの HEAD から `bash tools/plugins/f2/f2_step1.sh` を 3 回実行して取得。
- 日付: 2026-10-13 / 担当 dir: `tools/plugins/f2/` のみ (生成物は `tools/plugins/work/` = gitignore)
- 既知類型との関係: **(icall §4) D1 = 間接 call/jmp 脱落** が 11 閉包すべてで再現 (§3)。(DEFECTS.md) D15 は x64c stage-0 経路の同種事象で、本件は RetDec 経路 (別経路)。新規類型なし。
- 範囲: issue #199 の手順 1 (固有閉包 lift → `emcc -c`) と、手順 3 (差分試験) の実行可否の判定まで。**手順 2〜4 と出口条件 (差分試験 bit-exact) は未達** (§5)。

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
| 23 個の「機械語でも間接 call 無し」leaf の関数単位差分 (native ms_abi と wasm; `lift/t0_balance` 方式の一般化) | 部分的な bit-exact 実績。浮動小数引数には ARG pass 再適用が必要 | **新規子チケット案** `[PLG-F2-3]` (親 #199)。ARG pass は #197 |
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
