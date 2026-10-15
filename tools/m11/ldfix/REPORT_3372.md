# REPORT_3372 — 同類型 (スピル引数の 1 段 deref 脱落) の site 修復 3 箇所と ldfix_e2e の実測 (#3372 / CI-151)

既知類型との関係: **DEFECTS.md D4** (引数 reg 経由の disp=0 deref 脱落)。#2555 (REPORT_2555.md) の表の同類型。新規類型ではない。

## 0. 結論

- REPORT_2555 §2 の誤り 13 箇所のうち **3 箇所を site 単位で直した**: function_44f040 (表 #5)・function_47cf10 (表 #14)・function_6074b0 (表 #15)。
  書き換えは `fix_site_3372.py` (新規)。機械語 8 + 8 + 4 = **20 命令を capstone で照合**し、一致しなければ止める。IR は書き換える行が 1 件ずつ在るときだけ書く。
- `ldfix_e2e.sh` に step 1c (本 pass) を配線し、**最終コード (測定 commit `dd8894202`) で完走**した (rc=0)。
  stage4 は base / fix とも同じ到達段 (4/6)・同じ trap (`memory access out of bounds`)。survey は 22 項目が base と一致
  (差分は trap の IR 行番号のキーだけ。§5)。**観測上の変化は無し**。wasm サイズは +199 B。
- 一次分類 (`verify_deref_sites_2555.py`・17 行): base は OTHER 9 / ADDR 5 / MISMATCH 2 / SCAN_MISS 1、修復後は **LOAD 3** を加え OTHER 7 / ADDR 4 / MISMATCH 2 / SCAN_MISS 1。
- **未修復 (子 issue へ)**: 0x413340・0x44fb40・0x450420・0x4506e0・0x7888f0 (#3326 の成果が main に無い分。§1)、0x47b4a0・0xc40770 (複雑型。§6)。

## 1. 前提の確認 (#3326 の成果が main に無い)

- 本 issue の本文は「#3326 で 0x413340・0x44fb40・0x450420・0x4506e0・0x7888f0 の 5 箇所が `tools/m11/ldfix/fix_site_3326.py` で直った」と書く。
- 確認: `origin/main` (a5966bbc7) に `fix_site_3326.py` は無い (`git ls-tree -r --name-only origin/main | grep 3326` → 0 件)。
  `git log --all --grep=3326` / `--grep=CI-148` → 0 件。#3326 の PR は見つからず、issue #3326 は OPEN。
- よって、この 5 箇所は main の HEAD で**未修復**として扱う。子 issue で引き取る (受入 4 の 0x413340 の判定も同じ子に移す)。
- 表に無い **0x6074b0 (表 #15)** は #3372 の本文の一覧に入っていなかったので、本 PR に含めた (§2.3)。

## 2. 修復の内容 (`fix_site_3372.py`)

3 サイトとも、機械語の窓 (capstone) と IR 行の対応を見て書いた。「base」は `tools/m11/work/boot_final3.ll` (ldfix 前)。

### 2.1 function_44f040 (表 #5) — 引数 arg1 の `*arg1` 読出し脱落

機械語 (PE VA 0x44f040): `mov [rsp+0x60],rcx` (arg1) の後、`*arg1` を 3 箇所で使う。

| 箇所 (機械語 VA) | 機械語 | base IR | 修復 |
|---|---|---|---|
| 0x44f069・0x44f071 (nil 判定・長さ) | `rcx=[arg1]; test rcx; eax=dword[rcx-4]` | `icmp eq arg1,0` / `arg1-4` を load (base 形) | base は `%a1d = load [arg1]` で 1 段読み。ldfix 済みの形 (`%ldfxu14`) なら据え置き |
| 0x44f090・0x44f095 (44aeb0 第 1 引数) | `rcx=[rax] (=*arg1)` → call | `call 44aeb0(zext dword[arg2-4], esi)` | 第 1 引数を `*arg1` の値に置換 |
| 0x44f0cb〜0x44f0f6 (44ec40 第 3 引数 r8) | `r8=[[rsp+0x60]] (=*arg1)` → call | `call 44ec40(arg2, 0, zext dword[arg2-4], …)` | 第 3 引数を `%a1e` (44aeb0 の後で改めて読んだ `*arg1`) に置換 |

- (c) は `%a1e` を 44aeb0 の後で読む。44aeb0 が `*arg1` を書換えうるため、先の値 `%a1d` を流用しない。
- `ldfix.py` (F1 系) の出力では (a) が既に `%ldfxu14` で直っている (e2e の step 1 で確認)。`fix_site_3372.py` は両形を判定する。

### 2.2 function_47cf10 (表 #14) — `*arg1 + rbx*8` と `+8` の二重計上

機械語: `[rsp+0x40]=rcx` (0x47cf1c, entry で 1 回だけ書く) → `rcx=[[rsp+0x40]]` (=*arg1) → `rcx=*arg1 + rbx*8` (0x47cf89)、`rdx=*arg1 + rbx*8 + 8` (0x47cf95)、`call 409c80`。

- base IR (block `dec_label_pc_47cf81`): `%20 = %.pre6 + %arg1` (arg1 をアドレスとして使用)、`%22 = %21 + %20` (`%21 = %.pre6+8`)。
  `%22` は `16*arg2 + arg1 + 8` になり、rbx*8 が二重に計上されている。
- 修復: `%a1f = load i64 [arg1]` を同じ block の `%20` の前に入れ、`%20 = %.pre6 + %a1f`、`%22 = %21 + %a1f`。

### 2.3 function_6074b0 (表 #15) — 1 段読み脱落

機械語: `[rsp+0x40]=rcx` (0x6074b6) → `rax=[rsp+0x40]` → `rcx=[rax]` (=*arg1) → `call 4256c0`。
base IR: `%0 = call 4256c0(i64 %arg1)`。修復: `%a1g = load [arg1]` を入れて `call 4256c0(%a1g)`。
`ldfix.py` (F1 系) の出力では既に `%ldfxu24` で直っているので、その形なら据え置く (`fix_site_3372.py` が判定)。

## 3. 機械照合とネガティブコントロール

- 機械照合: 各サイトの命令 (VA・mnemonic・operand) を capstone の出力と完全一致で照合する (計 20 件: 44f040 8 件・47cf10 8 件・6074b0 4 件)。
  ISA の表記は `ldmach.Machine.disasm_fn` の出力に合わせた (例: `mov rcx, qword ptr [rsp + 0x60]`)。
- 実行 (base 入力 `boot_final3.ll`):

| 制御 | 操作 | 結果 (終了コード・例外) |
|---|---|---|
| 正 | 通常適用 | rc=0。`machine checks 20 ok (3 sites), IR edits 7 applied` |
| NC1 二重適用 | 修復後の IR を `--negctl double` で 2 回適用 | rc=1 `AssertionError: nil/len rows: neither base form nor ldfix form (1 each)` |
| NC2 機械照合の改変 | 0x44f090 の期待 operand の `[rax]` を `[rbx]` に変える (`--negctl mach`) | rc=1 `machine mismatch at 0x44f090: want ('mov', 'rcx, qword ptr [rbx]') got ('mov', 'rcx, qword ptr [rax]')` |
| NC3 IR base 形の改変 | `%19` の第 1 引数を `%14`→`%13` に変える (`--negctl ir`) | rc=1 `function_44f040 base row count 0 (want 1)` |
| 再適用の拒否 | 修復済み IR (`site_3372_fixed.ll`) を入力に再実行 | rc=1 (`nil/len rows` で停止) |

- 陽性対照として、一次分類で LOAD に変わったことを §4 で確認した (修復の効果の機械的な確認)。

## 4. 一次分類 (`verify_deref_sites_2555.py`)

同じ実行環境 (PE `block00031_PE.bin`・`--extra 0x7888f0`) で base と修復後を比べた。

| 入力 | 候補 | OTHER | ADDR | MISMATCH | LOAD | SCAN_MISS |
|---|---|---|---|---|---|---|
| base (`boot_final3.ll`) | 17 | 9 | 5 | 2 | 0 | 1 |
| 修復後 (`site_3372_fixed.ll`) | 17 | 7 | 4 | 2 | **3** | 1 |

- LOAD に変わったのは 0x44f040 の 0x44f095 (`%a1d`)・0x47cf10 の 0x47cfa4・0x6074b0 の 0x6074c3 の 3 件。
  (`verify_3372_final.json` の `verdict` と `ir_arg` を確認)。
- 一次分類は「機械的な振り分け」であり最終判定ではない (REPORT_2555 §5)。最終判定は、本 REPORT の §2 の窓読みによる。

## 5. ldfix_e2e の実測 (step 1c を配線した最終コード)

- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` (step 1c は本 PR で追加)。
- 測定 commit: **`dd8894202`** (コードを変えた最後の commit。`fix_site_3372.py` と `ldfix_e2e.sh` を含む)。
- 実測 (測定 commit `dd8894202` の HEAD で 1 回。`date -u +%s.%N` で計時): wall **47.5 s**・rc=0。実行前の load average `0.35 0.50 0.41` (1/5/15 分)、実行後 `0.72 0.58 0.44` (4 vCPU)。

| 項目 | base (修復前) | fix (修復後) | 判定 |
|---|---|---|---|
| stage4 到達 | 4/6 | 4/6 | 同じ |
| stage4 の threw | `memory access out of bounds` | `memory access out of bounds` | 同じ |
| wasm_size (B) | 6025281 | 6025480 | +199 |
| probe GetMem / FreeMem / FastMM_GetMem | 16 / 6 / 17 | 16 / 6 / 17 | 同じ |
| units_run / units_total / init_count / icall_ok | 17 / 942 / 18 / 24 | 17 / 942 / 18 / 24 | 同じ |
| survey ok / noproc / miss / trap | 136 / 0 / 14 / 9 | 136 / 0 / 14 / 9 | 同じ |
| survey trap_kinds | oob 8・halt0 1 | oob 8・halt0 1 | 同じ |
| judge (`judge_e2e.py`) | `STAGE4_JUDGE {"pass": true}` | | PASS |

- survey の 23 キーの比較 (base と fix の `M11_SURVEY` JSON): 22 キーは同一。`top_frame_idx` のみ、IR 行番号のキーが +1〜+2 ずれた
  (`1877`→`1878`、`5265`→`5266`、`14877`→`14878`・`14879`→`14880`・`14881`→`14882`)。件数は同じ。修復で IR の行数が増えたことによる。
- 観測上の変化が無いことは、修復した 3 箇所が stage4・survey の trap を消していないことを意味する。`memory access out of bounds` (stage4 の dllmain と survey の oob 8 件) の原因は、本 PR の 3 箇所には無い。
  本 PR の変更の意味は「機械語と IR の一致を 3 箇所で取り戻した」ことに限る。stage4 の trap の原因の切り分けは別件 (#942 系)。
- 修復の作用を e2e で見る経路: step 1c の出力 `work/ldfix_fixed.ll` の 44f040 (`%ldfxu14`・`%a1e`)・47cf10 (`%a1f`)。emcc -c の構文検証 (step 2) は通った。

## 6. 判定表 (REPORT_2555 §2) の更新

| 表 # | 関数 | 判定 (REPORT_2555) | 本 PR |
|---|---|---|---|
| 1 | 0x413340 | 誤り | 未修復 → 子 (C1) |
| 5 | 0x44f040 | 誤り | **修復** (§2.1) |
| 7 | 0x44fb40 | 誤り | 未修復 → 子 (C1) |
| 8 | 0x450420 | 誤り | 未修復 → 子 (C1) |
| 9〜11 | 0x450560 (3 箇所) | 誤り | 修復済 (#2502 `fix_450560.py`) |
| 12 | 0x4506e0 | 誤り | 未修復 → 子 (C1) |
| 13 | 0x47b4a0 | 誤り | 未修復 → 子 (C2・複雑型) |
| 14 | 0x47cf10 | 誤り | **修復** (§2.2) |
| 15 | 0x6074b0 | 誤り | **修復** (§2.3・表の一覧に無かった分) |
| 16 | 0xc40770 | 誤り (非 null 経路) | 未修復 → 子 (C2・複雑型) |
| + | 0x7888f0 | 誤り (取りこぼし) | 未修復 → 子 (C1) |
| — | 0x413c00・0x414c70・0x44f240 | 偽陽性 3 | 変更なし (走査定義の課題。REPORT_2555 §3) |
| — | 0x439f90 | 判定不能 1 | 変更なし |

## 7. 受入条件と未解決

| 受入条件 (#3372 本文) | 状態 |
|---|---|
| 残り 4 箇所 (0x44f040・0x47b4a0・0x47cf10・0xc40770) の機械照合付き IR 修復 | **一部**: 0x44f040・0x47cf10 を修復。0x47b4a0・0xc40770 は子 C2 |
| ネガティブコントロール (二重適用・機械照合の改変・IR base 形の不一致) | **達成** (§3) |
| `ldfix_e2e.sh` の stage4・survey の実測 (測定 commit を REPORT に書く) | **達成** (§5。測定 commit `dd8894202`) |
| 0x413340 の 3 番目引数の判定 | **未達** → 子 C1 |

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x413340・0x44fb40・0x450420・0x4506e0・0x7888f0 の site 修復 (#3326 の成果が main に無い分。0x413340 の 3 番目引数の判定を含む) | 同類型の誤り 5 箇所 (REPORT_2555 表 #1・#7・#8・#12・+) | 子 C1 (本 PR から起票) |
| 0x47b4a0・0xc40770 の site 修復 (複雑型: 比較・GEP・非 null 経路) | 同類型の誤り 2 箇所 | 子 C2 (本 PR から起票) |
| stage4 の `memory access out of bounds` (dllmain・survey の oob 8 件) の原因 | 観測上の trap が残る。本 PR の 3 箇所とは無関係と確認 | #942 (既存) |
| 走査の偽陽性 3 件・判定不能 1 件・取りこぼし定義 | 候補数の正しさ | #3328 [CI-149] (既存) |

## 8. 検証範囲・git diff 証跡

- 範囲内: 表 #5・#14・#15 の 3 箇所の IR 修復、機械照合 20 件、NC 4 種、ldfix_e2e (step 1c 込み) の 1 回完走、一次分類 17 行。
- 範囲外: 他の誤り箇所 (§6 の未修復)、stage4 の trap の原因、走査定義の変更、liftdiff batch (`--batch` は未実行)。
- 測定 commit: `dd8894202` (コード差分の最終 commit)。
  `git diff dd8894202 HEAD -- tools/m11/ldfix/fix_site_3372.py tools/m11/ldfix/ldfix_e2e.sh` の出力は、本 REPORT の commit 時点で空 (差分 0)。
- 素材: `fl-win64` は `extracted/block00031_PE.bin` (22,227,016 B) のみ展開。`work-m11` は main の `tools/m11/work/` (読込のみ・複製)。`toolchain-emsdk` は `/opt/emsdk` を使用。
- 作業物 (`tools/m11/ldfix/work/`・`tools/m11/work/`) は gitignore 対象で commit しない。

## 9. 再現

```
PE=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
python3 tools/m11/ldfix/fix_site_3372.py tools/m11/work/boot_final3.ll tools/m11/ldfix/work/site_3372_fixed.ll --pe $PE
python3 tools/m11/ldfix/fix_site_3372.py tools/m11/work/boot_final3.ll /dev/null --pe $PE --negctl {double,mach,ir}   # rc=1 が期待値
python3 tools/m11/ldfix/verify_deref_sites_2555.py tools/m11/ldfix/work/site_3372_fixed.ll --pe $PE --out <json> --extra 0x7888f0
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
```
