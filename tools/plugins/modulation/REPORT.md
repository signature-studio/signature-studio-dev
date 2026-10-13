# tools/plugins/modulation/REPORT.md — PLG-F5 (#202) modulation 8 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/modulation/` のみ / 検証起点 commit: §6 に記載 (コミット済み HEAD)
- 再現: `bash tools/plugins/modulation/modulation_e2e.sh` (判定 + 実測) / `bash tools/plugins/modulation/modulation_nega.sh` (ネガティブコントロール) / `python3 tools/plugins/modulation/report_tables.py` (§1〜§4 の表)
- 素材: `fl-win64` / `toolchain-retdec` (`/opt/retdec`) / `toolchain-emsdk` (`/opt/emsdk`) (`docs/WORKFLOW.md` §11)。環境は `modulation/env.sh`
- 方法の出典: PR #506 (PLG-F3 dynamics、未マージ) の `dynamics_e2e.sh` / `matrix_check.py` / `ids_crosscheck.py` と、PR #504 (PLG-F2、マージ済) の間接 call 監査。#506 の reviewer 指摘 (§5) は最初から回避した
- 既知類型との関係: **(icall §4) D1 = 間接 call/jmp 脱落が 8/8 本で再現** (§3)。(DEFECTS.md) D1〜D16 に該当する新規類型なし。
  engine の `emcc -c` 失敗 2 類型 (§4) は emcc が拒否する loud な IR 型エラーで silent miscompile ではない (差分試験は未実施)

## 0. 結論 (先出し)

1. **#202 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** PLG-P0a #195 / P0b #196 / P0c #197 が OPEN で、
   Eff_Render 単位の native ⟷ wasm 差分 harness も repo に無い。さらに下記 2 の欠陥が未修復のため、現状の鎖の出力は差分試験で必ず不一致になると推定する (本 run では差分試験をしていない)。
   → PR は **`Refs #202`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は殻 8/8 本で通った** (§1)。8 本すべてで RetDec+pass 鎖が完走 (lift_rc 0)、`emcc -c` rc 0、`x86_fp80` 関数 0、未実装 `__asm_*` helper 宣言 0、
   final.ll の define 数 = 閉包関数数。合計 **207 関数 / 92,917 B**。閉包 6 項目 × 8 本 + matrix に記録のある batch 4 項目 × 5 本 = **68/68 項目**が `PLUGIN_MATRIX.json` と一致
   (T0 3 本・T1 2 本は matrix の記録を再現、**T2 の殻 3 本 (Frequency Shifter / Vintage Chorus / Vintage Phaser) は今回初測定**)。
3. **ただし `emcc -c` の通過は正しさを意味しない。** 8 閉包の機械語には非 IAT の間接 call が **計 240 site** (別算法の線形 sweep も 240) あるが、lift 後 IR (`p.final.ll`) の間接 call は **0** (§3)。
   入口スロット (`Dispatcher` / `SaveRestoreState` / `ProcessParam` / `Eff_Render`) の間接 call も全て IR 側 0。PR #504 (eq-filter 11 本、550 → 0) と同じ欠陥で、#514 が追跡している。
4. **host 呼出面は P0b の応答表で覆える** (§2)。閉包が即値 ID で発行する Dispatcher ID は {2, 30, 36, 50} の 4 種 (slot0 の即値 ID site は計 14、独立走査も同一)。4 種とも `hostshim/hs_ids.json` の 35 ID に含まれ、動的 ID は 0 site。
5. **SIMD kernel 表への依存は Fruity Flangus だけ** (閉包内 3 site / 3 変数)。他 7 本は閉包にも frontier にも 0 site。Frequency Shifter と Hyper Chorus は DLL 固有関数走査で kernel 呼出 5 site を持つが、
   その関数 4 本ずつはどちらも閉包・frontier の外で、DLL 内のどこからも参照されない (§3)。
6. **C++ engine 4 本 (全て MSVC) は RetDec まで通るが `emcc -c` は 0/4 本** (§4)。4 本とも同じ 2 類型の IR 型エラーが連鎖し (PR #506 の Transient engine と同型)、VEX の未実装 helper が 53〜77 (distinct)、`.pdata` で define が無い range が各 2 件ある。
   殻の DSP 本体は engine 側にあるため、**殻 8/8 の通過は「8 本が wasm 化できる」を意味しない**。T1 の Hyper Chorus の見積りにこの engine の工数が含まれるかは未確認。

## 1. 閉包 lift 結果 (Delphi 殻 8 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessEvent / ProcessParam / Eff_Render) から `call/jmp rel32` で到達する、
framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。vcall / ptr = 間接呼出 site 数。iat = IAT 経由 Win32 呼出 site。
define = `p.final.ll` の `^define` 数。f80 = `x86_fp80` を含む define 数。未実装 helper = `p.simd.log` の `unimplemented N`。`emcc -c` 列は `emcc -c -O0 -msimd128` の終了コード。lift 秒は 3 回の min–max。

| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | define | f80 | 未実装 helper | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Frequency Shifter | 18978 | T2 | 29 / 15,659 | 75 / 16,254 | 34 | 6 | 0 | 29 | 0 | 0 | 0 | 3–4 |
| Fruity Chorus | 18989 | T1 | 17 / 10,859 | 41 / 4,409 | 12 | 3 | 1 | 17 | 0 | 0 | 0 | 3 |
| Fruity Flanger | 19007 | T0 | 25 / 5,846 | 37 / 3,979 | 8 | 2 | 0 | 25 | 0 | 0 | 0 | 2–3 |
| Fruity Flangus | 19009 | T0 | 19 / 6,823 | 39 / 5,613 | 10 | 13 | 0 | 19 | 0 | 0 | 0 | 2–3 |
| Fruity Phaser | 19066 | T0 | 21 / 6,016 | 33 / 3,889 | 9 | 2 | 0 | 21 | 0 | 0 | 0 | 2–3 |
| Hyper Chorus | 19144 | T1 | 28 / 11,440 | 72 / 18,110 | 25 | 3 | 0 | 28 | 0 | 0 | 0 | 3–4 |
| Vintage Chorus | 19265 | T2 | 28 / 14,074 | 66 / 12,800 | 48 | 5 | 0 | 28 | 0 | 0 | 0 | 3 |
| Vintage Phaser | 19267 | T2 | 40 / 22,200 | 77 / 17,213 | 52 | 7 | 0 | 40 | 0 | 0 | 0 | 3–4 |
| 計 | | | **207 / 92,917** | | | | | 207 | 0 | 0 | 0 | 23–25 |

- 通過 ≠ 正しさ (batch_plan §4)。正しさは差分試験でしか示せず、§3 の欠陥が残る間は差分試験の前提も満たさない。
- 殻の直接 Win32 API (`PLUGIN_MATRIX.json` の `win_direct_api`): Frequency Shifter = dynload 2 / file_io 4、Hyper Chorus = threads 2 / dynload 2 / file_io 4、Vintage Chorus・Vintage Phaser = dynload 2 / file_io 4。他 4 本は 0。
  dynload は engine DLL の動的ロードに使われると推定する (未解析、§4)。
- 事前推定 (issue 記載: 16.5 人日、PLUGIN_MATRIX の Tier 規則推定) と実測の差: 本 run は手順 1 の到達性だけを測っており、工数は測っていない。

## 2. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。slot0 = Dispatcher。

| プラグイン | host call site 計 | slot0 (Dispatcher) 即値 ID (site 数) | 動的 ID | 他 slot (offset: site) | `hs_ids.json` に無い ID |
|---|--:|---|--:|---|---|
| Frequency Shifter | 6 | 2 (1) / 36 (1) / 50 (1) | 0 | 0x100: 1, 0x108: 1, 0x120: 1 | なし |
| Fruity Chorus | 1 | 2 (1) | 0 | — | なし |
| Fruity Flanger | 1 | 2 (1) | 0 | — | なし |
| Fruity Flangus | 3 | 2 (1) | 0 | 0x100: 1, 0x108: 1 | なし |
| Fruity Phaser | 1 | 2 (1) | 0 | — | なし |
| Hyper Chorus | 3 | 2 (1) | 0 | 0x100: 1, 0x108: 1 | なし |
| Vintage Chorus | 2 | 2 (1) / 36 (1) | 0 | — | なし |
| Vintage Phaser | 4 | 2 (2) / 30 (1) / 36 (1) | 0 | — | なし |

- **別算法の検算** (`ids_crosscheck.py`、taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う): 8/8 本で taint 版の ID 件数を取りこぼしなく再現し、独立走査側にだけ現れる ID も 0 だった (PR #506 の dynamics で見つかった ID 59 のような差は本 8 本には無い)。
- 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。0x120 (Frequency Shifter 1 site) は P0b では fail-soft + 呼出記録のみ (意味未解析)。

## 3. SIMD kernel 表と間接 call 脱落

### 3.1 SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` で call site の所在関数を閉包 ranges / frontier に分類。kernel 番号は Balance (block 18983) の VA に正規化済み。

| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査の site / kernel 種 |
|---|--:|---|--:|---|
| Frequency Shifter | 0 | — | 0 | 27 / 5 |
| Fruity Chorus | 0 | — | 0 | 22 / 1 |
| Fruity Flanger | 0 | — | 0 | 22 / 1 |
| Fruity Flangus | 3 | 0x5de800 (1), 0x5de9d0 (1), 0x5df700 (1) | 0 | 25 / 4 |
| Fruity Phaser | 0 | — | 0 | 22 / 1 |
| Hyper Chorus | 0 | — | 0 | 27 / 5 |
| Vintage Chorus | 0 | — | 0 | 22 / 1 |
| Vintage Phaser | 0 | — | 0 | 22 / 1 |

- 22 site (0x5de390) は 8 本すべてに共通し、閉包にも frontier にも属さない (PR #506 の 7 本と同じ。framework 側の深い関数にあると推定、未確認)。
- Flangus の 3 変数 (var 0x715490 / 0x715498 / 0x7154d8) は、それぞれ 2 実装 (0x5de800|0x5de870、0x5de9d0|0x5dea40、0x5df700|0x5df770) のどちらかを選ぶ。`kernel_table.json` で 0x5dea40 は x87 命令を含む。
  `p0c/REPORT.md` に当該 6 アドレスの記載は無い (grep 0 件)。差分試験の有無は未確認 (§7)。
- Frequency Shifter と Hyper Chorus の 5 site / 4 kernel (0x5decb0 / 0x5df750 ×2 / 0x5de620 / 0x5df270) は、閉包・frontier のどちらにも属さない DLL 固有関数 4 本の中にある
  (Frequency Shifter: 0x5e67b0 / 0x5e72c0 / 0x5e8020 / 0x6d6f30、Hyper Chorus: 0x5e6430 / 0x5e6f40 / 0x5e7ca0 / 0x6ebcd0。両 DLL で関数サイズが 533 / 1,193 / 470 / 1,316 B と対応して同一)。
  この 8 関数は DLL 内のどこからも参照されない: `call/jmp rel32` の呼出元 0、RIP 相対メモリ operand・即値による参照 0、8 バイト境界の VA ポインタ 0、`.pdata` 以外の 4 バイト RVA 0 (確認スクリプトは本書の外のワンショットで、`modulation/` には未収録)。
  よって閉包の取りこぼしではなく未使用コードの可能性が高いと推定する (計算で生成したアドレス経由の呼出は排除できない)。2 DLL にしか無いため framework 判定 (13 DLL 以上) から外れた共通コードと推定する。

### 3.2 間接 call 脱落 (`icall_check.py`)

定義: 静的 site = 閉包 ranges の非 IAT 間接 call 命令数 (`tools/icall/audit_icall.py`、`call [reg+disp]`・`call [rip+var]` ほか)。IR = `p.final.ll` で callee が `@name` でない call の数。
別算法 = 閉包 ranges を capstone で線形 sweep して数えた非 IAT 間接 call (PR #504 の `xcheck_icall.py` と同じ方法)。`p.final.ll` は `insn.addr` を持たないため site 単位の dropped / 直接化の区別はできず、件数比較のみ。

| プラグイン | block | 静的 site | 別算法 | call あり関数 | IR の間接 call | 入口スロットの静的 → IR |
|---|--:|--:|--:|--:|--:|---|
| Frequency Shifter | 18978 | 40 | 40 | 16 | 0 | Dispatcher 2→0, SaveRestoreState 12→0, ProcessParam 2→0, Eff_Render 4→0 |
| Fruity Chorus | 18989 | 16 | 16 | 7 | 0 | DestroyObject 2→0, Dispatcher 1→0, SaveRestoreState 6→0, ProcessParam 2→0 |
| Fruity Flanger | 19007 | 10 | 10 | 4 | 0 | Dispatcher 1→0, SaveRestoreState 6→0, ProcessParam 2→0 |
| Fruity Flangus | 19009 | 23 | 23 | 10 | 0 | Dispatcher 1→0, SaveRestoreState 4→0, ProcessParam 2→0, Eff_Render 1→0 |
| Fruity Phaser | 19066 | 11 | 11 | 5 | 0 | Dispatcher 1→0, SaveRestoreState 6→0, ProcessParam 2→0 |
| Hyper Chorus | 19144 | 28 | 28 | 11 | 0 | Dispatcher 2→0, SaveRestoreState 9→0, ProcessParam 5→0, Eff_Render 1→0 |
| Vintage Chorus | 19265 | 53 | 53 | 13 | 0 | Dispatcher 10→0, SaveRestoreState 6→0, ProcessEvent 1→0, ProcessParam 3→0, Eff_Render 3→0 |
| Vintage Phaser | 19267 | 59 | 59 | 15 | 0 | Dispatcher 10→0, SaveRestoreState 10→0, ProcessEvent 1→0, ProcessParam 4→0, Eff_Render 3→0 |
| 計 | | **240** | **240** | | **0** | |

- 脱落ありの殻 8/8 本。`batch_lift.sh` の鎖に `tools/icall` の復元が接続されていない (#514、親 #199)。この測定は e2e の判定に含めない (既知で未修復のため。含めると常に FAIL になる)。含めたときに FAIL することは NC7-1 で確認した (§5)。
- 静的 site 数は `plugin_closure.py` の vcall + ptr と一致する (例: Frequency Shifter 34 + 6 = 40、Flanger 8 + 2 = 10)。

## 4. T2/T1: C++ engine DLL 4 本

4 本とも MSVC (VS2019) の C++ DLL で、import は KERNEL32 のみ。殻との結合方式 (LoadLibrary 経路) は未解析。Vintage Chorus / Phaser の engine は `VSTPluginMain` / `main` を export する (VST2 engine。issue 本文の「engine.vst ラップ」に対応)。

| プラグイン | engine block | サイズ B | `.text` B | `.pdata` 関数 / B | export | KERNEL32 import |
|---|--:|--:|--:|--:|---|--:|
| Frequency Shifter | 18977 | 263,168 | 113,056 | 418 / 106,022 | dispatch | 73 |
| Hyper Chorus | 19143 | 248,832 | 106,880 | 445 / 99,546 | DispatchToEngine | 77 |
| Vintage Chorus | 19266 | 204,800 | 127,663 | 542 / 115,986 | VSTPluginMain, main | 73 |
| Vintage Phaser | 19268 | 313,344 | 157,493 | 626 / 141,439 | VSTPluginMain, main | 73 |

`engine_lift.sh <block>` で全 `.pdata` 関数を `lift_ranges.sh` (RetDec+pass 鎖) → `emcc -c` に通した結果 (3 回とも同一。lift 秒のみ min–max):

| engine | RetDec rc | final.ll define | `.pdata` で define 無し (B) | range 内部に増えた define | f80 関数 | 未実装 helper (うち VEX) | `emcc -c` | 局所修復後の `emcc -c` | lift 秒 |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 18977 (Frequency Shifter) | 0 | 442 | 2 / 418 (777) | 24 | 0 | 86 (60) | 1 (失敗) | 1 (失敗) | 16–17 |
| 19143 (Hyper Chorus) | 0 | 465 | 2 / 445 (91) | 20 | 0 | 75 (57) | 1 (失敗) | 1 (失敗) | 15–16 |
| 19266 (Vintage Chorus) | 0 | 573 | 2 / 542 (159) | 31 | 1 | 64 (53) | 1 (失敗) | 1 (失敗) | 18 |
| 19268 (Vintage Phaser) | 0 | 657 | 2 / 626 (420) | 31 | 1 | 104 (77) | 1 (失敗) | 1 (失敗) | 22 |

- `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`engine_defs.py`。分母は `.pdata` 関数数、括弧は欠けた range の合計 B)。4 本とも欠けた 2 件は call 先として参照されない (missing_ref 0)。原因 (RetDec の関数境界統合 / 復号失敗) は未調査。
- 失敗の連鎖 (clang は最初の型エラーで止まるため 1 件ずつ露見。**4 本とも同一の 2 類型**):
  1. `icmp eq ptr %x, %arg3` (`%arg3` は i64 仮引数) → "defined with type 'i64' but expected 'ptr'"。`engine_fixcmp.py` (engine 局所 pass、共有鎖には未組込) で 4 本とも各 4 operand を直す。
  2. 直した後は `__asm_rep_stosq_memset` 呼出の引数が SSA 値を含む `zext` 定数式 → "zext constexprs are no longer supported" (4 本とも `e.fixcmp.ll` の同じ桁位置 87)。
- VEX (AVX/FMA) の未実装 helper は distinct で 53〜77。CPUID 分岐で SSE 路に固定できるかは未確認 (T1 の AVX 2 種は CPUID 分岐で SSE 路固定と `plugins/REPORT.md` §4.3 に記録あり)。
- f80 関数は Vintage Chorus の `function_18001c320` と Vintage Phaser の `function_1800218a0` (各 209 行) の 1 本ずつで、#197 の `f80_lower.py` の適用対象。
- 以上は到達性の実測で、engine の正しさは何も示していない。

## 5. 判定 (gate) の設計と PR #506 の reviewer 指摘への対応

#506 の指摘は (a) 判定が不合格でも exit 0 になる、(b) 判定そのものにネガティブコントロール (NC) が無い、の 2 点。本書では次のように作った。

| 検査 | 実装 | 不合格時 | NC (`modulation_nega.sh`) |
|---|---|---|---|
| 殻 8 本の合否 | `judge.py <status.csv> --blocks … --batch-dir work/batch`: lift_rc = 0 / f80 = 0 / `emcc -c` rc = 0 / declares_unimpl = 0 (-1 = 集計行なしも不合格) / define = 閉包関数数 / 全列が整数 / ヘッダ一致 / `p.final.ll` の define 数が行と一致 / `p.o` が非空 | exit 1 (入力不正は 2)。e2e は `||` で受けて `FAIL` を出し exit 1。**`OK` 行は全判定通過後の最終行にだけ出る** | NC3: 15 ケース (§6) |
| e2e スクリプト自身の終了コード | 判定を `--judge-only` で単独実行でき、 `STATUS_CSV` で入力を差し替えられる | 不合格行入りの CSV で exit 1 かつ出力に `[modulation_e2e] OK` を含まない | NC6 |
| stale な結果で合格しない | lift 前に `work/batch/<block>` を消す (`lift_ranges.sh` は `drc.ll` の存在だけを見る)。判定対象は今回の実行で `status.csv` に追記された行だけ | — | (設計) |
| `PLUGIN_MATRIX.json` との突合 | `matrix_check.py`: 閉包 6 項目 + matrix に `batch` 欄のある 5 本は 4 項目を status と比較 (計 68)。プラグイン数 ≠ 8 は exit 2 | exit 1 | NC4 |
| Dispatcher ID の別算法検算 | `ids_crosscheck.py` | exit 1 | NC5 |
| `emcc -c` ゲート / ranges が lift 範囲を決めること | — | — | NC1 / NC2 (#506 と同方式) |
| 間接 call 脱落の検出 | `icall_check.py --gate` (e2e では測定のみ。audit と別算法の不一致だけ FAIL) | `--gate` で脱落ありなら exit 1 | NC7 |

e2e の exit 0 が意味するのは「殻 8 本の judge / matrix_check / ids_crosscheck が全て合格し、icall_check の検算が一致し、engine 4 本の測定行が揃った」ことだけで、
**間接 call 脱落と engine の `emcc -c` 結果は判定に含めない**。最終行にこの 2 つの件数を併記する (例: `IR の間接 call 脱落あり 8/8 本 … engines の emcc -c rc=0 は 0/4 本`)。

## 6. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner・測定中は本検証の 1 プロセス列のみ)

| 項目 | 実測 |
|---|---|
| `modulation_e2e.sh` 全体 (`--skip-lift` 無し、3 回連続) | **210 s / 208 s / 206 s**、3 回とも exit 0 (8 閉包 + `closure_facts` + engine 4 本、逐次で並列数 1)。開始時 load average (1 分) は run 2: 0.66、run 3: 1.04 (run 1 は未記録)。 **この 3 回は `icall_check.py` の組込み前のスクリプト** (run 1 は未コミットの作業ツリーだが内容は e431efc と同一、run 2・3 は b95b8ae) |
| 3 回の結果一致 | 判定列 (lift_rc / defines / f80 / unimpl / `emcc -c`)・engine 欠落監査・`facts.json` (sha256 `c9911472…a8aa8`) は 3 回ともバイト一致 |
| lift 秒 (`status.csv` の seconds、3 回の min–max) | §1 の表の通り (8 本計 23–25 s)。engine は 18977: 16–17、19143: 15–16、19266: 18、19268: 22 |
| 前提 inventory (初回のみ) | `inventory/win_funcs.py` 518 s (Pool(14) を 4 core で実行、load average 最大 16.43)。 PR #504 の記録 (8 分 22 秒 = 502 s) と同程度。 block map は PLUGIN_MATRIX から再構成 (`block_manifest.json` が tarball に無く `nsis_names.py` が動かないため) |
| 最終 HEAD の再現 | (実行中。結果は後続コミットで追記) |

ネガティブコントロール (`modulation_nega.sh`、全 28 ケース。壊したケースは終了コードに加え、狙った理由の文字列が出力に含まれることも確認):
- NC1: `final.ll` (Fruity Flanger 19007) の関数 1 つの `ret` を除去 → `emcc -c` が **rc 1** (無改変は rc 0)。
- NC2: 閉包 ranges の末尾 1 つ (`function_6bd240`) を落として再 lift (24 → 23 range) → その define が消え (present 1 → 0)、全体は 25 → 23 (RetDec は 1 range から 2 define を出すことがあり、差は 1 とは限らない)。
- NC3 (`judge.py`、15 ケース): 無改変は exit 0。lift_rc=1 / f80=3 / emcc_c_rc=1 / declares_unimpl=5 / declares_unimpl=-1 / defines=24 (閉包 25) / lift_rc="x" / 行欠落 / 9 列に短縮 / 良い行の後に不合格行を追記 / `p.o` 欠落 / `p.final.ll` の define 数改変 の 12 ケースはすべて **exit 1**、ヘッダ改変・入力ファイル無しは **exit 2**。
- NC4 (`matrix_check.py`、5 ケース): 無改変 exit 0。Flanger の closure_funcs +1 / Hyper Chorus の vcall +1 / Fruity Chorus の status lift_rc=1 は **exit 1**、プラグインを 1 本落とす (7 本) は **exit 2**。
- NC5 (`ids_crosscheck.py`、2 ケース): 無改変 exit 0。Frequency Shifter の taint 側 ID 50 の件数を +1 すると **exit 1** (NG)。
- NC6 (`modulation_e2e.sh --judge-only`、2 ケース): 実 `status.csv` は exit 0 で `judge-only: PASS`。 Flanger の emcc_c_rc=1 行を最終行に足した CSV は **exit 1**、 `judge: FAIL 7/8`、出力に `[modulation_e2e] OK` を含まない。
- NC7 (`icall_check.py --gate`、4 ケース): 実データ (8/8 本が脱落) は **exit 1**。 Flanger の IR に間接 call を 9 本注入 (静的 site 10) は **exit 1**、10 本・11 本注入は **exit 0** (脱落 0/1 本)。

別系統の突合: Dispatcher ID の独立走査 (§2、8/8 本)、間接 call の線形 sweep (§3.2、240 = 240)、閉包 6 項目 + batch 4 項目の `PLUGIN_MATRIX.json` 突合 (68/68)。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`) と、host / kernel / 間接 call の静的な数え上げ。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp。範囲外の項目について、本書は何も主張しない。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。Eff_Render 単位の native (ms_abi VA 敷設) ⟷ wasm harness が無く、P0a/P0b/P0c が OPEN。§3.2 の欠陥が残る間は実施しても不一致 | #202 を閉じられない | #195 / #196 / #197 / #514 の完了後に #202 を再開 (Closes はその時)。harness は #506 が PM に起票依頼済みの「[PLG-F3a] Eff_Render 単位 native ⟷ wasm 差分 harness」を本 8 本にも適用 (PM 未起票) |
| Render test .flp の E2E (出口条件 4) | 同上 | FLEngine 統合待ち。#202 を継続 |
| 間接 call 脱落 (静的 240 site → IR 0、8/8 本) | 差分試験の前提 | #514 (本 run の数値をコメント済み) |
| engine 4 本の `emcc -c` 未通過 (E1 → E2、VEX 53〜77、define 無し各 2) と殻との結合方式 (殻の dynload 2) | 4 本 (うち Hyper Chorus は T1) | **#527 [PLG-F5-2] (本 run で起票)**。同型 #523 / #506 提案の PLG-F3b と PM が統合判断 |
| Vintage Chorus / Phaser の engine の f80 各 1 関数 | engine の wasm 化 | #197 (コメント済み) |
| Fruity Flangus の kernel 3 変数 (6 実装、うち 0x5dea40 は x87 を含む) の差分試験記録が `p0c/REPORT.md` に無い | Flangus の kernel 保証 | #197 (コメント済み) |
| host slot 0x120 (Frequency Shifter 1 site) と 0x100 / 0x108 (Flangus・Hyper Chorus 各 1 site) の意味 | host 結合 | #196 (コメント済み) |
| Frequency Shifter / Hyper Chorus に共通で DLL 内から参照されない 4 関数 (kernel 呼出 5 site) と、22 site (0x5de390) の所在 | 閉包の取りこぼしでないことの確認 | #195 (コメント済み) |
| Hyper Chorus (T1) の見積りに engine の工数が含まれるか | 見積り | #202 (PM 判断) |
| 本 dir と PR #506 の `dynamics/` で engine_*.sh / matrix_check / ids_crosscheck / env.sh が重複 | 保守 | PM: #506 のマージ後に共通化の要否を判断 |

## 8. DEFECTS.md 行案 (候補。追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| E1 icmp ptr/i64 混在 | `icmp eq ptr %x, %argN` (argN は i64) | 本 4 engine で各 4 operand (PR #506 の 2 engine も同型) | emcc "defined with type 'i64' but expected 'ptr'" | `engine_fixcmp.py` (局所)。`fix_ptr_params.py` の拡張が本筋 |
| E2 SSA 値入りの定数式 | `__asm_rep_stosq_memset` の引数に `zext (… i64 %v …)` | 本 4 engine (E1 を直した直後に露見) | emcc "zext constexprs are no longer supported" | 未修復 |

## 9. 成果物

| ファイル | 内容 |
|---|---|
| `modulation_e2e.sh` | 8 閉包 → batch_lift → `judge.py` → `closure_facts.py` → `matrix_check.py` → `ids_crosscheck.py` → `icall_check.py` → engine 4 本 (参考) |
| `judge.py` | 殻の合否判定 (gate)。exit 0/1/2 |
| `modulation_nega.sh` `nega_gates.py` | NC1〜NC7 (`nega_gates.py` は合成入力で各 gate を壊す) |
| `closure_facts.py` `matrix_check.py` `ids_crosscheck.py` `icall_check.py` | 閉包 / host ID / kernel / engine 外形 → `work/modulation/facts.json`、matrix 突合、ID 別算法検算、間接 call 監査 |
| `report_tables.py` | §1〜§4 の表の生成 |
| `engine_lift.sh` `engine_ranges.py` `engine_fixcmp.py` `engine_defs.py` | engine DLL の全 `.pdata` lift・欠落監査・局所修復 (PR #506 の同名スクリプトと同一手法。#506 のマージ後に共通化するのが望ましい) |
| `env.sh` | 環境 (fl-win64 展開・python venv)。 block map は main の `inventory/blockmap_from_matrix.py` を使う |
