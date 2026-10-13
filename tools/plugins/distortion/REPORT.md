# tools/plugins/distortion/REPORT.md — PLG-F6 (#203) distortion + multi-fx 9 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/distortion/` (PLG-F6-2 #545 で共有鎖 `tools/plugins/lift/` も変更) / 検証起点 commit: §1〜§3 は **8db8705** / **c0fcf60**、 §4 と §5 の engine 行は PLG-F6-2 (#545) の **66afda1** (e2e) と本書の commit (§5)
- 再現: `bash tools/plugins/distortion/distortion_e2e.sh` (測定 + 判定。 不合格は非 0) / `bash tools/plugins/distortion/distortion_nega.sh` (ネガティブコントロール) / `python3 tools/plugins/distortion/tables.py` (本書 §1〜§4 の表を出力)
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 環境は `distortion/env.sh`
- 手法の出典: PR #506 (PLG-F3 dynamics, 未マージ) の e2e / matrix_check / ids_crosscheck / engine_lift を踏襲。 #506 の reviewer 指摘 2 点 (判定が不合格でも exit 0 / 判定そのものの NC が無い) は §5 の通り最初から潰した
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし** (閉包の判定は「通る」ことだけで silent miscompile を検出しない。 差分試験は未実施。 §4 の engine 型エラー E1/E2/E5 は emcc が拒否する loud な IR 型エラー、§7)

## 0. 結論 (先出し)

1. **#203 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** PLG-P0a #195 / P0b #196 / P0c #197 が OPEN (2026-10-13 `gh issue view` で確認)。
   Eff_Render 単位の native (DLL を VA 敷設して ms_abi 実行) ⟷ wasm の harness も repo に無い。 → PR は **`Refs #203`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は Delphi 製 9 DLL (8 殻 + Distructor の `module`) すべてで通った** (§1)。 RetDec+pass 鎖 rc 0、`emcc -c` 0、`x86_fp80` 関数 0、
   合計 **336 関数 / 162,247 B**。 未実装 `__asm_*` helper は Love Philter の `__asm_rep_stosb_memset` 1 件のみ (issue 記載と一致、名前まで照合 §5)。
   T0/T1 の 6 本は `PLUGIN_MATRIX.json` の記録 (閉包 6 項目 + batch 4 項目) を再現、T2 の殻 2 本 (Distructor / Effector) は閉包 6 項目を再現し batch の lift 結果は今回初測定、
   **Distructor `module` (18916、116 関数) は閉包ごと今回初測定** (PLUGIN_MATRIX の `lift` 欄は各 plugin の先頭 module のみ)。 突合は 72/72 項目一致。
3. **host 呼出面は P0b の応答表 (`hs_ids.json`) で覆える。** 閉包の即値 Dispatcher ID は {2, 3, 8, 36} の 4 種で全て `hs_ids.json` に有る。 別算法の独立走査は Distructor に ID 48 の `call [reg]` × 2 site を追加で検出 (taint 版に載らない、ID 48 も `hs_ids.json` に有る)。
   動的 ID は Distructor 1 site のみ。 slot 0xc0 (Fast Dist 1 site) は P0b では fail-soft のみ (§2)。
4. **SIMD kernel 表への依存は 5 DLL に限られる**: Distructor 殻 1 / `module` 7 / Soft Clipper 2 / WaveShaper 11 / Love Philter 18 site。 Effector・Blood Overdrive・Fast Dist・Squeeze は閉包にも frontier にも 0 site (§3)。
   この 4 本の DSP は閉包内のインライン SSE に載っていると推定する (未確認)。 kernel 単位の差分試験 (P0c) では保証できず、**Eff_Render 単位の差分試験が必須**。
   **WaveShaper (2+2 site) と Love Philter (1+1 site) は P0c が bit-exact 未達と記録する 0x5dfd30 / 0x5dfdb0 を閉包で呼ぶ** (P0c §10.3: buf_diff 508,385 など。 dd 演算系列が真因)。
   Love Philter は #331 の対象に列挙された 0x5df040 も 1 site 使う。 Love Philter / `module` / Soft Clipper には Balance の 80 kernel にハッシュ対応付けできない呼出が計 7 種 (`raw:`) ある。
5. **C++ DLL 2 本 (Effector engine / Hardcore) は PLG-F6-2 (#545) で `emcc -c` rc 0 になった** (§4)。 真因は共有鎖 `lift/passes/ir5_patch.py` の定数式処理 2 件 (E2 / E5) と E1 (`icmp ptr/i64`) で、3 件とも共有鎖 (`lift/`) で直した。
   残る `x86_fp80` 関数 1 本ずつは `p0c/f80_lower.py` (f64 化) で落とす (精度は x87 の 64bit 仮数 → 53bit。 §4)。 **Hardcore の DSP 閉包は 144 関数 / 28,816 B (`.pdata` 1,726 関数 / 349,625 B の 8.3% / 8.2%)** (§4。 Effector engine は 144 関数 / 28,812 B)。
   未実装 helper は engine 全体で 110 / 102 (VEX 79 / 68) あるが、DSP 閉包が使うのは 11 / 11 (VEX 8 / 8)。 差分試験 (#544) と未実装 helper の実装は未着手。

## 1. 閉包 lift 結果 (Delphi 製 9 DLL)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / Eff_Render) から `call/jmp rel32` で到達する、framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数
(`lift/plugin_closure.py`)。 frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。 vcall / ptr = 間接呼出 site 数 (件数のみ)。 iat = IAT 経由 Win32 呼出 site。

| DLL | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define (うち range 内部の追加) | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Distructor | 18914 | T2 | 16 / 5,737 | 39 / 4,826 | 43 | 8 | 0 | 18 (2) | 0 | 0 | 0 | 2 |
| Distructor module | 18916 | T2 | 116 / 37,137 | 91 / 16,675 | 109 | 54 | 2 | 116 (0) | 0 | 0 | 0 | 5 |
| Effector | 18972 | T2 | 17 / 15,055 | 54 / 17,402 | 26 | 2 | 0 | 17 (0) | 0 | 0 | 0 | 3 |
| Fruity Blood Overdrive | 18987 | T0 | 13 / 8,052 | 48 / 9,170 | 14 | 2 | 0 | 13 (0) | 0 | 0 | 0 | 3 |
| Fruity Fast Dist | 19004 | T0 | 12 / 8,381 | 50 / 10,585 | 10 | 3 | 0 | 12 (0) | 0 | 0 | 0 | 3 |
| Fruity Love Philter | 19024 | T1 | 105 / 59,894 | 145 / 20,916 | 132 | 43 | 3 | 109 (4) | 0 | 1 | 0 | 10 |
| Fruity Soft Clipper | 19078 | T0 | 15 / 5,567 | 44 / 9,176 | 9 | 5 | 0 | 15 (0) | 0 | 0 | 0 | 3 |
| Fruity Squeeze | 19082 | T0 | 21 / 10,011 | 48 / 6,988 | 14 | 7 | 0 | 21 (0) | 0 | 0 | 0 | 3 |
| Fruity WaveShaper | 19089 | T0 | 21 / 12,413 | 63 / 11,508 | 40 | 13 | 2 | 21 (0) | 0 | 0 | 0 | 4 |
| 計 | | | **336 / 162,247** | | | | | 342 | 0 | 1 | 0 | |

- `emcc -c` 列は `emcc -c -O0 -msimd128` の終了コード (0 = 通過)。 **通過 ≠ 正しさ**: 正しさは差分試験でしか示せない (batch_plan §4)。
- final.ll define = `grep -c '^define'`。 括弧は RetDec が range 内部に切り出した関数の追加数 (`engine_defs.py` の extra_inside)。 全 9 DLL で「閉包 range の開始 VA に対応する define が無い」は 0 件、
  かつ define = 閉包関数数 + 追加数 が成り立つ (judge の条件、§5)。 つまり閉包の関数は 1 本も脱落していない。
- Distructor 殻は閉包 16 関数・host call 4 site と小さく、DSP 本体は `module` (18916、116 関数、kernel 7 site) 側にあると推定する (殻と `module` の結合方式は未解析)。
- 直接 Win32 API (`PLUGIN_MATRIX.json` `win_direct_api`): Effector = registry 3 / gdi 6 / clipboard 3 / threads 1 / dynload 2 / file_io 10 (どの module の値かは PLUGIN_MATRIX の定義未確認)。 Hardcore = registry 6 / dynload 3 / file_io 17 / gdi 6 / clipboard 3 / threads 1。 他の殻は 0。

## 2. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。 slot0 = Dispatcher。

| DLL | host call site 計 | slot0 (Dispatcher) 即値 ID (site) | 動的 ID | 他 slot (offset: site) | hs_ids.json に無い ID |
|---|--:|---|--:|---|---|
| Distructor | 4 | 8 (1) | 1 | 0x100: 1, 0x108: 1 | 無し |
| Distructor module | 20 | 3 (2) | 0 | 0x100: 9, 0x108: 9 | 無し |
| Effector | 1 | 2 (1) | 0 | — | 無し |
| Fruity Blood Overdrive | 1 | 2 (1) | 0 | — | 無し |
| Fruity Fast Dist | 2 | 2 (1) | 0 | 0xc0: 1 | 無し |
| Fruity Love Philter | 34 | 2 (1), 36 (1) | 0 | 0x100: 16, 0x108: 16 | 無し |
| Fruity Soft Clipper | 1 | 2 (1) | 0 | — | 無し |
| Fruity Squeeze | 1 | 2 (1) | 0 | — | 無し |
| Fruity WaveShaper | 7 | 2 (1) | 0 | 0x100: 3, 0x108: 3 | 無し |

- 即値 ID の distinct = {2, 3, 8, 36}。 `hs_ids.json` (35 ID) に**不足 0**。
- **別算法の検算** (`ids_crosscheck.py`、taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う): 9/9 DLL で taint 版の ID 件数を取りこぼしなく再現した。
  一致しない差は 1 点で、**Distructor に ID 48 の `call [reg]` が 2 site** (taint 版は host 経由と判定せず未計上)。 host 呼出か別オブジェクトの slot0 呼出かは未判別。
- 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。 0xc0 は P0b では 44 slot 共通の fail-soft + 呼出記録のみ (意味未解析)。

## 3. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` (kernel 変数経由・関数ポインタ slot 経由・直接 call の 3 経路) を再利用し、call site の所在関数を閉包 ranges / frontier で分類。
kernel 番号は Balance (block 18983) の VA に正規化。 DLL 側 VA を Balance の 80 kernel にハッシュ対応付けできなかった呼出は `raw:<その DLL の VA>` と表記 (別 DLL と番号が衝突しうる)。

| DLL | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査 site / kernel 種 |
|---|--:|---|--:|---|
| Distructor | 1 | 0x5dfae0 (1) | 0 | 23 / 2 |
| Distructor module | 7 | 0x5de390 (2), 0x5de4b0 (1), raw:0x5fc000 (2), raw:0x5fcdc0 (2) | 0 | 42 / 15 |
| Effector | 0 | — | 0 | 22 / 1 |
| Fruity Blood Overdrive | 0 | — | 0 | 22 / 1 |
| Fruity Fast Dist | 0 | — | 0 | 22 / 1 |
| Fruity Love Philter | 18 | 0x5de390 (2), 0x5de4b0 (1), 0x5dee50 (1), 0x5df040 (1), 0x5dfb60 (1), 0x5dfbe0 (1), 0x5dfd30 (1), 0x5dfdb0 (1), raw:0x6286f0 (2), raw:0x6288c0 (2), raw:0x6294b0 (3), raw:0x6295f0 (2) | 2 | 60 / 24 |
| Fruity Soft Clipper | 2 | 0x5dfae0 (1), raw:0x5dfb60 (1) | 0 | 26 / 4 |
| Fruity Squeeze | 0 | — | 0 | 22 / 1 |
| Fruity WaveShaper | 11 | 0x5de390 (2), 0x5de4b0 (1), 0x5dfb60 (2), 0x5dfbe0 (2), 0x5dfd30 (2), 0x5dfdb0 (2) | 0 | 53 / 18 |

- `scan_dll` の出力は `nvars=45 / nimpls=80 / kernels_hash_ok=80 / bad=0` (Distructor `module` / Love Philter / WaveShaper / Soft Clipper の 4 DLL で確認。 他 5 DLL は未確認)。 `raw:` の呼出は計 7 種 (`module` 2 / Love Philter 4 / Soft Clipper 1)。
  80 kernel とハッシュは全て一致しているので、Balance の VA へ写す規則 (ハッシュ → 最初の VA) で取れない同一ハッシュの別 VA (twin) と推定する (未確認)。
- 0x5de390 (22 site) は 9 DLL 共通で、閉包にも frontier にも属さない (framework 側の深い関数と推定、未確認)。

P0c (`p0c/REPORT.md`) で見た各 kernel の現状 (本 PR では再測定していない):

| kernel | P0c の記録 |
|---|---|
| 0x5de390 / 0x5de4b0 | f64mem。 0x5de390 は実機械語 ⟷ x87 版 / f64 lowering 版とも差分 0 / 300,000 (§3)。 f64mem 全体では ±1 ulp 0.018% を許容条件として記録 |
| 0x5dfae0 | transc。 f32 出力で 0 / 200,000 (§3) |
| 0x5dfb60 | k80_diff.py で bit-exact (§9) |
| 0x5dfbe0 | rc_chop。 `f80_lower.py --ext` で bit-exact (§10.0) |
| 0x5dfd30 / 0x5dfdb0 | **bit-exact 未達** (§10.0: 真因は dd 演算系列。 0x5dfdb0 は ext 全機能で buf_diff 508,385、§10.3)。 **WaveShaper 各 2 site / Love Philter 各 1 site が閉包で使う** |
| 0x5df040 | #331 の対象に列挙 (P0c §14.4 の記述)。 **Love Philter が閉包で 1 site 使う** |
| 0x5dee50 | P0c REPORT に個別記述を見つけられなかった (grep で 0 件)。 Love Philter が 1 site 使う |

## 4. C++ DLL 2 本 (Effector engine / Hardcore) — PLG-F6-2 (#545) で更新

両者とも MSVC C++ (VS2019, link 14.29)、export は `CreatePlugInstance` 1 つ、import に USER32 / GDI32 を含む (GUI を持つ)。 Effector engine の殻との結合方式 (LoadLibrary 経路) は未解析。

| DLL | block | サイズ B | `.text` B | `.pdata` 関数 / B | import (DLL: 件数) |
|---|--:|--:|--:|--:|---|
| Effector engine | 18973 | 498,176 | 273,056 | 1,305 / 251,711 | KERNEL32: 79, USER32: 31, GDI32: 11, ADVAPI32: 3, SHELL32: 1, ole32: 3 |
| Hardcore | 19101 | 641,536 | 376,416 | 1,726 / 349,625 | KERNEL32: 95, USER32: 31, GDI32: 11, COMDLG32: 2, ADVAPI32: 3, SHELL32: 2, ole32: 3 |

| DLL | RetDec rc | final.ll define | `.pdata` で define 無し (関数 / B) | f80 関数 (lowering 後) | 未実装 helper | `emcc -c` | lowering 前の f80 関数 / `emcc -c` | lift 秒 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Effector engine | 0 | 1,362 | 0 / 0 | 0 | 110 (うち VEX 79) | 0 | 1 / 1 | 42 |
| Hardcore | 0 | 1,780 | 0 / 0 | 0 | 102 (うち VEX 68) | 0 | 1 / 1 | 62 |

`engine_lift.sh <block>` は全 `.pdata` 関数を共有鎖 `lift/lift_ranges.sh` (RetDec+pass 鎖、`PLUG_F80_LOWER=1`) → `emcc -c` に通す。 「`.pdata` で define 無し」= range の開始 VA に define が無い数 (分母は `.pdata` 関数数)。
**この数は PLG-F6-2 で 1 → 0 になった**: 旧 1 関数 (61 B、MSVC の `_DllMainCRTStartup` 相当 = PE のエントリ) は脱落ではなく、RetDec が `@entry_point` と名付けていただけ (`engine_defs.py` が先頭ラベル `dec_label_pc_<VA>` で数える。 脱落ではないので扱いは不要: DSP ではなく、閉包にも入らない)。
`final.ll` の lowering 前は `e.pre_f80.ll`。 `lift_s` の 42 / 62 は PLG-F6-2 の実測 (RetDec の再実行を含む 1 回。 §5)。

PLG-F6-2 の修復 (起点 = §4 旧版の失敗連鎖 E1 → E2 / E5。 clang は最初の型エラーで止まるので 1 件ずつ露見した):

| 類型 | 原因 (実測) | 修復 | 回帰テスト (ネガコン付き) |
|---|---|---|---|
| E1 `icmp ptr %p, %i64arg` | 仮引数が i64 で、`icmp` だけ ptr 型 | `lift/passes/fix_icmp_ptr.py` (旧 `engine_fixcmp.py` を共有鎖へ移設、`lift_ranges.sh` の `fix_ptr_params` の直後) | `test_fix_icmp_ptr.sh`: 修復前 emcc rc 1 / 修復後 0 |
| E5 `%x = zext 0 to i64` (型の無い zext、Hardcore `function_180018de0` 1 site) | `ir5_patch.py` `fold_const_ops` が、畳めない外側の式 (`zext (i32 trunc (... add (zext (i32 xor (a, a))...`) を見つけると**内側を読み飛ばす** (`pos = j + 1`)。 A4 が `xor (a, a)` を `0` に畳んだ後の `zext (i32 0 to i64)` が畳まれず、A9L が型を捨てた `zext 0 to i64` を出す | `pos = idx + 1` (内側も走査) | `test_ir5_constexpr.py` E5 ケース |
| E2 SSA 値入りの `zext` 定数式 (`__asm_rep_stosq_memset` の引数、Effector engine 1 / Hardcore 1 site) | `ir5_patch.py` `lift_residual_constexpr`: `bitcast (ptr @g to ptr)` の除去は命令を挿入せず**行だけを変える**が、`if ins:` でしか書換え後の行を採用しなかったので、最内の constexpr が bitcast のまま止まり、外側の `icmp`/`zext` が命令化されず残った (`ir5_patch` 自身の集計で `残存 61 件`) | `if ins or newln != ln:` | 同 E2 ケース |

`test_ir5_constexpr.py`: 修復後の `ir5_patch.py` は 2 ケースとも欠陥 0、修復前 (`BASE=e64ef6f`) は 2 ケースとも欠陥を再現 (E5 = 型の無い zext、E2 = 残存 constexpr 9 件)。 `BASE=HEAD` (修復済み) を与えると exit 1 (テストが欠陥を検出できないと不合格になる)。
共有鎖を変えたので殻 9 本の回帰を取った: `distortion_e2e.sh` の殻の判定は 9/9 合格、`emcc_c` は 9 本とも 0 のまま (§5)。

f80 (x87) の扱い: lowering 前の `emcc -c` は wasm backend が `fpext double→x86_fp80` と `frem f80` を legalize できず落ちる (`do not know how to soften fp_extend` / `no libcall available for frem with type f80`)。
`PLUG_F80_LOWER=1` で `p0c/f80_lower.py` (x86_fp80 → double、既定 off) を通すと両 DLL とも `emcc -c` rc 0・f80 関数 0。 **f80 は精度を落とす** (64bit 仮数 → 53bit): 該当の 1 関数ずつ (`function_180040200` / `function_1800591f0`、各 209 行) は **DSP 閉包に入らない** (下の閉包の関数集合との照合で 0 件。 呼び元 `function_180021141` / `function_180033231` も閉包外)。 閉包の DSP には f64 化の精度影響が及ばない、と推定する (閉包内の fp 演算が f64 / SSE のみであることは未確認)。

DSP 閉包 (`closure_cpp.py`、C++ 用のエントリ抽出。 `plugin_closure.py` は Delphi の vtable 前提のため別実装):
CreatePlugInstance は `.pdata` に無い `jmp rel32` のサンクなので飛び先から depth 3 まで辿り、ctor が書く vptr (`lea R,[rip+d]; mov [X],R`) の vtable 3 本 (各 23 / 17 / 22 slot) を seed にし、
slot の関数から `call/jmp rel32` で到達する `.pdata` 関数を BFS する (関数内で参照される別 vtable の slot も加える = over-approximate)。 vtable = `.rdata` 内の「`.text` を指す qword」の連続で `.pdata` 開始 VA を 1 つ以上含むもの。

| DLL | seed vtable | 閉包 vtable | 閉包 関数 / B | `.pdata` 全体に対する割合 (関数 / B) | 間接 call site | IAT call site | 閉包の range に define 無し |
|---|--:|--:|--:|--:|--:|--:|--:|
| Effector engine | 3 | 7 | 144 / 28,812 | 11.0% / 11.4% | 82 | 48 | 0 |
| Hardcore | 3 | 7 | 144 / 28,816 | 8.3% / 8.2% | 82 | 48 | 0 |

- 割合の分母は上表の `.pdata` 関数 / B (1,305 / 251,711 と 1,726 / 349,625)。 2 DLL の閉包が同形 (144 関数・vtable 7) なのは、Hardcore が Effector engine と同じ engine 骨格を持つため (閉包の関数は VA は違うがサイズが近い、と推定。 ハッシュ照合は未実施)。
- 間接 call 82 site (vtable 経由と推定、未確認) は閉包の外へ出うる。 閉包は**直接 call の到達集合**で、`.pdata` 外の leaf (`ret 0` / `xor eax,eax` の slot、8 slot) は関数に数えない。 DSP の本体 (Eff_Render 相当の slot) の特定と差分試験は #544。
- **VEX**: 命令に `v` で始まる mnemonic を持つ `.pdata` 関数は Effector engine 13 / Hardcore 12 (`vex_scan.py`)。 うち **AVX 検出フラグ (cpuid + xgetbv の両方を持つ関数が書く .data の dword) を `cmp` で見て分岐するもの 11 / 10**、見ない (無条件に VEX を実行する) ものは各 2 関数 (Hardcore: 0x18005aef0 / 0x18005b0e0) で、**DSP 閉包に入る VEX 関数は各 2、うち無条件のものは 0**。
  閉包の VEX 関数 2 つのうち 1 つ (Hardcore 0x1800594d0) は `cmp [flag],0; jne <VEX 路>` の先に SSE 路 (`movdqa` / `psrld` / `psubd`) を持つ。 もう 1 つ (0x180036130、1,653 B) は `vmovdqu`/`vmovntdq` を使うメモリ操作 (memcpy 相当と推定、未確認) で、フラグを `cmp [..], 3` で見る。
  **決定: AVX 検出フラグを 0 に固定した前提で lift する (= SSE 路を使う)** 方式は成立する見込み。 ただし RetDec は両路を lift するので、VEX 路の `__asm_v*` helper 宣言は未実装のまま残る (リンクが要るなら `unreachable` 化か helper 実装)。 **この lift では固定を実装していない** (フラグの値は未定義のまま)。 実装は別 issue (§6)。
  未実装 helper 110 / 102 のうち DSP 閉包の関数が呼ぶのは 11 / 11 (VEX 8: `vcomiss vcvtdq2ps vmovaps vmovd vmovd__N vpand vpsrld vpsubd`、非 VEX 3: `int int3 movntps`)。 CPUID 分岐は VEX と SSE 路の両方が閉包にあるので、固定すれば VEX 8 件は不要と推定する (未確認)。

## 5. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner・逐次実行で並列数 1)

| 項目 | 実測 |
|---|---|
| 前提 inventory (初回のみ。 fl-win64 tarball 展開 + `win_scan` / `win_funcs` / `win_unique` / `win_abi` / `kernel_table` 生成を含む) | `inventory.sh` **9 m 10.5 s** (user 35 m 2 s)。 `win_funcs.py` が並列で走り、`uptime` で観測した load average (1 分) の最大は 17.23。 以降の run は生成済みを再利用 |
| `distortion_e2e.sh` 全体 (HEAD 8db8705 = c0fcf60 の e2e 系、inventory 済、3 回連続) | **4:29.80 / 4:29.74 / 4:26.43**、いずれも exit 0。 開始時 load average (1 分) 0.32 / 1.01 / 1.12。 内訳のうち 9 閉包 lift は 34–36 s (seconds 列の合計)、C++ DLL 2 本の lift は 96–98 s (下行の秒の合計)。 すべて逐次 (並列数 1)。 参考: コミット前の作業ツリー (`unimpl_names.py` 追加前) の 1 回目は 4:31.96 |
| lift 秒 (`status.csv` の seconds、3 回の min–max) | Distructor 2–3 / `module` 5–5 / Effector 3–4 / Blood Overdrive 2–3 / Fast Dist 2–3 / Love Philter 9–10 / Soft Clipper 2–3 / Squeeze 3–3 / WaveShaper 4–4 (9 本計 34–36 s)。 Effector engine 39–40 s、Hardcore 57–58 s |
| 3 回の結果一致 | 判定列 (`status.csv` の seconds 以外)・`shell_audit.csv`・`facts.json`・`engines.csv` (lift_s 以外) の sha256 先頭 16 桁は 3 回とも同一 (facts `6650e975d4e86b1e` / status `5a51892da5bfae1d` / audit `a5f384f76704ec66` / engines `f8063cfae5009545`) |
| 判定 (各回) | `judge.py` 9/9 block 合格 → `unimpl_names.py` 9/9 → `matrix_check.py` **72/72** 項目一致 (閉包 6 項目 × 8 plugin + batch 4 項目 × 6 plugin) → `ids_crosscheck.py` 9/9 → `judge.py --engines` 2/2 |
| `distortion_nega.sh` (HEAD c0fcf60、e2e の直後) | exit 0、**9.08 s**、**37/37** 項目 (下表) |

ネガティブコントロール (数値は `distortion_nega.sh` の出力。 判定系は「期待した理由の文言で落ちたか」まで照合する):

| NC | 内容 | 結果 |
|---|---|---|
| NC-J (18 件) | `distortion_e2e.sh --judge-only` に、実測 status.csv を 1 点だけ壊した入力を与える。 対照 (無改変) は exit 0 + 最終行 OK。 壊し方: `emcc_c_rc`=1 / `lift_rc`=1 (殻と `module`) / `f80_funcs`=3 / `declares_unimpl`=5・許容超過 (Love Philter 2 > 1)・-1 / `defines`=0・9999 / 非整数 / 行の削除・重複・対象外 block の追加 / 欠落監査 csv の `missing_define`=1・`function_defines`+1・`extra_inside`=0 / ヘッダ破損 | 壊した 17 件はすべて exit 1 (ヘッダ破損のみ入力不正の exit 2)、最終行 OK なし、期待した理由の文言が出力に有り |
| NC-JE (5 件) | engines.csv の判定。 対照 exit 0。 `lift_rc`=1 / `defines`=0 / 集計不能 (-1) / 行削除 | 4 件とも exit 1 |
| NC-N (5 件) | `unimpl_names.py`。 対照 exit 0。 別名の helper (stosb→stosw) / 未実装 0 の block に名前を追記 / 件数 1 だが名前の行が無い / log 無し | 4 件とも exit 1 |
| NC-E | Soft Clipper (19078) の `final.ll` の 1 関数の `ret` を除去 | `emcc -c` rc **0 → 1** |
| NC-R | 19078 の閉包 ranges 14 本の末尾 1 本 (`function_6c11c0`) を落として再 lift | その define 1 → 0、全体 define **15 → 13** (RetDec は 1 range から 2 define を出すことがあり差は 1 と限らない) |
| NC-I | `ids_crosscheck.py` に Distructor の ID 8 の件数を 1 → 2 にした facts を与える | exit 0 → **1** (9/9 → 8/9) |
| NC-M | `matrix_check.py`: Distructor の `closure_funcs` +1 / Fast Dist の `emcc_c_rc` を 1 にした status | 72/72 → **71/72** (exit 1)、後者も 71/72 (exit 1) |
| NC-D | `engine_defs.py` に実在しない range を 1 本足す | `missing_define` **1 → 2** |
| NC-W | e2e 本体 (`--skip-lift`) に、Fast Dist の最終行が `emcc_c_rc`=1 の lift 結果を与える | e2e 全体が exit 1、最終行 OK なし、`FAIL  block 19004 … emcc_c_rc=1` を表示 (#506 で露見した「判定が落ちても e2e が exit 0」の再発防止) |

衛生 (HEAD c0fcf60 + 本書): `git status --porcelain=v1 -- tools/plugins/distortion` は本書のみ未追跡、`git diff 042f869 HEAD --stat` の範囲は `tools/plugins/distortion/` のみ、`find tools/plugins/distortion -type f -size +1M` は 0 件。 大物は `tools/plugins/work/` (gitignore)。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`)・閉包 range の脱落監査・host / kernel 依存の静的な数え上げ・C++ DLL の到達性。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp、Hardcore の DSP 閉包の特定。 範囲外の項目について、本書は何も主張しない。

### 5.2 PLG-F6-2 (#545) の検証 (コミット済み HEAD **66afda1**、4 core / 15 GiB の Actions runner、逐次 = 並列数 1)

| 項目 | 実測 |
|---|---|
| inventory (初回: fl-win64 展開済み + 生成物なし) | `inventory.sh` **8:51.11** (`/usr/bin/time -v`、exit 0)。 load average (1 分) は実行中の観測で最大 16.40 |
| `distortion_e2e.sh` (HEAD 66afda1、inventory 済、RetDec 再実行を含む 1 回) | **5:10.69**、exit 0、最終行 `[distortion_e2e] OK`。 開始時 load average (1 分) 0.35。 殻 9 本 `judge.py` **9/9** 合格・`unimpl_names.py` 9/9・`matrix_check.py` / `ids_crosscheck.py` 通過・engine `judge.py --engines` **2/2** 合格・`closure_cpp` 判定 **2/2** 合格 |
| engine の lift 秒 (`engines.csv`) | Effector engine 42 / Hardcore 62 (各 1 回。 §4 旧版の 39–40 / 57–58 とほぼ同じで、 f80 lowering と icmp pass の追加分は秒単位では見えない) |
| `distortion_nega.sh` (HEAD 66afda1、e2e の直後) | exit 0、**9.74 s**、**44/44** 項目 (旧 37 + NC-JE の 3 列 + 理由照合 3 + NC-C 1。 下表) |
| `lift/passes/test_ir5_constexpr.py` | exit 0。 修復後は E5 / E2 とも欠陥 0、修復前 (`BASE=e64ef6f`) は 2 ケースとも欠陥再現。 `BASE=HEAD` (修復済み) では exit 1 |
| `lift/passes/test_fix_icmp_ptr.sh` | exit 0。 修復前 emcc rc 1 (`'%arg1' defined with type 'i64' but expected 'ptr'`) / 修復後 rc 0 |

追加の NC (`distortion_nega.sh`): NC-JE に 3 列 (engines.csv の `emcc_c_rc`=1 / `missing_define`=1 / `f80_funcs`=1 → いずれも exit 1 かつ出力にその列名の理由) を追加。 **#545 以前は engine の判定が `emcc_c_rc` を合否に使わず常に PASS だった**
(「判定が不合格でも exit 0 になる gate」の再発防止として、#545 の受入条件 (emcc_c_rc / missing_define / f80_funcs) を合否にし、 `emcc_c_rc`=1 を与えると落ちることを NC で固定した)。
NC-C: `closure_cpp.py` の seed 探索深さを 0 にすると `seed_vtables=0` で exit 1 (対照 exit 0)。 **範囲外の NC**: 閉包の関数集合が正しいか (取りこぼし・過剰) は NC では示せない。 別アルゴリズムの検算は未実施 (§6)。

e2e の殻の監査 (`shell_audit.csv`) は #514 (icall 書換えが batch_lift の既定 ON) 以降 `extra_inside` が閉包 range と一致せず、Distructor 18914 / Love Philter 19024 が FAIL になることを PLG-F6-2 の run 2 回目で確認した
(書換え後 PE の range で RetDec が追加 define を名付けるため。 閉包 16 → define 18 / 105 → 109)。 `engine_defs.py --also-ranges` (icall 書換え後の range も照合) で直した。 #514 (icall 書換えを batch_lift の既定にした、commit 237010e) は #520 の e2e 実測 (8db8705) の約 1 分後に入ったため、#520 の §5 の「3 回連続 exit 0」には反映されていない (main の `distortion_e2e.sh` は #514 以降未実行と推定。 main HEAD での再実行はしていない)。 `status.csv` の列も 10 → 12 (`icall,dispatch_calls`) に増えており、`judge.py` の列定義も合わせた。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 Eff_Render 単位の native / wasm harness が無く、P0a/P0b 未完 | #203 を閉じられない | #195 / #196 / #197 の完了後に #203 を再開 (Closes はその時)。 harness は新規 **#544 [PLG-F6-1]** に起票 (#506 §6 が提案する PLG-F3a と共通化できるので統合は PM 判断) |
| Render test .flp の E2E (出口条件 4) | 同上 | FLEngine 統合待ち。 親 #14 / #203 |
| ~~Effector engine / Hardcore の `emcc -c` 未通過~~ | — | **#545 で解消** (`emcc -c` rc 0・`missing_define` 0。 §4)。 ただし未実装 helper (VEX 含む 110 / 102) は宣言のみで未実装 → 下の行 |
| ~~Hardcore の DSP 閉包が未算出~~ | — | **#545 で算出** (144 関数 / 28,816 B。 §4)。 取りこぼし・過剰の検算 (別アルゴリズム) と、vtable の slot が何の関数か (Eff_Render 相当の特定) は未実施 → **#544 [PLG-F6-1]** にコメント |
| 未実装 helper の実装 (engine 110 / 102。 DSP 閉包が呼ぶのは VEX 8 + 非 VEX 3 / 同) と AVX 検出フラグの 0 固定 (§4 の決定) | wasm のリンク・実行 | **#197 (PLG-P0c) にコメント** (helper の実装は `msimd` 側の仕事。 共有する `__asm_v*` は #534 / #523 / #527 / #540 と共通) |
| f80 → f64 lowering の精度 (x87 の 64bit 仮数 → 53bit) | f80 関数 (各 1) は DSP 閉包の外なので DSP には及ばないと推定 (未確認) | #544 の差分試験で確認 |
| 共有鎖の修復 (E1 / E2 / E5) を、#534 (PLG-G2-2) / #523 / #527 / #540 が個別に直していないか | 同じ類型の重複修復 | PM 判断: 本 PR の `lift/passes/ir5_patch.py` / `fix_icmp_ptr.py` を先に merge すると、各 PR は rebase のみ。 #534 の run 2 本が並行しており衝突の可能性あり (本書執筆時点で #534 のブランチ push は無し) |
| `ir5_patch.py` の定数式 pass の他の読み飛ばし | `pos = j + 1` 型の読み飛ばしが `fold_const_ops` 以外に無いか未監査 | 新規起票しない (次に同類型が出たら #197 に追記) |
| `batch_lift.sh` (#514) 以降の `distortion_e2e.sh` が main で未実行だった (§5.2) | main の e2e が落ちていた (本 PR で修復) | 本 PR (Refs #545) |
| Distructor 殻と `module` (18916) の結合方式 | DSP がどちらにあるかの確定 | #544 (差分 harness の設計時に結合方式を解析する) |
| Love Philter の `__asm_rep_stosb_memset` (未実装 helper) | wasm 化 | #197 にコメント (issue 記載の memset 写像で足りるか) |
| 0x5dfd30 / 0x5dfdb0 の bit-exact 未達 (P0c §10.3) を WaveShaper 各 2 / Love Philter 各 1 site が閉包で使う | 両 plugin の出口条件 (bit-exact か許容条件の記録) | #197 にコメント (両 kernel の残差を許容条件にするか再実装かの判断が要る) |
| 0x5df040 (Love Philter が閉包で 1 site 使用) の P0c 残差 | Love Philter の kernel 保証 | #331 に依存を追記 |
| `raw:` kernel 呼出 7 種 (§3) が Balance の 80 kernel の twin か未確認 | kernel 依存の数え上げ | #197 にコメント |
| Distructor の ID 48 × 2 site (taint 版に載らない)・slot 0xc0・動的 ID 1 site の意味 | host 呼出面 | #196 作業 5 (0x13173a0 全 case 解析) に追記 |
| 0x5de390 の 22 site の所在 (閉包外・frontier 外) | §3 の解釈 | #197 / #195 の統合時に所在関数を特定 |
| `nsis_names.py` が Actions 上で動かない (`block_manifest.json` 不在) | inventory の再現性 | `mk_blockmap.py` で回避済み (#506 と同じ)。 `docs/WORKFLOW.md` §11 への追記は PM 判断 |
| `env.sh` / `mk_blockmap.py` / `engine_*.py` が #506 の `tools/plugins/dynamics/` と重複 (#506 が未マージのため複製) | 保守 | #506 マージ後に `tools/plugins/` 共通へ寄せる別 PR |
| `docs/DOC_MAP.md` の REPORT 索引に本書が未掲載 | 索引漏れ | PM が追記 (並行 run との衝突を避け本 PR では触らない) |

## 7. DEFECTS.md 行案 (候補・loud な IR 型エラー。 追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| E1 icmp ptr/i64 混在 | `icmp eq ptr %x, %argN` (argN は i64) | Effector engine 6 operand / Hardcore 11 operand | emcc "defined with type 'i64' but expected 'ptr'" | **修復済み**: `lift/passes/fix_icmp_ptr.py` (共有鎖)。 `test_fix_icmp_ptr.sh` |
| E2 SSA 値入りの定数式 | `__asm_rep_stosq_memset` の引数に `zext (… i64 %v …)` | Effector engine 1 site / Hardcore 1 site | emcc "zext constexprs are no longer supported" | **修復済み**: `ir5_patch.py` `lift_residual_constexpr` (`bitcast` 除去だけで行が変わる時に反復が止まる欠陥)。 `test_ir5_constexpr.py` |
| E5 型の無い zext | `%x = zext 0 to i64` | Hardcore `function_180018de0` 1 site | emcc "expected type" | **修復済み**: `ir5_patch.py` `fold_const_ops` (畳めない外側の式の内側を読み飛ばす `pos = j + 1`)。 `test_ir5_constexpr.py` |

## 8. 成果物

| ファイル | 内容 |
|---|---|
| `distortion_e2e.sh` | inventory → 9 閉包 → batch_lift → `judge.py` (殻) → `unimpl_names.py` → `closure_facts.py` → `matrix_check.py` → `ids_crosscheck.py` → C++ DLL 2 本 → `judge.py --engines`。 判定が落ちたら非 0 で終わり、最終行 `OK` は出ない。 `--skip-lift` / `--judge-only` あり |
| `judge.py` | status.csv / engines.csv の合否判定 (不合格で exit 1、入力不正で exit 2) |
| `unimpl_names.py` | 未実装 helper の名前を許容リストと突合 (`judge.py` は件数のみ) |
| `distortion_nega.sh` | ネガティブコントロール (§5) |
| `closure_facts.py` `tables.py` | 閉包 / host ID / kernel 依存 / C++ DLL 外形 → `work/distortion/facts.json` / §1〜§4 の表 |
| `matrix_check.py` `ids_crosscheck.py` | `PLUGIN_MATRIX.json` との突合 (閉包 6 項目 + batch 4 項目) / Dispatcher ID の別算法検算。 どちらも `--facts` / `--status` を取る |
| `engine_lift.sh` `engine_ranges.py` `engine_defs.py` | C++ DLL の全 `.pdata` lift (共有鎖 + f80 lowering)・欠落監査 (`engine_defs.py` は殻の閉包にも使う) |
| `closure_cpp.py` `vex_scan.py` | C++ DLL の DSP 閉包 (vptr → vtable → 直接 call の到達集合。 NC 用に `CLOSURE_CPP_SEED_DEPTH`) / VEX 関数と AVX 検出フラグ分岐の実測 |
| `../lift/passes/{fix_icmp_ptr.py,test_ir5_constexpr.py,test_fix_icmp_ptr.sh}` | 共有鎖への E1 修復と、E2 / E5 (`ir5_patch.py`) の回帰テスト (NC 付き)。 `lift_ranges.sh` に `PLUG_REUSE_DRC` / `PLUG_F80_LOWER` を追加 |
| `inventory.sh` `mk_blockmap.py` `env.sh` `targets.py` | `block_manifest.json` 不要の inventory 前提 / 環境 / 対象表 (block・Tier・許容) |
