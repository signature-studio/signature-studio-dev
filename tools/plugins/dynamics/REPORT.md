# tools/plugins/dynamics/REPORT.md — PLG-F3 (#200) dynamics 7 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/dynamics/` のみ / 検証起点 commit: **18b1cb3** (`dynamics_e2e.sh`・`dynamics_nega.sh`) と **2ba3978** (= 18b1cb3 + `ids_crosscheck.py` のみ)
- 再現: `bash tools/plugins/dynamics/dynamics_e2e.sh` (判定 + 実測) / `bash tools/plugins/dynamics/dynamics_nega.sh` (ネガティブコントロール)
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
| 19252 Transient | 0 | 551 | 2 / 522 (165 B) | 1 | 66 (57) | 1 (失敗) | 1 (失敗) |
| 19048 Multiband | 0 | 1,504 | 210 / 1,658 (22,916 B) | 0 | 39 (31) | 1 (失敗) | 1 (失敗) |

- `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`engine_defs.py`。 分母は `.pdata` 関数数、括弧は欠けた range の合計長)。 19048 は 210 件のうち 67 件が call 先として `declare` だけ残り、link 時に未解決になる。
  19252 の 2 件は参照なし。 原因 (RetDec の関数境界統合 / 復号失敗) は未調査。 逆に range 内部に別 define が増えた件数は 19252 で 29、19048 で 54。
- 失敗の連鎖 (clang は最初の型エラーで止まるため 1 件ずつ露見):
  1. 両 engine: `icmp eq ptr %x, %arg3` (`%arg3` は i64 仮引数) → "defined with type 'i64' but expected 'ptr'"。 `dynamics/engine_fixcmp.py` (engine 局所 pass、共有鎖には未組込) で各 4 operand を直す。
  2. 19252: 次に `__asm_rep_stosq_memset` 呼出の引数が SSA 値を含む `zext` 定数式 → "zext constexprs are no longer supported"。
  3. 19048: 次に `inttoptr i64 %arg2` で `%arg2` が i32 → "defined with type 'i32' but expected 'i64'"。
- VEX helper 未実装 (`vaddsd` / `vfmadd*` / `vcvt*` 等、distinct 宣言数) は、CPUID 分岐で SSE 路に固定できるかが未確認 (T1 の AVX 2 種は CPUID 分岐で SSE 路固定と plugins/REPORT.md §4.3 に記録あり)。
  Transient engine の f80 1 関数は #197 の `f80_lower.py` の適用対象。
- 以上は到達性の実測で、engine の正しさは何も示していない。

## 5. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner・同時に走らせたのは本検証の 1 プロセス列のみ)

| 項目 | 実測 |
|---|---|
| `dynamics_e2e.sh` 全体 (`--skip-lift` 無し、3 回連続、HEAD 18b1cb3) | 130 s / 126 s / 125 s、exit 0。 開始時 load average (1 分) 0.86 / 1.08 / 1.01 (内訳: 7 閉包 + closure_facts + engine 2 本。 いずれも逐次実行で並列数 1) |
| lift 秒 (`status.csv` の seconds、3 回の min–max) | Limiter 2–3 / Compressor 2 / Maximus 5–6 / Soundgoodizer 4 / Emphasis 3 / Multiband 殻 2 / Transient 殻 2–3 (7 本計 20–23 s)。 engine 19252: 10–12 s、19048: 38–41 s |
| 3 回の結果一致 | 判定列 (lift_rc / defines / f80 / `emcc -c`)・engine 欠落監査・`facts.json` は 3 回とも同一 (`facts.json` はバイト一致)。 `matrix_check`: 42/42 項目一致を 3 回とも確認 |
| `dynamics_nega.sh` | exit 0、2.4 s (NC1: rc 0 → 1、NC2: define 27 → 25 かつ対象関数 1 → 0) |
| `ids_crosscheck.py` (HEAD 2ba3978) | exit 0。 7/7 本で取りこぼしなし (§2) |
| クリーン worktree での全工程再現 (HEAD 2ba3978、環境変数なしの `env -i`、新規 `RUNNER_TEMP` で fl-win64 展開 + venv 作成から、inventory 生成を含む) | `dynamics_e2e.sh` exit 0、**379 s** (終了時 load average 2.88 / 6.65 / 4.61)。 判定列・`facts.json`・engine 欠落監査は上の 3 回と同一 (`facts.json` はバイト一致)。 続けて `ids_crosscheck.py` 7/7、`dynamics_nega.sh` OK。 worktree は終了後に削除 |
| 前提 inventory (初回のみ) | `inventory/win_funcs.py` 242.12 s (並列 14 プロセス / 4 core)、他 5 s 未満。 `block_manifest.json` が tarball に無く `nsis_names.py` が動かないため、`mk_blockmap.py` が `PLUGIN_MATRIX.json` から代替の blockmap (182 record) を合成 |

ネガティブコントロール (Fruity Limiter 19021):
- NC1: `final.ll` の関数 1 つの `ret` を除去 → `emcc -c` が **rc 1** (無改変は rc 0)。 `emcc -c` ゲートが壊れた IR を落とすことを確認。
- NC2: 閉包 ranges の末尾 1 つ (`function_6dd1f0`) を落として再 lift → その define が消え、全体は 27 → 25 (RetDec は 1 range から 2 define を出すことがあり、差は 1 とは限らない)。
  ranges が lift 範囲を実際に決めていることを確認。

別系統の突合: Dispatcher ID の独立走査は §2 の通り (`ids_crosscheck.py`、7/7 本で取りこぼしなし)。 閉包の 6 項目 (関数数・バイト・frontier 関数・frontier バイト・vcall・ptr) は、今回の再計算値と `PLUGIN_MATRIX.json` (2026-10-10 生成) が 7 本とも一致。
`define` 数 = 閉包関数数 も 7 本とも一致 (§1)。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`) と、host / kernel 依存の静的な数え上げ。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp。 範囲外の項目について、本書は何も主張しない。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 Eff_Render 単位の native / wasm harness が無く、P0a/P0b 未完 | #200 を閉じられない | #195 / #196 の完了後に #200 を再開 (Closes はその時)。 harness は新規子チケットを PM に起票依頼: 「[PLG-F3a] Eff_Render 単位の native(ms_abi VA 敷設) ⟷ wasm 差分 harness」 |
| Render test .flp の E2E (出口条件 4) | 同上 | FLEngine 統合待ち。 親 #14 / #200 |
| engine 2 本の `emcc -c` 未通過 (型エラー 3 類型の連鎖、VEX helper 未実装、`.pdata` 210 件 define 無し) | T2 の 2 本 (Multiband / Transient) | 新規子チケットを PM に起票依頼: 「[PLG-F3b] C++ engine DLL の lift 鎖: IR 型整合 pass + VEX helper + define 脱落の原因調査」 |
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
| `dynamics_e2e.sh` | 7 閉包 → batch_lift → 判定 (lift_rc / f80 / `emcc -c` が全 0) → `closure_facts.py` → engine 2 本 (参考) |
| `dynamics_nega.sh` | ネガティブコントロール 2 件 |
| `closure_facts.py` | 閉包 / host ID / kernel 依存 / engine 外形 → `work/dynamics/facts.json` |
| `matrix_check.py` `ids_crosscheck.py` | `PLUGIN_MATRIX.json` との 6 項目突合 (e2e に組込み) / Dispatcher ID の別算法検算 (単独実行: `source tools/plugins/dynamics/env.sh && python3 tools/plugins/dynamics/ids_crosscheck.py`) |
| `engine_lift.sh` `engine_ranges.py` `engine_fixcmp.py` | engine DLL の全 `.pdata` lift と局所修復 |
| `mk_blockmap.py` `env.sh` | `block_manifest.json` 不要の inventory 前提 / 環境 |
