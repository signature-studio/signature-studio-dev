# REPORT_3631: `410360` の間接 call `call qword ptr [rbx-0x50]` の実 target (#3631、親 #1965、REPORT_1676 §14 の続き)

既知類型との関係: `docs/DEFECTS.md` D15 と同じ形 (メモリ間接 call の IR 脱落)。ただし list B の VMT (`0xc9bc0`) を受ける場合の target は `ret` 1 命令の stub で、脱落しても状態は変わらない (無害)。他クラスの VMT を受ける場合は未測定 (§5)。

## 0. 結論

1. list B の VMT (`0xc9bc0`) を受ける場合、`410360` の `call qword ptr [rbx-0x50]` (VA `0x41037d`) の実 target は **VA `0x410070` (LVA `0x10070`)**。機械語は `ret` 1 命令 (`c3`、size 1)。IR に `function_410070` の定義は無い (`boot_final3.ll` で 0 件)。
2. 呼出し時の `rbx` は list B の VMT (LVA `0xc9bc0`)。実行時メモリで `[VMT-0x50]` = `0x10070` を 2 回 (n=2) 確認し、PE の静的値 (`0x410070`) と一致した。
3. よって list B の VMT を受ける場合、`410360` の脱落 call は **no-op**。stub は何も書かず、`410360` は後で `rax` を `[rbp+0x60]` から読み直して arg を返す。**list B の生成経路 (obj = `0xc9bc0`) では `410360` は `base(+8)=0` の原因ではない** (REPORT_1676 §4・§7 の候補から外れる)。`410360` は `40f9e0` 経由で他クラスの obj にも呼ばれ、その VMT の `[VMT-0x50]` は未測定のため、他クラスについては no-op とは言えない (§5)。
4. 残る未解決: `410320` の `call qword ptr [rax-0x30]` (VA `0x41032e`、NewInstance = VA `0x40f960`) も IR から脱落している (REPORT_1676 §7.2)。これは実機で instance を作る effectful な call で、本 issue の範囲外。下の未解決表に書く。

## 1. 機械語 (`trap_triage/disasm_fn.py`、`FL_WIN64_DIR` = `fl-win64` の展開先)

- `40f9e0` (`dl≠0` の経路): `40fa03 call 0x410320` → 戻り値 (rax) を `[rbp+0x50]` へ → `40fa13 mov rcx,[rbp+0x50]` → `40fa17 call 0x410360`。
- `410320`: `41032b mov rcx,rax` → `41032e call qword ptr [rax-0x30]` → 戻り値はそのまま rax (NewInstance の戻り値 = instance)。
- `410360`: `410376 mov rax,[rbp+0x60]` → `41037a mov rbx,[rax]` (instance の VMT) → `41037d call qword ptr [rbx-0x50]` → `410380 mov rax,[rbp+0x60]` → 戻る。
- IR の `function_410320` / `function_410360` は `ret arg1` のみ (REPORT_1676 §3)。IR では `410320` が NewInstance の戻り値の代わりに `arg1` (class ref) を返すため、IR の `410360` が受ける引数は機械語と異なる。今回の判定は機械語の経路で行った。

## 2. 静的 (PE、`pefile`)

`FL_WIN64_DIR/extracted/block00031_PE.bin`、ImageBase `0x400000`、LVA = RVA。VMT `0xc9bc0` は `.text` (VirtualSize `0xfa34b0`。RVA `0x1000`〜`0xfa44b0`、VA `0x401000`〜`0x13a44b0`、末尾は含まない) の内側にある。

| 位置 | 静的値 (raw VA) | LVA | 意味 (機械語の使い方) |
|---|---|---|---|
| `[VMT+0]` | `0x50aac0` | `0x10aac0` | slot 0 = Grow (REPORT_2408 §4) |
| `[VMT-0x20]` | `0x50a7f0` | `0x10a7f0` | `40f9e0` の `dl=0x81` 経路の `call [rbx-0x20]` が読む slot (同じ VMT) |
| `[VMT-0x30]` | `0x40f960` | `0xf960` | `410320` の NewInstance |
| `[VMT-0x50]` | `0x410070` | `0x10070` | **`410360` の target** |

- `LVA 0x10070` の 1 バイト: `0xc3` (`ret`)。`410070` の逆アセンブル (`disasm_fn.py 410070`) も `ret` のみ (size 1)。

## 3. 実行時 (`trap_triage/probe1676_410360.mjs`)

unit 0〜113 を実行し、unit 114 (`halt0`) の後に list B `[G2+188]` と VMT・`[VMT-0x30]`・`[VMT-0x50]` を読む。`image(static)` は `work/m11_image.bin` の同じ番地の値。

| 項目 | run 1 | run 2 |
|---|---|---|
| unit 114 | halt0 | halt0 |
| list B (`[G2+188]`) | `0x10bd4c20` | `0x10bd4c20` |
| `rbx = [instance]` (VMT) | `0xc9bc0` | `0xc9bc0` |
| `[VMT-0x30]` runtime / static | `0xf960` / `0xf960` | `0xf960` / `0xf960` |
| `[VMT-0x50]` runtime / static | `0x10070` / `0x10070` | `0x10070` / `0x10070` |
| `image[0x10070]` | `0xc3` | `0xc3` |

- 限界: `410360` は IR で call を持たないため、`call [rbx-0x50]` の実行そのものは trace で観測していない。実行時の値は「unit 114 の終了時点のメモリ」で読んだ (VMT は `.text` 内で、2 回の run の間に値は変わらなかった)。呼出しの経路は §1 の機械語で判断している。
- 限界: 確定したのは list B の VMT (`0xc9bc0`) に対する target だけ。他のクラスの instance では `[VMT-0x50]` の値は別になり得る (未測定)。

## 4. 検証結果 (測定 commit `54c7e3c7d`)

- 測定 commit: `54c7e3c7d` (`test(m11): probe the 410360 indirect call target (#3631)`。コード差分は `trap_triage/probe1676_410360.mjs` の追加のみ)。branch `3631-410360-vtable-target` は `origin/main` (`0c6550546`) から切った。
- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`) を `$RUNNER_TEMP/fl-win64` に展開。`toolchain-emsdk`・`toolchain-retdec`・`work-m11`・`work-liftdiff` は agent-setup が展開済み ([EMSDK]・[RETDEC]・`tools/m11/work`)。`work/lift_pe.sha256` は PE 指紋で手記録 (REPORT_1676 §6 と同じ手順)。`work/` は main の展開物を `cp -a` で worktree `ws-3631` へ複製した (1.7 GiB)。
- e2e `bash m11_e2e.sh` (foreground、worktree、commit `54c7e3c7d`): wall 51 s、`reached_stage` 4、survey ok 873 / trap 22 / miss 46 / noproc 1 (trap kinds: halt0 7・oob 15)、IR sha256 `9a9cfa06…`、**rc=1**。
  - rc=1 の原因: 実行 A (`m11_run.mjs`、`M11_PTRCHECK_MAX_NEW=69359`) の ptrcheck ratchet。`FAIL: ptrcheck image_va_words_new=69669 > max=69359`。既知: `tools/m11/REPORT_3520.md` の表で origin/main も 69669 (FAIL)、追跡 issue #3647 (OPEN)。本 issue の変更はこの経路に入らない。
  - 同じ判定を main の作業ツリー (`68eb512cd`) でも実行: rc=1、同じ 69669 FAIL、survey ok 873。
  - 各ゲートを個別に実行 (main の作業ツリーで、同じ `work/` の成果物に対して): `m11_judge.py --require-stage 4 --min-survey-ok 800` rc=0、`m11_tolerant_gate.py --strict-done 101 --survey-ok 873` rc=0、`--negctl` rc=0 (3 件検出)。`m11_run.mjs` を `M11_PTRCHECK_MAX_NEW` 無しで実行すると rc=0、有りで rc=1 (69669 > 69359) を再現。
- probe `probe1676_410360.mjs` n=2: §3 の表 (両回一致)。
- probe `probe1676_listB_writes.mjs` n=2: 両回とも unit 114 `halt0`・`L=0x10bd4c20`・`base=0`・`cnt=1` で生成、unit 275 `trap` (`base=0`・`cnt=2`)、unit 830 `trap` で L 消失。REPORT_1676 §2・§6 と一致。
- survey `SV_RAW=1 survey_units.mjs` n=2: 両回 `{"ok":873,"miss":46,"halt0":7,"oob":15,"noproc":1}`。unit 114 `halt0`・275 `oob`・830 `oob`。ok が 872 でなく 873 なのは `M11_FIX_535BF2` の既定 ON (REPORT_2521 §8.0.1) による差。
- 差分: `git diff 54c7e3c7d HEAD -- tools/m11 ':!tools/m11/trap_triage'` の出力は 0 行。`git diff --stat 54c7e3c7d HEAD -- tools/m11/trap_triage` の出力は `REPORT_1676.md` と `REPORT_3631.md` の 2 ファイルのみ (probe `probe1676_410360.mjs` は測定 commit `54c7e3c7d` に含まれるため差分に出ない)。
- branch は `origin/main` `0c655054` から切ったまま main を取り込んでいない。再 review 時点の `origin/main` (`abf0981f7`) は `tools/m11` を 9 ファイル変えているため、取り込むと測定の前提 (上の差分 0) が崩れる。PR は MERGEABLE (base と競合しない)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `410320` の `call qword ptr [rax-0x30]` (NewInstance、VA `0x41032e`) の脱落と、その instance 生成が list B の `base=0` に与える影響 | 実機の instance 生成が IR で欠ける。list B の `base=0` の残りの候補 | 親 #1965 への提案 (診断だけで実装を伴わないため子は起票しない) |
| 他クラスの instance の `[VMT-0x50]` (`40f9e0` 経由で他クラスの obj にも `410360` が呼ばれる。REPORT_1676 §8) | 本 probe は list B の VMT (`0xc9bc0`) だけ。他クラスでは `410360` の target が `ret` stub と限らず、no-op とは判定できない | 親 #1965 への提案 |
| `DEFECTS.md` への追記 (「メモリ間接 call の脱落で、list B の VMT では stub が `ret` で無害」の型) | 横断正本の更新 (他クラスの target が未測定のため、無害の一般化は不可) | PM 判断 (`docs/WORKFLOW.md` §5) |
