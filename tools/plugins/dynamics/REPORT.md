# tools/plugins/dynamics/REPORT.md — PLG-F3 (#200) dynamics 7 本: lift 前提の実測

> **正本**: `tools/plugins/dynamics/REPORT.md`。詳細は §4 / 付録 `tools/plugins/dynamics/REPORT_APPENDIX.md` §A。

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/dynamics/` のみ / 検証起点 commit: **b2094ba** (判定を gate にした `judge.py` 新設 + `dynamics_e2e.sh`・`dynamics_nega.sh` 修正後。 §5 の実測はすべてこの HEAD の detached worktree)
- 旧 HEAD (18b1cb3 / 2ba3978) の「exit 0」は、当時の判定が不合格でも exit 0 になる実装だったため合格の根拠から外し、b2094ba の実測に置き換えた (旧値は 16b79f0 の本書)
- 再現: `bash tools/plugins/dynamics/dynamics_e2e.sh` (判定 + 実測。 不合格・行欠落は exit 1) / `bash tools/plugins/dynamics/dynamics_nega.sh` (ネガティブコントロール NC1〜NC3)
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 環境は `dynamics/env.sh`
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし** (§7 の 3 件は emcc が拒否する loud な IR 型エラーで、silent miscompile ではない。
  差分試験を未実施のため D1〜D16 / batch_plan §4 の ARG・IND に該当するかは未確認)

## 0. 結論 (先出し)

1. **#200 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** PLG-P0a #195 / P0b #196 /
   P0c #197 が OPEN で、`framework/REPORT.md` §0 は「`TFruityPlug*` 実体生成 未達 / Eff_Render 差分 未実施」と記録している。
   Eff_Render 単位で native (DLL を VA 敷設して ms_abi 実行) と wasm を比べる harness も repo に無い (`lift/t0_balance/` は kernel 単位)。
   → PR は **`Refs #200`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は 7/7 本で通った。** Delphi 殻 7 本すべてで RetDec+pass 鎖が完走 (lift_rc 0)、`emcc -c` 通過、
   `x86_fp80` 関数 0、未実装 `__asm_*` helper 宣言 0。 合計 **312 関数 / 154,522 B** (§1)。
   T0/T1 の 5 本は `PLUGIN_MATRIX.md` の記録を再現、**T2 の殻 2 本 (Multiband Compressor / Transient Processor) は今回初測定**。
   閉包の関数数・バイト数・frontier・呼出数は `PLUGIN_MATRIX.json` の `lift` 欄と 7 本 × 6 項目すべて一致。
3. **host 呼出面は P0b の応答表で覆える。** 閉包が即値 ID で発行する Dispatcher ID は taint 版で {2, 30, 36, 38, 50} の 5 種 15 site、
   別算法の独立走査はこれに加えて ID 59 (Maximus・Soundgoodizer 各 2 site) を検出した。 6 種すべて `hostshim/hs_ids.json` の 35 ID に含まれる (§2)。 動的 ID は 4 site。 slot 0x80 (Emphasis 1 site) / 0x120 (Limiter・Compressor 各 1 site) は P0b では fail-soft のみ。
4. **SIMD kernel 表への依存は 3 本に限られる。** 閉包内の kernel 呼出は Limiter 1 / Maximus 5 / Soundgoodizer 5 site で、
   Compressor・Emphasis・Multiband・Transient は閉包にも frontier にも 0 site (§3)。 この 4 本は DSP 本体が閉包に載っていると推定する
   (frontier の先の framework 内部は未追跡)。 その場合 kernel 単位の差分試験 (P0c) では保証できず、**Eff_Render 単位の差分試験が必須**。
   Maximus / Soundgoodizer が使う 0x5dee90 は P0c の汎用 harness で `buf_diff`=2,565,360 が未解決 (#331)。
5. **T2 の C++ engine 2 本は RetDec まで通るが `emcc -c` は未通過** (§4)。 engine は 3 類型の IR 型エラーが連鎖し、
   VEX (AVX/FMA) の未実装 helper 宣言が Transient 57 / Multiband 31 (distinct) ある。 T2 の見積 4 人日/本には engine 側の未知工数が残る。

## 1. 閉包 lift 結果 (Delphi 殻 7 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / Eff_Render)
から `call/jmp rel32` で到達する、framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。
frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。 vcall / ptr = 間接呼出 site 数 (件数のみ記録)。 iat = IAT 経由 Win32 呼出 site。

| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Fruity Limiter | 19021 | T0 | 27 / 15,869 | 63 / 9,926 | 38 | 40 | 0 | 27 | 0 | 0 | 0 |
| Fruity Compressor | 18990 | T1 | 31 / 11,887 | 47 / 7,640 | 17 | 4 | 0 | 31 | 0 | 0 | 0 |
| Maximus | 19148 | T1 | 84 / 46,094 | 114 / 20,001 | 128 | 100 | 2 | 84 | 0 | 0 | 0 |
| Soundgoodizer | 19245 | T1 | 65 / 29,732 | 81 / 13,434 | 78 | 77 | 2 | 65 | 0 | 0 | 0 |
| Emphasis | 18974 | T1 | 60 / 25,572 | 82 / 18,013 | 65 | 9 | 0 | 60 | 0 | 0 | 0 |
| Fruity Multiband Compressor (殻) | 19047 | T2 | 19 / 9,515 | 51 / 6,814 | 33 | 3 | 0 | 19 | 0 | 0 | 0 |
| Transient Processor (殻) | 19251 | T2 | 26 / 15,853 | 63 / 13,447 | 37 | 7 | 0 | 26 | 0 | 0 | 0 |
| 計 | | | **312 / 154,522** | | | | | 312 | 0 | 0 | 0 |

- 最右列は `emcc -c -O0 -msimd128` の終了コード (0 = 通過)。 **通過 ≠ 正しさ**: 正しさは差分試験でしか示せない (batch_plan §4)。
- 所要 (lift_ranges.sh のみ) と e2e 全体の秒は §5。
- 殻の直接 Win32 API (`PLUGIN_MATRIX.json` `win_direct_api`): Multiband = dynload 10 / file_io 17、Transient = process 1 / dynload 2 / file_io 4。 他 5 本は 0。

## 2. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を
閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。 slot0 = Dispatcher。

| プラグイン | host call site 計 | slot0 (Dispatcher) site: 即値 ID (site 数) | 動的 ID | 他 slot (offset: site) |
|---|--:|---|--:|---|
| Fruity Limiter | 11 | 2 (1) / 30 (2) / 50 (1) | 0 | 0x100: 3, 0x108: 3, 0x120: 1 |
| Fruity Compressor | 4 | 2 (1) / 50 (1) | 1 | 0x120: 1 |
| Maximus | 32 | 2 (1) / 30 (1) | 2 | 0x100: 14, 0x108: 14 |
| Soundgoodizer | 13 | — | 1 | 0x100: 6, 0x108: 6 |
| Emphasis | 6 | 2 (1) / 30 (1) / 38 (1) | 0 | 0x80: 1, 0x100: 1, 0x108: 1 |
| Fruity Multiband Compressor | 6 | 2 (1) / 30 (1) | 0 | 0x100: 2, 0x108: 2 |
| Transient Processor | 6 | 2 (1) / 36 (1) | 0 | 0x100: 2, 0x108: 2 |

- 即値 ID の distinct = {2, 30, 36, 38, 50} (taint 版)。 `hs_ids.json` (35 ID / 894 site) に**不足 0**。
- **別算法の検算** (`ids_crosscheck.py`、taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う):
  7/7 本で taint 版の ID 件数を取りこぼしなく再現した。 一致しない差は 1 点で、**Maximus と Soundgoodizer に ID 59 の `call [reg]` が各 2 site**
  (taint 版は host 経由と判定せず未計上)。 ID 59 は `hs_ids.json` に含まれるので応答表は足りる。 host 呼出か別オブジェクトの slot0 呼出かは未判別。
- 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。 0x80 / 0x120 は P0b では 44 slot 共通の
  fail-soft + 呼出記録のみ (意味未解析)。 いずれも ctor 完走 (P0b 未達部) の後に Eff_Render 到達で初めて意味が決まる。

## 3. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` (kernel 変数経由・関数ポインタ slot 経由・直接 call の 3 経路) を再利用し、call site の所在関数を
閉包 ranges / frontier で分類。 kernel 番号は Balance (block 18983) の VA に正規化済み。

| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site 数) | frontier 内 site | DLL 固有関数走査の site / kernel 種 |
|---|--:|---|--:|---|
| Fruity Limiter | 1 | 0x5dfae0 (1) | 0 | 23 / 2 |
| Fruity Compressor | 0 | — | 0 | 22 / 1 |
| Maximus | 5 | 0x5de390 (2), 0x5dee90 (1), 0x5dfae0 (1), 0x5dfc90 (1) | 2 | 47 / 15 |
| Soundgoodizer | 5 | 0x5de390 (2), 0x5dee90 (1), 0x5dfae0 (1), 0x5dfbe0 (1) | 2 | 47 / 15 |
| Emphasis | 0 | — | 0 | 22 / 1 |
| Fruity Multiband Compressor | 0 | — | 0 | 22 / 1 |
| Transient Processor | 0 | — | 0 | 22 / 1 |

最右列の 22 site (0x5de390) は 7 本すべてに共通し、閉包にも frontier にも属さない。 framework 側の深い関数にあると推定 (未確認)。
Maximus と Soundgoodizer は 47 site / 15 kernel で、閉包内で差があるのは rc_chop の 0x5dfc90 と 0x5dfbe0 のみ。

P0c (`p0c/REPORT.md`) で見た各 kernel の現状 (本 PR では再測定していない):

| kernel | 区分 | P0c の記録 |
|---|---|---|
| 0x5de390 | f64mem | 実機械語 ⟷ x87 版 / f64 lowering 版とも差分 0 / 300,000 (§3)。 同区分 (f64mem) 全体では ±1 ulp 0.018% を許容条件として記録 |
| 0x5dfae0 | transc | f32 出力で 0 / 200,000 (§3)。 bit-exact 100% が必要なら Intel x87 アルゴリズム再実装 (将来オプション) |
| 0x5dfbe0 / 0x5dfc90 | rc_chop | `f80_lower.py --ext` で bit-exact (§10、p0c4_e2e 2000 case で 0 / 0) |
| 0x5dee90 | SSE mix | Balance harness は 1,071 / 1,071 bit-exact (`plugins/REPORT.md` §3)。 P0c 汎用 harness は `buf_diff` 2,565,360 が残り **#331 で未解決** (§14.3) |

## 4. T2: C++ engine DLL 2 本

両 engine は export が `CreateEngine` 1 つ、import が KERNEL32 のみ (CRT は静的リンクと推定)。 殻との結合方式 (LoadLibrary 経路) は未解析。

| engine | block | サイズ B | `.text` B | `.pdata` 関数 / B | KERNEL32 import |
|---|--:|--:|--:|--:|--:|
| Multiband Compressor `comp_eng` | 19048 | 537,600 | 423,808 | 1,658 / 359,159 | 88 |
| Transient Processor engine | 19252 | 190,464 | 115,136 | 522 / 106,367 | 73 |

`engine_lift.sh <block>` で全 `.pdata` 関数を `lift_ranges.sh` (RetDec+pass 鎖) → `emcc -c` に通した結果:

| engine | RetDec rc | final.ll define | `.pdata` で define 無し | f80 関数 | 未実装 helper (うち VEX) | `emcc -c` | 局所修復後の `emcc -c` |
|---|--:|--:|--:|--:|--:|--:|--:|
| 19252 Transient | 0 | 551 | 0 / 522 | 0 (既定の `PLUG_F80_LOWER=1` で 1 → 0) | 5 | **0 (成功)** (旧 1 失敗) | — (不要) |
| 19048 Multiband | 0 | 1,712 | 0 / 1,658 | 0 | 5 | 1 (失敗) | **0 (成功)** (`engine_fixcmp.py` の i32 修正後) |

- 2026-10-14 実測 (測定 commit `db4fe1f0`、`engine_lift.sh` 単独実行、Transient 16 s / Multiband 64 s)。 未実装 helper の列は `e.simd.log` の `unimplemented N` の値。 旧表の 66 (57) / 39 (31) は distinct 宣言数で数え方が違うため直接比べない。
- 未実装 helper の内訳 (`m11_simd2.py`、`tools/plugins/lift/passes/`)。 VEX 形 (`v*`) は同名 SSE 形へ委譲 (dst 上位は src1 由来で SSE 形の a 由来と一致する扱い) したうえで、cvt 2 オペランド形・`cvtpd2dq`/`cvttpd2dq`・`pmovsxdq`・`rep_movsb_memcpy`・`rep_stosw_memset`・`int`/`int3` (到達で abort) を追加した。

  | engine | 変更前 (HEAD) | 変更後 (711d9ece) | 残件 |
  |---|--:|--:|---|
  | 19252 Transient | 59 | 12 | `movntps` (store, 値のみ渡る) / `vmovsd` store 形 / `vucomisd`・`vcomisd`・`vucomiss` (flag 未モデル。#1408 の範囲) / スカラー FMA 7 宣言 (`vfmadd132sd`・`vfmadd213sd`×2・`vfmadd231sd`×2・`vfmsub213sd`・`vfnmadd231sd`) |
  | 19048 Multiband | 34 | 6 | `movntps` / スカラー FMA 5 種 (`vfmadd213sd`・`vfmadd231sd`×2・`vfnmadd132sd`・`vfnmadd231sd`) |

- 旧測定 (commit `c0afd85b`・`711d9ece`) の詳細は付録 `REPORT_APPENDIX.md` §C に分割移動 (内容無変更)。 **#1698 (PLUG_NO_STATIC_DETECT 既定化の engine 影響)**: 19048 は既定で `missing_define` 208→0、19252 は不変 (測定 commit 30a7b5b4)。 詳細は付録 §D。
- 残件の実体 (`e.simd.log` の `unimplemented:` 行、本 HEAD で再取得): 19252 は 12 行 = `movntps`・`vcomisd`・`vucomisd`・`vucomiss`・`vmovsd` (store) と FMA 7 行 (うち 3 引数 `i128,i128,i128` 形が 3 行)。 19048 は 6 行 = `movntps` と FMA 5 行 (うち 3 引数 `i128,i128,i128` 形が 1 行)。 `e.final.ll` の VEX 宣言の引数数は 19252 で 1 引数 16 / 2 引数 34 / 3 引数 8、19048 で 11 / 15 / 6。 3 引数 FMA は残件に出るため、残件表に 3 引数形が出ない理由は「IR で 2 引数に落ちる」ではない。 委譲が 3 引数形を拾わないことは合成 `.ll` でのみ確認 (下記の `vfmadd213sd(i128,i128,i64)` の未実装)。
- shared pass への影響 (T0 / T1 `batch_lift.sh`): **未測定**。 VEX 委譲で従来 no-op だった VEX 形が SSE 実装になるため、影響の有無は未確認。
- 再現手順 (`work/dynamics/simdchk/` は `**/work/` で gitignore 対象。 入力は engine ごとの `engine_lift.sh` 出力): (1) `work/dynamics/engine<B>/e.final.ll` を入力に `python3 tools/plugins/lift/passes/m11_simd2.py <final.ll> > <dir>/m11_simd.c` で helper C を生成 (統計は stderr)。 (2) `msimd11_core.h` (`tools/plugins/lift/passes/msimd11_core.h`) を同じ dir に置き、`#include "../msimd11_core.h"` を `"msimd11_core.h"` に直して `emcc -c -msimd128 -w -O0 <m11_simd.c> -o /dev/null` を実行 (rc を見る)。 `include` の書換えは generator の出力先に合わせた一時措置。 2026-10-14 の `simdchk` 本体の生成コマンドは本 REPORT 以外に記録が無い。 本 HEAD (`c0afd85b`) では `toolchain-emsdk` を使い、上記の手順で両 engine とも rc 0 を実測 (`/opt/emsdk` 既存)。
- 受入条件の判定: `emcc -c` rc 0 は 2 本とも達成。 f80 関数 0 も 2 本とも達成。 未実装 helper 宣言 0 は**未達** (12 / 6)。 残件は下記の子 issue へ。
- 既知の限界: `ucomis`/`comis` の SSE 形は従来どおり `(void)a; (void)b;` で flag を反映しない (`m6 ir6 [P1]` 相当は未移植)。 本 PR はこれを変えていない。 `movntps`・`vmovsd` store・FMA の意味は未確定で stub のまま。

- `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`engine_defs.py`。 分母は `.pdata` 関数数、括弧は欠けた range の合計長)。 19048 は 210 件のうち 67 件が call 先として `declare` だけ残り、link 時に未解決になる。
  19252 の 2 件は参照なし。 逆に range 内部に別 define が増えた件数は 19252 で 29、19048 で 54。
- **脱落の原因 (#1412)**: 19048 の欠落 210 件のうち 208 件は RetDec の静的検出 (`statically linked function`) による除去。 残り 2 件 (19252・19048 とも `CreateEngine` / `entry_point`) は名前付き define で存在する偽陽性。 集計を直した HEAD (db4fe1f0) で `missing_define` は両 engine とも 0。 詳細は付録 `REPORT_APPENDIX.md` §A。
- 失敗の連鎖と修正 (clang は最初の型エラーで止まるため 1 件ずつ露見。 修正は engine 局所の `dynamics/engine_fixcmp.py`、共有鎖には未組込):
  1. 両 engine: `icmp eq ptr %x, %arg3` (`%arg3` は i64 仮引数) → 修正済み (19252 は該当 0 件、19048 は 1 件)。
  2. 19048: `inttoptr i64 %arg2` で `%arg2` が i32 → 修正済み (`zext i32 → i64` を挿入。 `function_18004f7f8` の 1 件)。 修正後の `emcc -c` rc 0。
  3. 19252: 旧記載の `zext` 定数式 (`__asm_rep_stosq_memset`) は今回の HEAD では露見せず。 代わりに f80 (`fpext`/`frem`/`fp_round` on x86_fp80) が `emcc -c` を落としていた → `PLUG_F80_LOWER=1` (既存の `p0c/f80_lower.py`) で解消。 `engine_lift.sh` の既定を `1` にした。
- 残り (本 issue の範囲外として子 issue へ): 未実装 helper 宣言 (VEX 含む) の 59 / 34、 `.pdata` 関数の define 脱落 (19252 2 件 / 19048 210 件、うち 19048 の 67 件は call 先) の原因 → 19048 は §4 の通り静的検出が原因 (208 件)。 19252 の 2 件は未特定 (子 issue)。
- VEX 形の委譲の前提 (未検証を含む): (a) 委譲は `gen_body` で SSE 形を呼ぶため、SSE 分岐の条件 (`n == 2` 等) を満たす 2 引数 VEX 形 (`__asm_vaddsd(i128,i128)`・`__asm_vaddsd__21(i128,i64)`) だけが実装される。 合成 `.ll` で確認: 3 引数 `__asm_vaddsd__30(i128,i128,i128)` と `__asm_vfmadd213sd(i128,i128,i64)` は委譲後も未実装のまま。 (b) 残件に 3 引数形は出る (FMA の `i128,i128,i128` 形が 19252 で 3 行、19048 で 1 行。 `c0afd85b` の `e.simd.log` で実測)。 前段の「2 引数形だけ実装」の説明は、3 引数 FMA が残件に残ることで裏付けられる。 (c) VEX.128 は dst の上位 128bit をゼロにするが、委譲は SSE 形と同じく src1 由来で保持する。 ymm 系は i256 trap で止まるため現状の到達には影響しない前提 (未検証)。
- VEX helper 未実装 (`vaddsd` / `vfmadd*` / `vcvt*` 等、distinct 宣言数) は、CPUID 分岐で SSE 路に固定できるかが未確認 (T1 の AVX 2 種は CPUID 分岐で SSE 路固定と plugins/REPORT.md §4.3 に記録あり)。
  Transient engine の f80 1 関数は #197 の `f80_lower.py` の適用対象。
- #1408 (スカラー FMA3 の実装。方式は `docs/DECISIONS.md` D14)。 `m11_simd2.py` に `vf[n]m{add,sub}{132,213,231}sd` の 3 引数形を追加 (`msimd11_core.h` の `_fma*sd` 系へ委譲)。 engine_lift 実測の測定 commit は `45a59279` (lift コードの変更はこの commit のみ。以降の `git diff 45a59279 HEAD -- tools/plugins/lift/passes/ tools/plugins/dynamics/` は REPORT と検証用 `fma12_check.c` の追加だけ)。
  - 実機照合 (`tools/plugins/dynamics/fma12_check.c`、測定 commit `e0165b38`、Intel Xeon 8573C・FMA3・20,000 乱数・gcc -O0): 12 形 (3 順序 × 4 演算) すべてで lane0 の値が一致 (tol-mismatch 0)。 bit 完全一致は fma/fms の 6 形。 fnm/fnms の 6 形 (`vfnmadd*`・`vfnmsub*`) は ±0 と NaN の符号が実機と異なる (strict-bit-mismatch: 132 fnm 184・fnms 180、213 fnm 179・fnms 209、231 fnm 198・fnms 206 / 20,000)。 未解決: 符号差の修正は本 PR の範囲外 (起票先は未定、PM 判断)。
  - `engine_lift.sh` 単独実行 (変更後): 19252 Transient unimpl 12 → 5 (`emcc_c_rc` 0、24.6 s)、19048 Multiband unimpl 6 → 1 (`emcc_c_rc` 1 → fixcmp 後 0、62 s)。 残件は 19252 が `movntps`・`vmovsd` store・`vcomisd`・`vucomisd`・`vucomiss`、19048 が `movntps`。
  - 生成 helper C (`simdchk<B>/m11_simd.c`) の `emcc -c -msimd128 -w -O0`: 19252 rc 0、19048 rc 0。
  - 残件 (子 issue に分割): movntps・vmovsd store (宛先復元) / ucomis・comis (flag 反映)。 #1408 は受入条件「未実装 helper 宣言 0」を未達として部分達成 (`Refs #1408`)。

## 5. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner・同時に走らせたのは本検証の 1 プロセス列のみ)

- 測定 commit: **cb3a89a6** (origin/main)。 この後の差分は文書のみ (REPORT.md の分割移動・REPORT_APPENDIX.md 新設・DOC_MAP 索引 1 行)。
  `git diff cb3a89a6 HEAD -- tools/plugins/dynamics ':!*.md'` の出力は空 (コード差分 0 の証跡)。 文書差分の概要は `git diff cb3a89a6 HEAD -- tools/plugins/dynamics --stat` で REPORT.md のみ。 `docs/WORKFLOW.md` §6 に従い現 HEAD での e2e 再測定は不要 (下の `engine_lift.sh` 再測定は HEAD で実施)。
- §4 の数値は db4fe1f0 で再測定 (到達性の実測のみで、engine の正しさは示さない)。 静的検出の切替前後の内訳は付録 §A。

| 項目 | 実測 |
|---|---|
| `dynamics_e2e.sh` 全体 (`--skip-lift` 無し、inventory 済で 3 回連続、HEAD b2094ba、`env -i`) | 167 s / 168 s / 166 s、いずれも exit 0・`judge: rows=7/7 bad=0`・最終行 `[dynamics_e2e] OK`。 開始時 load average (1 分) 0.98 / 1.05 / 1.03 (内訳: 7 閉包 + 判定 + closure_facts + matrix_check + engine 2 本。 いずれも逐次実行で並列数 1) |
| 判定の入力 (`status7.csv`、4 回とも) | 7 本とも lift_rc 0 / declares_unimpl 0 / f80_funcs 0 / emcc_c_rc 0。 declares_unimpl は「未計測 -1」ではなく実測の 0 (`batch_lift.sh` は simd ログに `unimplemented N` が無いと -1 を書く。 `judge.py` は -1 を不合格にする) |
| lift 秒 (`status.csv` の seconds、3 回の min–max) | Limiter 2–3 / Compressor 2 / Maximus 6 / Soundgoodizer 5 / Emphasis 3–4 / Multiband 殻 2–3 / Transient 殻 2–3 (7 本計 25 s / 23 s / 25 s)。 engine 19252: 12–14 s、19048: 47–49 s |
| 結果一致 (クリーン 1 回 + 上の 3 回 = 4 回) | 判定列 (lift_rc / defines / f80 / `emcc -c`)・engine 欠落監査 (lift 秒を除く全列)・`facts.json` は 4 回とも同一 (`facts.json` は sha256 が 4 本一致、先頭 `1d1d7d5a8d00c7e0`)。 `matrix_check`: 42/42 項目一致を 4 回とも確認 |
| `dynamics_nega.sh` (HEAD b2094ba、3 回) | 3 回とも exit 0、3 s / 4 s / 4 s (NC1: rc 0 → 1、NC2: define 27 → 25 かつ対象関数 1 → 0、NC3: 下記)。 終了時に `status.csv` / `status7.csv` が元と cmp 一致 |
| `ids_crosscheck.py` (HEAD b2094ba) | exit 0 (1 秒未満)。 7/7 本で取りこぼしなし (§2)。 本スクリプトは 2ba3978 から挙動不変 (59d0f2e の docstring 1 行のみ) |
| クリーン worktree での全工程再現 (HEAD b2094ba、環境変数なしの `env -i`、新規 `RUNNER_TEMP` で fl-win64 展開 + venv 作成から、inventory 生成を含む) | `dynamics_e2e.sh` exit 0、**556 s** (開始時 load average 2.43 / 2.63 / 1.18 = 直前に中断した別の inventory 実行の残り。 終了時 1.79 / 7.24 / 5.23)。 判定・`facts.json`・engine 欠落監査は上の 3 回と同一。 続けて `ids_crosscheck.py` 7/7、`dynamics_nega.sh` OK。 上の 3 回連続はこの同じ worktree の inventory を使った。 worktree は終了後に削除 |
| 前提 inventory (初回のみ) | `inventory/win_funcs.py` 242.12 s (並列 14 プロセス / 4 core)、他 5 s 未満。 `block_manifest.json` が tarball に無く `nsis_names.py` が動かないため、`mk_blockmap.py` が `PLUGIN_MATRIX.json` から代替の blockmap (182 record) を合成 |

ネガティブコントロール (Fruity Limiter 19021):
- NC1: `final.ll` の関数 1 つの `ret` を除去 → `emcc -c` が **rc 1** (無改変は rc 0)。 `emcc -c` ゲートが壊れた IR を落とすことを確認。
- NC2: 閉包 ranges の末尾 1 つ (`function_6dd1f0`) を落として再 lift → その define が消え、全体は 27 → 25 (RetDec は 1 range から 2 define を出すことがあり、差は 1 とは限らない)。
  ranges が lift 範囲を実際に決めていることを確認。
- NC3 (判定 `judge.py` そのもの。 実測の `status7.csv` 7 行を 1 セルずつ壊した合成 CSV を渡す。 rows=採用行/対象 block 数、bad=不合格行数):

  | 入力 | judge.py の rc | rows / bad |
  |---|--:|---|
  | 対照 (実測 `status7.csv` そのまま) | 0 | 7/7 / 0 |
  | Limiter `emcc_c_rc=1` | 1 | 7/7 / 1 |
  | Limiter `lift_rc=1` + `f80_funcs=3` | 1 | 7/7 / 1 (行単位で数える) |
  | Maximus `declares_unimpl=5` | 1 | 7/7 / 1 |
  | Compressor `declares_unimpl=-1` (未計測値) | 1 | 7/7 / 1 |
  | Transient の行を落とす | 1 | 6/7 / 1 |
  | e2e 配線: `work/batch/status.csv` に Limiter `emcc_c_rc=1` の行を足し `dynamics_e2e.sh --skip-lift` | exit 1 (`[dynamics_e2e] FAIL`)、`[dynamics_e2e] OK` 行 0 本 | — |

  NC3 自身の識別力: `judge.py` の終了コードを常に 0 に差し替える (= 修正前の挙動相当) と、合成 6 件はすべて rc 0、e2e 配線は exit 0・OK 行 1 本となり
  `dynamics_nega.sh` は `[dynamics_nega] FAIL` (exit 1)。 差し替えは使い捨ての detached worktree 上で行い、`git show HEAD:` で戻して `git diff` が空であることを確認した。

別系統の突合: Dispatcher ID の独立走査は §2 の通り (`ids_crosscheck.py`、7/7 本で取りこぼしなし)。 閉包の 6 項目 (関数数・バイト・frontier 関数・frontier バイト・vcall・ptr) は、今回の再計算値と `PLUGIN_MATRIX.json` (2026-10-10 生成) が 7 本とも一致。
`define` 数 = 閉包関数数 も 7 本とも一致 (§1)。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`) と、host / kernel 依存の静的な数え上げ。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp。 範囲外の項目について、本書は何も主張しない。

## 5b. 間接呼出到達先を加えた推移閉包 (#537 の closure_indirect 定義を流用)

- 再現: `bash tools/plugins/dynamics/indirect_e2e.sh` (前提の inventory・閉包が無ければ dynamics_e2e.sh --skip-lift で生成)。 定義・検査 C1〜C4 は `dynamics/closure_indirect.py` (`sampler/closure_indirect.py` の `Pe` / `bfs` を import、sampler 側は無変更)
- 定義: total = 直接 call/jmp 閉包 (base) ∪ 非共通 ∧ 閉包外 ∧ データ参照あり関数 (root) からの BFS。 検査 C2 は sampler の `unreached.json` が無いため、同定義を本 dir 内で再計算して照合
- 検査: C1 base 再現 / C2 root 再計算一致 / C3 total ⊆ 非共通 / C4 capstone ⊆ byte 走査 → **PASS 4 checks × 7 plugins**
- 増分 (実測・ `work/dynamics/indirect.json`):

| プラグイン | base 関数 / B | total 関数 / B | 非共通に占める total (関数 % / B %) |
|---|--:|--:|--:|
| Fruity Limiter | 27 / 15,869 | 79 / 27,327 | 46.5 / 36.1 |
| Fruity Compressor | 31 / 11,887 | 60 / 14,971 | 62.5 / 29.3 |
| Maximus | 84 / 46,094 | 245 / 96,652 | 44.4 / 29.4 |
| Soundgoodizer | 65 / 29,732 | 212 / 74,909 | 46.0 / 26.7 |
| Emphasis | 60 / 25,572 | 109 / 39,305 | 56.2 / 43.2 |
| Fruity Multiband Compressor | 19 / 9,515 | 50 / 14,121 | 47.2 / 44.0 |
| Transient Processor | 26 / 15,853 | 65 / 22,135 | 53.7 / 29.1 |
| 計 | 312 / 154,522 | **820 / 289,420** | |

- lift (増分閉包を `lift_ranges.sh` = batch_lift と同一鎖で実行): **7/7 lift_rc=0 / declares_unimpl=0 / f80=0 / emcc_c_rc=0** (judge.py 7/7 合格)。 増分閉包の関数数は base の約 1.8〜3.3 倍 (Emphasis 109/60、Compressor 60/31、Soundgoodizer 212/65)
- 実測時間 (`indirect_e2e.sh`、コミット前の作業ツリー): **73 s / rc=0**。 `closure_indirect.py` 2.7 s、lift 7 本の合計 71 s (Limiter 7 / Compressor 5 / Maximus 23 / Soundgoodizer 18 / Emphasis 9 / Multiband 4 / Transient 5 s)
- 判定の負例: 増分 status から 1 行を落とすと judge.py が exit 1 (行欠落の検出)
- **範囲外 (主張しない)**: 増分閉包の lift が通ったのは emcc の wasm バックエンドを通ったことだけ。 差分試験 (native ⟷ wasm の bit 比較) と wasm リンク・実行は未実施。 増分閉包の内容が正しい機能か (間接呼出の到達先が実際に呼ばれるか) は未検証
- 注意: 増分後も "非共通 ∧ total 外" の関数は Maximus 307 / 232,504 B、Soundgoodizer 249 / 205,150 B と残る (sampler の #537 と同じく、閉包の取りこぼしは解消していない)。 残差の内訳 (lea 残 関数は Maximus 2 / Soundgoodizer 1 のみ) は本節の対象外

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 Eff_Render 単位の native / wasm harness が無く、P0a/P0b 未完 | #200 を閉じられない | #195 / #196 の完了後に #200 を再開 (Closes はその時)。 harness は新規子チケットを PM に起票依頼: 「[PLG-F3a] Eff_Render 単位の native(ms_abi VA 敷設) ⟷ wasm 差分 harness」 |
| Render test .flp の E2E (出口条件 4) | 同上 | FLEngine 統合待ち。 親 #14 / #200 |
| engine 2 本の未実装 helper 宣言 (Transient 12 / Multiband 6、FMA・movntps・vmovsd store・ucomis flag) | T2 の 2 本 (Multiband / Transient) | #1408 ([PLG-F3-8]) |
| `.pdata` 範囲の define 脱落 (Multiband 210 件 / Transient 2 件) | T2 の 2 本 | 解消済み (#1412。 偽陽性の集計を修正、db4fe1f0) |
| `emcc -c` (`e.final.ll` と生成 helper C の両方) は 2 本とも rc 0 で達成済み (型エラー 3 類型は `engine_fixcmp.py` と `PLG_F80_LOWER` で解消) | — | 解消済み (#1163) |
| Transient engine の f80 1 関数 | engine の wasm 化 | #197 (`f80_lower.py` の適用) にコメント |
| 0x5dee90 の P0c 汎用 harness 残差 (2,565,360) | Maximus / Soundgoodizer の kernel 保証 | #331 (既存) にこの依存を追記 |
| host slot 0x80 / 0x120 と動的 ID 4 site の意味 | Emphasis / Limiter / Compressor ほか | #196 作業 5 (0x13173a0 全 case 解析) に追記 |
| Maximus / Soundgoodizer の ID 59 × 各 2 site が taint 版に載らない (host 呼出か否か未判別) | host 呼出面の数え上げ | #196 作業 5 (0x13173a0 全 case 解析) にあわせて ABI.md §6 の taint 精密化 (T-ABI-3) に追記 |
| 22 site (0x5de390) の所在 (閉包外・frontier 外) | §3 の解釈 | #197 / #195 の統合時に所在関数を特定 |
| `nsis_names.py` が Actions 上で動かない (`block_manifest.json` 不在) | inventory の再現性 | `mk_blockmap.py` で回避済み。 `docs/WORKFLOW.md` §11 への追記は PM 判断 |
| `docs/DOC_MAP.md` の REPORT 索引に本書が未掲載 | 索引漏れ | PM が追記 |

## 7. DEFECTS.md 行案 (候補・loud な IR 型エラー。 追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| E1 icmp ptr/i64 混在 | `icmp eq ptr %x, %argN` (argN は i64) | Transient / Multiband engine 各 4 operand | emcc "defined with type 'i64' but expected 'ptr'" | `engine_fixcmp.py` (局所)。 `fix_ptr_params.py` の拡張が本筋 |
| E2 SSA 値入りの定数式 | `__asm_rep_stosq_memset` の引数に `zext (… i64 %v …)` | Transient engine | emcc "zext constexprs are no longer supported" | 未修復 |
| E3 i32 仮引数の i64 使用 | `inttoptr i64 %arg2` (arg2 は i32) | Multiband engine | emcc "defined with type 'i32' but expected 'i64'" | 未修復 |

## 8. 成果物

| ファイル | 内容 |
|---|---|
| `dynamics_e2e.sh` | 7 閉包 → batch_lift → 判定 (`judge.py`。 不合格・行欠落は exit 1 で OK 行なし) → `closure_facts.py` → `matrix_check.py` → engine 2 本 (参考) |
| `judge.py` | `status.csv` の合否判定: `judge.py <status.csv> [block ...] [-o out.csv]`。 lift_rc / declares_unimpl / f80_funcs / emcc_c_rc が全 0 で rc 0、不合格 rc 1、入力不正 rc 2 |
| `dynamics_nega.sh` | ネガティブコントロール 3 件 (NC1 `emcc -c` / NC2 ranges / NC3 判定) |
| `closure_facts.py` | 閉包 / host ID / kernel 依存 / engine 外形 → `work/dynamics/facts.json` |
| `matrix_check.py` `ids_crosscheck.py` | `PLUGIN_MATRIX.json` との 6 項目突合 (e2e に組込み) / Dispatcher ID の別算法検算 (単独実行: `source tools/plugins/dynamics/env.sh && python3 tools/plugins/dynamics/ids_crosscheck.py`) |
| `engine_lift.sh` `engine_ranges.py` `engine_fixcmp.py` | engine DLL の全 `.pdata` lift と局所修復 |
| `mk_blockmap.py` `env.sh` | `block_manifest.json` 不要の inventory 前提 / 環境 |
