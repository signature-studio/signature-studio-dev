# tools/plugins/f2 REPORT — PLG-F2 eq-filter 11 本: 手順 1 (固有閉包 lift) の再現と、差分試験の前提監査 (#199) + icall 復元の接続と回帰ゲート (#514, §7) + leaf 23 関数の関数単位差分 (#515, §8)

> **正本**: `tools/plugins/f2/REPORT.md`。§8 (#515 leaf 23 関数の差分試験)・§9 (#547 xmm 引数復元 pass) の詳細は付録 `tools/plugins/f2/REPORT_APPENDIX.md`。

- 検証起点 commit: **09d9fd8** (origin/main 0f22d9c を基点とする `199-plg-f2-eq-filter-step1`)。数値はすべてこの HEAD から `bash tools/plugins/f2/f2_step1.sh` を 3 回実行して取得。
- 日付: 2026-10-13 / 担当 dir: `tools/plugins/f2/` のみ (生成物は `tools/plugins/work/` = gitignore)
- 既知類型との関係: **(icall §4) D1 = 間接 call/jmp 脱落** が 11 閉包すべてで再現 (§3)。(DEFECTS.md) D15 は x64c stage-0 経路の同種事象で、本件は RetDec 経路 (別経路)。新規類型なし。
- 既知類型との関係 (#2726・§11): **(DEFECTS.md) D5** (xmm 引数脱落) の残件 (no_placeholder・slot_occupied・引数の割当て)。新規類型なし。
- 範囲: issue #199 の手順 1 (固有閉包 lift → `emcc -c`) と、手順 3 (差分試験) の実行可否の判定まで。**§8 (#515) で「機械語にも間接 call 無し」の leaf 23 関数だけ関数単位差分を実施**。**手順 2〜4 と出口条件 (差分試験 bit-exact) は未達** (§5)。

## 0. 結論 (先出し)

1. **手順 1 は再現した**: eq-filter の Delphi 殻 11 block (Frequency Splitter の C++ engine block 18980 は T3 別トラックで対象外) を RetDec + pass 鎖で lift し、**11/11 が `lift_rc=0`・`emcc -c` rc=0**。閉包関数数・バイト数・rc は `PLUGIN_MATRIX.json` の記録と **11/11 一致**。1 コマンド 51 秒 (3 回とも 51 秒)。
2. **ただし `emcc -c` 通過は正しさを意味しない**: 11 閉包の機械語には非 IAT の間接 call が **計 550 site** あるが、lift 後 IR (`p.final.ll`) の間接 call は **0**。入口スロット `Eff_Render` も 11/11 が静的に間接 call を 1〜16 件持つのに IR 側は 0 件 (§3)。RetDec が間接 call を decoder 段で捨てる既知欠陥 ((icall §4) D1) で、`batch_lift.sh` 鎖には `tools/icall` の復元 (binary pre-rewrite) が接続されていない。
3. 例: Fruity Bass Boost の入口 `Eff_Render` (閉包 JSON の名前; 0x6c8cb0) は機械語では `this+0x134` と `[this+0x130]` の float を渡して `call qword ptr [0x729560]` (rip 相対の関数ポインタ変数; kernel 表の変数かは未確認) を呼ぶだけの関数。lift 後 IR (`function_6c8cb0`) は call を失い、`this+308` を返すだけの 9 行になっている (callee が使う引数が消えた結果、仮引数も `%arg1` の 1 本のみ)。
4. よって **この鎖の出力に対する差分試験は、実施しても必ず不一致になる**。差分試験の前提は (a) icall 復元の接続、(b) P0a/P0b/P0c (#195/#196/#197、いずれも open) の統合、の 2 段 (§5)。本 PR では出口条件を満たさないため `Refs #199` で、`Closes` は付けない。**(a) は #514 で接続済み (§7)。§1〜§6 は接続前 (`PLUG_ICALL=0`) の記録で、`f2_step1.sh` が今も再現する。**

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
| `batch_lift.sh` の鎖に `tools/icall` の間接 call 復元 (binary pre-rewrite + `__icall_dispatch`) が無く、550 site 脱落 | 11 本すべて。接続しない限り差分試験は必ず不一致 | **解消 → #514 (§7)**: 接続済み + 回帰ゲート `icall_gate.py` |
| 手順 2〜4: 共有 framework wasm とのリンク・Host shim・kernel 表・`Eff_Render` 差分試験・Render test .flp E2E | 出口条件 (差分試験 bit-exact) | 既存 #195 (P0a) / #196 (P0b) / #197 (P0c) が完了待ち。`framework/REPORT.md` §0 は `TFruityPlug*` 実体生成が未達と記録。本 issue (#199) に残す |
| 23 個の「機械語でも間接 call 無し」leaf の関数単位差分 (native ms_abi と wasm; `lift/t0_balance` 方式の一般化) | 部分的な bit-exact 実績。浮動小数引数には ARG pass 再適用が必要 | **新規子チケット案** `[PLG-F2-3]` (親 #199)。ARG pass は #197 → **#515 で実施 (§8): 一致 15 / 不一致 8。不一致は ARG pass 未接続 (#547)** |
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
| `f2_step2.sh` `icall_gate.py` `icall_gate_waivers.json` `xcheck_rewriter.py` `nc_icall.sh` `matrix_check.py` | #514 (§7): 接続後の再現 / 回帰ゲート / waiver / 別算法検算 / ネガコン / matrix 突合 (step1 と共用) |
| `env.sh` | `FL_WIN64_DIR` と python 依存 (pefile, capstone) の準備 |

## 7. PLG-F2-2 (#514): batch_lift 鎖への icall 復元の接続と回帰ゲート

- 検証起点 commit: **9204aec** (`514-plg-f2-icall-restore`、origin/main bfccd23 基点)。数値は同 HEAD で `bash tools/plugins/f2/f2_step2.sh` を 3 回実行して取得 (REPORT 追記のみの commit が後続)。
- 既知類型との関係: **(icall §4) D1** (間接 call/jmp 脱落) を解消方向。dynamics で **(icall §4) D12** (Delphi landing pad) を 4 site 再現 (§7.4)。新規類型 2 件 (§7.6)。
- 範囲: IR 上の site VA の被覆まで。restored IR (全関数 `i64 f(void)`、BLK 経由) の wasm リンク・実行・native 比較は範囲外 (#199 手順 2〜4、#195/#196/#197)。

### 7.1 結論
1. eq-filter 11 閉包で、機械語の非 IAT 間接 call **550 site のうち 549 site が IR の `call void @__icall_dispatch(i64 <元 site VA>)` に復元**された (#504 は 0)。残る 1 site (18979 の 0x741035) は RetDec が基本ブロックごと除去しており、通常制御フローからは到達不能と推定される (§7.3)。lift_rc 0・`emcc -c` rc 0・matrix 突合 DIFF 0 は 11/11 のまま。
2. 接続は `lift_ranges.sh` の opt-in `PLUG_ICALL=1` (§7.2)。`batch_lift.sh` は既定 ON (`PLUG_ICALL=0` で従来鎖)。`f2_step1.sh` は `PLUG_ICALL=0` を明示し、#504 の数値 (550 → 0、52 秒、DIFF 0) をそのまま再現する。
3. 接続中に `tools/icall/icall_rewrite.py` の欠陥を 1 件見つけて直した (§7.6 N1): 関数をちょうど連続配置すると RetDec が隣接 range を併合し、後続関数の `define` が落ちる (11 閉包中 4 block で 5 関数)。
4. 回帰ゲート `icall_gate.py` は、機械語の site VA を IR の dispatch site VA が全て覆わないと exit 1。ネガコン 5 件 (復元を外す・site 1 本削除・site VA 不明・偽 waiver・waiver 無し) が全て FAIL (§7.5)。
5. 同じゲートを #506 の dynamics 7 閉包に適用した: lift は 7/7 完走だが **4 site が FAIL** (Maximus・Soundgoodizer の landing pad)。ゲートの「適用できる形」は確認でき、4 site は #529 に起票。

### 7.2 接続方式 (tools/icall の手順 `integration/README.md` §1 と同じ 3 段を `lift_ranges.sh` に入れた)
| 段 | 処理 | 出力 (`work/batch/<block>/`) |
|---|---|---|
| pre | `icall_rewrite.py --pe PE --funcs <閉包 ranges>`: 間接 call/jmp を memory-ABI + 共有 stub に展開、閉包内 ABI を BLK 経由に仮想化、`[reg]` 補償 (D7)、comis | `p.icall.dll` `p.icall.map.json` |
| decode | RetDec を **書換え PE** に、`map.json.ranges` + stub 2 本の range で実行 (decode-only) | `p.drc.ll` |
| post | `ir_icall_restore.py`: new→元 VA、stub 呼出し → `call void @__icall_dispatch(i64 <元 site VA>)` / `__icall_comis()` | `p.drc.restored.ll` → 以降は従来の pass 鎖 (`ir_normalize` …`m11_simd2`) |

- `PLUG_IMG_HI` は元 PE から算出 (書換え PE の `.icall` section は含めない)。BLK は元 image の外の絶対 VA (`map.json` の `blk`、例 18979 = 0x944000) で `m11_passes` の VA shift 対象外。runtime 側 (`rt/icall_rt.c` の `ICALL_BLK` と `__icall_dispatch` の VA→関数表) の結合は手順 2〜4 の課題。
- 例: Bass Boost の入口 `Eff_Render` (`function_6c8cb0`) は §0.3 の 9 行 (`this+308` を返すだけ) から 68 行になり、`call void @__icall_dispatch(i64 7113932)` (= 0x6c8ccc、機械語の `call qword ptr [0x729560]` の site) を持つ。シグネチャは `i64 f(void)` (引数は BLK 経由)。
- `status.csv` に列 `icall` `dispatch_calls` を追加 (末尾追加のみ。既存の列順・#506 の `dynamics_e2e.sh` の添字参照は不変)。

### 7.3 結果 (`f2_step2.sh` 3 回目の `work/batch/status.csv` と `work/f2/gate.json`)
`機械語 site` = 閉包 ranges の capstone 線形 sweep による非 IAT `call` の VA 数 (`icall_gate.py`)。`IR dispatch` = `p.final.ll` の `call void @__icall_dispatch(i64 N)` 行数。`waived` = 後述。`defines` は閉包関数数と全 block で一致 (`closure_stats.py` の assert)。

| block | plugin | 閉包関数 | defines | 機械語 site | IR dispatch | waived | lift_rc | emcc -c rc | lift 秒 |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 18953 | EQUO | 39 | 39 | 82 | 82 | 0 | 0 | 0 | 6 |
| 18975 | Emphasizer | 38 | 38 | 39 | 39 | 0 | 0 | 0 | 6 |
| 18979 | Frequency Splitter (Delphi 殻) | 45 | 45 | 121 | 120 | 1 | 0 | 0 | 8 |
| 18982 | Fruity 7 Band EQ | 14 | 14 | 14 | 14 | 0 | 0 | 0 | 4 |
| 18984 | Fruity Bass Boost | 11 | 11 | 13 | 13 | 0 | 0 | 0 | 4 |
| 19005 | Fruity Fast LP | 14 | 14 | 15 | 15 | 0 | 0 | 0 | 4 |
| 19006 | Fruity Filter | 13 | 13 | 17 | 17 | 0 | 0 | 0 | 5 |
| 19013 | Fruity Free Filter | 14 | 14 | 17 | 17 | 0 | 0 | 0 | 4 |
| 19058 | Fruity Parametric EQ | 17 | 17 | 21 | 21 | 0 | 0 | 0 | 5 |
| 19059 | Fruity Parametric EQ 2 | 73 | 73 | 137 | 137 | 0 | 0 | 0 | 11 |
| 19145 | Low Lifter | 28 | 28 | 74 | 74 | 0 | 0 | 0 | 6 |
| 合計 | | 306 | 306 | **550** | **549** | 1 | | | 63 (復元なし = §2 は 35) |

- IR の native 間接 call (callee が `%reg`) は 11 block とも 0、機械語の `jmp` を stub 化した dispatch (extra) も 0。dispatch は全て `call` 由来。
- **waived 1 件 = 18979 の `call [rdi+0x1f0]` (0x741035, `Eff_Render` ではなく 0x740e30 の case 分岐)**。RetDec は 0x741007-0x74103b のブロックを除去している (`p.drc.restored.ll` に `insn.addr` が 0x741035 の命令が 0 件)。機械語を手で追うと到達不能と推定 (手作業の追跡で、機械検証ではない): 0x740e6a で `eax=[rbp+0x40]; cmp eax,0xe; jge` により v<14、0x740ee9 `cmp eax,5; jg` で v≥6、0x740f15 `sub eax,6; je` で v≥7、0x740f1c `sub eax,8` で v-14 は -7…-1 (符号なし 6 以上) となり 0x740f22 `jae 0x7411dd` が必ず成立するので 0x740f28 `jmp 0x741007` は実行されない (Delphi の `case` に残った 14〜19 ラベルの死コード; 前提は [rbp+0x40] が 0x740e6a〜0x740ee6 の間で書き換わらないこと)。同関数への他経路は、0x740e30〜0x741200 の分岐先走査で `jmp 0x741007` 1 本のみ。
- 5 関数の脱落 (§7.6 N1) の修正前の初回実行: 18975 define 37/38・18982 13/14・19013 13/14・19145 26/28 (`closure_stats.py` の assert で検出)。これらの欠落関数は間接 call を持たず、ゲートの site 突合だけでは見えない → define 数突合 (`f2_step2.sh` の `closure_stats.py`) も回帰条件に含めた。

### 7.4 回帰ゲート `icall_gate.py` と dynamics (#506) への適用
- 機械語側 (rewriter/`audit_icall.py` と別算法): 閉包 ranges を capstone で線形 sweep し、IAT 以外の間接 `call` の VA 集合。IR 側: `__icall_dispatch(i64 VA)` の VA 集合と、callee が `%reg` の call 数。
- FAIL (exit 1) 条件: **F1** 機械語 site VA が IR に無い (waiver が無い) / **F2** IR の間接 call 総数 + waived < 機械語 site 数 / **F3** site VA 不明 (`i64 0`) の dispatch / **F4** waiver 無効。waiver は `icall_gate_waivers.json` の (block, site, reason) で、**raw IR (`p.drc.restored.ll`) に当該 VA の `insn.addr` を持つ命令が 1 つも無い**ときだけ有効 (call だけ落ちた場合は BLK store 列が元 VA 付きで残るので waiver は通らない)。
- 使い方は閉包 ranges と IR の置き場が `batch_lift.sh` と同じなら block 番号だけ: `python3 tools/plugins/f2/icall_gate.py <block>...`。任意の PE/IR は `--pe --ranges --ir [--raw-ir]`。
- **dynamics 7 block** (19021 18990 19148 19245 18974 19047 19251、#506 の `dynamics_e2e.sh` と同じ一覧) を同じ `batch_lift.sh` で 61 秒 (7 本逐次、開始 load average 0.25) lift: 7/7 が lift_rc 0・`emcc -c` rc 0。ゲート: 機械語 640 site に対し IR dispatch 636、**FAIL 2 block**: Maximus (19148) 230 → 228、Soundgoodizer (19245) 157 → 155。欠けた 4 site は全て `call qword ptr [rbx - 0x20]` (0x780d84・0x78a727・0x77a5d4・0x783f77)、raw IR に命令が無い = **(icall §4) D12 landing pad** (到達不能コードではなく、例外巻き戻し時に実行され得る仮想 dtor 呼出し)。(初回測定 (waiver 無し) の記録。現在の扱いは §7.7 = waiver 方式 (b) で処理し、gate PASS。) 残る 5 block は PASS。別算法 (rewriter の dispatch 化 site と線形 sweep) は 640 = 640 で集合一致。起票: **#529**。

### 7.5 検証 (HEAD 9204aec、4 core Actions runner、`f2_step2.sh`)
| 項目 | 実測 |
|---|---|
| 前提 work/ | `win_scan.py` 9 秒、`win_funcs.py` **518 秒** (初回 1 回のみ、終了時 load average 14.42 / 13.47 / 7.23)。`mk_blockmap.py` 0 秒 |
| `f2_step2.sh` ×3 | **88 / 89 / 88 秒** (逐次、開始時 1 分 load average 0.71 / 0.90 / 0.98)。3 回とも exit 0、「回帰ゲート」以降の出力は md5 一致 (b63db372…) |
| `f2_step1.sh` (`PLUG_ICALL=0`) | 52 秒、exit 0、matrix DIFF 0、`550 → IR 間接 call 0`、leaf 55 / 23 (#504 と同一) |
| `nc_f2.sh` (#504 のネガコン 3 件) | 3/3 DETECTED (復元周りの変更後も有効) |
| 別算法 `xcheck_rewriter.py` | 機械語の線形 sweep と rewriter(recursive descent) の dispatch 化 site (mn=call) の VA 集合が 11/11 block で一致、合計 550 = 550 (dynamics 7 block は 640 = 640) |
| 別算法 (IR 側) | `batch_lift.sh` が `grep -c` で `status.csv` に出す `dispatch_calls` の合計 549 = ゲートの `ir_dispatch_calls` 549 |
| `tools/icall/tests/test_icall.py` | unit 部 PASS (0 failed)。pe 部は OTT DLL が無く SKIP → #530 |

ネガティブコントロール (`bash tools/plugins/f2/nc_icall.sh`、9.2 秒、Bass Boost 18984 の 13 site、全て期待どおり):
| 検査 | 壊し方 | 結果 |
|---|---|---|
| 正常 | — | rc 0、13 / 13 |
| NC1 | `PLUG_ICALL=0` で同じ閉包を lift (復元を外す) | rc 1、IR dispatch 0 → F1 missing=13 + F2 |
| NC2 | 正常 IR から `__icall_dispatch` 呼出しを 1 行削除 | rc 1、12 / 13 → F1 missing=1 + F2 |
| NC3 | dispatch の site VA を 0 に変更 | rc 1、F3 unattributed=1 + F1 |
| NC4 | NC2 で落とした site に偽 waiver | rc 1、F4 (raw IR に当該 VA の命令が残る) |
| NC5 | 18979 の正当な waiver を外す | rc 1、F1 missing=1 (120 / 121) |

### 7.6 新規欠陥類型の行案 (DEFECTS.md の直接編集は PM 判断)
| 仮 ID | 層 | 症状 | 根本原因 | 検出信号 | 修復 |
|---|---|---|---|---|---|
| N1 | ours (icall_rewrite) | 後続関数の `define` が 1 個落ちる (eq-filter 4 block で 5 関数)。dispatch は残るので site 突合では見えない | 関数終端が 16 の倍数だと次の関数と連続配置になり、RetDec の `--select-ranges` が `[a,b)+[b,c)` を 1 関数に併合する (`p.drc.config.json` の `function_7b1cd0` の `endAddr` が次関数の終端) | `define` 数 ≠ 閉包関数数 (`closure_stats.py` の assert) | `icall_rewrite.py` の `next_slot()`: 連続になる場合だけ 16 byte 空ける (連続しない配置はバイト一致) |
| N2 | fe (RetDec opt) | 機械語の間接 call site が IR に無い。ただし正当な場合がある | RetDec が基本ブロックを除去 (18979 0x741035。通常制御フローから到達不能と推定)。call だけが落ちたのではなくブロックごと | raw IR に当該 VA の `insn.addr` 命令が 0 件 (call 落ちなら BLK store 列が残る) | 修復不要。waiver (理由必須) で明示し、ゲートが機械検証 |

### 7.7 #529 (PLG-F3-2): dynamics 4 site の D12 landing pad を waiver 方式 (b) で処理

- **方式 (a) を採らなかった理由**: `tools/icall/landing` は FLEngine の 879 site 用の別パイプライン (`lift_pad.py`・`verify_pads.py`)。plugin PE の pad を batch 鎖に載せるには scope 抽出・IR 接続・`__lp_icall` 配線が要るため本 issue の範囲を超える。
- **方式 (b) の根拠 (機械検証)**: `xdata_scope.py` で 19148・19245 の scope table を抽出。4 site はいずれも `kind=0` の handler 領域 (`cmp byte [rbp+0x58],0` 〜 reraise `call`) の内側で、直前の `jmp` で領域を飛び越す。領域内への分岐は同関数内 0 件。ゲートの F4 (raw IR に当該 VA の命令無し) で機械検証。

| site | 関数 | scope 領域 (RVA) | jump target |
|---|---|---|---|
| 0x780d84 (19148) | 0x780d00 | [0x380d6a,0x380d96) | 0x380db0 |
| 0x78a727 (19148) | 0x78a660 | [0x38a70d,0x38a739) | 0x38a750 |
| 0x77a5d4 (19245) | 0x77a550 | [0x37a5ba,0x37a5e6) | 0x37a600 |
| 0x783f77 (19245) | 0x783eb0 | [0x383f5d,0x383f89) | 0x383fa0 |

- **実測 (base 97f28539 + waiver 追加)**: `batch_lift.sh` 7 本 68 秒 (load 開始時 0.25 台、7/7 lift_rc 0・`emcc -c` rc 0)。`icall_gate.py` 7 本: **PASS (exit 0)**、waived 4 (19148: 2, 19245: 2)、F1 未被覆 0。
- **ネガコン**: waiver 無し (`--waivers` で空配列) → **FAIL (exit 1)、F1 missing=2 (19148)・missing=2 (19245)**。`attributed()` は raw IR に実在する VA (0x40ad30) を検出し、waiver の 4 site は raw IR に 0 件 (F4 不発 = waiver 有効)。
- **残る前提 (未検証)**: waiver の reason は「通常制御フローからは到達不能と推定」まで。根拠は scope table の構造と raw IR に命令が無いことで、到達不能の証明ではない。「DSP 経路に例外を投げる箇所が無い」は未検証。例外が DSP 内で送出されれば pad が実行され、間接 call が翻訳されないまま動く (silent miscompile)。Delphi では `_RaiseExcept` 系 RTL helper や、整数除算 0 などのハードウェア例外 (SEH 経由で unwind) が pad を起動し得る。IAT 0 件の確認では不足。追跡 #529。

### 7.7b #529 追補: 例外経路の一次スキャン

- 結論: 直接 call の範囲では W の unwind 元になる trap は閉包内に無い。ただし未確認 3 項目が残り「無い」の証明ではない。実測表・判定・再現は付録 `REPORT_APPENDIX_529.md` §1。

### 7.8 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| waiver 4 site の「DSP 経路に例外を投げる箇所が無い」の確認 (7.7b の 1〜3) | 未検証。W の間接 call と frontier 先の trap/raise が残る。例外が DSP 内で送出されると pad が実行され、waiver の前提が崩れる | #529 (PR は Refs #529。Closes は付けない) |

### 7.9 未解決 (§7.7 から継続)
未解決 4 件 (#530・#195〜#197・#515・18979 waiver の推定) の表は付録 `REPORT_APPENDIX_529.md` §2。

## 8. PLG-F2-3 (#515): leaf 23 関数の関数単位差分試験 → 付録

結論: 対象 23 関数で **一致 15 / 不一致 8 / 実行不能 0**。不一致 8 は全て (DEFECTS.md) D5 (xmm 引数脱落、#547 の pass で未解消)。表・ARTIFACT 根拠・ネガコン・限界・再現・実測時間は [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §8。

## 9. PLG-F2-4 (#547): xmm 引数復元 pass (opt-in `PLUG_XMMARG=1`) → 付録

受入条件 1 は**未達** (不一致 8 のまま。pass は opt-in `PLUG_XMMARG=1`・既定 OFF)。HEAD `2f77ace` での実測 (6 block lift・`leaf_diff.sh` n=3・`nc_leaf.py`) は一致 15 / 不一致 8 / 実行不能 0 で、接続前と同一。分類器 (`xmm_arg_drop`) の変更は liftdiff 全体に効くが、既存 results (`tools/liftdiff/results/*`・`tools/flelift/boot/results/mixed_summary.md`) は旧分類のまま・再分類は未実施。実測・未解決は [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §9。

## 10. PLG-F2-5 (#613): #232 (LD-1) `ldfix` の接続 (opt-in `PLUG_LDFIX=1`) → 付録
受入条件 1 は**未達** (現行 26f90ada の V1 は不一致 8)。受入条件 3 は**未達に改める**: #613 の B arm (`PLUG_LDFIX=1`) で一致に変わったとした 0x6b0ef0・0x6ca5c0 は、現行の V1 (`PLUG_XMMARG=1 PLUG_LDFIX=1`、測定 commit 26f90ada) で再現せず、両方とも不一致 (最終判定 15/8/0)。LDFIX 単独の寄与は現行では未測定で、#613 の A/B 対照 (17/6) が現行で再現しない原因は未確定。詳細は [`REPORT_APPENDIX_613.md`](REPORT_APPENDIX_613.md) 末尾の追補 (#2726)。
## 10.1 (#871 部分) 0x6f1650 の切り分け → 付録
0x6f1650 (19059) の不一致は image 配置 (RVA) と IR 絶対 VA 定数のずれが原因と確定。修正は未実施で #871 に残す。詳細は [`REPORT_APPENDIX_871.md`](REPORT_APPENDIX_871.md)。

## 11. PLG-F2-8 (#2726): 残不一致 6 関数の原因切り分けと #547 ablation の再定義 → 付録

- 結論: arm V0 (`PLUG_XMMARG=0 PLUG_LDFIX=0`) と V1 (`PLUG_XMMARG=1 PLUG_LDFIX=1`) で一致 15 / 不一致 8 / 実行不能 0 が同一。V1 は XMMARG と LDFIX を同時に切り替えた arm で、両者の寄与は分離していない。V0 → V1 (合成) で最終判定が変わった関数は 0 件 (合成 arm の事実で、LDFIX 単独の効果はここからは言えない)。一次採点が変わったのは 0x6b0ef0・0x6ca5c0 (0/8 → 7/8、不一致のまま)。測定 commit `26f90ada`。
- 残 6 関数の原因 (1 行ずつ):

| VA (block) | 原因 | 根拠 |
|---|---|---|
| 0x6bfec0 (18975)・0x6c9b60 (18975) | no_placeholder | 接続できる placeholder が無い (`skipped`=`no_placeholder`) |
| 0x6c8c90 (19005)・0x6cc2e0 (19006) | slot_occupied | 位置 3 を整数 `%arg4` で宣言済み (`slot_occupied(xmm3, IR params=4)`) |
| 0x6b0ef0 (18982)・0x6ca5c0 (19013) | 引数の割当て | 復元は xmm2 のみ。xmm1・xmm3 は entry の `je 0x6b0f03` → 0x6b117f の経路で未定義のまま読まれる (k80abi の線形走査が見落とす) |

- 0x6f1650 (19059): 署名のみ変化 (両方 match 11/11/11)。不一致の原因は #871 の image 配置で、pass とは無関係。
- 修復は未適用 (子 issue へ)。数値・再現は [`REPORT_APPENDIX_2726.md`](REPORT_APPENDIX_2726.md)。
