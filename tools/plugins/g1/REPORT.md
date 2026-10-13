# tools/plugins/g1/REPORT.md — PLG-G1 (#206) synth-simple + drum-synth 14 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/g1/` のみ (生成物は `tools/plugins/work/` = gitignore) / 検証起点 commit: **86ca2d5** (スクリプト一式。 これ以降の commit は REPORT.md・`dropped_entries.py`・DOC_MAP の追加と、`g1_e2e.sh` の echo 文言 1 行 (§6 → §10) の修正のみ) / 再現: `bash tools/plugins/g1/g1_e2e.sh` (測定 + gate 5 本) / `bash tools/plugins/g1/g1_nega.sh` (ネガティブコントロール 9 件)。 環境は `g1/env.sh`
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 手法の出所: PR #506 (PLG-F3) と `tools/plugins/f2/` (PLG-F2)
- 既知類型との関係: **(icall §4) D1 = 間接 call/jmp 脱落**が 12 閉包すべてで再現 (§6; (DEFECTS.md) D15 は x64c stage-0 経路の同種事象で、本件は RetDec 経路)。 新規の loud な IR 型エラー 2 類型 (E4/E5) を §7 で報告 (行案は §11)。 silent miscompile の新規類型は**未検出** (差分試験を未実施のため、無いことの証明ではない)
- 範囲: issue #206 の手順 1 (固有閉包 lift → `emcc -c`) の再現と手順 2〜4 の前提監査。 **手順 2〜4 と出口条件 (差分試験 bit-exact + Render test .flp) は未達** (§10)

## 0. 結論 (先出し)

1. **#206 の出口条件は未達で、本 run では着手できない** → PR は `Refs #206` (Closes しない)。 PLG-P0a #195 / P0b #196 / P0c #197 が OPEN で、Gen_Render 単位で native (ms_abi) と wasm を比べる harness は未整備 (関数単位は [LD-6] #122 が OPEN)。
   Generator の発音試験に要る MIDI 入力 (#37) も OPEN (オーディオ経路 #11 は CLOSED)。
2. **手順 1 は Delphi 殻 12 block (13 本; Wasp と Wasp XT は同一 PE) で 12/12 通った**: lift_rc 0 / `emcc -c` rc 0 / `x86_fp80` 関数 0 / 未実装 `__asm_*` helper 宣言 0。
   閉包は block 重複なしで **497 関数 / 207,507 B** (§2)。 `PLUGIN_MATRIX.json` の `lift` 欄との突合は 148/148 項目一致 (T2 の殻 5 本 = BassDrum / Drumaxx / Drumpad / DrumSynth Live / SimSynth は matrix に `lift.batch` 欄が無く、lift と `emcc -c` は今回が初測定。 SimSynth は閉包の数値も matrix に無く比較対象外)。
3. **ただし `emcc -c` 通過は正しさを意味しない**: 12 閉包の機械語に非 IAT の間接 call が **計 659 site** あるが、lift 後 IR の間接 call は **0** (12/12 block、`Gen_Render` / `TriggerVoice` / `Voice_Render` / `Eff_Render` の入口を含む)。
   よって**現行の鎖の出力は、差分試験を実施しても必ず不一致になる**。 eq-filter (#199) の 550 site と同じ欠陥で、接続は [PLG-F2-2] #514 が追跡している (§6)。
4. **host 呼出面は P0b の応答表でほぼ覆える**: 閉包が即値 ID で発行する Dispatcher ID は taint 版で {2, 3, 8, 25, 36, 50, 90} と動的 ID 3 site (Dance)。 **ID 25 (Wasp / Wasp XT 各 1 site) は `hs_ids.json` (35 ID) に無い**。
   別算法の独立走査は ID 64 (4 本 × 各 4 site) と ID 128 (Dance 1 site) も検出し、この 2 つも応答表に無い (host 呼出か否かは未判別) (§4)。
5. **SIMD kernel 依存は 5 本**: 3x Osc / BeepMap / Fruit Kick / Fruity DX10 が閉包内に各 11 site、SimSynth が 1 site。 残り 7 殻は閉包にも frontier にも 0 site (§5)。
6. **付随 C++ DLL 7 本 (engine 6 + MiniSynth 単体) は RetDec まで通るが、`emcc -c` は 7/7 とも未通過** (§7)。 5 類型の IR 型エラーが連鎖し、2 本 (DrumSynth Live engine / SimSynth_Eng) は `.pdata` の 206 / 219 関数が define 無し。
   T2 の見積 (4 人日/本) には engine 側の未知工数が含まれていない。
7. **gate は不合格で非 0 終了し、各 gate にネガコンがある** (#506 の reviewer 指摘への対処、§3)。 実装中に gate が実際に落ちた事例が 3 件ある (§3 末尾)。

## 1. 対象と block 割当

`PLUGIN_MATRIX.json` の `win.modules` から確定 (`matrix_check.py` が block 割当を matrix と突合する)。 Tier / 推定人日は matrix の値 (合計 33 人日 = issue 本文)。

| plugin | Tier | 人日 | Delphi 殻 block | C++ DLL block (種別) | 備考 |
|---|---|--:|--:|--:|---|
| 3x Osc | T1 | 1.5 | 21148 | 21149 (engine; export は `dispatch`) | |
| BassDrum | T2 | 4 | 21182 | 21183 (engine) | |
| BeepMap | T1 | 1.5 | 21194 | — | |
| Drumaxx | T2 | 4 | 21297 | 21298 (engine) | |
| Drumpad | T2 | 4 | 22383 | 22384 (engine) | |
| Fruit Kick | T1 | 1.5 | 23634 | — | |
| Fruity DX10 | T1 | 1.5 | 23636 | — | |
| Fruity Dance | T1 | 1.5 | 23638 | — | `Gen_Render` は 1 B の `ret` (§8)。 描画系の plugin と推定 (未確認) |
| Fruity DrumSynth Live | T2 | 4 | 23644 | 23645 (engine) | |
| MiniSynth | T2 | 4 | — (殻なし) | 23921 (単体 DLL, MSVC C++) | 閉包 lift の対象外。 DLL 全体を §7 で測定 |
| Plucked! | T0 | 0.5 | 24157 | — | |
| SimSynth | T2 | 4 | 24170 | 24168 (`SimSynth_Eng`) | matrix は先頭 module = engine のため `lift` 欄なし |
| Wasp | T0 | 0.5 | 24302 | — | Wasp XT と同一 block (閉包 1 つで 2 本) |
| Wasp XT | T0 | 0.5 | 24302 | — | |

## 2. 手順 1: 固有閉包 lift (Delphi 殻 12 block)

定義: 閉包 = vtable override 実装 (Generator は `Gen_Render` / `TriggerVoice` / `Voice_*` を含む) から `call/jmp rel32` で到達する、framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。
frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。 vcall / ptr = 間接呼出 site 数、 iat = IAT 経由 Win32 呼出 site。 右端 4 列は `batch_lift.sh` の `status.csv` (`emcc -c` は `-O0 -msimd128`、0 = 通過)。

| plugin | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 3x Osc | 21148 | T1 | 76 / 22,485 | 69 / 9,580 | 33 | 47 | 5 | 76 | 0 | 0 | 0 |
| BassDrum | 21182 | T2 | 22 / 23,406 | 63 / 15,567 | 82 | 4 | 0 | 22 | 0 | 0 | 0 |
| BeepMap | 21194 | T1 | 79 / 23,052 | 77 / 9,587 | 54 | 51 | 5 | 81 | 0 | 0 | 0 |
| Drumaxx | 21297 | T2 | 45 / 34,112 | 65 / 17,002 | 31 | 3 | 0 | 45 | 0 | 0 | 0 |
| Drumpad | 22383 | T2 | 27 / 19,743 | 53 / 13,661 | 25 | 2 | 0 | 27 | 0 | 0 | 0 |
| Fruit Kick | 23634 | T1 | 69 / 18,658 | 63 / 7,940 | 25 | 47 | 2 | 69 | 0 | 0 | 0 |
| Fruity DX10 | 23636 | T1 | 70 / 21,843 | 62 / 7,312 | 27 | 46 | 2 | 70 | 0 | 0 | 0 |
| Fruity Dance | 23638 | T1 | 27 / 9,788 | 85 / 10,397 | 40 | 10 | 0 | 27 | 0 | 0 | 0 |
| Fruity DrumSynth Live | 23644 | T2 | 39 / 16,344 | 78 / 11,157 | 56 | 10 | 0 | 39 | 0 | 0 | 0 |
| Plucked! | 24157 | T0 | 17 / 5,926 | 40 / 9,586 | 16 | 4 | 0 | 17 | 0 | 0 | 0 |
| SimSynth | 24170 | T2 | 17 / 10,909 | 48 / 10,528 | 24 | 4 | 0 | 17 | 0 | 0 | 0 |
| Wasp / Wasp XT | 24302 | T0 | 9 / 1,241 | 12 / 1,756 | 5 | 3 | 1 | 9 | 0 | 0 | 0 |
| 計 (12 block) | | | **497 / 207,507** | | | | | 499 | 0 | 0 | 0 |

- 集計: 閉包 関数・B は 12 block の和 (Wasp / Wasp XT は 1 回だけ数える)。 define は `p.final.ll` の `^define` 行数。
- **BeepMap だけ define が閉包関数より 2 多い (79 → 81)**: RetDec が 1 range (0x730630–0x73069a, 107 B) の内部 2 箇所 (0x73067e / 0x730684) を別 define に切り出したため。 閉包関数の欠落は 0 (§3 gate 1b)。

## 3. gate 設計 (#506 の reviewer 指摘への対処)

#506 の指摘は 2 点: (a) 判定が不合格でも exit 0 / 最終 `OK` 行が無条件、(b) 判定自体のネガティブコントロール (NC) が無い。 本 run では最初から次の形にした。
`g1_e2e.sh` は `set -euo pipefail` で、**どの gate も非 0 を返せばその場で終了し、最終行 `[g1_e2e] OK` は全 gate 通過後にだけ出る**。

| gate | スクリプト | 不合格条件 (exit 1) | NC |
|---|---|---|---|
| 1 | `judge.py` (`status.csv`) | block ごとに: 行がちょうど 1 つ / 全列整数 / `closure_funcs>0` / `lift_rc==0` / `emcc_c_rc==0` / `f80_funcs==0` / `declares_unimpl==0` (-1 = 件数行なしも不合格) / `defines>=closure_funcs`。 要求外の block の行・ヘッダ不正・ファイル不在も不合格。 `--out` は全 block 合格時のみ書く | NC3, NC4 |
| 1b | `define_audit.py` | 閉包 range の開始 VA ごとに `function_<VA>` の define が `p.final.ll` に在ること (欠落 > 0 → 不合格)、range 外の define (unexpected) > 0 → 不合格。 range 内部の余剰 define は件数を報告して許容 | NC9 |
| 2 | `matrix_check.py` | `closure_funcs/bytes`・frontier 関数/B・vcall・ptr が matrix の `lift` 欄と不一致、matrix の `lift.batch` (lift_rc / emcc_c_rc / f80 / unimpl) が status と不一致、対象 plugin 集合・block 割当が matrix と不一致、facts が空 | NC5 |
| 3 | `ids_crosscheck.py` | taint 版の Dispatcher ID 件数 > 独立走査の件数 (取りこぼし)、facts の plugin 集合が `common.py` と不一致 | NC6 |
| 4 | `icall_check.py` | 独立算法の線形 sweep の数 ≠ `audit_icall.py` の到達 site + `gap_sites`、audit JSON 不在 | NC7 |
| (形式) | `engine_check.py` | C++ DLL 7 本の行が揃い全列整数で `lift_rc>=0`・`defines>=1`。 **`emcc -c` rc は合否に使わない** (§7 の通り全 7 本が既知の理由で非 0) | NC8 |

**gate にしないもの** (誤解防止): IR の間接 call 数 (§6)、`hs_ids.json` に無い Dispatcher ID (§4)、C++ DLL の `emcc -c` rc (§7)。 いずれも「現状の未解決」を測るもので、`findings.py` が e2e 末尾に件数を出す (常に exit 0)。
gate にすると e2e が常に落ちるため、起票先付きの未解決として §10 に置いた。

実装中に gate が実際に落とした事例:
1. 初版 `judge.py` は `defines==closure_funcs` を要求し、BeepMap (79 → 81) で FAIL した。 RetDec の range 内分割は正当な出力なので、`defines>=closure_funcs` + 名前での欠落検査 (gate 1b) に置換した。
2. 初版 `icall_check.py` は「`audit_icall.py` の静的 site = 独立 sweep」を要求し、5 block (3x Osc / BeepMap / Fruit Kick / DX10 / Dance) で sweep が +1 になり FAIL した。 原因は audit が到達不能と判定した gap の間接 call (各 `gap_sites=1`、 例: 3x Osc の 0x72b8b2 `call [rbx-0x20]`)。
   sweep = 到達 site + `gap_sites` が 12/12 block で成立するため、関係式として採用した (`f2/REPORT.md` §4 は 11 block で audit = sweep と記録)。
3. NC4 の初回実行で、不合格 CSV を渡した run が `work/g1/status12.csv` を上書きしていた (gate の成果物汚染)。 `judge.py --out` を全合格時のみ書く形に直し、NC4 に「成果物が不合格 run の前後で不変」の検査を足した。

## 4. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。 slot0 = Dispatcher。

| plugin | host call site 計 | slot0 の即値 ID (site 数) | 動的 ID | 他 slot (offset: site) |
|---|--:|---|--:|---|
| 3x Osc | 7 | 2 (3) / 36 (1) / 90 (1) | 0 | 0x28: 1, 0xf8: 1 |
| BassDrum | 2 | 2 (1) | 0 | 0x30: 1 |
| BeepMap | 13 | 2 (5) / 36 (1) / 90 (1) | 0 | 0x28: 2, 0x100: 2, 0x108: 2 |
| Drumaxx | 1 | 2 (1) | 0 | — |
| Drumpad | 1 | 2 (1) | 0 | — |
| Fruit Kick | 10 | 2 (4) / 36 (1) / 90 (1) | 0 | 0x28: 1, 0xc0: 1, 0x100: 1, 0x108: 1 |
| Fruity DX10 | 12 | 2 (4) / 36 (1) / 90 (1) | 0 | 0x28: 2, 0x100: 2, 0x108: 2 |
| Fruity Dance | 7 | 8 (1) / 3 (1) / 2 (1) | 3 | 0x28: 1 |
| Fruity DrumSynth Live | 14 | 3 (1) / 50 (1) / 2 (1) | 0 | 0x18: 1, 0x28: 2, 0x58: 2, 0x100: 1, 0x108: 1, 0x128: 4 |
| Plucked! | 10 | 2 (1) | 0 | 0x28: 2, 0x58: 1, 0x60: 1, 0xf8: 1, 0x100: 2, 0x108: 2 |
| SimSynth | 3 | 2 (1) | 0 | 0x128: 2 |
| Wasp / Wasp XT | 2 | 8 (1) / 25 (1) | 0 | — |

- taint 版の distinct ID = {2, 3, 8, 25, 36, 50, 90}。 `framework/hostshim/hs_ids.json` (35 ID) に無いのは **25 だけ** (Wasp / Wasp XT 各 1 site) → [PLG-P0b] #196 へ。
- **別算法の検算** (`ids_crosscheck.py`: taint を使わず閉包を線形逆アセンブルし、`mov r8d, imm` / `xor r8d, r8d` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う): 13/13 本で taint 版の ID 件数を取りこぼしなく再現した。
  差は 2 点: ID 64 が 3x Osc / BeepMap / Fruit Kick / DX10 に各 4 site、ID 128 が Dance に 1 site。 どちらも `hs_ids.json` に無い。 host 呼出か別オブジェクトの slot0 呼出かは未判別 (taint は host 経由と判定しなかった)。
- slot 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。 動的 ID と 0x128 の意味は未解析。

## 5. SIMD kernel 表への依存

`p0c/kernel_matrix.py` の `scan_dll` (kernel 変数経由・関数ポインタ slot 経由・直接 call の 3 経路) を再利用し、call site の所在関数を閉包 ranges / frontier で分類 (`closure_facts.py`)。

| plugin | 閉包内 site | 閉包内で呼ぶ callee (site 数) | frontier 内 site | DLL 固有関数走査の site / callee 種 |
|---|--:|---|--:|---|
| 3x Osc | 11 | 0x5de410 (1), 0x5df240 (4), 0x5dffc0 (1), 0x5dfff0 (1), 0x5f89c0 (1), 0x5f8b90 (1), 0x5f8dc0 (2) | 0 | 33 / 8 |
| BeepMap | 11 | 同上の 4 種 + 0x5f9480 (1), 0x5f9650 (1), 0x5f9880 (2) | 0 | 33 / 8 |
| Fruit Kick | 11 | 同上の 4 種 + 0x5f8a00 (1), 0x5f8bd0 (1), 0x5f8e00 (2) | 0 | 33 / 8 |
| Fruity DX10 | 11 | 同上の 4 種 + 0x5f9520 (1), 0x5f96f0 (1), 0x5f9920 (2) | 0 | 33 / 8 |
| SimSynth | 1 | 0x5dee50 (1) | 0 | 23 / 2 |
| 他 7 殻 (BassDrum / Drumaxx / Drumpad / Dance / DrumSynth Live / Plucked! / Wasp 系) | 0 | — | 0 | 22 / 1 |

- 0x5de410 / 0x5df240 / 0x5dffc0 / 0x5dfff0 / 0x5dee50 は P0c の kernel 表 (`work/kernel_table.json`) にある。 0x5df240 は `p0c/REPORT.md` が f32 出力 bit-exact とする kernel。 本 PR で kernel の正しさは再測定していない。
- **0x5f89c0 ほか DLL 固有 VA の callee は kernel 表に無い** (正規化できなかった VA)。 該当は 4 plugin (3x Osc / BeepMap / Fruit Kick / DX10) で、各 3 callee・4 site。 正体は未調査。
- 最右列の 22 site (1 種) は 7 殻に共通し、閉包にも frontier にも属さない framework 側の関数と推定 (#506 §3 と同じ値; 未確認)。

## 6. 間接 call 監査 (`tools/icall/audit_icall.py --funcs <閉包関数 VA> --ir work/batch/<block>/p.final.ll`)

定義: 「静的 site」= 閉包関数範囲を capstone で recursive descent した非 IAT の `call` 間接命令数 (`call [reg+disp]`・`call [rip+var]` ほか)、「gap」= audit が到達不能と判定したが decode できた間接 call/jmp、「線形 sweep」= 独立算法 (`icall_check.py`、閉包 ranges を線形逆アセンブルして即値でない call のうち IAT 呼出を除く) の件数、「IR」= `p.final.ll` で callee が `@name` でない call の数。

| block | plugin | 静的 site | gap | 間接 call を持つ関数 | IR の間接 call | 入口の静的→IR |
|--:|---|--:|--:|--:|--:|---|
| 21148 | 3x Osc | 84 | 1 | 21 | 0 | Gen_Render 1→0 |
| 21182 | BassDrum | 86 | 0 | 15 | 0 | Gen_Render 1→0, TriggerVoice 2→0 |
| 21194 | BeepMap | 109 | 1 | 26 | 0 | Gen_Render 1→0, Voice_Render 3→0 |
| 21297 | Drumaxx | 34 | 0 | 21 | 0 | Gen_Render 1→0, TriggerVoice 1→0 |
| 22383 | Drumpad | 27 | 0 | 14 | 0 | Gen_Render 1→0, TriggerVoice 1→0 |
| 23634 | Fruit Kick | 73 | 1 | 21 | 0 | Gen_Render 1→0, Voice_Render 1→0 |
| 23636 | Fruity DX10 | 74 | 1 | 20 | 0 | Gen_Render 1→0 |
| 23638 | Fruity Dance | 49 | 1 | 15 | 0 | TriggerVoice 5→0 |
| 23644 | Fruity DrumSynth Live | 66 | 0 | 23 | 0 | Gen_Render 9→0, TriggerVoice 2→0 |
| 24157 | Plucked! | 20 | 0 | 7 | 0 | — (Gen_Render / Voice_Render は静的にも間接 call 無し) |
| 24170 | SimSynth | 28 | 0 | 13 | 0 | Gen_Render 5→0, TriggerVoice 1→0 |
| 24302 | Wasp / Wasp XT | 9 | 0 | 4 | 0 | Eff_Render 1→0 |
| 計 | | **659** | 5 | | **0** | 入口を持つ 11 block で ≥1 → 0 |

- 線形 sweep は 12/12 block で「静的 site + gap」と一致 (計 664 = 659 + 5)。 全スロットの内訳は `work/g1/icall_table.md`。
- eq-filter (#199) と同じ欠陥で、`batch_lift.sh` の鎖に `tools/icall` の復元が無いことが原因 → **[PLG-F2-2] #514** (batch_lift への icall 接続と回帰ゲート化) の対象に本 12 block を含める。
- 間接 call を持たない入口 (Plucked! の `Gen_Render` / `Voice_Render`) は関数単位の差分試験候補 (浮動小数引数には ARG pass が要る: #197)。 [PLG-F2-3] #515 の方式の一般化を検討。

## 7. 付随 C++ DLL 7 本 (engine 6 + MiniSynth 単体)

外形 (`closure_facts.py` → `work/g1/cpp_facts.json`): 6 本は export が `CreatePlugInstance` 1 つ (3x Osc の engine のみ `dispatch`)、import は KERNEL32 (+ USER32 / GDI32 など)。 殻との結合方式 (LoadLibrary 経路) は未解析。

`engine_lift.sh <block>` で全 `.pdata` 関数を `lift_ranges.sh` (RetDec+pass 鎖) → `emcc -c` に通した結果:

| DLL | block | `.pdata` 関数 | RetDec rc | final.ll define | `.pdata` で define 無し (B) | f80 関数 | 未実装 helper | `emcc -c` | 局所修復後 | lift 秒 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 3x Osc engine | 21149 | 425 | 0 | 442 | 2 (525) | 0 | 60 | 1 | 1 | 9 |
| BassDrum engine | 21183 | 1,578 | 0 | 1,656 | 1 (61) | 0 | 92 | 1 | 1 | 38 |
| Drumaxx engine | 21298 | 1,660 | 0 | 1,739 | 1 (61) | 0 | 103 | 1 | 1 | 45 |
| Drumpad engine | 22384 | 1,403 | 0 | 1,456 | 1 (61) | 1 | 89 | 1 | 1 | 33 |
| DrumSynth Live engine | 23645 | 1,571 | 0 | 1,389 | **206 (19,093)** | 0 | 8 | 1 | 1 | 39 |
| MiniSynth (単体) | 23921 | 1,481 | 0 | 1,530 | 1 (61) | 0 | 98 | 1 | 1 | 36 |
| SimSynth_Eng | 24168 | 1,686 | 0 | 1,510 | **219 (27,581)** | 1 | 17 | 1 | 1 | 46 |

- `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`engine_defs.py`、分母は `.pdata` 関数数、括弧は欠けた range の合計長)。 DrumSynth Live / SimSynth_Eng は 66 / 70 件が call 先として `declare` だけ残り、link 時に未解決になる。 原因 (RetDec の関数境界統合 / 復号失敗) は未調査。
- 「局所修復」= `engine_fixcmp.py` (icmp ptr/i64 混在の operand に `inttoptr` を挿入; 共有鎖には未組込)。 `emcc` が最初に出すエラー (clang は最初の型エラーで止まるため 1 件ずつ露見):

| 類型 | 症状 (`emcc` のエラー) | 該当 DLL | 備考 |
|---|---|---|---|
| E1 | `'%argN' defined with type 'i64' but expected 'ptr'` (`icmp eq ptr %x, %argN`) | 6 本 (SimSynth_Eng を除く) | `engine_fixcmp.py` で解消 (#506 §7 の E1 と同一) |
| E2 | `zext constexprs are no longer supported` (SSA 値入りの定数式) | 3x Osc / Drumpad / MiniSynth | 未修復 (#506 §7 の E2 と同一) |
| E3 | `'%arg2' defined with type 'i32' but expected 'i64'` | DrumSynth Live engine | 未修復 (#506 §7 の E3 と同一) |
| E4 | `expected type` (`%x = zext 0 to i64`: 定数式展開が型を落とす) | BassDrum / Drumaxx engine | 新規。 未修復 |
| E5 | `select constexprs are no longer supported` (`add i64 0, select (...)`) | SimSynth_Eng (修復前から) | 新規。 未修復 |

- f80 関数は Drumpad engine と SimSynth_Eng に各 1 → #197 の `f80_lower.py` の適用対象。 未実装 helper 数は `simd.log` の「unimplemented N」(distinct 宣言数)。
- 以上は到達性の実測で、正しさは何も示していない。 DLL ごとの最初のエラーは `work/g1/engine<block>/first_errors.txt`。

## 8. Generator 入口の網羅 (`dropped_entries.py`)

`plugin_closure.py` は vtable override のうち実装関数の正規化ハッシュが 13 DLL 以上で共通のものを「framework 既定実装」として入口から外す。 この判定で DSP が閉包の外に隠れていないかを、外れたスロットの実装サイズと機械語で確認した
(`python3 tools/plugins/g1/dropped_entries.py`、 12 殻で 41 スロット)。

機械語の内訳: `c3` (`ret` のみ、1 B) 24 件 (`Idle_Public` / `Gen_Render` (Dance, Wasp) / `Voice_Kill` / `Voice_Release` / `GetName` (Wasp) ほか) / `33 c0 c3` (`xor eax,eax; ret`、3 B) 9 件 (`Voice_ProcessEvent` ほか) /
`ProcessEvent` の同一形 (`xor eax,eax; sub edx,1; test edx,edx; jne; mov [rcx+0xe0],r8d; ret` 相当、17 B) 3 件 / 薄い thunk (`call rel32` を含む。 `DestroyObject` 3 本 30 B、`NewTick` 21 B、`ProcessEvent` 14 B) 5 件。

- Generator の描画系入口のうち外れたものはすべて 1–3 B の stub: `Gen_Render` と `Voice_Kill` / `Voice_Release` は Dance と Wasp 系、`Voice_ProcessEvent` は 7 殻。 `TriggerVoice` / `Voice_Render` / `Eff_Render` は外れておらず閉包に載る。
- **残る盲点**: 薄い thunk 5 本は `call rel32` を持つが、thunk 自体が framework 判定で入口から外れるため、その call 先は BFS の起点にならない。 destroy / NewTick / ProcessEvent 系で DSP ではないと推定 (call 先の所在は未確認)。

## 9. 検証

コミット済み HEAD **86ca2d5** を `git worktree add --detach` した別 worktree (`work/` 空) で実行。 4 core / 15 GiB の Actions runner、実行は逐次 (並列数 1)、各 run の間に他の重い処理は走らせていない。
前提 inventory (`prep.sh`) は clean worktree へ dev worktree の生成物 (`win_scan` / `winfuncs` / `win_unique` / `win_abi` / `kernel_table` の JSON) をコピーして使い、再生成していない。

| 項目 | 実測 |
|---|---|
| 前提 inventory の生成 (dev worktree で 1 回、`prep.sh`) | **377 s** (`win_funcs.py` が主。 `Pool(14)` を 4 core で実行、終了時 load average (1 分) 16.3)。 `g1_e2e.sh` は work/ が在れば作り直さない |
| `g1_e2e.sh` 全体 (C++ DLL 7 本を含む。 3 run: dev / clean / clean 2 回目) | **440 / 442 / 448 s** (dev / clean 1 回目 / clean 2 回目)、いずれも exit 0 |
| 開始時 load average (1 分) | 0.62 / 0.51 / 0.90 (同順) |
| lift 秒 (`status.csv` の seconds 12 block 計。 同上 3 run の min–max) | **33–39 s** (39 / 33 / 36) |
| C++ DLL 7 本の lift 秒 (`engines.csv` の `lift_s`、3 run の min–max、block 順は §7) | 9 / 38–39 / 45–46 / 33–34 / 39–40 / 36 / 46–52 |
| run 間の一致 | dev と clean 2 回で `facts.json` はバイト一致 (sha256 先頭 `6152896e`)。 `status12.csv` (seconds 列を除く)・`icall_table.md`・`define_table.md`・`cpp_facts.json`・`engines.csv` (lift_s 列を除く) も一致 |
| gate 通過 | clean HEAD で gate 1 (12/12 block) / 1b (不合格 0) / 2 (148/148) / 3 (13/13) / 4 (sweep ≠ 到達 + gap の block 0) / C++ DLL 形式検査 (7/7) すべて合格、exit 0 |
| `g1_nega.sh` (clean HEAD 86ca2d5) | exit 0、**38 s**、NC1〜NC9 すべて DETECTED (dev worktree の同内容の run も全 DETECTED) |

ネガティブコントロール (数値; 対照は無改変で合格することを併記):
- NC1 `emcc -c` (Wasp 24302): `final.ll` の定義 1 つの `ret` を除去 → rc **0 → 1**。
- NC2 ranges: 閉包 ranges 8 → 7 (末尾 `function_6a55f0` を落として再 lift) → define 9 → 7、 対象関数 1 → 0。
- NC3 `judge.py`: 実測 `status12.csv` (12 行、対照 rc 0) を 1 箇所ずつ壊した **137 変異** (block ごとに lift_rc=1 / f80=3 / emcc_c_rc=1 / unimpl=5 と -1 / defines=closure-1 / closure=defines+1 / closure=0 / seconds 非数値 / 行削除 / 行重複の 10 種 × 12、要求外 block 追加 1、ファイル全体 4 = ヘッダのみ・空・ヘッダ不正・不在) → **受理 0 / 拒否 137**。
- NC4 e2e の終了コード: 先頭 block の `emcc_c_rc` を 1 にした CSV を `G1_STATUS_CSV` で渡して `g1_e2e.sh --skip-lift --judge-only` → **rc 1、通過行 0** (対照 rc 0、通過行 1)。 `work/g1/status12.csv` は不合格 run の前後で sha256 不変。
- NC5 `matrix_check.py` / NC6 `ids_crosscheck.py`: 対照 rc 0。 BassDrum の `closure_funcs`+1・Fruit Kick を欠く・空 facts → rc 1 (3 件とも)。 3x Osc の ID 2 の件数 3 → 4・空 facts → rc 1。
- NC7 `icall_check.py` / NC8 `engine_check.py`: 対照 rc 0。 3x Osc の audit 静的 site +1・audit JSON 1 本欠く → rc 1。 engines.csv の末尾行を欠く・`lift_rc` を非整数 → rc 1。
- NC9 `define_audit.py`: 対照 rc 0 / `function_408930` を `function_ffffff` に改名 → rc 1 / `final.ll` 無し → rc 1。

別系統の突合は gate 2 (matrix 148 項目) / 3 (ID の独立走査) / 4 (間接 call の線形 sweep)。 規約確認 (HEAD): `git diff bfccd23 HEAD --stat` の変更は `tools/plugins/g1/` と `docs/DOC_MAP.md` のみ。 20 MiB 超の blob なし (`find tools/plugins/g1 -size +20M` 空)。 REPORT は 250 行以内。
検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`) と host / kernel / 間接 call の静的な数え上げ。 範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp。 範囲外の項目について本書は何も主張しない。

## 10. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 Gen_Render / Eff_Render 単位の native (ms_abi VA 敷設) ⟷ wasm harness が未整備 ([LD-6] #122 は関数単位)、P0a/P0b 未完 | #206 を閉じられない | #195 / #196 の完了後に #206 を再開 (Closes はその時)。 harness は #506 §6 が PM に依頼済みの「[PLG-F3a]」を family 共通として流用できるか PM 判断 |
| Render test .flp の E2E (出口条件 4)、発音試験に要る MIDI 入力 | 同上 | FLEngine 統合待ち。 MIDI 入力は #37 (OPEN)。 親 #14 / #206 |
| 間接 call 659 site の脱落 (12/12 block)。 `batch_lift.sh` に icall 復元が未接続 | 全 13 本。 接続しない限り差分試験は必ず不一致 | **#514** ([PLG-F2-2]) に本 12 block を追記済み (コメント) |
| 間接 call を持たない入口 (Plucked! の Gen_Render / Voice_Render) の関数単位差分 | 部分的な bit-exact 実績 | **#515** ([PLG-F2-3]) の方式の一般化を PM 判断 |
| Dispatcher ID 25 (Wasp / Wasp XT) が応答表に無い。 ID 64 (4 本 × 4 site)・128 (Dance) は host 呼出か未判別。 動的 ID (Dance 3 site)・slot 0x128 / 0x58 / 0x18 の意味も未解析 | P0b の応答表 / host 呼出面の網羅 | #196 に追記済み (0x13173a0 全 case 解析と合わせる) |
| DLL 固有 VA の callee (4 plugin × 3 callee × 計 4 site, §5) と共通 22 site の正体 | kernel 依存の網羅 | #197 / #195 の統合時に所在関数を特定 |
| C++ DLL 7 本の `emcc -c` 未通過 (E1〜E5、未実装 helper 8〜103 種、`.pdata` 206 / 219 件 define 無し) | T2 の 6 本 (BassDrum / Drumaxx / Drumpad / DrumSynth Live / SimSynth / MiniSynth) と 3x Osc の engine | **新規子チケットを PM に起票依頼**: 「[PLG-G1b] C++ DLL の lift 鎖: IR 型整合 pass (E1〜E5) + define 脱落の原因調査」。 #506 の「[PLG-F3b]」と範囲が重なるため統合を PM 判断 |
| Drumpad engine / SimSynth_Eng の f80 各 1 関数 | engine の wasm 化 | #197 に追記済み (`f80_lower.py` の適用) |
| MiniSynth は殻のない単体 DLL で閉包ベースの手順 1 が適用できない。 薄い thunk 5 本の call 先が閉包の起点にならない (§8) | 1 本 (T2, 4 人日) / 閉包の完全性 (DSP でないと推定) | #206 に残す。 lift 方式 (DLL 全体 / vtable 起点) は PM 判断。 thunk の call 先確認は次の run |
| SimSynth は matrix に `lift` 欄が無い (先頭 module が engine) | matrix の欠落 | `tools/plugins/REPORT.md` / `PLUGIN_MATRIX.json` の生成元 (`tier.py`) の修正は PM 判断。 本 PR は `matrix_check.py` に `NOT_IN_MATRIX` として明示 |
| `win_funcs.py` が 4 core で長い (§9)、Actions の 60 分枠を圧迫 | 再実行コスト | `work-plugins-*` 素材化は #293 (allowlist 追加) で PM 判断 (#199 §5 と同件) |

## 11. DEFECTS.md 行案 (候補・loud な IR 型エラー。 追加の可否は PM 判断)

- **E4 `zext` の型落ち**: 症状 `%x = zext 0 to i64` (元の型が無い) / 観測 BassDrum・Drumaxx engine / 検出信号 emcc "expected type" / 修復 未。
- **E5 select 定数式**: 症状 `add i64 0, select (i1 ..., ...)` / 観測 SimSynth_Eng / 検出信号 emcc "select constexprs are no longer supported" / 修復 未。 (E1〜E3 は #506 §7 と同一。 間接 call 脱落は既存 (icall §4) D1 / D15 の再確認。)

## 12. 成果物

`g1_e2e.sh` (prep → 閉包 lift → gate 1/1b/2/3/4 → C++ DLL 7 本 → 未解決の件数; `--skip-lift` / `--skip-engines` / `--judge-only`) / `g1_nega.sh` + `judge_nc.py` (NC 9 件) /
gate 本体 `judge.py` `define_audit.py` `matrix_check.py` `ids_crosscheck.py` `icall_check.py` `engine_check.py` (単独実行可; `g1/env.sh` を source) /
測定 `closure_facts.py` `findings.py` `dropped_entries.py`、 対象の正本 `common.py` / 前提 `prep.sh` `mk_blockmap.py` (`block_manifest.json` 不要) `env.sh` / C++ DLL `engine_lift.sh` `engine_ranges.py` `engine_defs.py` `engine_fixcmp.py` (#506 から移植)。
