# tools/plugins/ctlvfx/REPORT.md — PLG-F8 (#205) controller / VFX / gui-only 他 28 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/ctlvfx/` のみ / 検証起点 commit: **e6243b5** (e2e・gate 4 本・facts の実測) と **10de9b8** (nega・probe の実測)。
  10de9b8 以降の差分は `REPORT.md` と `report_tables.py` (表の体裁) のみ
- 再現: `bash tools/plugins/ctlvfx/ctlvfx_e2e.sh` (gate 4 本 + 実測) / `bash tools/plugins/ctlvfx/ctlvfx_nega.sh` (全 gate のネガティブコントロール)
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 環境は `ctlvfx/env.sh`
- 手法の出典: 先行 PR #506 (PLG-F3 dynamics 7 本、未マージ) の `dynamics_e2e.sh` / `matrix_check.py` / `ids_crosscheck.py` / `engine_*`。 #506 は未マージのため
  本 dir に複製して独立させた (`env.sh` `mk_blockmap.py` `engine_*` は複製、他は 28 本向けに書き直し)。 #506 の reviewer 指摘 2 件 (判定が不合格でも exit 0 /
  判定自体のネガコン無し) は最初から避けた (§5)
- 既知類型との関係 (`docs/DEFECTS.md`): 差分試験を未実施のため**確認できていない**。 関係しうるのは D15 (stage-0 のメモリ間接 call 欠落): 本 28 本の
  間接 call site は vcall 2018 + ptr 299 (§1)。 §7 の 1 件 (rep stosb helper 未実装) は loud な link 時エラーで silent miscompile ではない

## 0. 結論 (先出し)

1. **#205 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** PLG-P0a #195 / P0b #196 / P0c #197 が OPEN で、
   Eff_Render / 各 override 単位で native と wasm を比べる harness も repo に無い。 GUI 5 本 (HTML NoteBook / NoteBook / NoteBook 2 / Big Clock / Dashboard) は
   GUI shim #10 にも依存する。 → PR は **`Refs #205`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は 28 本中 27 本が gate を通り、Dashboard 1 本が不合格。** 27 本は RetDec+pass 鎖が完走 (lift_rc 0)、`emcc -c` 通過、`x86_fp80` 関数 0、
   未実装 helper 宣言 0。 Dashboard は lift_rc 0・`emcc -c` 通過だが **`__asm_rep_stosb_memset(ptr,i8,i64)` が未実装で宣言のみ残る** (定義が供給されなければ link で未解決になる。 §6・§7)。
   `emcc -c` 通過は宣言だけで通るため、`declares_unimpl` を判定に含めない gate ではこの 1 本を見逃す。
   このため `ctlvfx_e2e.sh` は **意図的に exit 1** (28/28 になるまで赤)。 閉包合計 **1822 関数 / 654,352 B** (28 本、`PLUGIN_MATRIX.json` の `lift` 欄と 28 本 × 6 項目すべて一致)。
3. **規模は 2 極**: Dashboard (417 関数 / 128,061 B) と Fruity Envelope Controller (423 / 133,907 B) の 2 本で 840 関数 / 261,968 B (全体の 関数 46.1% / バイト 40.0%)。 残り 26 本は 7〜94 関数 / 1,863〜43,660 B。
   この 2 本は kernel 表の init が検出できず (§3)、#205 本文が「framework 別構成 (一致 44%) の 3 本」に含めるうちの 2 本 (P0a #195 の確認結果待ち)。
4. **Eff_Render を持つのは 9 本のみ** (Edison / LSD / Peak Controller / Spectroman / dB meter / Transmitter / Transporter / Tuner / Wave Candy)。 残り 19 本は
   Dispatcher / ProcessParam / ProcessEvent / NewTick / Voice 系 (TriggerVoice を持つ 11 本 = VFX 7 + Generators 4) の override が主で、Eff_Render を override しない (Dashboard と Voltage Controller は Gen_Render を持つ)。 差分試験の単位は Eff_Render 無しの 19 本では「イベント列 → 状態 / 出力イベント」になる (harness 未整備)。
5. **host 呼出面**: 即値 Dispatcher ID は 15 種 56 site (動的 ID 7 site)。 `hs_ids.json` (35 ID) に無い ID が **4 種 (25 / 84 / 93 / 102)**: VFX Envelope 84 ×2、VFX Script 102 ×3、
   Dashboard 25 ×1、Fruity Envelope Controller 93 ×1。 P0b #196 の応答表に足す対象 (§2)。 VFX Script は IAT 経由の Win32 呼出が 79 site (他は 0〜3)。
6. **SIMD kernel 表への依存は 3 本**: Edison (3 site)・LSD (1)・Spectroman (2)。 他 23 本は閉包内 0 site。 Dashboard / Envelope Controller は init 未検出で**未測定** (0 ではない)。
7. **C++ engine 2 本 (Tuner / VFX Sequencer の T2) は RetDec まで通るが `emcc -c` は未通過** (§4)。 #506 の engine と同じ型エラー類型 (E1 → E2) が出る。
8. **gate は初回実測で 2 回自己修正した** (§5.2): `defines == closure_funcs` は RetDec の range 内分割 (4 本で define が +2〜+5) で誤不合格 → `defines >= closure_funcs` と `closure_defs.py` に分離。
   `ids_crosscheck.py` の「8 命令窓」は Dashboard の `mov r8d,8` → `call [rax]` (間 8 命令超) を拾えず false NG → clobber 打切りに変更。

## 1. 閉包 lift 結果 (Delphi 殻 28 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / ProcessEvent / NewTick / Voice 系 / Eff_Render 等) から `call/jmp rel32` で
到達する、framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。 frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。
vcall / ptr = 間接呼出 site 数 (件数のみ記録)。 iat = IAT 経由 Win32 呼出 site。 final.ll define > 閉包関数数 の 4 本 (Formula Controller +5 / HTML NoteBook +4 / Dashboard +2 / Envelope Controller +2) は
RetDec が 1 range を複数 define に切ったもので、range 開始 VA の define 脱落は 28 本とも 0 (`closure_defs.py`、§5)。

| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Control Surface | 18797 | T2 | 59 / 25,234 | 122 / 14,594 | 160 | 20 | 0 | 59 | 0 | 0 | 0 | 4–5 |
| Edison | 18955 | T1 | 89 / 40,228 | 207 / 37,466 | 113 | 18 | 1 | 89 | 0 | 0 | 0 | 6–7 |
| Fruity Big Clock | 18986 | T1 | 10 / 4,229 | 23 / 3,532 | 8 | 3 | 0 | 10 | 0 | 0 | 0 | 2 |
| Fruity Formula Controller | 19012 | T1 | 63 / 24,040 | 97 / 11,337 | 87 | 10 | 0 | 68 | 0 | 0 | 0 | 4–5 |
| Fruity HTML NoteBook | 19016 | T1 | 34 / 8,902 | 81 / 11,144 | 43 | 4 | 1 | 38 | 0 | 0 | 0 | 2–3 |
| Fruity LSD | 19019 | T2 | 26 / 8,772 | 63 / 9,500 | 45 | 8 | 0 | 26 | 0 | 0 | 0 | 2–3 |
| Fruity NoteBook | 19052 | T0 | 8 / 2,179 | 28 / 3,001 | 23 | 1 | 0 | 8 | 0 | 0 | 0 | 2–3 |
| Fruity NoteBook 2 | 19054 | T0 | 12 / 3,064 | 37 / 4,123 | 22 | 1 | 0 | 12 | 0 | 0 | 0 | 2 |
| Fruity Peak Controller | 19062 | T0 | 26 / 8,529 | 44 / 6,357 | 16 | 7 | 0 | 26 | 0 | 0 | 0 | 3 |
| Fruity Spectroman | 19080 | T0 | 20 / 10,098 | 59 / 15,765 | 25 | 11 | 0 | 20 | 0 | 0 | 0 | 3 |
| Fruity X-Y Controller | 19093 | T0 | 36 / 9,242 | 60 / 8,891 | 35 | 1 | 0 | 36 | 0 | 0 | 0 | 3 |
| Fruity X-Y-Z Controller | 19094 | T0 | 44 / 20,142 | 90 / 14,484 | 119 | 3 | 0 | 44 | 0 | 0 | 0 | 4–5 |
| Fruity dB meter | 19096 | T0 | 7 / 2,222 | 19 / 2,639 | 2 | 2 | 0 | 7 | 0 | 0 | 0 | 2–3 |
| Transmitter | 19253 | T1 | 46 / 29,698 | 86 / 20,699 | 93 | 12 | 0 | 46 | 0 | 0 | 0 | 4 |
| Transporter | 19254 | T1 | 39 / 22,741 | 76 / 17,260 | 54 | 11 | 0 | 39 | 0 | 0 | 0 | 4 |
| Tuner (+engine 19256) | 19255 | T2 | 18 / 10,645 | 59 / 15,633 | 40 | 5 | 0 | 18 | 0 | 0 | 0 | 3 |
| VFX Color Mapper | 19257 | T0 | 13 / 1,863 | 21 / 2,931 | 16 | 1 | 0 | 13 | 0 | 0 | 0 | 2 |
| VFX Envelope | 19258 | T0 | 60 / 18,674 | 86 / 10,912 | 82 | 8 | 0 | 60 | 0 | 0 | 0 | 4–5 |
| VFX Key Mapper | 19259 | T0 | 19 / 5,848 | 32 / 4,388 | 34 | 2 | 0 | 19 | 0 | 0 | 0 | 2–3 |
| VFX Keyboard Splitter | 19260 | T0 | 32 / 9,988 | 40 / 7,124 | 33 | 3 | 0 | 32 | 0 | 0 | 0 | 4 |
| VFX Level Scaler | 19261 | T0 | 29 / 9,600 | 45 / 5,686 | 29 | 5 | 0 | 29 | 0 | 0 | 0 | 3 |
| VFX Script | 19262 | T1 | 94 / 25,859 | 111 / 14,610 | 102 | 17 | 79 | 94 | 0 | 0 | 0 | 4 |
| VFX Sequencer (+engine 19264) | 19263 | T2 | 51 / 14,364 | 70 / 10,907 | 71 | 4 | 0 | 51 | 0 | 0 | 0 | 4 |
| Wave Candy | 19297 | T1 | 72 / 43,660 | 119 / 25,358 | 88 | 13 | 1 | 72 | 0 | 0 | 0 | 15 |
| Dashboard | 21206 | T2 | 417 / 128,061 | 116 / 15,913 | 348 | 62 | 3 | 419 | 0 | 1 | 0 | 12 |
| Fruity Envelope Controller | 23648 | T3 | 423 / 133,907 | 103 / 11,870 | 185 | 61 | 3 | 425 | 0 | 0 | 0 | 14 |
| Fruity Keyboard Controller | 23660 | T1 | 20 / 5,293 | 43 / 5,523 | 27 | 2 | 0 | 20 | 0 | 0 | 0 | 3 |
| Fruity Voltage Controller | 23675 | T1 | 55 / 27,270 | 68 / 14,204 | 118 | 4 | 0 | 55 | 0 | 0 | 0 | 5 |
| 計 | | | **1822 / 654,352** | | | | | 1835 | 0 | 1 | 0 | 各回の計 130 / 125 / 127 |

- lift 秒の列は status.csv に残る全回 (n=3 回、`lift_ranges.sh` のみ。 emcc 除く) の min–max
- Tier 別 (本数 / 閉包関数 / B / gate 項目全 0 の本数): T0: 12 / 306 / 101,449 / 12、T1: 10 / 522 / 231,920 / 10、T2: 5 / 571 / 187,076 / 4、T3: 1 / 423 / 133,907 / 1

- `emcc -c` 列は `emcc -c -O0 -msimd128` の終了コード (0 = 通過)。 **通過 ≠ 正しさ**: 正しさは差分試験でしか示せない (batch_plan §4)。 宣言のみの未実装 helper は `emcc -c` を通る (Dashboard)。
- 本表の iat は閉包内の IAT 呼出 site 数で、`PLUGIN_MATRIX.json` の `win_direct_api` とは集計範囲が異なる。 Edison は élastique を静的に含み (PLUGIN_MATRIX の deps)、`testdll_x64.dll`
  (45,056 B、CreatePlugInstance 無し) を併せ持つが、本測定の対象は殻の閉包 89 関数のみ (élastique が閉包に入っているかは未確認)。

## 2. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。 slot0 = Dispatcher。

| プラグイン | host call site 計 | slot0 (Dispatcher) 即値 ID (site) | 動的 ID | 他 slot (offset: site) |
|---|--:|---|--:|---|
| Control Surface | 6 | 3 (2) / 2 (1) | 0 | 0x98: 1, 0x100: 1, 0x108: 1 |
| Edison | 19 | 36 (2) / 19 (1) / 38 (1) / 2 (1) | 0 | 0x100: 7, 0x108: 7 |
| Fruity Big Clock | 3 | 37 (2) / 2 (1) | 0 | — |
| Fruity Formula Controller | 9 | 36 (1) / 2 (1) | 0 | 0x98: 1, 0x100: 3, 0x108: 3 |
| Fruity HTML NoteBook | 3 | 14 (1) / 2 (1) | 1 | — |
| Fruity LSD | 8 | 2 (1) | 1 | 0x100: 2, 0x108: 2, 0x128: 2 |
| Fruity NoteBook | 1 | 2 (1) | 0 | — |
| Fruity NoteBook 2 | 1 | 2 (1) | 0 | — |
| Fruity Peak Controller | 8 | 36 (2) / 2 (1) | 0 | 0x98: 1, 0x100: 2, 0x108: 2 |
| Fruity Spectroman | 5 | 2 (1) | 0 | 0x100: 2, 0x108: 2 |
| Fruity X-Y Controller | 4 | 2 (1) | 0 | 0x98: 1, 0x100: 1, 0x108: 1 |
| Fruity X-Y-Z Controller | 4 | 2 (1) | 0 | 0x98: 1, 0x100: 1, 0x108: 1 |
| Fruity dB meter | 1 | 2 (1) | 0 | — |
| Transmitter | 14 | 50 (2) / 30 (1) / 2 (1) | 0 | 0x98: 1, 0x100: 2, 0x108: 2, 0x120: 1, 0x128: 4 |
| Transporter | 8 | 50 (2) / 2 (1) | 1 | 0x80: 1, 0x120: 1, 0x128: 2 |
| Tuner | 2 | 2 (2) | 0 | — |
| VFX Color Mapper | 9 | — | 0 | 0x28: 2, 0x30: 3, 0x130: 1, 0x138: 1, 0x140: 1, 0x148: 1 |
| VFX Envelope | 13 | 84 (2) | 0 | 0x28: 3, 0x30: 2, 0x100: 1, 0x108: 1, 0x130: 1, 0x138: 1, 0x140: 1, 0x148: 1 |
| VFX Key Mapper | 12 | — | 0 | 0x28: 2, 0x30: 1, 0x100: 2, 0x108: 2, 0x130: 2, 0x138: 1, 0x140: 1, 0x148: 1 |
| VFX Keyboard Splitter | 9 | 3 (1) | 0 | 0x28: 2, 0x30: 2, 0x130: 1, 0x138: 1, 0x140: 1, 0x148: 1 |
| VFX Level Scaler | 11 | — | 0 | 0x28: 2, 0x30: 3, 0x100: 1, 0x108: 1, 0x130: 1, 0x138: 1, 0x140: 1, 0x148: 1 |
| VFX Script | 18 | 102 (3) / 3 (2) / 2 (1) / 36 (1) | 1 | 0x28: 3, 0x30: 2, 0x100: 1, 0x108: 1, 0x138: 2, 0x140: 1 |
| VFX Sequencer | 4 | 2 (1) | 0 | 0x18: 1, 0x100: 1, 0x108: 1 |
| Wave Candy | 4 | — | 0 | 0x100: 2, 0x108: 2 |
| Dashboard | 13 | 27 (2) / 2 (2) / 8 (1) / 25 (1) | 1 | 0x10: 1, 0x28: 1, 0x30: 2, 0x48: 1, 0x98: 1 |
| Fruity Envelope Controller | 8 | 93 (1) / 2 (1) | 1 | 0x10: 1, 0x28: 1, 0x98: 1, 0x100: 1, 0x108: 1 |
| Fruity Keyboard Controller | 4 | 2 (1) | 0 | 0x28: 2, 0x98: 1 |
| Fruity Voltage Controller | 11 | 50 (1) / 2 (1) | 1 | 0x28: 1, 0x30: 1, 0x100: 2, 0x108: 2, 0x128: 2 |

- 即値 ID distinct = 15 種 [2, 3, 8, 14, 19, 25, 27, 30, 36, 37, 38, 50, 84, 93, 102]、即値 ID site 計 56、動的 ID site 計 7、host call site 総計 212
- hs_ids.json に無い即値 ID: {'VFX Envelope': {'84': 2}, 'VFX Script': {'102': 3}, 'Dashboard': {'25': 1}, 'Fruity Envelope Controller': {'93': 1}}
- host call site 0 の plugin: なし

- **別算法の検算** (`ids_crosscheck.py`、taint を使わず閉包を線形逆アセンブルし、`mov r8d, imm` の後 r8 が書き換わる前の `call [reg]` (disp 0) を全数拾う上位集合): 28/28 本で taint 版の ID 件数を取りこぼしなく再現。
- `hs_ids.json` に無い 4 ID (25 / 84 / 93 / 102) は上記の独立走査も同 site を拾う (host 呼出か別オブジェクトの slot0 呼出かは未判別)。
- 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。 Voice 系を持つ 10 本 (VFX 6 + Dashboard / Envelope / Keyboard / Voltage Controller) の 0x28 / 0x30 と、9 本の 0x98 (Control Surface / Formula / Peak / X-Y / X-Y-Z / Transmitter / Dashboard / Envelope / Keyboard Controller) は、他に例が無い slot で意味未解析。

## 3. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` (kernel 変数経由・関数ポインタ slot 経由・直接 call の 3 経路) を再利用し、call site の所在関数を閉包 ranges / frontier で分類。

| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査 site / kernel 種 |
|---|--:|---|--:|---|
| Edison | 3 | 0x5dee50 (2) / 0x5df040 (1) | 4 | 46 / 15 |
| Fruity LSD | 1 | 0x5e8a60 (1) | 0 | 23 / 2 |
| Fruity Spectroman | 2 | 0x5df210 (1) / 0x5df860 (1) | 0 | 24 / 3 |
| Dashboard | init 未検出 | | | |
| Fruity Envelope Controller | init 未検出 | | | |
| 他 23 本 (閉包内 site 0、init 検出済み) | 0 | — | 0 | 22 / 1 ; 27 / 5 ; 30 / 7 ; 33 / 9 ; 42 / 13 |

- 閉包内に kernel 呼出がある plugin: ['Edison', 'Fruity LSD', 'Fruity Spectroman']

- 閉包内 0 site の 23 本は kernel init を検出した上での 0 (3 + 23 + 未測定 2 = 28)。 DLL 固有関数走査の 22 site (0x5de390) は閉包にも frontier にも属さず、framework 側の深い関数にあると推定 (未確認)。
- P0c (`p0c/REPORT.md`) の記録との照合 (本 PR では再測定しない): 0x5df210 は実機械語との差分 0 / 300,000 (p0c/REPORT §3)、0x5df860 は buf_diff=0 に到達済み、
  Edison の 0x5df040 は「abi-mismatch 残 7」(数値差分の対象外)。 **0x5dee50 (Edison) と 0x5e8a60 (LSD) は p0c/REPORT.md に記載が無い** (grep 0 件)。

## 4. T2: C++ engine DLL 2 本

| engine (殻) | block | サイズ B | `.text` B | `.pdata` 関数 / B | KERNEL32 import | export |
|---|--:|--:|--:|--:|--:|---|
| Tuner | 19256 | 226,816 | 144,160 | 598 / 134,669 | 73 | VSTPluginMain, main |
| VFX Sequencer | 19264 | 394,752 | 224,446 | 861 / 209,368 | 88 | CreatePlugInstance |

`engine_lift.sh <block>` で全 `.pdata` 関数を `lift_ranges.sh` (RetDec+pass 鎖) → `emcc -c` に通した結果 (e2e 1 回分。 列は `engines.csv` の列名):

| block | `.pdata` 関数 | RetDec rc | define | f80 関数 | 未実装 helper | `emcc -c` | 局所修復 operand | 修復後 `emcc -c` | lift 秒 | define 無し (B) | missing_ref | range 内の別 define | function define |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 19256 | 598 | 0 | 629 | 1 | 88 | 1 | 4 | 1 | 23 | 2 (538) | 0 | 31 | 627 |
| 19264 | 861 | 0 | 928 | 0 | 39 | 1 | 4 | 1 | 43 | 2 (270) | 0 | 67 | 926 |

- 失敗の連鎖は #506 の engine と同じ 2 類型: E1 `icmp eq ptr %x, %arg3` (`%arg3` は i64 仮引数、`engine_fixcmp.py` で局所修復) → 修復後は E2 `__asm_rep_stosq_memset` 引数の SSA 値入り `zext` 定数式
  ("zext constexprs are no longer supported")。 両 engine とも同一の 2 段。
- 未実装 helper のうち v 接頭辞 (VEX 系) は Tuner 78 / VFX Sequencer 29 (distinct)。 `rep stosb/stosw/stosd` `rep movsb` の helper 未実装も含む (Dashboard の 1 件と同根、§7 H1)。
- `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`engine_defs.py`。 括弧は欠けた range の合計長)。 参照されている欠落 (missing_ref) は両 engine とも 0。
- 以上は到達性の実測で、engine の正しさは何も示していない。

## 5. gate の設計と検証

### 5.1 #506 の reviewer 指摘への対応

| #506 の指摘 | 本 dir の対応 |
|---|---|
| 判定が不合格でも exit 0 (`bad` を表示するだけ、`OK` 行が無条件) | 判定を `judge.py <status.csv>` に切り出し、不合格 1 件で exit 1 (入力不能は exit 2)。 `ctlvfx_e2e.sh` は gate 4 本 (judge / closure_defs / matrix_check / ids_crosscheck) を全部走らせてから、1 本でも不合格なら exit 1 で `[ctlvfx_e2e] FAIL: <gate 名>` を出し、`OK` 行は全合格時のみ |
| 判定の NC が無い | `ctlvfx_nega.sh`: judge 15 件・e2e の判定部 2 件・matrix_check 4 件・ids_crosscheck 3 件・closure_defs 4 件・lift 本体 4 件 (下表) |
| `declares_unimpl` が判定外 (「未実装 helper 0」の主張と不一致) | 判定に含めた (`== 0`)。 `-1` (simd.log 無し) も不合格。 実測で Dashboard の 1 件を検出 |
| (追加) 古い `status.csv` の行で通る | e2e は今回の実行で追記された行だけを `work/ctlvfx/status.csv` にして判定する。 judge は 28 本すべての行を要求し、無い本は不合格 |

判定規則 (`judge.py`、同一 block が複数行なら最後の行): header 一致・targets.py 外の block 無し・名前一致・`closure_funcs > 0`・`lift_rc == 0`・`emcc_c_rc == 0`・`f80_funcs == 0`・`declares_unimpl == 0`・`defines >= closure_funcs`・数値欄が整数。
`closure_defs.py`: 全 range の開始 VA に `define @function_<VA>` があり (missing 0)、閉包外の define が無い (outside 0)。 `matrix_check.py`: facts が targets.py の 28 本と過不足なく一致し、
block が PLUGIN_MATRIX の win モジュールに在り、Tier が #205 本文の表記と一致し、閉包 6 項目が `PLUGIN_MATRIX.json` の `lift` 欄と一致 (28 × 8 + 集合 1 = 225 項目)。
注意: `matrix_check` の期待値 (`PLUGIN_MATRIX.json`、2026-10-10 生成) も `plugin_closure.py` 由来なので、**再現性の確認であって独立検算ではない**。 独立検算は `ids_crosscheck.py` (Dispatcher ID) と、判定の `defines` ⟷ 閉包 ranges の突合 (`closure_defs.py`: RetDec 出力と閉包 ranges は別の工程)。

### 5.2 実測 (コミット済み HEAD・4 core / 15 GiB の Actions runner。 行ごとに HEAD を併記)

| 項目 | 実測 |
|---|---|
| 新規 worktree (`work/` 無し) からの前提 inventory (fl-win64 展開・venv 作成込み。 `win_funcs.py` が大半) | 528 s (並列 14 プロセス / 4 core。 同時にスクリプトを書いていた)。 1 回のみ |
| `ctlvfx_e2e.sh` 全体 (inventory 済み、`--skip-lift` 無し。 2 回、n=2) | **402 s (HEAD 1ab96c7) / 405 s (HEAD e6243b5)**、どちらも exit 1。 開始時 load average (1 分) 2.97 / 1.92。 逐次実行 (facts のみ 4 並列) |
| 内訳 (lift 28 本 / `closure_facts.py` / engine 2 本) | lift 計は下の行。 `closure_facts.py` 単体 **197 s** (4 並列、開始時 load average 0.60、HEAD 10de9b8)。 engine は下の行 |
| lift 秒 (`status.csv` の seconds、3 回の計) | 130 / 125 / 127 s。 plugin 別の min–max は §1 表。 engine: Tuner 22–23 s、VFX Sequencer 43 s (2 回) |
| gate の結果 (HEAD e6243b5) | judge **FAIL 27/28** (Dashboard `declares_unimpl=1`) / closure_defs 28/28 / matrix_check 225/225 / ids_crosscheck 28/28。 最終行 `[ctlvfx_e2e] FAIL: judge`、**exit 1** |
| 初回 (HEAD 1ab96c7) | judge FAIL 27/28 に加え ids_crosscheck **27/28** (Dashboard が false NG: 8 命令窓)。 → e6243b5 で clobber 打切りに変更し 28/28。 exit 1 (`FAIL: judge ids_crosscheck`) |
| 回をまたぐ一致 | `status.csv` の判定列 (seconds 以外) は 2 回とも全 28 行同一。 `facts.json` は sha256 `8fdb5154ce26a4fc…` で 2 回バイト一致 (上の `closure_facts.py` 単体の再実行でも同一 = 3 回目)。 `engines.csv` は lift_s 以外同一 |
| `ctlvfx_nega.sh` (HEAD 10de9b8) | §5.3 |
| 規約面の検査 (`docs/WORKFLOW.md` §6) | `git status --porcelain=v1 -- tools/plugins/ctlvfx` は空。 `git diff 042f869 HEAD --stat` は `tools/plugins/ctlvfx/` のみ (REPORT 込み 18 ファイル)。 20 MiB 超の blob 0 件 (`find -size +20M`)。 `work/` `__pycache__/` は commit していない |

### 5.3 ネガティブコントロール (`ctlvfx_nega.sh`、基準 = 実測 `status.csv` の全行を合格値にそろえたもの。 実測が Dashboard で不合格のため)

`ctlvfx_nega.sh` (HEAD 10de9b8): exit 0、**12.0 s**、33 件すべて期待どおり (期待を外した件数 0)。 対照は常に「壊す前」を同じ手順で通して rc を併記する。

| gate | 壊し方 (対象) | 対照 rc → 壊した rc |
|---|---|---|
| `judge.py` (15 件) | 基準 (全行を合格値にそろえた CSV) → 0。 Fruity dB meter の行を 1 箇所だけ: `emcc_c_rc=1` / `lift_rc=1` / `f80_funcs=3` / `f80_funcs=-1` / `declares_unimpl=5` / `declares_unimpl=-1` / `defines=6` (閉包 7) / 行削除 / targets 外 block の行追加 / `seconds=x` / header 破壊 / name 不一致 | 0 → **1** (12 件すべて) |
| 同 (許容側 2 件) | 不合格行の**後**に合格行がある (再実行で直った形) / 入力ファイル無し | 0 (最後の行を採用) / **2** (入力不能) |
| `ctlvfx_e2e.sh --judge-only` (2 件) | 合格 CSV → rc 0 かつ `[ctlvfx_e2e] OK` が出る。 `emcc_c_rc=1` の CSV → rc 1 かつ `OK` 行が**出ない** (#506 の「不合格でも OK / exit 0」の直接の反証) | 0 → **1** |
| `matrix_check.py` (5 件) | 実測 facts → 0。 dB meter の `closure_funcs` +1 (`MISMATCH Fruity dB meter closure_funcs 7 8` を出力) / Wave Candy の `vcall` +1 / Tuner を facts から欠落 / PLUGIN_MATRIX の VFX Script の Tier を T9 | 0 → **1** (4 件) |
| `ids_crosscheck.py` (3 件) | 実測 facts → 0。 taint 側 ID 3 (Control Surface) の件数 +1 / Wave Candy を facts から欠落 | 0 → **1** (2 件) |
| `closure_defs.py` (4 件) | 実測 batch → 0。 dB meter の final.ll の define を 1 つ別名に (脱落) / 閉包外の `function_deadbeef` を混入 / final.ll を削除 | 0 → **1** (3 件) |
| lift 本体 (dB meter 19096) | 無改変 final.ll の `emcc -c` → 0。 `ret` を 1 つ除去 → **1**。 閉包 ranges 7 → 6 で再 lift: `function_6b47b0` は 1 → 0 本、define 7 → 6 | (L1a/L1b/L2a/L2b + define 減を確認) |

- 実測の `status.csv` そのものに対する `judge.py` は rc 1 (27/28、Dashboard)。 基準を実測から作るのは、実測が不合格でも NC の対照 (rc 0) を成立させるため。
- **#506 の `dynamics_nega.sh` NC2 についての所見 (未確認)**: ranges を `tr ',' '\n' | wc -l` で数えており、`ranges.txt` は末尾改行が無いため 1 少なく数える。 本 dir で同じ式を使うと 7 range を 6 と数え、実際には 2 range を落としていた
  (本 dir は `grep -c .` に修正し 7 → 6 / define 7 → 6)。 #506 の「27 → 25 (RetDec は 1 range から 2 define を出すことがある)」は、2 range を落としたことで説明がつく可能性が高い。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`)・host / kernel 依存の静的な数え上げ・gate の識別力。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、GUI、Render test .flp、vendor ライブラリ (élastique)。 範囲外の項目について、本書は何も主張しない。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 harness が無く P0a/P0b/P0c 未完。 Eff_Render 無しの 19 本はイベント列単位の harness も要る | #205 を閉じられない | #195 / #196 / #197 の完了後に #205 を再開 (Closes はその時)。 harness は #506 で依頼済みの「[PLG-F3a] native ⟷ wasm 差分 harness」にイベント単位の版を含める (PM に起票依頼) |
| Render test .flp の E2E (出口条件 4) と GUI 5 本 | 同上 | FLEngine 統合・GUI shim #10 待ち。 親 #14 / #205 |
| **Dashboard の `__asm_rep_stosb_memset` 未実装 (gate 不合格 1 本)**。 engine 2 本にも stosb / stosw / movsb 等 | Dashboard が 28/28 の阻害要因。 link で未解決 | 新規子チケットを PM に起票依頼: 「[PLG-F8a] plugin lift 鎖の rep stos/movs (byte/word/dword) helper 実装」(`m11_simd2.py` 移植か `fw_rep.py` 経由。 §7 H1)。 28/28 後に `ctlvfx_e2e.sh` が exit 0 になる |
| `hs_ids.json` に無い Dispatcher ID 25 / 84 / 93 / 102 (Dashboard / VFX Envelope / Envelope Controller / VFX Script、計 7 site) | P0b の応答表が不足 | #196 にコメント (host 呼出か別オブジェクトの slot0 呼出かの判別も) |
| host slot 0x28 / 0x30 (Voice 系 10 本)・0x98 (9 本)・動的 ID 7 site の意味 | P0b の fail-soft 範囲を超える可能性 | #196 作業 5 (全 case 解析) に追記 |
| VFX Script の IAT 経由 Win32 呼出 79 site (どの API かは未集計) | Win32 shim の範囲 | #196 にコメント (API 内訳の集計は未実施) |
| Dashboard / Envelope Controller の kernel 表 init 未検出 (kernel 依存が未測定) | 2 本の P0c 依存が不明 | #195 (framework 別構成 3 本の確認) にコメント |
| kernel 0x5dee50 (Edison)・0x5e8a60 (LSD) が `p0c/REPORT.md` に記載無し。 0x5df040 (Edison) は #331 の residual diff 対象 | Edison / LSD の kernel 保証 | #197 にコメント、0x5df040 は #331 に追記 |
| T2 engine 2 本 (Tuner / VFX Sequencer) の `emcc -c` 未通過 (E1 → E2、VEX helper 未実装 78 / 29、`.pdata` 脱落 2 / 2) | T2 の 2 本 | #506 で依頼済みの「[PLG-F3b] C++ engine DLL の lift 鎖」に統合 (PM に起票依頼) |
| Tuner engine の f80 関数 1 | engine の wasm 化 | #197 (`f80_lower.py` の適用) にコメント |
| Edison の élastique (vendor) が閉包に入るか未確認。 `testdll_x64.dll` 未測定 | Edison の見積 | #205 の続報で確認。 ライセンス面は `docs/LEGAL.md` に従い PM 判断 |
| `env.sh` `mk_blockmap.py` `engine_*` が #506 の `dynamics/` と重複 | 保守二重化 | #506 マージ後に共通化 (PM 判断) |
| `nsis_names.py` が Actions 上で動かない (`block_manifest.json` 不在) | inventory の再現性 | `mk_blockmap.py` で回避済み。 `docs/WORKFLOW.md` §11 への追記は PM 判断 (#506 と共通) |
| `docs/DOC_MAP.md` の REPORT 索引に本書が未掲載 | 索引漏れ | PM が追記 |

## 7. DEFECTS.md 行案 (候補・loud な欠陥。 追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| H1 `rep stos/movs` の byte/word/dword 版 helper が宣言のみ | `declare void @__asm_rep_stosb_memset(ptr,i8,i64)` が final.ll に残り、`emcc -c` は通るが link で未解決 | Dashboard 1 件 (閉包内 `call` 1 site)、engine 2 本にも stosb / stosw / movsb (Tuner は stosd も) | `p.simd.log` の `unimplemented N` > 0 (`declares_unimpl`)。 **`emcc -c` rc=0 では見えない** | `m11_simd2.py` は `rep_stosq_memset` / `rep_movsq_memcpy` のみ実装 (`final.ll` の宣言は残る)。 framework 側の `fw_rep.py` + `fw_rt.c` (`fw_rep_stosb`) が同等を持つ。 plugin 鎖へ移植するか fw_rep を通す。 到達性の探針 (`probe_rep.sh`): Dashboard の final.ll に `fw_rep.py` を当てると `@__asm_rep_` の出現 8 → 0、`@fw_rep_` 0 → 8 (6 call site を正規化、declare 2 追加)、`emcc -c` rc 0。 意味の一致と link は未検証 |
| E1 / E2 (#506 §7 と同一類型) | engine で `icmp ptr` に i64 混在 / SSA 値入り `zext` 定数式 | Tuner / VFX Sequencer engine | emcc の型エラー (loud) | E1 は `engine_fixcmp.py`、E2 は未修復 |

## 8. 成果物

| ファイル | 内容 |
|---|---|
| `targets.py` | 対象 28 本 (name / 殻 block / Tier / engine block) の唯一の一覧 |
| `ctlvfx_e2e.sh` | 28 閉包 → batch_lift → gate (judge / closure_defs / matrix_check / ids_crosscheck) → closure_facts → engine 2 本 (参考)。 不合格で exit 1。 `--judge-only <csv>` で判定だけ |
| `judge.py` `closure_defs.py` `matrix_check.py` `ids_crosscheck.py` | gate 4 本 (不合格で exit 1) |
| `ctlvfx_nega.sh` `nega_mut.py` | 全 gate のネガティブコントロール / 実測データを 1 箇所だけ壊す補助 |
| `closure_facts.py` `report_tables.py` `probe_rep.sh` | 閉包 / host ID / kernel 依存 / engine 外形 → `work/ctlvfx/facts.json` (4 並列。 出力順固定) / REPORT §1〜§4 の表の生成 / Dashboard の未実装 helper への候補修復 (`fw_rep.py`) の到達性探針 |
| `engine_lift.sh` `engine_ranges.py` `engine_defs.py` `engine_fixcmp.py` | engine DLL の全 `.pdata` lift と局所修復 (#506 から複製) |
| `mk_blockmap.py` `env.sh` | `block_manifest.json` 不要の inventory 前提 / 環境 (#506 から複製) |
