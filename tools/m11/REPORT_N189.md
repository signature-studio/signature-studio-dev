# M11 strict 候補の残り (証拠表 行 255・270・271) の判定 (#3574 / [M11-N189] / 親 #3492)

結論:
- **行 270** (`function_f5cf40`・jcc `f5d0d6`) と **行 271** (`function_f5d510`・jcc `f5d782`) は **真陽性 (2/2)**。
  機械語の比較値は間接 call `call qword ptr [rax+0x28]` の戻り値 (`eax`) から作られるが、IR にこの call は無い。
  IR の件数は、呼出し先オブジェクトの先頭 8 バイト (vtable ポインタ) の load から作られている。
  入口判定 (脱出 T へ行く条件分岐) も IR に無い (§2)。
- **行 255** (`function_ea8a80`・jg `ea8af0`) は、issue が名指しした前提を確認した
  (`function_1060d20` は `[arg1+0x14]` を書かない・書くのは `[arg1+0x48]` のみ。内部で呼ぶ `function_12df530` は書込み無し)。
  ただし同じ区間にある間接 call `ea8ad9` の遷移先は PE の静的情報では決まらない。
  よって行 255 の偽陽性判定は **条件付き** (未解決表の 1 行目。§3)。
- 測定 commit `dc71eecfa`。入力 IR の sha256 は既存 REPORT と一致 (`69c774de…a43`)。

## 1. 入力と再現

- 素材: `work-m11` を展開 (`tools/m11/work/boot_final.ll`・19,787,837 B・sha256 `69c774ded8aaf717…7932a43`)。
  PE: `$FL_WIN64_DIR/extracted/block00031_PE.bin` (`fl-win64`・22,227,016 B・sha256 `b2c64da40921cf26…f9496d`)。
- 証拠表 (288 件): `python3 tools/m11/guard699/scan_guard.py <IR> --pe <PE> --report <strict.json>` (strict 288)、
  続けて `python3 tools/m11/trap_triage/strict_evidence.py <IR> --pe <PE> --report <strict.json> --out <tsv>` (TSV 288 行・sha256 `9f8979edae78ff28…`)。
  前回 (#1653 等) の記録と件数 288・入力 sha256 が一致した。
- 判定材料: `LD_M11_PE=<PE> python3 tools/m11/trap_triage/judge_3574.py <IR> <tsv>` (本 PR で追加。判定はしない)。
  機械語の jcc 前後・間接 call・IR の B/L/T の終端と preds・255 の呼出し先の書込み先を出す。
- 独立検算 (別スクリプト): `python3 tools/m11/trap_triage/judge_dump.py <IR> <tsv> 270 271` (main 版) の IR 側 (`BLK-term`・`LH-icmp`) が、
  本 REPORT の IR 観察と一致 (行 270: `br label %dec_label_pc_f5d0e3`・`%80 = icmp eq i32 %79, 0` のみ / 行 271: `br label %dec_label_pc_f5d78d`・`%68 = icmp eq i32 %67, 0` のみ)。
- 不使用: `judge_ctx.py` は測定 commit の基点 `5b1f9dffc` に無かった (main へは PR #3552 の merge `1ce426b58` で後から入った)。`judge_ctx.py` は jcc 前後 8 命令・IR ブロック・参照元を出すが、jcc より前の間接 call の列挙と、呼出し先の書込み解析は出さない。行 255 の判定に要るのはこの 2 つのため、判定材料 `judge_3574.py` を本 PR で追加した。`judge_3574.py` が依存するのは `tools/m11/ldfix/ldmach.py` (基点にある) のみ。

## 2. 行 270・271: 機械語の比較値と IR の対応

### 2-1. 行 270 (`function_f5cf40`)

| 項目 | 機械語 (f5cf40) | IR (`function_f5cf40`) |
|---|---|---|
| N の出所 | `f5d0c5: call qword ptr [rax+0x28]` (`rax` = [O]、O は `f5d012: call e25f80` の戻り値) → `eax` | 対応する call が無い。`%39 = inttoptr %38` (O) の後は load のみ |
| 件数の初期値 | `f5d0c8` 以降 `r13d = eax − 1 + 1` = N (`f5d0cd`・`f5d0dc`) | `%55 = load i64, ptr %39` (O の先頭 8 B = vtable ポインタ)、`%56 = %55 + 4294967296`、`store %56 → r13.0.in` |
| 比較 | `f5d0d1 mov ebx,ecx(=0)`・`f5d0d3 cmp ebx,r13d`・`f5d0d6 jg f5d198` (N < 1 で脱出) | 入口の比較なし。L `dec_label_pc_f5d0e3` の比較は back-edge の `%80 = icmp eq (%79,0)` のみ |
| 入口 (B→L) | B `dec_label_pc_f5cfc0` の終端は `br label %dec_label_pc_f5d0e3` (無条件) | 同左 |
| 脱出先 T | `f5d198` | `dec_label_pc_f5d198` の preds は `{dec_label_pc_f5d0e3}` のみ (ループ本体を 1 回以上通らないと届かない) |

判定: **真陽性**。機械語の jcc (N < 1 で T へ) に対応する入口判定が IR に無い。
比較値 N の SSA 対応は「無し」(call 脱落)。IR が件数に使うのは vtable ポインタの下位 32 bit (`%55` 由来)。

### 2-2. 行 271 (`function_f5d510`)

| 項目 | 機械語 (f5d510) | IR (`function_f5d510`) |
|---|---|---|
| N の出所 | `f5d76c: call qword ptr [rax+0x28]` (`rax` = `[[rbp+0x5c8]+8]` の vtable) → `eax` | 対応する call が無い。`%50 = load i64, ptr %49` (vtable) |
| 件数 | `f5d771 mov ebx,eax`・`f5d773 sub ebx,1` | `%51 = %50 + 4294967296` → `rbx.0.in`。`%rbx.0 = low32` |
| 比較 | `f5d776 mov [rbp+0x584],ecx`・`f5d77c cmp [rbp+0x584],ebx`・`f5d782 jg f5d82d` | L `dec_label_pc_f5d78d` の比較は `%68 = icmp eq (%67,0)` (back-edge) のみ |
| 入口 (B→L) | B `dec_label_pc_f5d6e4` の終端は `br label %dec_label_pc_f5d78d` (無条件) | 同左 |
| 脱出先 T | `f5d82d` | `dec_label_pc_f5d82d` の preds は `{dec_label_pc_f5d78d}` のみ |

注意 (誤判定の罠): T の `dec_label_pc_f5d82d` の中に `%74 = icmp slt i32 %73, 1` がある。
これは入口判定ではない。`%72 = load` (jcc の後の間接 call `f5d83f`・機械語 `f5d842 test eax,eax`・`f5d844 jle f5d88f` に対応) の値を見る **別の判定**で、N を見ていない。
これを行 271 の入口判定とみなすと偽陽性になる。

判定: **真陽性**。行 270 と同じ構造。

### 2-3. 件数 (IR の意味論からの推定・未実行)

IR の件数は `low32(vtable ポインタ)`、機械語の件数は N (間接 call の戻り値)。両者は一般に一致しない。
これは IR 意味論からの推定で、実行による確認はしていない (§6 の未解決)。

## 3. 行 255: 前提の確認 (`function_ea8a80`)

- 入口判定 (機械語): `ea8a9f cmp dword ptr [rcx+0x14],0` → `ea8aa3 jle ea8be8`。
  IR (入口ブロック `dec_label_pc_ea8a80`): `%2 = load i32 [arg1+20]`・`%3 = icmp slt %2,1`。同じ判定。
- 行 255 の jg (機械語): `ea8ae3 mov r14d,[rcx+0x14]`・`ea8ae7 sub r14d,1`・`ea8af0 jg ea8bd4` (`esi`=0 と比較)。
  この比較の N2 は、入口判定の後の call の後で読み直した `[arg1+0x14]`。IR では `%18 = load [%1]` (`dec_label_pc_ea8aa9`)。
  IR に call 後の icmp は無く、入口の `%3` が判定を兼ねる。よって偽陽性とするには **N2 = N1**、すなわち入口判定と jg の間の呼出しが `[arg1+0x14]` を変えないことが要る。
- 入口判定と jg の間にある呼出し (`judge_3574.py` の出力):
  - (a) `ea8aad call 0x1060d20` (引数 `rcx` = arg1)。直接 call を再帰で辿った到達可能な書込みは **2 件**:
    `1060d2a mov dword ptr [rbx+0x48], 0`・`1060d57 add dword ptr [rbx+0x48], 1`。`[arg1+0x14]` への書込みは **0 件**。
    `1060d20` の直接 call は `12df530` のみ。`12df530` は `mov rax,[rcx+8]`・`imul edx,[rcx+0x10]`・`movsxd`・`lea`・`ret` の 5 命令で、メモリ書込みは無い。
    → issue の名指しの前提は確認。
    - 検出器に依らない根拠 (全命令の手読み): `1060d20` の 31 命令を PE から逆アセンブルして全て読んだ。直接 call 1 (`1060d49 call 0x12df530`)・間接 call 0。
      `rbx` (= arg1) へのメモリ書込みは `1060d2a mov dword ptr [rbx+0x48],0` と `1060d57 add dword ptr [rbx+0x48],1` の 2 件のみ。`[rbx+0x14]` は `1060d33 mov edi,dword ptr [rbx+0x14]` の読み 1 件のみ。
      他のメモリ操作は stack (`push`・`call` の戻り番地・`pop`・`ret`) と `1060d4e movzx rax,byte ptr [rax+0x13]` (読み) だけ。
  - (a') `ea8ab2`〜`ea8ac6` (呼出し直後・書込み無し): `ea8ab6 cmp dword ptr [rax+0x48],0` は読みのみ。他はレジスタ操作と分岐。
  - (b) `ea8ad9 call qword ptr [rax]` (rax = `[slot 0x15e0a48]`)。slot は `.data` にあり、静的な値は `0x15f34a0` (`.bss` 領域。起動時に決まる値)。
    したがって遷移先 `[0x15f34a0]` は静的に確定しない。引数は `rcx = &[rbp+0x30]`・`edx = 0x120` (スタック上の領域)。
    IR に対応する call は無い (D15 と同型。§4)。**未解決**: この call が `[arg1+0x14]` を書かないことは未確認。
  - (c) `ea8ac9`〜`ea8ae3` のうち (b) 以外 (`lea rcx,[rbp+0x30]`・`mov edx,0x120`・`mov rax,[rip+…]`・`xor`・`mov rcx,[rbp+0x28]`・`mov r14d,[rcx+0x14]` など) は書込み無し (読みと、レジスタ操作のみ)。
- 負の対照: 書込み検出器は既知の `1060d20` の `[rbx+0x48]` 書込みを 2 件検出 (期待 2)。
  同じ検出器で `[arg1+0x14]` (disp 0x14) への書込みは 0 件を返す。検出器が書込みを取りこぼさないことは、この既知の 2 件で確認した。
  ただし検出器 (`judge_3574.py` の `closure_writes`) は disp だけで書込みを判定し、base レジスタを見ない。直接 call のみ辿る。
  そのため上の「0 件」は、検出器の結果だけに依らず、全命令の手読み (上の (a) の内訳) でも確かめた。
- 判定: 行 255 は **偽陽性 (条件付き)**。(a) の確認により、入口判定と jg の間で N が変わるのは (b) の間接 call が書く場合だけ。
  (b) の遷移先を決めるまで、偽陽性は確定しない。

## 4. DEFECTS との関係 (D15 の変種・PM 判断)

- `docs/DEFECTS.md` D15 (メモリ間接 call `call qword ptr [reg+N]` の欠落) と同型。間接 call (`call` のオペランドに `[` を含むもの) の数は、PE の `.pdata` 関数範囲を `ldmach.Machine.disasm_fn` で線形 disasm して数えた。jcc より前は `ins[:k]` (k は jcc の添字)。
  - 行 270 (`f5cf40`・165 命令): jcc `f5d0d6` より前は **3 本** (`f5d02f`・`f5d04a`・`f5d0c5`)。関数全体は **5 本** (jcc の後の 2 本は `f5d122`・`f5d15d`)。
  - 行 271 (`f5d510`・2601 命令): jcc `f5d782` より前は **1 本** (`f5d76c`)。jcc の後は 109 本 (うち `f5d83f` は §2-2 の注意の対象)。関数全体は **110 本**。
  - 行 271 の jcc より前の数 (1 本) は、レビュー側の `judge_3574.py` 出力 (`間接 call 1 件`) とも一致する。
  いずれも IR に対応する call が無い。vtable の load だけが残る。
- 違い: D15 の記述は「call ブロックが空 (pc store のみ)」。今回は IR ブロックが空ではなく、vtable の load が **call の戻り値の位置に入る**。
  件数の SSA 値になるため、判定 (N の入口判定) に影響する。D15 の変種 (候補) として扱う。
- DEFECTS 行案 (採番は PM 判断。本 PR は `docs/DEFECTS.md` を変更しない): 「メモリ間接 call の戻り値が、呼出し先オブジェクトの先頭 8 B (vtable ポインタ) の load で置き換わる。call は脱落し、load だけ残る。ループ件数・分岐の比較値に使われると、入口判定が消える」。
  検出信号: 機械語の `call qword ptr [reg+N]` の戻り値 `eax` の後続 cmp/test に対応する IR の icmp が無く、同じ関数に `load [obj]` → `add 2^32` の定型がある。

## 5. 受入条件の判定 (issue #3574)

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 行 270・271 の比較値の SSA 対応を確定し、真陽性 / 偽陽性を判定して REPORT に書く | 達成 | §2 (両行とも真陽性。比較値の対応は「call 脱落・件数は vtable 由来」) |
| 2. 行 255 の偽陽性前提 (入口判定と guard の間の `function_1060d20` が `[arg1+20]` を書かない・内部の `function_12df530` の副作用) | 達成 (issue が名指しした 2 点) | §3 (a)。ただし同区間の (b) `ea8ad9` は issue に無い新規の未確認点で、未解決表に書いた |
| 3. 判定方法と測定 commit・入力 sha256 を REPORT に書く | 達成 | §1・§7 |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 255 の区間の間接 call `ea8ad9` (`call [[0x15e0a48]]`) の遷移先が静的に決まらない | 行 255 の偽陽性が条件付き (N2 = N1 の確認が 1 点残る) | 親 #3492 (既存の追跡先。遷移先の実行時トレースは再測定扱いのため子 issue は起票しない) |
| D15 の変種 (戻り値が vtable ポインタに置換) の DEFECTS 行案の採番 | 類型の登録が未了 | PM 判断 (本 issue へのコメントで報告) |
| 行 270・271 の関数 (`f5cf40`・`f5d510`) の件数の実行時の影響 (§2-3 の推定) | 実行結果への影響は未測定 | 親 #3492 |

## 7. 測定 commit と差分

- 測定 commit: `dc71eecfa` (判定材料 `tools/m11/trap_triage/judge_3574.py` を追加した commit。REPORT より前)。
- 測定 commit から本 REPORT を含む HEAD までの `tools/m11` のコード差分 (md 以外): `git diff dc71eecfa HEAD -- tools/m11 ':(exclude)*.md'` = 0 行 (本 PR の差分は md と `docs/DOC_MAP.md` のみ)。
- 基点 `origin/main` (`5b1f9dffc`) からの `tools/m11` の差分は `judge_3574.py` の 165 行追加のみ (`git diff --stat 5b1f9dffc dc71eecfa -- tools/m11`)。
- 数値の再現: §1 の 4 コマンド。`work/` は gitignore 対象で commit しない。
- 差し戻し対応 (文言と数の修正) で、§3・§4 の機械語の数は PE (§1 の sha256 と一致) から `ldmach` で再計数し直した。判定コード・測定 commit は変えていない。
- IR 側 (`work-m11`) は、この修正の素材に無かった。IR 側の記述 (BLK-term・preds・icmp の有無) は測定時の記録のままで、この修正では再確認していない。
