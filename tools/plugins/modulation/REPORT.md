# tools/plugins/modulation/REPORT.md — PLG-F5 (#202) modulation 8 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/modulation/` のみ (+ `docs/DOC_MAP.md` の索引 1 行) / 検証起点 commit: **8603db1** (スクリプト一式。 main の #514 (237010e) マージ後の判定修正と reach_check.py を含む) / 最新の検証 HEAD: **b9fe1d8** (main の lift 鎖変更を取り込んだ版。 §6 に実測)
- 再現: `bash tools/plugins/modulation/modulation_e2e.sh` (判定 + 実測) / `bash tools/plugins/modulation/modulation_nega.sh` (ネガティブコントロール) / `python3 tools/plugins/modulation/report_tables.py` (§1〜§4 の表)
- 素材: `fl-win64` / `toolchain-retdec` (`[RETDEC]`) / `toolchain-emsdk` (`[EMSDK]`) (`docs/WORKFLOW.md` §11、 パスは `docs/REFERENCES.md`)。環境は `modulation/env.sh`
- 方法の出典: PR #506 (PLG-F3 dynamics、マージ済) の `dynamics_e2e.sh` / `matrix_check.py` / `ids_crosscheck.py` と、PR #504 (PLG-F2、マージ済) の間接 call 監査。#506 の reviewer 指摘 (§5) は最初から回避した
- 既知類型との関係: **(icall §4) D1 = 間接 call/jmp 脱落**は従来鎖 (`PLUG_ICALL=0`) で 8/8 本再現、 main の既定鎖 (#514 で復元を接続) では 0/8 本 (§3.2)。 (DEFECTS.md) D1〜D16 に該当する新規類型なし。
  engine の `emcc -c` 失敗 (§4) は emcc が拒否する loud なエラーで silent miscompile ではない (差分試験は未実施)

## 0. 結論 (先出し)

1. **#202 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** PLG-P0a #195 / P0b #196 / P0c #197 が OPEN で、
   Eff_Render 単位の native ⟷ wasm 差分 harness も repo に無い (本 run では差分試験をしていない)。
   → PR は **`Refs #202`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は殻 8/8 本で通った** (§1)。8 本すべてで RetDec+pass 鎖が完走 (lift_rc 0)、`emcc -c` rc 0、`x86_fp80` 関数 0、未実装 `__asm_*` helper 宣言 0、
   final.ll の define 数 = 閉包関数数。合計 **207 関数 / 92,917 B**。閉包 6 項目 × 8 本 + matrix に記録のある batch 4 項目 × 5 本 = **68/68 項目**が `PLUGIN_MATRIX.json` と一致
   (T0 3 本・T1 2 本は matrix の記録を再現、**T2 の殻 3 本 (Frequency Shifter / Vintage Chorus / Vintage Phaser) は今回初測定**)。
3. **ただし `emcc -c` の通過は正しさを意味しない** ((icall §4) D1)。8 閉包の機械語には非 IAT の間接 call が **計 240 site** (別算法の線形 sweep も 240) ある。従来鎖 (`PLUG_ICALL=0`) の lift 後 IR では **0** (8/8 本が脱落、§3.2)。
   main の既定鎖 (`PLUG_ICALL=1`、PR #539 / #514 が復元を接続) では IR 側 **240** で脱落 **0/8 本**、`f2/icall_gate.py` (site VA 単位の被覆) も 8/8 本 PASS。e2e は `icall_check.py --gate` を判定に含める。
4. **host 呼出面は P0b の応答表で覆える** (§2)。閉包が即値 ID で発行する Dispatcher ID は {2, 30, 36, 50} の 4 種 (slot0 の即値 ID site は計 14、独立走査も同一)。4 種とも `hostshim/hs_ids.json` の 35 ID に含まれ、動的 ID は 0 site。
5. **SIMD kernel 表への依存: 閉包 + frontier の中では Fruity Flangus だけ** (閉包内 3 site / 3 変数。他 7 本は 0 site)。**ただし frontier より深い framework 関数に kernel 呼出がある**。
   Frequency Shifter / Hyper Chorus の kernel 呼出 5 site は閉包・frontier の外の 4 関数ずつにあり (framework 共通ハッシュ、33〜42 DLL が同一)、うち 3 関数 (4 site) は閉包から frontier の薄いラッパー経由の direct call で到達する (§3.1・§3.3)。
   よって FS / HC が kernel に依存しないとは言えず、**未確定**。
6. **C++ engine 4 本 (全て MSVC) は RetDec まで通り、`emcc -c` は b9fe1d8 で 2/4 本** (18977・19143 が rc 0)。19266・19268 は f80 (x87) 系のエラー (`fp_extend` / `frem` / `fp_round`) で失敗した。f80 段 (`p0c/f80_lower.py`) を足した 35d8f3d5 では 4/4 本 (§4 表の「f80 段後」列、付録 `REPORT_APPENDIX.md`)。VEX の未実装 helper は 50〜71 (distinct、648383c)、`.pdata` で define が無い range が各 2 件ある。
   殻の DSP 本体は engine 側にあるため、**殻 8/8 の通過は「8 本が wasm 化できる」を意味しない**。T1 の Hyper Chorus の見積りにこの engine の工数が含まれるかは未確認。
7. **閉包の境界**: frontier の先で、framework 共通ハッシュに一致しない関数 (hash < 13 DLL) が閉包から direct call で到達する (8/8 本、計 61 関数 / 26,713 B、§3.3)。`plugin_closure.py` の閉包にも frontier にも入らない。追跡 issue の起票は PM 依頼 (§7)。

## 1. 閉包 lift 結果 (Delphi 殻 8 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessEvent / ProcessParam / Eff_Render) から `call/jmp rel32` で到達する、
framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。vcall / ptr = 間接呼出 site 数。iat = `plugin_closure.py` が数える RIP 相対メモリ operand の call/jmp site (IAT 経由 Win32 呼出が大半だが IAT slot とは限らない。Fruity Chorus の 1 site は `.bss` 上の実行時設定の関数ポインタ変数 0x713060 への `call [rip+…]` @0x40e4b6)。
define = `p.final.ll` の `^define` 数。f80 = `x86_fp80` を含む define 数。未実装 helper = `p.simd.log` の `unimplemented N`。`emcc -c` 列は `emcc -c -O0 -msimd128` の終了コード。lift 秒は既定鎖 (`PLUG_ICALL=1`、icall 復元を含む) の e2e 実行の値 (出典は §4 直下の注)。

| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | define | f80 | 未実装 helper | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Frequency Shifter | 18978 | T2 | 29 / 15,659 | 75 / 16,254 | 34 | 6 | 0 | 29 | 0 | 0 | 0 | 5–6 |
| Fruity Chorus | 18989 | T1 | 17 / 10,859 | 41 / 4,409 | 12 | 3 | 1 | 17 | 0 | 0 | 0 | 5 |
| Fruity Flanger | 19007 | T0 | 25 / 5,846 | 37 / 3,979 | 8 | 2 | 0 | 25 | 0 | 0 | 0 | 4 |
| Fruity Flangus | 19009 | T0 | 19 / 6,823 | 39 / 5,613 | 10 | 13 | 0 | 19 | 0 | 0 | 0 | 4–5 |
| Fruity Phaser | 19066 | T0 | 21 / 6,016 | 33 / 3,889 | 9 | 2 | 0 | 21 | 0 | 0 | 0 | 5 |
| Hyper Chorus | 19144 | T1 | 28 / 11,440 | 72 / 18,110 | 25 | 3 | 0 | 28 | 0 | 0 | 0 | 5 |
| Vintage Chorus | 19265 | T2 | 28 / 14,074 | 66 / 12,800 | 48 | 5 | 0 | 28 | 0 | 0 | 0 | 5 |
| Vintage Phaser | 19267 | T2 | 40 / 22,200 | 77 / 17,213 | 52 | 7 | 0 | 40 | 0 | 0 | 0 | 7 |
| 計 | | | **207 / 92,917** | | | | | 207 | 0 | 0 | 0 | 41 |

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

| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | 全 .pdata 関数の走査の site / kernel 種 (framework 関数を含む) |
|---|--:|---|--:|---|
| Frequency Shifter | 0 | — | 0 | 27 / 5 |
| Fruity Chorus | 0 | — | 0 | 22 / 1 |
| Fruity Flanger | 0 | — | 0 | 22 / 1 |
| Fruity Flangus | 3 | 0x5de800 (1), 0x5de9d0 (1), 0x5df700 (1) | 0 | 25 / 4 |
| Fruity Phaser | 0 | — | 0 | 22 / 1 |
| Hyper Chorus | 0 | — | 0 | 27 / 5 |
| Vintage Chorus | 0 | — | 0 | 22 / 1 |
| Vintage Phaser | 0 | — | 0 | 22 / 1 |

- 22 site (kernel 0x5de390) は 8 本すべてに共通し、閉包にも frontier にも属さない。§3.3: 閉包外の kernel 呼出関数は 8 本で計 120 関数、全て framework 共通ハッシュ (13 DLL 以上) で DLL 固有 0。
- Flangus の 3 変数 (var 0x715490 / 0x715498 / 0x7154d8) は、それぞれ 2 実装 (0x5de800|0x5de870、0x5de9d0|0x5dea40、0x5df700|0x5df770) のどちらかを選ぶ。`kernel_table.json` で 0x5dea40 は x87 命令を含む。
  `p0c/REPORT.md` に当該 6 アドレスの記載は無い (grep 0 件)。差分試験の有無は未確認 (§7)。
- Frequency Shifter と Hyper Chorus の 5 site / 4 kernel (0x5decb0 / 0x5df750 ×2 / 0x5de620 / 0x5df270) は、閉包・frontier のどちらにも属さない 4 関数ずつの中にある
  (FS: 0x5e67b0 / 0x5e72c0 / 0x5e8020 / 0x6d6f30、HC: 0x5e6430 / 0x5e6f40 / 0x5e7ca0 / 0x6ebcd0。サイズ 533 / 1,193 / 470 / 1,316 B が対応)。**これらは参照されている** (`reach_check.py`、§3.3):
  - 呼出元関数 (`call/jmp rel32`) は FS で 2 / 3 / 1 / 2 本、HC で 2 / 3 / 1 / 1 本。`.pdata` 全関数の線形逆アセンブルと、E8/E9/EB のバイトパターン走査の 2 通りで一致。
  - 正規化ハッシュを持つ DLL は 42 / 42 / 42 / 33 本 (`work/fw_hash_counts.json`) で、framework 共通ハッシュ (13 DLL 以上) である。
  - 3 関数 (4 site) は閉包から direct call で到達する: FS `0x6ddf40`[閉包] → `0x5e9dd0`[frontier、78 B・call 1 本の薄いラッパー] → `0x5e9810` → … → 各関数 (HC は `0x6ea000` → `0x5e9a50` → `0x5e9490` → …)。
  - 残る `0x6d6f30` / `0x6ebcd0` は閉包から direct call では届かない。祖先の根は FS 2 本 (うちデータ・即値・RIP 相対の参照あり 1)、HC 1 本 (参照あり 1)。vtable 状データ経由の到達は未追跡。
  - 前版の「DLL 内のどこからも参照されない」「framework 判定から外れた」「未使用コードの可能性が高い」は誤りで撤回する (独立走査の指摘で反証、本版で再測定)。**FS / HC の kernel 依存は未確定**。

### 3.2 間接 call 脱落 (`icall_check.py`)

定義: 静的 site = 閉包 ranges の非 IAT 間接 call 命令数 (`tools/icall/audit_icall.py`、`call [reg+disp]`・`call [rip+var]` ほか)。IR = `p.final.ll` で callee が `@name` でない call (元の間接 call) と `@__icall_dispatch` 呼出 (#514 の復元) の数 (`audit_icall.py` の `ir_call_ind_total`)。
別算法 = 閉包 ranges を capstone で線形 sweep して数えた非 IAT 間接 call (PR #504 の `xcheck_icall.py` と同じ方法)。`p.final.ll` は `insn.addr` を持たないため site 単位の dropped / 直接化の区別はできず、件数比較のみ。

| プラグイン | block | 静的 site | 別算法 | call あり関数 | IR の間接 call | 入口スロットの静的 → IR |
|---|--:|--:|--:|--:|--:|---|
| Frequency Shifter | 18978 | 40 | 40 | 16 | 40 | Dispatcher 2→2, SaveRestoreState 12→12, ProcessParam 2→2, Eff_Render 4→4 |
| Fruity Chorus | 18989 | 16 | 16 | 7 | 16 | DestroyObject 2→2, Dispatcher 1→1, SaveRestoreState 6→6, ProcessParam 2→2 |
| Fruity Flanger | 19007 | 10 | 10 | 4 | 10 | Dispatcher 1→1, SaveRestoreState 6→6, ProcessParam 2→2 |
| Fruity Flangus | 19009 | 23 | 23 | 10 | 23 | Dispatcher 1→1, SaveRestoreState 4→4, ProcessParam 2→2, Eff_Render 1→1 |
| Fruity Phaser | 19066 | 11 | 11 | 5 | 11 | Dispatcher 1→1, SaveRestoreState 6→6, ProcessParam 2→2 |
| Hyper Chorus | 19144 | 28 | 28 | 11 | 28 | Dispatcher 2→2, SaveRestoreState 9→9, ProcessParam 5→5, Eff_Render 1→1 |
| Vintage Chorus | 19265 | 53 | 53 | 13 | 53 | Dispatcher 10→10, SaveRestoreState 6→6, ProcessEvent 1→1, ProcessParam 3→3, Eff_Render 3→3 |
| Vintage Phaser | 19267 | 59 | 59 | 15 | 59 | Dispatcher 10→10, SaveRestoreState 10→10, ProcessEvent 1→1, ProcessParam 4→4, Eff_Render 3→3 |
| 計 |  | 240 | 240 |  | 240 |  |

- 既定鎖 (`PLUG_ICALL=1`、main の #514 以降) では **脱落 0/8 本** (IR 側 240 = 静的 240)。`f2/icall_gate.py 18978 … 19267` (site VA 単位の被覆、別実装) も 8/8 本 PASS (機械語 240・dispatch 240・未被覆 0)。e2e は `icall_check.py --gate` を判定に含める。
- 従来鎖 (`PLUG_ICALL=0 bash lift/batch_lift.sh <8 block>` → `icall_check.py`) では 静的 240 → IR 0 で脱落 **8/8 本** (`--gate` は exit 1)。lift は 8 本計 22 s (1 回、復元付きの既定鎖は 41 s)。PR 作成時 (519b3aa) の測定と一致し、NC7-5 (dispatch を除いた IR) でも再現する。
- 静的 site 数は `plugin_closure.py` の vcall + ptr と 8 本中 7 本で一致する (例: Frequency Shifter 34 + 6 = 40、Flanger 8 + 2 = 10)。Fruity Chorus は 12 + 3 = 15 に対し静的 16 で、差の 1 site は §1 の iat=1 (`.bss` 上の関数ポインタ変数への `call [rip+…]`。`audit_icall.py` は IAT slot でないので非 IAT 側に数える)。

### 3.3 閉包の境界 (`reach_check.py`)

`plugin_closure.py` の BFS は framework 共通ハッシュの関数 (frontier) で止まる。そのハッシュは call/jmp の rel32 を除いて作る (`inventory/win_funcs.py`) ため、呼び先が DLL ごとに違っても frontier になりうる。frontier の先は、閉包にも frontier にも入らない。
`reach_check.py` は (A) `.pdata` 全関数 (チェーン unwind 除く) の線形逆アセンブルで call/jmp の辺を作り、閉包を根に frontier も越えて BFS する。target = §3.1 の kernel 呼出 site を持つ閉包外・frontier 外の関数、leak = 閉包から到達し閉包に属さず framework 共通ハッシュ (13 DLL 以上) でない関数。
検算 (B') は逆アセンブルせず E8/E9/EB のバイトパターンから辺を拾った上位集合: A の辺が全て B' にあり、A で到達する target は B' の逆辺でも閉包に届くことを確かめる (不一致なら exit 1)。

| プラグイン | block | 閉包 / frontier 関数 | 辺 A / B' (B' のみ) | 閉包外 kernel 呼出関数 (site) | うち DLL 固有 (hash < 13 DLL) | うち閉包から direct call で到達 (site) | 到達しない関数の祖先の根: データ参照あり / なし | leak 関数 / B |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Frequency Shifter | 18978 | 29 / 75 | 24371 / 24377 (6) | 18 (27) | 0 | 3 (4) | 15 / 1 | 7 / 2119 |
| Fruity Chorus | 18989 | 17 / 41 | 23352 / 23355 (3) | 14 (22) | 0 | 0 (0) | 14 / 0 | 20 / 11355 |
| Fruity Flanger | 19007 | 25 / 37 | 23333 / 23336 (3) | 14 (22) | 0 | 0 (0) | 14 / 0 | 6 / 2665 |
| Fruity Flangus | 19009 | 19 / 39 | 23360 / 23363 (3) | 14 (22) | 0 | 0 (0) | 14 / 0 | 5 / 1930 |
| Fruity Phaser | 19066 | 21 / 33 | 23308 / 23310 (2) | 14 (22) | 0 | 0 (0) | 14 / 0 | 5 / 1930 |
| Hyper Chorus | 19144 | 28 / 72 | 24466 / 24472 (6) | 18 (27) | 0 | 3 (4) | 15 / 0 | 7 / 2119 |
| Vintage Chorus | 19265 | 28 / 66 | 24413 / 24416 (3) | 14 (22) | 0 | 0 (0) | 14 / 0 | 6 / 2665 |
| Vintage Phaser | 19267 | 40 / 77 | 24587 / 24589 (2) | 14 (22) | 0 | 0 (0) | 14 / 0 | 5 / 1930 |
| 計 | | | 191190 / 191218 | 120 | 0 | 6 (8) | | 61 / 26713 |

- 検算: 8/8 本で A ⊆ B'、A で到達なのに B' で届かない target 0。B' にだけある辺は計 28 辺 (命令境界を見ない偽陽性)。
- 閉包外の kernel 呼出関数は計 120 関数で、全て framework 共通ハッシュ (DLL 固有 0)。閉包から direct call で到達するのは FS・HC の各 3 関数 (4 site) のみ。残りは閉包から direct call では届かない (FS 0x6d6f30 / HC 0x6ebcd0 は呼出元あり、他は A の辺での呼出元なし。呼出元ゼロの理由は未解析)。
- leak: 8/8 本で閉包から direct call で到達する hash < 13 DLL の関数がある (計 61 関数 / 26,713 B)。パスは常に frontier の framework 関数を通る (`work/modulation/refs/<block>.json`)。hash < 13 は DLL 固有のロジックを意味せず (絶対アドレスを含む RTL 等でも起こりうる)、中身は未解析。
- 範囲: データ参照経由 (vtable・関数ポインタ) の到達は追わない。DLL ごとの `.pdata` 内の direct call/jmp のみ。

## 4. T2/T1: C++ engine DLL 4 本

4 本とも MSVC (VS2019) の C++ DLL で、import は KERNEL32 のみ。殻との結合方式 (LoadLibrary 経路) は静的解析で §4.1 に記録 (呼出箇所は未了)。Vintage Chorus / Phaser の engine は `VSTPluginMain` / `main` を export する (VST2 engine。issue 本文の「engine.vst ラップ」に対応)。

| プラグイン | engine block | サイズ B | `.text` B | `.pdata` 関数 / B | export | KERNEL32 import |
|---|--:|--:|--:|--:|---|--:|
| Frequency Shifter | 18977 | 263,168 | 113,056 | 418 / 106,022 | dispatch | 73 |
| Hyper Chorus | 19143 | 248,832 | 106,880 | 445 / 99,546 | DispatchToEngine | 77 |
| Vintage Chorus | 19266 | 204,800 | 127,663 | 542 / 115,986 | VSTPluginMain, main | 73 |
| Vintage Phaser | 19268 | 313,344 | 157,493 | 626 / 141,439 | VSTPluginMain, main | 73 |

`engine_lift.sh <block>` で全 `.pdata` 関数を `lift_ranges.sh` (RetDec+pass 鎖) → `emcc -c` に通した結果。RetDec rc・define 数・欠落 range・f80 は 519b3aa・8603db1・648383c・b9fe1d8 で同一。未実装 helper・`emcc -c` の経緯は付録 `REPORT_APPENDIX.md` の §E。下表は b9fe1d8 以降の値。lift 秒は全測定の min–max:

| engine | RetDec rc | final.ll define | `.pdata` で define 無し (B) | range 内部に増えた define | f80 関数 | 未実装 helper (うち VEX) | `emcc -c` | 局所修復後の `emcc -c` | f80 段後の `emcc -c` (erc3) | lift 秒 |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 18977 (Frequency Shifter) | 0 | 442 | 2 / 418 (777) | 24 | 0 | 70 (55) | 0 (成功) | 0 (適用 0 件) | 0 (f80 段不要) | 13–17 |
| 19143 (Hyper Chorus) | 0 | 465 | 2 / 445 (91) | 20 | 0 | 64 (52) | 0 (成功) | 0 (適用 0 件) | 0 (f80 段不要) | 13–16 |
| 19266 (Vintage Chorus) | 0 | 573 | 2 / 542 (159) | 31 | 1 | 60 (50) | 1 (失敗) | 1 (失敗、適用 0 件) | 0 (f80 段後、f80 1 → 0) | 15–18 |
| 19268 (Vintage Phaser) | 0 | 657 | 2 / 626 (420) | 31 | 1 | 92 (71) | 1 (失敗) | 1 (失敗、適用 0 件) | 0 (f80 段後、f80 1 → 0) | 17–22 |

- `emcc -c` の列は b9fe1d8 の実測 (`engines.csv`)、「f80 段後」列は 35d8f3d5 の実測 (`summary.csv` erc3)。8603db1・648383c の 0/4 本から変わった。旧記述 (4 本とも E1 → E2) は P-E1 取り込み後は成り立たず、`engine_fixcmp.py` は 0 件 (E2 は b9fe1d8 で未確認)。lift 秒の出典は raw の `summary.csv`・`engines.csv` が無く (`work/` は gitignore)、run 番号も未記録のため commit 履歴の記載に基づく: (a) 4d57b9ef・8603db17 (8603db1 時点) と 4282160f (648383c 時点) の本体表 = 18977 16–17 / 19143 15–16 / 19266 18 / 19268 22 (58297bfe で 21–22、4282160f で 20–22)、(b) 9f661ead が統合した 35d8f3d5 の PR 作成時の追補 = 18977 13–14 / 19143 13 / 19266 15 / 19268 17–18。表は (a) と (b) の union。19268 の 20・21 は (a) の記載にのみ現れ、元の記録が無いため出典不明。
- `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`engine_defs.py`。分母は `.pdata` 関数数、括弧は欠けた range の合計 B)。**名前の不一致 (#527 追補)**: 欠けた range は RetDec が export 名・既知名 (dispatch / entry_point 等) で define された関数と判定された前 run の記録がある。名前照合の再現は未取得 (付録 `REPORT_APPENDIX_527.md` §I.2・§I.2.1)。
- 失敗した 2 本 (19266・19268): 最初のエラーは `e.final.ll` の `emcc -c` (`first_errors.txt`) で、E1 (icmp ptr/i64) でも E2 (zext 定数式) でもない。エラーは 4 件 (`4 errors generated.`): `do not know how to soften fp_extend` ×2、`no libcall available for frem with type f80` ×1、`no libcall available for fp_round with type f80` ×1。どちらも `e.final.ll` に x86_fp80 を含む define が 8 個ある (`grep -c x86_fp80`) うちの、どの関数で出たかは未特定。f80 型の演算の legalize 失敗で、#197 の `f80_lower.py` (f80 → f64) の対象と見られる (未検証)。
- VEX (AVX/FMA) の未実装 helper は distinct で 50〜71 (648383c・b9fe1d8 とも同値)。CPUID 分岐で SSE 路に固定できるかの静的な下調べ (`sampler/vex_guard.py`、HEAD 70385178 で 4 本を 2026-10-13 に再実行): VEX 関数 8/8/9/13 (VEX 命令 635/658/588/916)、cpuid 関数 2/2/2/3、xgetbv 関数 2/2/2/2、VEX 関数の直接 call 鎖 (即値 call/jmp のみ、深さ 3) に cpuid/xgetbv 関数が届いたものは 0/0/0/0。間接 call (`call [rip+...]`・関数ポインタ・vtable) は未追跡のため、「SSE 固定は静的に不成立」とは言えない。動的な分岐の実測は未実施。T1 の AVX 2 種の SSE 路固定は `plugins/REPORT.md` §4.3 に記録あり。
- f80 関数は Vintage Chorus の `function_18001c320` と Vintage Phaser の `function_1800218a0` の 1 本ずつ (#197 の対象)。以上は到達性の実測で、engine の正しさは何も示していない。
- **PLG-F5-2 / #527 追補**: `engine_lift.sh` に `p0c/f80_lower.py` の段を追加し、4 本すべて `emcc -c` rc 0 (表の「f80 段後」列)。これは前 run の記録で、本 PR の修正 run では再現していない (付録 §I.2.1)。4 本の順次実行の合計は 65.2 s (35d8f3d5、PR 作成時の実測。修正 run では未再実行)。f80→f64 は bit-exact ではなく (#197 で未検証)、通過は正しさを示さない。詳細は付録 `REPORT_APPENDIX.md`。gate (`engine_judge.py`) の判定と名前照合の付録は `REPORT_APPENDIX_527.md` (§I・§I.2)。

### 4.1 殻と engine の結合方式 (受入 5、静的解析)

- 殻 (18978 / 19144 / 19265 / 19267) は 4 本とも KERNEL32 の `LoadLibraryExW` / `GetProcAddress` / `FreeLibrary` を import。engine 名は殻の文字列 (fl-win64 を展開し pefile と UTF-16 / ASCII 走査で確認。`work/` 無し): FS = `Engine_x64.dll` (0x2dda74) + `dispatch` (0x2dda92)、HC = `engine_x64.dll` (0x2e9704) + `DispatchToEngine` (0x2e9722)、VC = `engine_x64.dll` + VST 系名 (0x2d9db0〜0x2daaa0)、VP = `engine_x64.dll` + VST 系名 (0x2db640〜0x2dc330)。
- VST 系名は `VSTPluginMain` のほか大文字小文字違い 8 種 (計 9 種、`vstpluginmain` は 2 箇所。殻 19265 で確認)。
- engine の export: 18977 = `dispatch`、19143 = `DispatchToEngine`、19266 / 19268 = `VSTPluginMain` / `main`。19268 の import は KERNEL32 の `LoadLibraryExW` / `GetProcAddress` / `FreeLibrary`。
- 結論 (推定): 殻が `LoadLibraryExW(engine_x64.dll)` → `GetProcAddress(<export>)` で engine を動的ロードする (§1 の dynload 2 と一致)。
- 未解析: 殻内の `GetProcAddress` 呼出箇所と引数の実値 (#527 に残す)、engine の `DllMain` の扱い。範囲外: bit-exact・wasm リンク方式 (#202 / #197)。

## 5. 判定 (gate) の設計と PR #506 の reviewer 指摘への対応

判定の設計 (検査の一覧表・NC の対応) は付録 `REPORT_APPENDIX.md` §H に分割移動した。

e2e の exit 0 が意味するのは「殻 8 本の judge / matrix_check / ids_crosscheck が全て合格し、`icall_check.py --gate` (脱落 0) と `reach_check.py` の検算が通り、engine 4 本の測定行が揃った」ことだけで、
**閉包の取りこぼし (leak) と engine の `emcc -c` 結果は判定に含めない**。最終行にこの 2 つの件数を併記する (実行例は §6)。

## 6. 検証 (スクリプトは 8603db1 から不変。 検証は 8603db1・648383c・b9fe1d8 の 3 起点・4 core / 15 GiB の Actions runner・測定中は本検証の 1 プロセス列のみ)

| 項目 | 実測 |
|---|---|
| main (237010e = #514) を merge した 0e1e2f1 の `modulation_e2e.sh` (inventory 生成から) | **exit 1**、9 分 44 秒。judge が `batch_lift.sh` の 12 列ヘッダ (`icall,dispatch_calls` 追加) を入力不正として拒否。`judge.py` が 10 / 12 列を受理するよう修正 (NC3-9 / NC3-11) |
| 修正後 (8603db1、inventory 済み) の `modulation_e2e.sh` 全体 | exit 0、**331 s** (`elapsed=331s`、終了時 load average 1.01 / 1.51 / 3.13、開始時は未記録)。判定 8/8・matrix 68/68・ID 8/8・icall 脱落 0/8 本・reach_check 検算 OK・engines の `emcc -c` rc=0 は 0/4 本。1 回のみ (n=1) |
| 検証 HEAD **b9fe1d8** (main の lift 鎖変更を取り込んだ版) の `modulation_e2e.sh` (inventory 生成から、`work/` 無し、`tools/plugins/work/` を削除してから実行) | **exit 0、617 s** (`elapsed=617s`、終了時 loadavg 1.35 / 5.38 / 4.29、n=1)。judge 8/8・matrix 68/68・ID 8/8・icall 脱落 0/8 本 (静的 240 → IR 240)・reach_check 検算 OK・leak 8/8 本・engines の `emcc -c` rc=0 は **2/4 本** (18977・19143 が 0、19266・19268 が 1)。`modulation_nega.sh` も **exit 0、34 s** (`nega_gates: OK (0 件不一致)`) |
| main merge 版 HEAD **648383c** の `modulation_e2e.sh` (inventory 生成から、`work/` 無しの worktree) | **exit 0、869 s** (`elapsed=869s`、終了時 loadavg 1.05 / 4.95 / 5.19、n=1)。judge 8/8・matrix 68/68・ID 8/8・icall 脱落 0/8 本 (静的 240 → IR 240)・reach_check 検算 OK・leak 8/8 本 (計 61 関数 / 26,713 B)・engines の `emcc -c` rc=0 は 0/4 本。`modulation_nega.sh` も **exit 0、45 s** (`nega_gates: OK`) |
| 内訳 | `reach_check.py` 単体は 102.9 s / 105.2 s (2 回)。8 本の lift は 41 s (2 回とも)。engine 4 本の lift は 16 / 15 / 18 / 21 s |
| `facts.json` | sha256 `c9911472…a8aa8` は 519b3aa の記録と一致 |
| 旧版 (519b3aa〜cc1edb8、`PLUG_ICALL` 導入前の鎖) の記録 | `modulation_e2e.sh` 3 回 **210 / 208 / 206 s** (exit 0)、クリーン worktree (`env -i`、inventory 生成から) **761 s**、再実行 **213 s**。前提 inventory の `win_funcs.py` は 518 s (Pool(14) を 4 core で実行、PR #504 の記録は 502 s)。block map は PLUGIN_MATRIX から再構成 (`block_manifest.json` が tarball に無く `nsis_names.py` が動かないため) |
| 規約検査 | `git status --porcelain=v1 -- tools/plugins/modulation`: 追跡外・未コミットなし (REPORT 修正の commit 後)。20 MiB 超のファイル 0。`work/` は gitignore で未追跡 |

ネガティブコントロール (`modulation_nega.sh` exit 0、45 s。NC1 / NC2 の 2 ケース + `nega_gates.py` の 37 ケース (NC3: 15 / NC4: 5 / NC5: 2 / NC6: 2 / NC7: 5 / NC8: 8) = 計 39 ケース。壊したケースは終了コードに加え、狙った理由の文字列が出力に含まれることも確認):
- NC1: `final.ll` (Fruity Flanger 19007) の関数 1 つの `ret` を除去 → `emcc -c` が **rc 1** (無改変は rc 0)。
- NC2: 閉包 ranges の末尾 1 つ (`function_6bd240`) を落として再 lift (24 → 23 range) → その define が消え (present 1 → 0)、全体は 25 → 23 (RetDec は 1 range から 2 define を出すことがあり、差は 1 とは限らない)。
- NC3 (`judge.py`、15 ケース): 無改変は exit 0。lift_rc=1 / f80=3 / emcc_c_rc=1 / declares_unimpl=5 / declares_unimpl=-1 / defines=24 (閉包 25) / lift_rc="x" / 行欠落 / 9 列に短縮 / 良い行の後に不合格行を追記 / `p.o` 欠落 / `p.final.ll` の define 数改変 の 12 ケースはすべて **exit 1**、ヘッダ改変・入力ファイル無しは **exit 2**。
- NC4 (`matrix_check.py`、5 ケース): 無改変 exit 0。Flanger の closure_funcs +1 / Hyper Chorus の vcall +1 / Fruity Chorus の status lift_rc=1 は **exit 1**、プラグインを 1 本落とす (7 本) は **exit 2**。
- NC5 (`ids_crosscheck.py`、2 ケース): 無改変 exit 0。Frequency Shifter の taint 側 ID 50 の件数を +1 すると **exit 1** (NG)。
- NC6 (`modulation_e2e.sh --judge-only`、2 ケース): 実 `status.csv` は exit 0 で `judge-only: PASS`。 Flanger の emcc_c_rc=1 行を最終行に足した CSV は **exit 1**、 `judge: FAIL 7/8`、出力に `[modulation_e2e] OK` を含まない。
- NC7 (`icall_check.py --gate`、5 ケース): 実データ (既定鎖、脱落 0) は **exit 0**。Flanger の IR から復元 dispatch を除き (従来鎖相当) 間接 call を 0 本 / 9 本注入 (静的 site 10) は **exit 1**、10 本・11 本注入は **exit 0**。
- NC8 (`reach_check.py`、8 ケース): 実データ (Flanger) は既定で検算 OK の **exit 0**、`--gate` は leak ありで **exit 1**。合成グラフ 6 ケース: frontier を越えた先の固有関数 {3, 4} が leak に出る / 辺を除くと空 / 辺のない関数は入らない / A = B' は不一致なし / B' から辺を落とすと A ⊄ B' と A で到達なのに B' で届かないを検出 / A が辺を取りこぼすと B' でだけ届く target を報告。

別系統の突合: Dispatcher ID の独立走査 (§2、8/8 本)、間接 call の線形 sweep (§3.2、240 = 240)、辺抽出のバイト走査による検算 (§3.3、不一致 0)、閉包 6 項目 + batch 4 項目の `PLUGIN_MATRIX.json` 突合 (68/68)。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`) と、host / kernel / 間接 call の静的な数え上げ。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp。範囲外の項目について、本書は何も主張しない。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。Eff_Render 単位の native (ms_abi VA 敷設) ⟷ wasm harness が無く、P0a/P0b/P0c が OPEN | #202 を閉じられない | #195 / #196 / #197 の完了後に #202 を再開 (Closes はその時)。harness は #506 が PM に起票依頼済みの「[PLG-F3a] Eff_Render 単位 native ⟷ wasm 差分 harness」を本 8 本にも適用 (PM 未起票) |
| Render test .flp の E2E (出口条件 4) | 同上 | FLEngine 統合待ち。#202 を継続 |
| 間接 call 脱落: 従来鎖 (`PLUG_ICALL=0`) で静的 240 site → IR 0 (8/8 本)、既定鎖 (PR #539) で 0/8 本 | 解消済み (e2e が回帰ゲート) | #514 は PR #539 でマージ済みだが issue は OPEN。close は PM 判断 |
| engine 4 本の VEX helper 50〜92 (未着手)、define 無し各 2、殻との結合方式 (殻の dynload 2)。`emcc -c` は f80 段で 4/4 本 (35d8f3d5) だが、stub を含む通過 | 4 本 (うち Hyper Chorus は T1) | **#527 [PLG-F5-2] (OPEN、本 PR で追跡)**。同型 #523 / #506 提案の PLG-F3b と PM が統合判断。f80 の 2 本は #197 にも関係する |
| Vintage Chorus / Phaser の engine の f80 各 1 関数 | engine の wasm 化 | #197 (コメント済み) |
| Fruity Flangus の kernel 3 変数 (6 実装、うち 0x5dea40 は x87 を含む) の差分試験記録が `p0c/REPORT.md` に無い | Flangus の kernel 保証 | #197 (コメント済み) |
| host slot 0x120 (Frequency Shifter 1 site) と 0x100 / 0x108 (Flangus・Hyper Chorus 各 1 site) の意味 | host 結合 | #196 (コメント済み) |
| 閉包・frontier の外にある kernel 呼出関数 (FS / HC 各 4 本・5 site、うち 3 関数 4 site は閉包から direct call で到達) と、frontier の先で閉包から到達する hash < 13 DLL の関数 (8/8 本、計 61 関数 / 26,713 B)。FS / HC の kernel 依存は未確定 | 閉包・frontier の定義の取りこぼし (§3.3) | **PM に起票依頼 `[PLG-F5-3]`** (下記)。#195 に訂正コメント投稿済み (前コメントの「参照されない」は誤り) |
| Hyper Chorus (T1) の見積りに engine の工数が含まれるか | 見積り | #202 (PM 判断) |
| 本 dir と `dynamics/` (PR #506、マージ済) で engine_*.sh / matrix_check / ids_crosscheck / env.sh が重複 | 保守 | PM: 共通化の要否を判断 |

**起票依頼 (PM)**: `[PLG-F5-3] Closure boundary: kernel-calling framework functions beyond the frontier and non-shared-hash functions leaking out of the closure (plugin_closure.py)`。背景は §3.3。
受入条件案: (1) frontier の先 (薄いラッパー越し) で閉包から到達する hash < 13 DLL の関数を閉包に含める、または frontier の判定に呼び先ハッシュを含める、(2) `reach_check.py --gate` が 8 本で exit 0、(3) 深部 framework の kernel 呼出 (FS / HC 5 site) を P0a / P0c のどちらの範囲に置くか決める。親 #202、関連 #195 / #197。本 PR の範囲外。

## 8. DEFECTS.md 行案 (候補。追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| E1 icmp ptr/i64 混在 | `icmp eq ptr %x, %argN` (argN は i64) | 本 4 engine で各 4 operand (PR #506 の 2 engine も同型) | emcc "defined with type 'i64' but expected 'ptr'" | 共有鎖 `fix_icmp_ptr.py` (P-E1、main 取り込み済み)。b9fe1d8 で `engine_fixcmp.py` は 0 件 |
| E2 SSA 値入りの定数式 | `__asm_rep_stosq_memset` の引数に `zext (… i64 %v …)` | 8603db1 時点の 4 engine (E1 を直した直後に露見)。b9fe1d8 では未確認 | emcc "zext constexprs are no longer supported" | 未修復 |

## 9. 成果物

| ファイル | 内容 |
|---|---|
| `modulation_e2e.sh` | 8 閉包 → batch_lift → `judge.py` → `closure_facts.py` → `matrix_check.py` → `ids_crosscheck.py` → `icall_check.py --gate` → `reach_check.py` → engine 4 本 (参考・判定外) |
| `judge.py` | 殻の合否判定 (gate)。exit 0/1/2 |
| `modulation_nega.sh` `nega_gates.py` | NC1〜NC8 (`nega_gates.py` は合成入力で各 gate を壊す) |
| `closure_facts.py` `matrix_check.py` `ids_crosscheck.py` `icall_check.py` | 閉包 / host ID / kernel / engine 外形 → `work/modulation/facts.json`、matrix 突合、ID 別算法検算、間接 call 脱落の判定 |
| `reach_check.py` | 閉包の境界の監査 (§3.3): `.pdata` 全関数の辺・バイト走査の検算・閉包からの BFS・leak → `work/modulation/refs/<block>.json` |
| `report_tables.py` | §1〜§4 の表の生成 |
| `engine_judge.py` | engine 4 本の到達性 gate (exit 0/1/2)。`--selftest` は合成入力 8 ケース (good 1 + NC 7)。付録 `REPORT_APPENDIX_527.md` §I |
| `engine_lift.sh` `engine_ranges.py` `engine_fixcmp.py` `engine_defs.py` | engine DLL の全 `.pdata` lift・欠落監査・局所修復 (PR #506 の同名スクリプトと同一手法。共通化は §7) |
| `env.sh` | 環境 (fl-win64 展開・python venv)。 block map は main の `inventory/blockmap_from_matrix.py` を使う |
