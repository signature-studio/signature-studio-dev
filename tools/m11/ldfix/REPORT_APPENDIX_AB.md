# 付録: ldfix 常設化 A/B 検証 (CAB-131) — tools/m11/ldfix/

> **正本**: `tools/m11/ldfix/REPORT.md` (概要・§7)。本書はその付録で、CAB-131 常設化の
> A/B 詳細・halt0 対応表・CAB-233 引継ぎを扱う。検証手順は `docs/WORKFLOW.md` §6。

**判定: 達成 (stage 5 進捗測定込み)**。CAB-231 の ldfix (load 取り違え修復 pass) を `m11_gen_ir2.sh` に常設組み込みし、
残存していた load_dropped 変種 3 関数を **F1v pass (新設) で吸収して load_dropped 892→0 (liftdiff closure 全数実測)**。
常設化後の pipeline で全既存 e2e 回帰 (m11 boot stage4 / 942 unit survey / shimx_link 純リンク) は
**base↔fix で全数値完全同一** (非劣化) であることを機械検証した。通常起動の units_run は 17/942 のまま
(stage 5 未達) — 進捗は「残欠陥の確定」と「halt0 53 unit の対応表更新」として記録 (§4/§5)。

再現: `bash tools/m11/m11_e2e.sh --full` (ldfix 込みで再生成) + `bash tools/m11/ldfix/embed_e2e.sh --batch` (A/B 検収)。

## 1. 結論 (実測)

| 項目 | base (= 常設化前) | fix (= 常設化後) | 差 |
|---|--:|--:|--:|
| gen_ir2 生成 IR 中の ldfix 修復関数 | 0 | **955 + F1v 4 = 959** | +4 |
| liftdiff `load_dropped` タグ数 (closure 全数) | 892 | **0** (CAB-231 fix では残 2) | **-892** |
| mainline reached_stage / units / init_count | 4/6, 17/942, 18 | 同一 | ±0 |
| mainline survey ok / trap (kinds) | 812 / 83 (OOB 34・halt0 48・abort 1) | 同一 | ±0 |
| stage4 (ldfix/stage4.sh, post 後 IR) probe/units/init/GetMem/icall | 4 / 17・942 / 18 / 13 / 19 | 同一 | ±0 |
| shimx_link 純リンク run (units_run / init_count_var) | 17 / 18 | 17 / 18 | ±0 |
| shimx_link 純リンク survey (ok/oob/halt0) | 800 / 50 / 44 | 800 / 50 / 44 | ±0 |
| wasm サイズ (mainline build, alloca 足場) | 6,008,690 B | 6,010,853 B | +2,163 (F1v 分) |
| wasm-ld signature mismatch / undefined | 0 / 0 | 0 / 0 | ±0 |

- **F1v 4 関数の liftdiff verdict** (§3.2 同一足場実測): `10d35b0` / `106d220` / `108ec70` が **match 化**
  (106d220 は icall_drop も消滅)。`126c000` (追加 1 件) は icall_drop が支配し不反転。
- post (m11_post.py) レポートは base/fix 完全同一 (sigfix 6,675 / weak 7,421 / trampoline 7,399)。

## 2. 常設化 (組込手順) — 既存ファイル変更は 2 件

### 2.1 `tools/m11/m11_gen_ir2.sh` (変更 +13 行)

`PY2` (dotfix/fnclex0 rename) ブロック直後に追加: PE (`block00031_PE.bin`) と capstone/pefile があるとき
`python3 ldfix/ldfix.py work/boot_final.ll work/boot_final.ldfix.ll --pe "$PE" --report work/ldfix_report.json`
を実行し `mv` で in-place 化 (無ければ警告して skip)。詳細はコミットされたスクリプト本体を参照。

- 適用位置は **m11_passes 後・m11_post (weak 化/sigfix) 前** (CAB-231 REPORT §6-2 推奨)。実測: pre-post 適用でも
  修復関数数は post 後適用と同一 (F1=902 / F1v=4 / F2=30 / F3a=3 / F3b=5 / F3c=16, errors=0)。
- `--full` で gen_ir2 が 3 回走っても冪等 (2 回目以降 no-op, 11 秒/回)。失敗時は `set -euo pipefail` で落ちる
  (fail-loud)。capstone/pefile 欠如のときのみ skip+警告。

### 2.2 `tools/m11/ldfix/ldfix.py` (変更 +180 行 = F1v pass)

F1 の 3 連形 (`ptrtoint(C1)→trunc→store 直接`) から外れる**変種 3 形**を吸収する `fix_f1v()` を追加し
pass 鎖を `F1 → F1v → F2 → F3a → F3b → F3c` にした。いずれも機械語 (capstone) の rip 相対 RMW
`add/sub dword [g], imm` が正本で delta (= C1-C0) == ±imm 突合を必須条件にする:

| 変種 | IR 形 (RetDec 出力) | 対象 | 修復 |
|---|---|---|---|
| (a) direct | store は `[C0]` 直接だが**別 path に同一 target の生 store** があり従来 guard で除外 | `108ec70` | 生 store が RMW と異なる機械語ブロックなら許可して値を張替え |
| (b) select | `pt(C1)→trunc` が **select operand** に合流し select 結果が `[C0]` へ store | `106d220` (add+1/sub-1 の合流) | load→add を挿入し select operand を張替え |
| (c) slot | `pt(C1)→trunc` が **reg2mem slot** に退避され merge block の reload が `[c0]` へ store | `10d35b0` | slot への store 値を load+add に張替え (書込効果は既存 merge store が担う) |

共通 guard: (1) pt の使用は trunc のみ (2) trunc 値のアドレス用途なし (3) 書込効果の証人として
「`%tv` (直接/select結果/reload値) → `[C0]` store」が IR 中に実在 (4) RMW target・即値一致。
修復は**値の張替えのみ** (store 増減なし)。SSA 名は専用 counter (`ldfxv%d`) のため F1〜F3c 既存関数の
テキストは **1 行も変わらない** (ldfix_fixed.ll との diff = 4 関数のみを実測確認)。

### 2.3 変更しなかったもの

`m11_e2e.sh` / `m11_build.sh` / `m11_post.py` / `m11_passes.py` / shimx_link / tools/shimx / tools/icall / tools/liftlib は無変更
(ldfix REPORT §6-4 の「gen_ir2 に 1 ブロック」方式のため build 側は無変更でよい)。なお `ldfix/stage4.sh` には
生成 `m11_simd.c` の `#include "../msimd11_core.h"` が `ldfix/work/stage4/` 基準で解決される潜在依存があり
(CAB-231 実施時は work/ 内の一時 header が存在)、本 ticket では `embed_e2e.sh` 側で header を配置して回避
(既存ファイル無変更、§8-3)。

## 3. A/B 検証 (embed_e2e.sh / embed_sx_ab.sh, 全数実測)

### 3.1 liftdiff closure 全数 batch (7,421 関数 × 9 pattern, boot_state 共用, shards 12)

| 指標 | base (CAB-231 batch_base) | fix1 (CAB-231, post 後適用) | **fix2 (本 ticket, 常設化 IR)** |
|---|--:|--:|--:|
| match / mismatch / unexec | 2,275 / 2,885 / 2,261 | 3,157 / 2,004 / 2,260 | **3,134 / 1,995 / 2,292** |
| `load_dropped` | **892** | 2 | **0** |

fix2 は**常設化 pipeline が実際に生成する IR** (= m11_post 前) の採点。fix1 (post 後適用) とは足場差
(sigfix 済 call site の有無) があり match 数は直接比較しない (遷移: match→mismatch 93 / mismatch→match 69 /
unexec シフト ±39 = 足場差 + 実行ノイズ)。同一足場での F1v 分離を §3.2 で実施。

### 3.2 差分関数 60 件の足場一致 batch (F1v 分離)

fix3 source (`post(ldfix(boot_final.ll))`) と CAB-231 fix1 source (`ldfix(post(boot_final3.ll[alloca済]))`) の
テキスト差分は**ちょうど 60 関数** = F1v 4 + CAB-129 alloca 拡幅 56 (CAB-231 の入力 IR には alloca 適用済だったため)。
この 60 関数だけを同一足場で採点 (`--set file:work/diff60_vas.txt`):

| 関数 | fix1 | fix3 (常設化) | 判定 |
|---|---|---|---|
| `10d35b0` | mismatch + load_dropped | **match** (tag 無し) | F1v 効果 ✓ |
| `106d220` | mismatch + load_dropped + icall_drop | **match** (tag 無し) | F1v 効果 ✓ |
| `108ec70` | mismatch + wasm_trap | **match** (tag 無し) | F1v 効果 ✓ |
| `126c000` | mismatch + callee_divergence + icall_drop | 同一 | F1v 適用だが icall_drop 支配で不反転 |
| alloca 拡幅 56 関数 | — | 55 不変 / `43b7e0` match→mismatch | alloca 有無の既知差分 (alloca 足場では match)。本 ticket 変更と無関係 |

結論: **F1v による新規 mismatch は 0**、match 化 3 (= load_dropped 残存の全て)。残 7,361 関数はテキスト同一
(§3.1 fix2 で全数採点済)。

### 3.3 stage4 + survey + shimx_link 純リンク (alloca 適用足場 = CAB-129 検収と同じ)

`embed_sx_ab.sh` (alloca 適用 → m11_post → m11_build → run/survey/judge → shimx_link --soft):

| 項目 | base | fix |
|---|---|---|
| m11_judge reached_stage / units / init_count | 4/6, 17/942, 18 | 同一 |
| mainline survey ok/trap/kinds | 812 / 83 (OOB 34, halt0 48, abort 1) | 同一 |
| 停止理由 | `function_4133f0 ← 446400 ← 44bb70 ← 455790` OOB | 同一 |
| sx 純リンク run: units_run / init_count_var / dllmain_done | 17 / 18 / false | 同一 |
| sx 純リンク survey kinds | ok 800 / oob 50 / halt0 44 / closure外 46 / abort 1 / noproc 1 | 同一 |
| wasm / mismatch / undefined | 6,008,690 / 0 / 0 | 6,010,853 / 0 / 0 |

- m11_judge 出力の base/fix byte 比較は **wasm サイズ行のみ差分** (残り全行同一)。
- sx `--trace --soft --fix` 足場 (halt0 対応表の足場, §5) も base/fix 完全同一: ok 800 / oob 41 / halt0 53
  (942 unit の kind 差分 0)。この足場は CAB-129 受入時の per-unit kind を今日の harness でも完全再現 (drift 0)。
- 注意: sx 純リンク plain --soft survey の絶対値 (ok 800/oob 50) は CAB-129 受入時 (ok 807/oob 44) と異なるが
  **CAB-177 の build.sh 変更 (cbtrans wiring, `--wrap=m11_icall`) による harness 側変化**。base/fix 同一 harness
  状態での比較なので A/B 判定 (差分 0) には影響しない。

## 4. stage 5 進捗測定と残存ボトルネック優先順

常設化によって units_run は 17/942 で不変 (halt0 内訳も不変)。原因は実測で確定済:

1. **通常起動の停止点は unit #18 の `_UStrAsg` OOB (4133f0 ← 446400 ← 44bb70)**。F3a 修復済みだが残差は
   「src refcount path の別欠陥 (COW increment 経路)」(CAB-231 §4.2) — F1v はこの経路に触れない。
2. F1v 修復の 4 関数は unit 初期化の失敗時 Halt 経路の refcount 操作系で #18 停止より深く、
   通常起動の units_run / survey 内訳を動かさない (§3.3 実測)。

### 4.1 残存ボトルネック優先順 (タグ数 = 常設化 IR の全数 batch 実測, カッコ内は CAB-231 post 足場)

| 優先 | ボトルネック | 実測規模 | 根拠と手当て |
|---|---|---|---|
| 1 | `callsite_arg_drop` (sigfix 0 詰めの意味補完) | 257 (312) | 機械語データフロー実装が F3b/F3c 緩和と共通基盤 (CAB-231 §8-2)。survey OOB 34 の主力 (8cbcb0 系 x9 = 8cc190←8c7a10←8c5cc0 のポインタ不正) |
| 2 | `zero_init_drop` / `arg_drop` 複合 | 42 (52) / 46 (47) | F2 適用 8 関数が複合欠陥。単独 pass では verdict 不反転を実測済 → 複数 pass 同時適用の結合試験 |
| 3 | halt0 53 unit (失敗時に Halt(0)) | 53 (survey trap 95 中) | §5 対応表。LoadStringW=0 (リソース未接続) と TLS 系の切分け |
| 4 | survey unit #18 の FastMM 407a50 GetMem OOB | 1 (44bb70 前段) | CAB-129 §7-2 のまま。FastMM_GetMem 単体差分 |
| 5 | closure 外呼出 / proc 無し | 46 + 1 | m11_icall 表拡張 (0x41d0e0 系以外の seed) |
| 6 | `ucomisd/comisd` flag 未反映 | fcmp 0 件 | m6 [P1] pass 未移植。FPU 比較分岐の意味未保証 |

stage 6 (DllMain 正常終了) までの距離: unit #18 OOB 解消 (優先 1+2) → 942 unit 完走 (優先 3-5) → Halt0/longjmp。
**優先 1 の callsite_arg_drop 機械語突合が最短経路** (survey OOB 34 と halt0 一部を同時に削れる可能性)。

## 5. halt0 53 unit 対応表の更新 (CAB-129 REPORT §5 の継続)

`halt0_map.py` (新設) で survey per-unit JSON → `Runtime error 0 at 0x…` の全数抽出
(`python3 tools/m11/ldfix/halt0_map.py <survey.json> --out <map.json>`)。CAB-129 受入データの精緻化:

| 発生点 (Runtime error アドレス) | unit 数 | unit 一覧 |
|---|--:|---|
| 0x1027A4B0 | 17 | 88, 163, 185, 186, 246, 280, 312, 329, 369, 371, 616, 648, 771, 830, 874, 889, 906 |
| 0x112C0338 | 12 | 54, 55, 57, 59, 60, 61, 62, 63, 64, 139, 161, 308 |
| 0x112C02E8 / 0308 / 0318 | 5 / 3 / 2 | 366,877,881,899,936 / 86,510,662 / 520,653 |
| 0x112C02F8 / 0388 / 0398 | 各 1 | 41 / 504 / 605 |
| (MessageBox 無し) | 11 | 23, 87, 266, 292, 297, 305, 493, 494, 556, 585, 924 |

- アドレス解釈の訂正 (CAB-129 §5 補足): 発生点は**静的 VA ではなく wasm heap アドレス** (image は heap+0 敷設、
  0x1027A4B0 は image 22.5MB 超え = FastMM/VirtualAlloc 領域)。すなわち「発生点 = 関数 PC」ではなく
  **unit init 失敗時に読まれる (本来 return address が入るべき) メモリ位置の実体**。0x112C03xx は 0x10 刻みの
  構造体列、0x1027A4B0 は 17 unit が同一値 = 共通 helper 経路の示唆。
- **ldfix 常設化による変化 = 0** (A/B 実測): 942 unit の kind 差分 0、halt0 53 unit の unit 集合・アドレス差分 0
  (`sx_halt0_ab.sh` → work/sxhalt0_{base,fix}/)。今日の harness + base IR は CAB-129 受入時の per-unit kind を
  942 unit 全て完全再現 (drift 0)。
- harness 側の非依存変化 (CAB-177 由来, base/fix 同一): クラスタ**構造は完全保存** (×17/×12/×5/×3/×2/×1×3) で
  アドレスが FastMM レイアウトシフトで一様移動 (0x1027A4B0→0x1027AEA0, 0x112C03xx→0x112C0Cxx 系)。
  実測 JSON: `results/halt0_map_{cab129_base,sxfix_base_today,sxfix_fix}.json`。
- shim 相関 (53 unit 中): TlsGetValue 52 / MessageBoxA 42 / LoadStringW 22 (CAB-129 §5 と一致) —
  主因候補は LoadStringW=0 (リソース未接続) と TLS 系で不変。halt0 削除には shimx リソース接続 (CAB-177 系) と
  優先 1-2 の欠陥修復が別途必要。

## 6. CAB-233 (native 全起動 942 unit 完走) への引き継ぎ

1. **callsite_arg_drop の機械語突合修復** (優先 1): `ldmach.py` (capstone→IR block 対応) を流用し call site の
   引数レジスタ/stack slot を機械語側から再構成する pass を新設。F1v と同じ「IR 形 + 機械語証拠の両建て」規約を踏襲。
2. **複合欠陥の結合試験**: F2 適用 8 関数は arg_drop/zero_init_drop/icall_drop 併発 — 単独 pass では verdict
   不反転 (CAB-231 §3 実測)。複数 pass 同時適用 + verdict 反転数で評価する検収形式を推奨。
3. **halt0 53 unit**: §5 対応表を入力に (a) LoadStringW リソース接続 (shimx hostbridge, tools/shimx は CAB-177 管轄) と
   (b) 0x1027A4B0 クラスタ 17 unit の共通 helper 特定 (unit lva 一覧は results/halt0_map_*.json) を並行で。
4. **検収基盤**: `embed_e2e.sh --batch` と `halt0_map.py` をそのまま使用可。liftdiff の boot_state は target 毎に
   `tools/liftdiff/work/<target>/boot_state.json` への共用コピーが必要 (m11/m11_ldfix 間で byte 同一を実測済)。
   full batch は中断に弱い (--out truncate, resume 無し) ので差分関数だけ `--set file:` 部分採点が実用的 (§3.2)。

## 7. 成果物 (tools/m11/ldfix/ 追加分)

| パス | 役割 |
|---|---|
| `ldfix.py` (更新) | F1v pass 追加 (select/slot/direct 変種, 専用 counter, 冪等) |
| `../../m11_gen_ir2.sh` (更新) | ldfix 常設適用ブロック (§2.1) |
| `embed_e2e.sh` | 常設化 A/B 検収 (stage4 + survey、`--batch` で liftdiff 全数、マーカー付き中断再開可) |
| `embed_sx_ab.sh` / `sx_halt0_ab.sh` | alloca 足場の mainline+shimx 純リンク A/B / halt0 足場の survey A/B |
| `halt0_map.py` | survey JSON → halt0 発生点 × unit 対応表抽出 |
| `targets/m11_ldfix_embedded{,_post}.json` | liftdiff target (常設化 IR / post 後・F1v 分離用) |
| `results/halt0_map_*.json` | halt0 対応表実測 (CAB-129 受入時 / 今日 base / 今日 fix) |
| `work/` (gitignore) | ir_base_noldfix.ll / ir_fix_embedded.ll / batch_*.jsonl / stage4/*_emb/ / sxhalt0_*/ |

## 8. 未解決・次タスク提案

1. `126c000` は F1v 適用後も icall_drop 支配で不反転 — 深経路の別欠陥 (simd_helper / icall_drop 系)。
   CAB-231 §4.2 の「修復により差分顕在化」と同型、後続 ticket 課題。
2. fix2 全数 batch の unexec 2292 は fix1 より +32 — 足場差と shard 負荷の合成と推定 (CAB-231 §4.3 同様)。
3. stage4.sh の msimd11_core.h 潜在依存 (§2.3) は既存ファイル無変更で回避したが、次回 CAB で stage4.sh 側の
   1 行修正を推奨。
