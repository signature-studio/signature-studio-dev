# tools/plugins/pitch_time/REPORT.md — PLG-F7 (#204) pitch-time 8 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/pitch_time/` のみ / 検証起点 commit: **1b35efd** (スクリプト一式。 以降の commit は REPORT.md のみ) (各実測の HEAD は §5)
- 再現: `bash tools/plugins/pitch_time/pitch_time_e2e.sh` (判定 + 実測。 gate が 1 つでも不合格なら非 0 で終わり、最終行は `FAIL`) /
  `bash tools/plugins/pitch_time/pitch_time_nega.sh` (ネガティブコントロール。 期待した終了コードにならなければ非 0)
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 環境は `pitch_time/env.sh`
- 先行 PR #506 (dynamics, `tools/plugins/dynamics/`) の手法を適用した。 #506 は本書の時点で未マージで、レビュー指摘 (判定が不合格でも exit 0 /
  判定そのもののネガコン無し) も未修正のため、本 PR は #506 のファイルに依存せず自己完結で書き、**判定を `judge.py` に切り出して不合格で非 0**、
  判定ごとにネガコンを付けた。 #506 の branch には触れていない。
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし**。 §4 の C++ module で出た型エラー 2 類型は emcc が拒否する loud な IR エラーで、#506 REPORT §7 の
  E1 (icmp ptr/i64 混在) / E2 (SSA 値入り zext 定数式) と同型。 silent miscompile の有無は差分試験を未実施のため未確認。

## 0. 結論 (先出し)

1. **#204 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** blockedBy の PLG-P0a #195 / P0b #196 / P0c #197 が OPEN で、
   Eff_Render 単位で native ⟷ wasm を比べる harness も repo に無い。 → PR は **`Refs #204`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は Delphi 殻 7/7 本で通った。** RetDec+pass 鎖が完走 (lift_rc 0)、`emcc -c` rc 0、`x86_fp80` 関数 0、未実装 `__asm_*` helper 宣言 0。
   合計 468 関数 / 202,449 B (§1)。 Tier T2/T3 の 3 本 (Scratcher / Newtone / Vocodex) は `PLUGIN_MATRIX.json` に `batch` 欄が無く、今回が初の lift。
   閉包規模 6 項目 × 7 本 = 42 項目は `PLUGIN_MATRIX.json` と全て一致し、`batch` 欄を持つ 4 本の 4 項目 = 16 項目も再測定値と一致 (計 58/58)。
3. **Pitcher は殻を持たない MSVC C++ 単体のため、閉包 (vtable override 起点) の手法が適用できない**。 `.pdata` 1,363 関数の全 lift は RetDec 完走・
   f80 0 だが `emcc -c` は未通過 (§4)。 Scratcher の engine (timecode decoder) も同様。 Newtone の engine (VST、`.pdata` 10,656 関数) は RetDec が終わらず**未測定** (§4)。
4. **host 呼出面は P0b の応答表で覆える。** 殻 7 本の Dispatcher 即値 ID は {2, 3, 14, 30, 36, 38, 50} の 7 種 20 site で、`hs_ids.json` に**不足 0**。
   別算法の独立走査は同じ 20 site を取りこぼしなく再現し、#506 で見えた ID 59 のような差分は出なかった (§2)。
   Dispatcher 以外の host slot 呼出は 74 site あり、P0b では全て fail-soft (応答 0) のみ。
5. **SIMD kernel 表への依存は 5 本** (Vocoder 4 / Gross Beat 2 / Newtime 3 / Newtone 3 / Vocodex 7 site。 Scratcher と Pitch Shifter は閉包内 0 site)。
   閉包内で呼ぶ kernel は 15 種 19 site で、P0c の `kernel_table.json` (0x5de390–0x5e1780 帯の 80 実装) に載るのは 9 種、0x61xxxx / 0x62xxxx 帯の 6 種は表に無い (§3)。
6. **変更は `tools/plugins/pitch_time/` のみ。** gate の自己検査 (ネガコン) は §5。

## 1. 閉包 lift 結果 (Delphi 殻 7 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / Eff_Render ほか) から `call/jmp rel32` で到達する、
framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。 frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。
vcall / ptr = 間接呼出 site 数 (件数のみ)。 iat = IAT 経由 Win32 呼出 site。 define = `p.final.ll` の `define` 数。

| プラグイン | block | Tier (見積 人日) | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | define | f80 関数 | 未実装 helper | `emcc -c` rc | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Fruity Scratcher | 19071 | T2 (4) | 42 / 18,530 | 70 / 8,366 | 71 | 15 | 1 | 42 | 0 | 0 | 0 | 3 |
| Fruity Vocoder | 19087 | T0 (0.5) | 23 / 14,659 | 59 / 16,047 | 25 | 13 | 1 | 23 | 0 | 0 | 0 | 3 |
| Gross Beat | 19098 | T1 (1.5) | 60 / 32,035 | 95 / 11,616 | 50 | 53 | 1 | 60 | 0 | 0 | 0 | 5 |
| Newtime | 19166 | T1 (1.5) | 94 / 22,500 | 119 / 14,903 | 107 | 25 | 0 | 94 | 0 | 0 | 0 | 4 |
| Newtone | 19217 | T3 (15) | 99 / 23,757 | 119 / 14,833 | 113 | 25 | 0 | 99 | 0 | 0 | 0 | 4 |
| Pitch Shifter | 19221 | T1 (1.5) | 34 / 16,875 | 74 / 14,485 | 74 | 5 | 0 | 34 | 0 | 0 | 0 | 3 |
| Vocodex | 19270 | T2 (4) | 116 / 74,093 | 199 / 45,273 | 171 | 90 | 2 | 118 | 0 | 0 | 0 | 11 |
| 計 | | | **468 / 202,449** | | | | | 470 | 0 | 0 | 0 | |

- 最右の 2 列: `emcc -c -O0 -msimd128` の終了コード (0 = 通過) と lift 秒 (`lift_ranges.sh` のみ、`status.csv` の seconds、run C の 1 回分。 n=3 の min–max は §5)。
  **通過 ≠ 正しさ**: 正しさは差分試験でしか示せない (batch_plan §4)。
- Vocodex の define 118 は閉包 116 + RetDec が range 0x84c570–0x84c949 の内部に切り出した 2 define (0x84c8e3 / 0x84c8f1)。 range 開始 VA の define は 116/116 あり、脱落は 0
  (`judge.py` の欠落監査。 他 6 本は余分 define 0)。
- 殻の直接 Win32 API (`PLUGIN_MATRIX.json` `win_direct_api`、今回は再測定していない): Scratcher = process 1 / dynload 2 / file_io 4、Gross Beat・Vocodex = audio_codec_midi 6、
  Newtime = file_io 3 / clipboard_dnd 1、Newtone = file_io 37 / clipboard_dnd 10 / threads 5 / network 7 / dynload 5 / gdi_direct 5 / process 1、Vocoder・Pitch Shifter = 0。
- T0/T1 の 4 本 (Vocoder / Gross Beat / Newtime / Pitch Shifter) は issue 本文の「T0 41/41, T1 44/45 が `emcc -c` 通過済み」を再現した (4/4)。

## 2. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。
slot0 = Dispatcher。

| プラグイン | host call site 計 | slot0 (Dispatcher) site: 即値 ID (site 数) | 動的 ID | 他 slot (offset: site) |
|---|--:|---|--:|---|
| Fruity Scratcher | 18 | 2 (1) / 14 (2) | 5 | 0x8: 1, 0x68: 2, 0x70: 1, 0x78: 3, 0x100: 1, 0x108: 2 |
| Fruity Vocoder | 7 | 2 (1) | 0 | 0x100: 3, 0x108: 3 |
| Gross Beat | 7 | 2 (1) / 3 (1) | 1 | 0x100: 2, 0x108: 2 |
| Newtime | 18 | 2 (2) / 30 (1) / 36 (1) / 38 (1) | 3 | 0x100: 1, 0x108: 1, 0x120: 1, 0x128: 5, 0x158: 1, 0x160: 1 |
| Newtone | 18 | 2 (2) / 30 (1) / 36 (1) / 38 (1) | 3 | 0x100: 1, 0x108: 1, 0x120: 1, 0x128: 5, 0x158: 1, 0x160: 1 |
| Pitch Shifter | 4 | 2 (1) | 1 | 0x100: 1, 0x108: 1 |
| Vocodex | 37 | 2 (2) / 50 (1) | 2 | 0x8: 1, 0x18: 1, 0x100: 14, 0x108: 14, 0x120: 2 |

- 即値 ID の distinct = {2, 3, 14, 30, 36, 38, 50} (taint 版、計 20 site)。 `hs_ids.json` (35 ID) に**不足 0**。 動的 ID は 15 site (Scratcher 5 / Newtime 3 / Newtone 3 / Vocodex 2 / Gross Beat 1 / Pitch Shifter 1)。
- **別算法の検算** (`ids_crosscheck.py`、taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う): 7/7 本で taint 版の ID 件数を取りこぼしなく再現し、
  独立走査にだけ現れる ID も 0 だった (#506 の Maximus / Soundgoodizer の ID 59 に相当する差分は無し)。 比較した site は 20。
- 他 slot の 74 site は offset 0x8 / 0x18 / 0x68 / 0x70 / 0x78 / 0x100 / 0x108 / 0x120 / 0x128 / 0x158 / 0x160 で、P0b の host shim は slot0 と slot6 以外を fail-soft (応答 0 + 呼出記録) にしている
  (`framework/REPORT.md` 冒頭の TFruityHost shim の行)。 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。 0x68–0x78 は Scratcher だけ、0x128 / 0x158 / 0x160 は Newtime と Newtone だけ。
  これらの意味は ctor 完走 (P0b 未達部) の後に Eff_Render へ到達して初めて決まる。
- Newtime と Newtone は host 呼出面が完全に同一 (18 site、ID 2×2 / 30 / 36 / 38、動的 3、同じ slot 内訳) で、閉包は 94 → 99 関数。 同系統のコードと推定する (関数単位の比較は未実施)。

## 3. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` (kernel 変数経由・関数ポインタ slot 経由・直接 call の 3 経路) を再利用し、call site の所在関数を閉包 ranges / frontier で分類。
kernel 番号は Balance (block 18983) の VA に正規化済み。 `[x87 有無]` は `work/kernel_table.json` (`inventory/kernel_table.py`) の kernel 実装が x87 命令を含むか。

| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site 数) [x87 命令の有無] | frontier 内 site | DLL 固有関数走査の site / kernel 種 |
|---|--:|---|--:|---|
| Fruity Scratcher | 0 | — | 0 | 22 / 1 |
| Fruity Vocoder | 4 | 0x5decb0 (3) [x87 無], 0x5dedf0 (1) [x87 有] | 0 | 26 / 3 |
| Gross Beat | 2 | 0x5de4b0 (1) [x87 有], 0x5df240 (1) [x87 有] | 0 | 44 / 14 |
| Newtime | 3 | 0x5df860 (1) [x87 無], 0x61cd50 (1) [表に無し], 0x61cf20 (1) [表に無し] | 0 | 30 / 8 |
| Newtone | 3 | 0x5df860 (1) [x87 無], 0x61cec0 (1) [表に無し], 0x61d090 (1) [表に無し] | 0 | 30 / 8 |
| Pitch Shifter | 0 | — | 0 | 27 / 5 |
| Vocodex | 7 | 0x5de390 (2) [x87 有], 0x5dfbe0 (1) [x87 有], 0x5dfff0 (1) [x87 有], 0x5e03f0 (1) [x87 無], 0x62a140 (1) [表に無し], 0x62ae70 (1) [表に無し] | 0 | 51 / 18 |

閉包内の kernel は 15 種 19 site (表内 9 種 / 表に無し 6 種)。 P0c の記録 (`p0c/REPORT.md`、本 PR では再測定していない) との対応:
- bit-exact / 許容条件つきの記録がある: 0x5dedf0 (f32chain、x87fix 後 buf_diff 2,571,305 → 0、2000 case)、0x5df240 (f32 mul、出力バッファ bit-exact)、0x5dfbe0 (rc_chop、ext 修正後 288,922 → 0)、
  0x5de390 / 0x5de4b0 (f64mem 区分、±1 ulp 0.018% を許容条件として記録)、0x5decb0 / 0x5df860 (p0c4 の ABI 修正後に buf_diff 0)。
- 使用 kernel として記録はあるが bit-exact の記録は見当たらない: 0x5e03f0 (§2 の「per-DLL variant は機械語が同一」)。
- P0c REPORT に記載が見当たらない: 0x5dfff0 (x87 有) と、kernel 表に載らない 6 種 (0x61cd50 / 0x61cf20 は Newtime、0x61cec0 / 0x61d090 は Newtone、0x62a140 / 0x62ae70 は Vocodex)。
  0x61xxxx / 0x62xxxx は Balance の正規化から外れた DLL 固有 VA の可能性があるが未確認 (推定)。
- Scratcher と Pitch Shifter は閉包・frontier とも kernel 0 site。 DSP 本体が閉包にあるか framework 内部にあるかは未追跡 (#506 §3 と同じ留保)。 この 2 本と、kernel 以外を使う部分は
  kernel 単位の差分試験 (P0c) では保証できず、**Eff_Render 単位の差分試験が必須**。

## 4. C++ module 3 本 (Pitcher 本体 / Scratcher engine / Newtone engine)

3 本とも MSVC C++ (VS2019, link 14.29)。 `plugin_closure.py` の起点 (Delphi vtable override) が無いため §1 の閉包は作れず、`cpp_lift.sh` で全 `.pdata` 関数を
RetDec+pass 鎖 → `emcc -c` に通した (#506 の `engine_lift.sh` と同方式)。

| module | block | サイズ B | `.text` B | `.pdata` 関数 / B | export | import (DLL: 関数数) |
|---|--:|--:|--:|--:|---|---|
| Pitcher (本体、殻なし) | 19222 | 446,464 | 278,848 | 1,363 / 263,719 | CreatePlugInstance | KERNEL32 84 / USER32 31 / GDI32 11 / ADVAPI32 3 / SHELL32 1 / ole32 3 |
| Scratcher `engine_x64.dll` | 19072 | 165,376 | 96,508 | 447 / 91,339 | createTimecodeDecoder / destroyTimecodeDecoder / getPosition / gotSignal / process | KERNEL32 72 |
| Newtone `Newtone_Engine_x64.dll` | 19216 | 4,967,424 | 3,513,928 | 10,656 / 3,174,673 | VSTPluginMain | WS2_32 2 / KERNEL32 144 / USER32 88 / GDI32 24 / SHELL32 4 / ole32 6 / WINMM 2 / IMM32 5 |

| module | RetDec rc | final.ll define | `.pdata` で define 無し | f80 関数 | 未実装 helper (うち VEX `__asm_v*`) | `emcc -c` | 局所修復後 | lift 秒 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Pitcher | 0 | 1,434 | 1 / 1,363 (61 B) | 0 | 94 (67) | 失敗 | 失敗 | 35–36 |
| Scratcher engine | 0 | 465 | 1 / 447 (61 B) | 1 | 62 (54) | 失敗 | 失敗 | 10–11 |
| Newtone engine | **未完** | — | — | — | — | — | — | 4 分 20 秒超で中止 |

- 失敗の連鎖 (clang は最初の型エラーで止まるため 1 件ずつ露見。 最初のエラー文は `work/pitch_time/cpp<block>/c0/first_errors.txt`):
  1. 両 module: `icmp eq ptr %x, %argN` (`%argN` は i64 仮引数) → "defined with type 'i64' but expected 'ptr'" (**E1**)。 `cpp_fixcmp.py` (本 dir 内の局所 pass、共有鎖には未組込) が Pitcher 6 / Scratcher 4 operand を直す。
  2. 直した後の最初のエラーは両 module とも `zext constexprs are no longer supported` (**E2**)。 E2 の先に何が露見するかは未確認 (clang は最初のエラーで止まる。 #506 の E3 に当たるかも不明)。
  3. E1 / E2 は #506 REPORT §7 の同名類型と同型。 新規の類型は無い。
- `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`cpp_defs.py`。 分母は `.pdata` 関数数、括弧は欠けた range の長さ)。 2 module とも 1 件 61 B で、final.ll 内から参照されていない (missing_ref 0)。 原因 (RetDec の関数境界統合 / 復号失敗) は未調査。
  逆に range 内部に RetDec が切り出した別 define は Pitcher 71 / Scratcher engine 18。
- 未実装 helper の VEX 内訳の再現: `grep -o 'unimplemented: [^ ]* __asm_[a-z0-9_]*' work/pitch_time/cpp19222/c0/e.simd.log | sort -u | grep -c '__asm_v'` → 67 (全体は `sort -u | wc -l` = 94。 19072 は 54 / 62)。
  VEX 以外の未実装は SSE の packed 比較 (`cmpeqps` ほか) / `blendvps` / `cvtpd2dq` と CRT 由来の `fxsave` / `in` / `int` / `iretd`。 CPUID 分岐で SSE 路に固定できるかは未確認。
- Scratcher engine の f80 1 関数は #197 の `f80_lower.py` の適用対象。 engine は timecode decoder の API で、殻 (`dynload` 2) との結合 (LoadLibrary 経路) は未解析。
- **Newtone engine は未測定**: `cpp_lift.sh 19216 900` は range 文字列が 255,737 字 (retdec の引数 1 個の上限 131,072 B 超) のため 7 chunk に分けた。 chunk 0 (1,666 range / 874,451 B) で RetDec のログが
  `optimizations` phase (35 s 時点) から進まず、4 分 20 秒を超えても終了せず RSS 6.2 GB に達したため中止した (n=1。 比較: #506 REPORT 記載の Multiband engine 1,658 関数 / 359,159 B は 38–41 s)。
  `.drc.ll` は途中で出力されていた (33.7 MB) が、`lift_ranges.sh` は RetDec の終了を待つ。 7 chunk 全体は 60 分の job 上限に収まらないと判断した。 したがって T3 (15 人日、推定) の根拠となる engine 側の到達性は未確認。
- 外形だけから言えること: Newtone engine は VST2 plugin (`VSTPluginMain`) で USER32 88 / GDI32 24 を import するため GUI 込みの完全な VST、WS2_32 2 関数 (issue 本文の「ws2_32 保有」を確認)。
  文字列ヒット (大小無視、ASCII + UTF-16LE): engine に zplane 8 / elastique 15、Newtone 殻・Newtime 殻に zplane 各 1。 ライセンス判断は #152 / #163 に従う (事実整理のみ)。

issue 本文の事実主張の再計測 (`closure_facts.py` の `claims`、`PLUGIN_MATRIX.json` の hints): elastique 文字列を持つ win モジュールは **31** (本文の「31 DLL」と一致)。 pitch-time ファミリでは 6 モジュール
(Gross Beat / Newtime / Newtone 殻 / Newtone engine / Vocodex 殻 / Sytrus)。 殻 7 本の elastique 文字列ヒット数は Scratcher 2 / Vocoder 2 / Pitch Shifter 6 / Gross Beat 24 / Newtime 24 / Newtone 24 / Vocodex 25。
API 利用なのか文言なのかは未解析。 Pitcher 本体は 436.0 KiB (446,464 B) で Delphi framework 無し (hints: TFruityPlug / FruityWrapper)。 Vocodex に同梱の Sytrus は block 19294 (`Synthesizer/Sytrus_x64.dll`、6,308,352 B)、
Vocodex 殻内の文字列 'Sytrus' は 1 件。 Sytrus の lift は #209 [PLG-G4] の範囲で、本 PR は測っていない。

## 5. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner)

gate の設計 (#506 のレビュー指摘への対応):
- `judge.py` が 1 block ごとに 行の有無 / closure_funcs>0 / lift_rc==0 / declares_unimpl==0 / f80_funcs==0 / emcc_c_rc==0 に加え、**欠落監査** (ranges 数 == closure_funcs、全 range の開始 VA に `function_<VA>` の define がある) を課す。
  `-1` (未測定) は不合格。 終了コード: 0 合格 / 1 不合格 (理由を全件表示) / 2 入力不正。 前回実行の合格行で今回の失敗を隠さないよう、`--since-line` で今回追記された行だけを読む。
- e2e は `set -euo pipefail` + EXIT trap で、判定・`matrix_check`・`ids_crosscheck`・`judge --engines` のどれかが非 0 なら非 0 で終わり、最終行は `[pitch_time_e2e] FAIL`。 `OK` 行は全て通ったときだけ出る。
- 初回の e2e (未コミット) で gate が実際に落ちた: Vocodex が `defines=118 != closure_funcs=116` で exit 1。 原因は RetDec が range 0x84c570–0x84c949 の内部に 2 define を切り出したことで、脱落ではない。
  判定条件を「define 数の一致」から「全 range の開始 VA に define がある」に直した (§1)。

| 項目 | 実測 |
|---|---|
| `pitch_time_e2e.sh` 全体 (3 回、HEAD A = 5938ec9、B・C = 1b35efd。 A は Newtone engine の RetDec 1 プロセスが最初の約 50 s 並走) | A 168.8 s / B 169.1 s / C 168.9 s、全て exit 0 (開始時 load average 1 分: 1.05 / 0.64 / 0.99。 逐次実行で並列数 1。 B・C の 2 回は 1b35efd、A との差は未使用だった `--heavy` 分岐の削除のみ) |
| lift 秒 (`status.csv`、3 回の min–max) | 殻: Scratcher 3 / Vocoder 2–3 / Gross Beat 5 / Newtime 3–4 / Newtone 4 / Pitch Shifter 2–3 / Vocodex 11–12 (s)。 C++: Pitcher 35–36 / Scratcher engine 10–11 (s) |
| 結果の一致 | A・B・C の正規化ログ (judge の表示、matrix_check・ids_crosscheck の出力、`cpp.csv` の lift_s 以外、clang の最初のエラー文) の `diff` が空 (A と B、B と C) |
| `matrix_check.py` | 58/58 (閉包 42 + batch 16) |
| `ids_crosscheck.py` | 7/7、20 site を突合 |
| `pitch_time_nega.sh` | exit 0、5.3 s (HEAD 1b35efd)。 NC1 / NC2 の数値確認に加え、期待した終了コードの確認 28 件が全て一致 (`<-- FAIL` 0 件) |
| 前提 inventory (初回のみ) | `win_scan` から `kernel_table` まで 370 s (並列 14 プロセス / 4 core、load average 8–17)。 `block_manifest.json` が tarball に無く `nsis_names.py` が動かないため `mk_blockmap.py` が `PLUGIN_MATRIX.json` から代替の blockmap (182 record) を合成 |

ネガティブコントロール (`pitch_time_nega.sh`。 全件が期待した終了コードになることを数値で確認):

| NC | 壊し方 | 結果 (実測) |
|---|---|---|
| NC1 | Vocoder の final.ll の関数 1 つの `ret` を除去 | `emcc -c` rc 0 → 1 |
| NC2 | Vocoder の閉包 ranges の末尾 1 つを落として再 lift | range 22 → 21、define 23 → 21、`function_6d5790` 1 → 0 (RetDec は 1 range から複数 define を出すため差は 1 と限らない) |
| NC3 | `judge.py` に不合格を 1 つずつ注入 (Scratcher / Newtime): emcc_c_rc=1 / lift_rc=1 / f80=3 / unimpl=5 / 行欠落 / f80=-1 / define 脱落 / ranges≠closure_funcs | 無改変 rc 0。 8 種とも rc 1 |
| NC3 | 入力不正: 非数値 / block 指定なし / ファイル無し / 監査引数なし。 古い行のみ (`--since-line`) | rc 2 ×4。 古い行のみ rc 1 |
| NC4 | `pitch_time_e2e.sh --judge-only` に不合格の status CSV / cpp CSV を渡す | どちらも rc 1、`PASS` 行なし、`FAIL (exit` 行あり。 合格 CSV は rc 0 |
| NC5 | `matrix_check.py`: closure_funcs +1 / batch 欄の emcc_c_rc=1 / 殻 0 本 | 無改変 rc 0。 3 種とも rc 1 |
| NC6 | `ids_crosscheck.py`: taint 側 ID 件数 +1 (Scratcher の ID 14) / ID を全て空に | 無改変 rc 0。 2 種とも rc 1 (空の突合は合格にしない) |
| NC7 | `judge.py --engines`: 期待値を 1 つ変更 / 測定行の欠落 / expected に無い block | 無改変 rc 0。 変更・欠落 rc 1、未知 block rc 2 |

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`)、host / kernel 依存の静的な数え上げ、C++ module 2 本の到達性。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp、Newtone engine の lift、クリーン worktree (inventory 生成から) での全工程再現。 範囲外の項目について、本書は何も主張しない。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 Eff_Render 単位の native / wasm harness が無く、P0a/P0b/P0c 未完 | #204 を閉じられない | #195 / #196 / #197 の完了後に #204 を再開 (Closes はその時)。 harness は #506 REPORT §6 が PM に依頼した「[PLG-F3a]」と共通 (未起票) |
| Render test .flp の E2E (出口条件 4)。 Newtime / Newtone は `render_test` 無し (`PLUGIN_MATRIX.json`) | 同上 | FLEngine 統合待ち。 親 #14 / #204 |
| Newtone engine (10,656 関数) の lift が RetDec 段で終わらない (§4) | T3 15 人日 (推定) の根拠が engine 側で未確認 | 新規子チケットを PM に起票依頼: 「[PLG-F7a] Newtone engine の lift: RetDec の時間・メモリ (chunk 当り 4 分超 / RSS 6 GB 超) と分割方針」 |
| Pitcher 本体・Scratcher engine の `emcc -c` 未通過 (E1→E2、未実装 helper 94 / 62、define 無し 1 件ずつ)、Scratcher engine の f80 1 関数 | T2 の 2 本 (見積 4 人日/本) に未知工数 | #506 REPORT §6 の「[PLG-F3b] C++ engine DLL の lift 鎖」に Pitcher 本体・Scratcher engine を追加するよう PM に依頼。 f80 は #197 にコメント |
| kernel 6 種 (0x61cd50 / 0x61cf20 / 0x61cec0 / 0x61d090 / 0x62a140 / 0x62ae70) が `kernel_table.json` に無く、0x5dfff0 の P0c 記録も見当たらない (§3) | Newtime / Newtone / Vocodex の kernel 保証範囲が不明 | #197 (P0c) にコメント |
| host 他 slot 74 site と動的 ID 15 site の意味 (§2) | P0b の fail-soft (応答 0) で足りるかは未確認 | #196 作業 5 (0x13173a0 全 case 解析) にコメント |
| elastique / zplane / Sytrus の文字列ヒットの意味 (§4) と Newtone engine の第三者ライセンス | Gross Beat / Newtime / Newtone / Vocodex の配布可否 | #152 / #163 にコメント (事実のみ) |
| Vocodex と Sytrus (block 19294) の結合方式 | Vocodex の見積 4 人日に Sytrus 側が含まれるか不明 | #209 [PLG-G4] にコメント |
| 本 PR と #506 で `env.sh` / `mk_blockmap.py` / `matrix_check.py` / `ids_crosscheck.py` / `cpp_*` (#506 の `engine_*`) が重複 | 保守性 | #506 のマージ後に `tools/plugins/` 直下へ共通化する子チケットを PM に提案。 #506 の判定にも `judge.py` と同じ gate を入れる (レビュー指摘) |
| `nsis_names.py` が Actions 上で動かない (`block_manifest.json` 不在) | inventory の再現性 | `mk_blockmap.py` で回避済み。 `docs/WORKFLOW.md` §11 への追記は PM 判断 |
| `docs/DOC_MAP.md` の REPORT 索引に本書が未掲載 | 索引漏れ | PM が追記 |

## 7. DEFECTS.md 行案

新規の類型は無い。 §4 の E1 / E2 は #506 REPORT §7 の E1 / E2 と同型の loud な IR 型エラー (emcc が拒否)。 差分試験を未実施のため、silent miscompile の有無は未確認。

## 8. 成果物

| ファイル | 内容 |
|---|---|
| `pitch_time_e2e.sh` | 殻 7 本 → batch_lift → `judge.py` (gate) → `closure_facts.py` → `matrix_check.py` → `ids_crosscheck.py` → C++ module 2 本 → `judge.py --engines` (gate) |
| `pitch_time_nega.sh` | 各 gate のネガティブコントロール (NC1–NC7) |
| `judge.py` | shell 判定 (欠落監査込み) と `--engines` (期待列との drift 検出)。 不合格で非 0 |
| `expected_cpp.csv` | C++ module 2 本の測定列の基準 (lift_s 列を除く)。 値は 1 回目の測定を記録したもので、A・B・C の 3 回が一致した (一致 = drift 無し。 独立な正解ではない) |
| `closure_facts.py` | 閉包 / host ID / kernel 依存 / C++ module 外形 / 文字列ヒット / issue 本文の事実主張 → `work/pitch_time/facts.json` |
| `matrix_check.py` `ids_crosscheck.py` | `PLUGIN_MATRIX.json` との突合 (閉包 6 項目 + batch 4 項目) / Dispatcher ID の別算法検算 |
| `cpp_lift.sh` `cpp_ranges.py` `cpp_fixcmp.py` `cpp_defs.py` | C++ module の全 `.pdata` lift (chunk 分割対応。 多 chunk の集計は合成入力で確認しただけで、実 module では未実行)・局所修復・欠落監査 |
| `mk_blockmap.py` `env.sh` | `block_manifest.json` 不要の inventory 前提 / 環境 |
