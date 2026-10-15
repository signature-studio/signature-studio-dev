# REPORT_3372 — 同類型 (スピル引数の 1 段 deref 脱落) の site 修復 3 箇所と ldfix_e2e の実測 (#3372 / CI-151)

既知類型との関係: **DEFECTS.md D4** (引数 reg 経由の disp=0 deref 脱落)。#2555 (REPORT_2555.md) の表の同類型。新規類型ではない。

## 0. 結論

- REPORT_2555 §2 の誤り 13 箇所のうち、本 issue の範囲で **3 箇所を site 単位で直した**: function_44f040 (表 #5)・function_47cf10 (表 #14)・function_6074b0 (表 #15)。
  書き換えは `fix_site_3372.py` (新規)。機械語 9 + 8 + 4 = **21 命令を capstone で照合**し、一致しなければ止める。IR は書き換える行が 1 件ずつ在るときだけ書く。
  - 「3 箇所を修復」は **base IR (`boot_final3.ll`) 上の数**。このうち 0x6074b0 と 0x44f040 の (a) は `ldfix.py` (F1 系) が既に直す (`%ldfxu24`・`%ldfxu14`) ので、`fix_site_3372.py` はその形を据え置く。e2e の fix 側で新たに入るのは **0x44f040 の (b)(c) の 2 行と 0x47cf10 の 2 行 (計 4 行。IR edits 4)**。
- `ldfix_e2e.sh` に step 1d (本 pass) を配線した。**HEAD `f87d3389e` で完走した (rc=0・judge PASS・wall 45.2 s。§5.1)**。
  stage4 は base / fix とも到達 4/6・同じ trap (`memory access out of bounds`)。survey は 23 キーのうち `top_frame_idx` (IR 行番号) の 5 キーだけが base と異なり、件数は全て一致。**観測上の変化は無し**。wasm サイズは base 6025281 → fix 6025498 (+217 B)。
- 測定 commit は **`f87d3389e`** (コードを変えた最後の commit)。前回の測定 commit `dd8894202` (main の step 1c を含まない pipeline) の値は §5.2 に残す。
- 一次分類 (`verify_deref_sites_2555.py`・17 行): base は OTHER 9 / ADDR 5 / MISMATCH 2 / SCAN_MISS 1、修復後は **LOAD 3** を加え OTHER 7 / ADDR 4 / MISMATCH 2 / SCAN_MISS 1。HEAD で再計算して同じ値 (§4)。
- 残りの誤り箇所の現状: 0x413340・0x44fb40・0x450420・0x4506e0・0x7888f0 は main の #3326 (PR #3400・main `bb4443c19`) で修復済み (step 1c)。0x413340 の 3 番目引数の判定は #3416 [CI-154] (CLOSED) で済み、その修復は #3426 [CI-157] (OPEN)。0x47b4a0・0xc40770 (複雑型) は #3418 [CI-156] (OPEN)。

## 1. 前提の確認 (#3326 の成果の取り込み)

- 測定時 (測定 commit `dd8894202`): `origin/main` (a5966bbc7) に `fix_site_3326.py` は無かった (`git ls-tree -r --name-only origin/main | grep 3326` → 0 件)。このため 0x413340・0x44fb40・0x450420・0x4506e0・0x7888f0 を未修復として扱い、子 issue へ移した。
- 現在: #3326 は PR #3400 (main `bb4443c19`) で merge 済み。`ldfix_e2e.sh` の step 1c が `fix_site_3326.py` を呼ぶ。5 箇所の修復は `tools/m11/ldfix/REPORT_3326.md` §0 に記録されている。
- PR の head (`f87d3389e`) は main (`670c91ef6`) と競合しない (`git merge-tree --write-tree` rc=0)。
- 表に無い **0x6074b0 (表 #15)** は #3372 の本文の一覧に入っていなかったので、本 PR に含めた (§2.3)。

## 2. 修復の内容 (`fix_site_3372.py`)

3 サイトとも、機械語の窓 (capstone) と IR 行の対応を見て書いた。「base」は `tools/m11/work/boot_final3.ll` (ldfix 前)。

### 2.1 function_44f040 (表 #5) — 引数 arg1 の `*arg1` 読出し脱落

機械語 (PE VA 0x44f040): `mov [rsp+0x60],rcx` (arg1) の後、`*arg1` を 3 箇所で使う。

| 箇所 (機械語 VA) | 機械語 | base IR | 修復 |
|---|---|---|---|
| 0x44f069・0x44f071 (nil 判定・長さ) | `rcx=[arg1]; test rcx; eax=dword[rcx-4]` | `icmp eq arg1,0` / `arg1-4` を load (base 形) | base は `%a1d = load [arg1]` で 1 段読み。ldfix 済みの形 (`%ldfxu14`) なら据え置き |
| 0x44f090・0x44f095 (44aeb0 第 1 引数) | `rcx=[rax] (=*arg1)` → call | `call 44aeb0(zext dword[arg2-4], esi)` | 第 1 引数を `*arg1` の値に置換 |
| 0x44f0cb〜0x44f0f6 (44ec40 第 3 引数 r8) | `r9=[rsp+0x60]` → `r9=[r9]` (=*arg1) → `mov r8,r9` (0x44f0f0) → call | `call 44ec40(arg2, 0, zext dword[arg2-4], …)` | 第 3 引数を `%a1e` (44aeb0 の後で改めて読んだ `*arg1`) に置換。機械照合は 0x44f0cb・0x44f0d0・0x44f0f0・0x44f0f6 の 4 命令 |

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

- 機械照合: 各サイトの命令 (VA・mnemonic・operand) を capstone の出力と完全一致で照合する (計 **21 件**: 44f040 9 件・47cf10 8 件・6074b0 4 件)。
  ISA の表記は `ldmach.Machine.disasm_fn` の出力に合わせた (例: `mov rcx, qword ptr [rsp + 0x60]`)。
- 実行 (base 入力 `boot_final3.ll`・HEAD `f87d3389e`・worktree で再実行):

| 制御 | 操作 | 結果 (終了コード・例外) |
|---|---|---|
| 正 | 通常適用 | rc=0。`machine checks 21 ok (3 sites), IR edits 7 applied` |
| NC1 二重適用 | 修復後の IR を `--negctl double` で 2 回適用 | rc=1 `AssertionError: nil/len rows: neither base form nor ldfix form (1 each)` |
| NC2 機械照合の改変 | 0x44f090 の期待 operand の `[rax]` を `[rbx]` に変える (`--negctl mach`) | rc=1 `machine mismatch at 0x44f090: want ('mov', 'rcx, qword ptr [rbx]') got ('mov', 'rcx, qword ptr [rax]')` |
| NC3 IR base 形の改変 | `%19` の第 1 引数を `%14`→`%13` に変える (`--negctl ir`) | rc=1 `function_44f040 base row count 0 (want 1)` |
| NC4 0x44f0f0 の期待の改変 (f87d3389e で追加) | `check_machine` を直接呼び、0x44f0f0 の期待 operand を `r8, r8` に変える | rc=1 `machine mismatch at 0x44f0f0: want ('mov', 'r8, r8') got ('mov', 'r8, r9')` |
| 再適用の拒否 | 修復済み IR (`site_3372_fixed.ll`) を入力に再実行 | rc=1 (`nil/len rows` で停止) |

- 陽性対照として、一次分類で LOAD に変わったことを §4 で確認した (修復の効果の機械的な確認)。

## 4. 一次分類 (`verify_deref_sites_2555.py`)

同じ実行環境 (PE `block00031_PE.bin`・`--extra 0x7888f0`) で base と修復後を比べた。測定は測定 commit `dd8894202` で行い、HEAD `f87d3389e` で再計算して同じ値を得た。

| 入力 | 候補 | OTHER | ADDR | MISMATCH | LOAD | SCAN_MISS |
|---|---|---|---|---|---|---|
| base (`boot_final3.ll`) | 17 | 9 | 5 | 2 | 0 | 1 |
| 修復後 (`site_3372_fixed.ll`) | 17 | 7 | 4 | 2 | **3** | 1 |

- LOAD に変わったのは 0x44f040 の 0x44f095 (`%a1d`)・0x47cf10 の 0x47cfa4・0x6074b0 の 0x6074c3 の 3 件。
  (`verify_3372_final.json` の `verdict` と `ir_arg` を確認)。
- 一次分類は「機械的な振り分け」であり最終判定ではない (REPORT_2555 §5)。最終判定は、本 REPORT の §2 の窓読みによる。

## 5. ldfix_e2e の実測

### 5.1 HEAD `f87d3389e` (本 PR の結論。測定 commit)

- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` (前景・1 回・worktree 上)。step 1d は本 PR で追加。
- 素材: `fl-win64` は `extracted/block00031_PE.bin` (22,227,016 B) のみ展開。`work-m11` は `tools/m11/work/` に展開 (gitignore・読込のみ)。`toolchain-emsdk` は runner の emsdk を使用 (`[EMSDK]`。スクリプトの step 2 が既定で読む場所)。
- 測定 commit: **`f87d3389e`** (コードを変えた最後の commit。`fix_site_3372.py` の 0x44f0f0 照合の追加)。
- 計時 (`date -u +%s.%N` の差): **rc=0・wall 45.2 s**。load average は実行前 `0.40 0.57 0.27`、実行後 `1.18 0.74 0.35` (1/5/15 分。4 vCPU)。
- 入力 IR: `tools/m11/work/boot_final3.ll` の sha256 は **`010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e`**。別 REPORT (`tools/m11/REPORT_SHX-T27.md`) が接頭辞 `010451ad…` で記録した boot_final3.ll と一致する。

| 項目 | base (修復前) | fix (修復後) | 判定 |
|---|---|---|---|
| stage4 到達 | 4/6 | 4/6 | 同じ |
| stage4 の threw | `memory access out of bounds` | `memory access out of bounds` | 同じ |
| wasm_size (B) | 6025281 | 6025498 | +217 |
| probe GetMem / FreeMem / FastMM_GetMem | 16 / 6 / 17 | 16 / 6 / 17 | 同じ |
| units_run / units_total / init_count / icall_ok | 17 / 942 / 18 / 24 | 17 / 942 / 18 / 24 | 同じ |
| survey ok / noproc / miss / trap | 136 / 0 / 14 / 9 | 136 / 0 / 14 / 9 | 同じ |
| survey trap_kinds | oob 8・halt0 1 | oob 8・halt0 1 | 同じ |
| judge (`judge_e2e.py`) | `STAGE4_JUDGE {"pass": true, "stage_base": 4, "stage_fix": 4, …}` | | PASS |

- step 1d の出力は `fix_site_3372: machine checks 21 ok (3 sites), IR edits 4 applied`。base 入力での 7 件のうち (a) と 0x6074b0 の 3 件は、step 1 の `ldfix.py` が既に直しているため数えない。
- survey の 23 キーの比較 (base と fix の `M11_SURVEY` JSON): 22 キーは同一。`top_frame_idx` のみ、IR 行番号のキーが +1〜+2 ずれた
  (`1877`→`1878`、`5265`→`5266`、`14877`→`14878`・`14879`→`14880`・`14881`→`14882`)。件数は同じ。修復で IR の行数が増えたことによる。
- 観測上の変化が無いことは、修復した 3 箇所が stage4・survey の trap を消していないことを意味する。`memory access out of bounds` (stage4 の dllmain と survey の oob 8 件) の原因は、本 PR の 3 箇所には無い。
  本 PR の変更の意味は「機械語と IR の一致を 3 箇所で取り戻した」ことに限る。stage4 の trap の原因の切り分けは別件 (#942 系)。
- 修復の作用を e2e で見る経路: step 1d の出力 `work/ldfix_fixed.ll` の 44f040 (`%ldfxu14`・`%a1e`)・47cf10 (`%a1f`)。emcc -c の構文検証 (step 2) は通った。

### 5.2 前回の測定 commit `dd8894202` (main の step 1c を含まない pipeline)

- 実行 (測定時): 同じコマンド。測定 commit `dd8894202` の HEAD で 1 回。wall **47.5 s**・rc=0。load average 実行前 `0.35 0.50 0.41`、実行後 `0.72 0.58 0.44` (4 vCPU)。
- 結果: stage4 は 4/6 (base / fix)・同じ trap。wasm_size は base 6025281 → fix 6025480 (+199 B)。survey は ok 136 / noproc 0 / miss 14 / trap 9 (base / fix 同一)、trap_kinds 同一。judge `pass: true`。
- 入力 IR の sha256 は測定時に記録していなかった。当時の `work-m11` 展開物が §5.1 と同じ `boot_final3.ll` かは未確認。
- §5.1 と §5.2 の wasm_size の差 (fix 6025498 と 6025480 の +18 B) は、HEAD で追加された main の step 1c (`fix_site_3326.py`) による IR の差と見ている。この差の寄与は分離して測っていない。

### 5.3 旧試行 (`60cb4d886`・素材不足・記録のみ)

- `60cb4d886` の worktree で同じコマンドを実行したところ rc=1。`tools/m11/work/boot_final3.ll 無し` で step 0 停止。runner の `$ARTIFACTS_DIR` に `work-m11`・`toolchain-emsdk` が無く、PR 本文に `oc_artifacts:` 行が無かったため。stage4・survey は未実行。
- 現在の結論ではない。HEAD の測定は §5.1。

## 6. 判定表 (REPORT_2555 §2) の更新

| 表 # | 関数 | 判定 (REPORT_2555) | 本 PR・現状 |
|---|---|---|---|
| 1 | 0x413340 | 誤り | main の #3326 で修復済み (step 1c)。3 番目引数の判定は #3416 [CI-154] (CLOSED)、その修復は #3426 [CI-157] (OPEN) |
| 5 | 0x44f040 | 誤り | **修復** (§2.1) |
| 7 | 0x44fb40 | 誤り | main の #3326 で修復済み (step 1c) |
| 8 | 0x450420 | 誤り | main の #3326 で修復済み (step 1c) |
| 9〜11 | 0x450560 (3 箇所) | 誤り | 修復済 (#2502 `fix_450560.py`) |
| 12 | 0x4506e0 | 誤り | main の #3326 で修復済み (step 1c) |
| 13 | 0x47b4a0 | 誤り | 未修復 → #3418 [CI-156] (OPEN・複雑型) |
| 14 | 0x47cf10 | 誤り | **修復** (§2.2) |
| 15 | 0x6074b0 | 誤り | **修復** (§2.3・表の一覧に無かった分。ldfix.py の `%ldfxu24` と同形なら据え置き) |
| 16 | 0xc40770 | 誤り (非 null 経路) | 未修復 → #3418 [CI-156] (OPEN・複雑型) |
| + | 0x7888f0 | 誤り (取りこぼし) | main の #3326 で修復済み (step 1c) |
| — | 0x413c00・0x414c70・0x44f240 | 偽陽性 3 | 変更なし (走査定義の課題。REPORT_2555 §3) |
| — | 0x439f90 | 判定不能 1 | 変更なし |

## 7. 受入条件と未解決

| 受入条件 (#3372 本文) | 状態 |
|---|---|
| 残り 4 箇所 (0x44f040・0x47b4a0・0x47cf10・0xc40770) の機械照合付き IR 修復 | **一部**: 0x44f040・0x47cf10 を修復。0x47b4a0・0xc40770 は #3418 [CI-156] (OPEN) |
| ネガティブコントロール (二重適用・機械照合の改変・IR base 形の不一致) | **達成** (§3。HEAD `f87d3389e` で再実行) |
| `ldfix_e2e.sh` の stage4・survey の実測 (測定 commit を REPORT に書く) | **達成**: HEAD `f87d3389e` で完走 (§5.1)。前回の測定 commit `dd8894202` も §5.2 に残す |
| 0x413340 の 3 番目引数の判定 | 判定は #3416 [CI-154] (CLOSED・COMPLETED)。修復の判断は #3426 [CI-157] (OPEN) へ |

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x413340 の 3 番目引数 (呼出先 0x412fc0 の IR が機械語と不一致) の修復 | 同類型の疑い 1 箇所 (値の取り違え) | #3426 [CI-157] (OPEN) |
| 0x47b4a0・0xc40770 (複雑型: 比較・GEP・非 null 経路) の site 修復 | 同類型の誤り 2 箇所 | #3418 [CI-156] (OPEN) |
| stage4 の `memory access out of bounds` (dllmain・survey の oob 8 件) の原因 | 観測上の trap が残る。本 PR の 3 箇所とは無関係と確認 | #942 (既存) |
| 走査の偽陽性 3 件・判定不能 1 件・取りこぼし定義 | 候補数の正しさ | #3328 [CI-149] (既存) |

- 完了済み (参考): 0x413340・0x44fb40・0x450420・0x4506e0・0x7888f0 の修復は main の #3326 (PR #3400)。子 #3416・#3417 は CLOSED (COMPLETED)。

## 8. 検証範囲・git diff 証跡

- 範囲内: 表 #5・#14・#15 の 3 箇所の IR 修復、機械照合 21 件、NC 4 種、ldfix_e2e (step 1d 込み) の HEAD `f87d3389e` での完走 (§5.1)、前回の測定 commit `dd8894202` での完走 (§5.2)、一次分類 17 行 (§4)。
- 範囲外: 他の誤り箇所 (§6 の未修復)、stage4 の trap の原因、走査定義の変更、liftdiff batch (`--batch` は未実行)。
- 測定 commit: **`f87d3389e`** (コードを変えた最後の commit)。測定 commit から HEAD までのコード差分は 0 行 (`git diff f87d3389e HEAD -- tools/m11/ldfix ':(exclude)*.md'` の出力は空)。差分は本 REPORT (`REPORT_3372.md`) だけ。
- 前回の測定 commit `dd8894202` から測定 commit `f87d3389e` までの差分 (`git diff dd8894202 f87d3389e -- tools/m11/ldfix/ldfix_e2e.sh tools/m11/ldfix/fix_site_3372.py`):
  - `fix_site_3372.py` … 1 行追加 (機械照合 `(0x44f0f0, 'mov', 'r8, r9')`。§2.1 の 44ec40 第 3 引数の経路を機械照合する)。
  - `ldfix_e2e.sh` … 4 行追加・1 行削除 (step 1c に main の `fix_site_3326.py` が入り、本 pass は 1d に置かれた)。

  ```diff
  -step "1c/5 function_44f040 の *arg1 読出し脱落 (#3372・機械語照合付き): work/ldfix_fixed.ll を上書き"
  +step "1c/5 同類型の site 単位修復 (#3326・機械語照合付き): work/ldfix_fixed.ll を上書き"
  +python3 "$HERE/fix_site_3326.py" "$HERE/work/ldfix_fixed.ll" "$HERE/work/ldfix_fixed_site.ll" --pe "$PE" || fail "fix_site_3326.py"
  +mv "$HERE/work/ldfix_fixed_site.ll" "$HERE/work/ldfix_fixed.ll"
  +step "1d/5 function_44f040 / 47cf10 / 6074b0 の *arg1 読出し脱落 (#3372・機械語照合付き): work/ldfix_fixed.ll を上書き"
  ```

- 素材: §5.1 の通り。`fl-win64` は PE 1 本のみ展開した (e2e の参照先はこれだけ)。
- 作業物 (`tools/m11/ldfix/work/`・`tools/m11/work/`) は gitignore 対象で commit しない。

## 9. 再現

```
PE=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
python3 tools/m11/ldfix/fix_site_3372.py tools/m11/work/boot_final3.ll tools/m11/ldfix/work/site_3372_fixed.ll --pe $PE
python3 tools/m11/ldfix/fix_site_3372.py tools/m11/work/boot_final3.ll /dev/null --pe $PE --negctl {double,mach,ir}   # rc=1 が期待値
python3 tools/m11/ldfix/verify_deref_sites_2555.py tools/m11/ldfix/work/site_3372_fixed.ll --pe $PE --out <json> --extra 0x7888f0
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
```
