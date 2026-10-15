# M11 strict 候補の残り (証拠表 行 255・270・271) の判定 (#3574 / [M11-N189] / 親 #3492)

結論:
- **行 270** (`function_f5cf40`・jcc `f5d0d6`) と **行 271** (`function_f5d510`・jcc `f5d782`) は **真陽性 (2/2)**。
  機械語の比較値は間接 call `call qword ptr [rax+0x28]` の戻り値 (`eax`) から作られるが、IR にこの call は無い。
  IR の件数は、呼出し先オブジェクトの先頭 8 バイト (vtable ポインタ) の load から作られている。
  入口判定 (脱出 T へ行く条件分岐) も IR に無い (§2)。
- **行 255** (`function_ea8a80`・jg `ea8af0`) は、issue が名指しした前提を確認した
  (`function_1060d20` は `[arg1+0x14]` を書かない・書くのは `[arg1+0x48]` のみ。内部で呼ぶ `function_12df530` は書込み無し)。
  同じ区間の間接 call `ea8ad9` は `ippsZero_8u` (`dsp_ippv2.dll`) への呼出しと PE の束縛箇所から同定した。
  その公開仕様 (`pDst` から `len` バイトを 0 にする) により書込み範囲は `[rbp+0x30, rbp+0x150)` と確定し、`[arg1+0x14]` と交わらない。
  よって行 255 の偽陽性判定は、`dsp_ippv2.dll` の `ippsZero_8u` が公開仕様どおりに動くことを前提に置く (**条件付き**。§3・§6)。
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
| 件数の初期値 | `f5d0ca` (`mov r13d,eax`) 以降 `r13d = eax − 1 + 1` = N (`f5d0cd`・`f5d0dc`) | `%55 = load i64, ptr %39` (O の先頭 8 B = vtable ポインタ)、`%56 = %55 + 4294967296`、`store %56 → r13.0.in` |
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
  - (b) `ea8ad9 call qword ptr [rax]` (`ea8ac9` `lea rcx,[rbp+0x30]`・`ea8acd` `mov edx,0x120`・`ea8ad2` `mov rax,[0x15e0a48]`)。
    - 静的値: `.data` の `0x15e0a48` の中身は `0x15f34a0` (`.bss`)。よって遷移先は `[0x15f34a0]`。
    - 束縛箇所 (PE): `0x6542eb lea rdx,[0x15f34a0]`・`0x6542f2 lea r8,[rip+0x34df]` (VA `0x6577d8` = UTF-16LE `ippsZero_8u`)・`0x6542fc call 0x653dd0` (結果は `0x654301 test al,al`)。
      同じ関数 (`0x653f40`) の `0x653f59 lea rcx,[0x6572dc]` (UTF-16LE `dsp_ippv2.dll`) で読んだモジュールのハンドルを `0x15fe0e8` に保存 (`0x653f6a`)。
    - 束縛関数 `0x653dd0`: 名前を narrow 化 (`0x414850`) し、`0x15fe0e8` のハンドルと名前で `0x4235f0` を呼び、結果を `[rdx]` (= 格納先) に書く。
      結果が NULL なら、接頭辞 `legacy90` を付けた名前で再探索する (`0x653e1e`〜)。両方 NULL なら `al = 0` を返す (`0x653e5b`〜)。
    - `0x15f34a0` を rip 相対で参照する箇所は 2 つだけ (全 `.text` の逆アセンブル走査): 束縛 `0x6542eb`、と同じ slot を呼ぶ `0x653cbd` (関数 `0x653cb0`。`cmp rdx,0x7fffffff`・`jge` の後、rcx・rdx を変えず `call [0x15f34a0]`)。
    - 同定の根拠 (公開仕様): Intel IPP Developer Guide and Reference 2026-0 の `Zero` (https://www.intel.com/content/www/us/en/docs/ipp/developer-guide-reference/2026-0/zero.html、ID 790148、4/28/2026)。
      `IppStatus ippsZero_8u(Ipp8u* pDst, int len)` は「先頭 `len` 要素を 0 にする」。`len` ≤ 0 は `ippStsSizeErr`、`pDst` が NULL は `ippStsNullPtrErr` で、どちらも書込みは無い。
      `Ipp8u` は 1 B なので、この呼出し (`rcx = rbp+0x30`・`edx = 0x120`) の書込み範囲は `[rbp+0x30, rbp+0x150)` (0x120 B)。
    - 残る前提: `[0x15f34a0]` の実際の値は、実行時に `dsp_ippv2.dll` の GetProcAddress 相当で決まる。`fl-win64.tar.zst` の member 一覧に `.dll` は 0 件 (`dsp_ippv2.dll` は素材に無い) ため、その export を照合していない (§6)。
    - IR に対応する call は無い (D15 と同型。§4)。
  - (c) `ea8ac9`〜`ea8ae3` のうち (b) 以外 (`lea rcx,[rbp+0x30]`・`mov edx,0x120`・`mov rax,[rip+…]`・`xor`・`mov rcx,[rbp+0x28]`・`mov r14d,[rcx+0x14]` など) は書込み無し (読みと、レジスタ操作のみ)。
- 負の対照: 書込み検出器は既知の `1060d20` の `[rbx+0x48]` 書込みを 2 件検出 (期待 2)。
  同じ検出器で `[arg1+0x14]` (disp 0x14) への書込みは 0 件を返す。検出器が書込みを取りこぼさないことは、この既知の 2 件で確認した。
  ただし検出器 (`judge_3574.py` の `closure_writes`) は disp だけで書込みを判定し、base レジスタを見ない。直接 call のみ辿る。
  そのため上の「0 件」は、検出器の結果だけに依らず、全命令の手読み (上の (a) の内訳) でも確かめた。
- 判定: 行 255 は **偽陽性 (条件付き)**。入口判定と jg の間で N (`[arg1+0x14]`) が変わるのは、(b) の間接 call が書く場合だけ。
  書込み範囲の判定は次の 2 点で成り立つ。
  - (A) 呼出し先 `[0x15f34a0]` は公開仕様の `ippsZero_8u` と同じ動作をする (書込みは `[rbp+0x30, rbp+0x150)` のみ)。公開仕様は (b) の同定で照合した。`dsp_ippv2.dll` の export の照合は未了 (§6)。
  - (B) arg1 はこのフレームを指さない。`ea8a80` は `sub rsp,0x158`・`mov rbp,rsp` (`ea8a8f`) なので、`[rbp+0x30, rbp+0x150)` は関数フレーム `[rsp, rsp+0x158)` の中で、戻り番地より下にある。
    arg1 は呼出し元が渡した値 (呼出し元のフレーム・ヒープ・グローバルを指す) とする。arg1 < rsp なら arg1+0x18 < rsp+0x30、arg1 ≥ rsp+0x158 なら arg1+0x14 > rsp+0x150 なので、`[arg1+0x14, arg1+0x18)` は書込み範囲と交わらない。
    フレーム内を指す値 (解放済みフレームを指す不正な値を含む) は前提の外とする。
  (A) が成り立てば、(B) と合わせて N2 = N1 となり偽陽性が確定する。(A) の DLL 照合が残る限り、判定は条件付きのまま。

## 4. DEFECTS との関係 (D15 の変種・PM 判断)

- `docs/DEFECTS.md` D15 (メモリ間接 call `call qword ptr [reg+N]` の欠落) と同型。間接 call (`call` のオペランドに `[` を含むもの) の数は、PE の `.pdata` 関数範囲を `ldmach.Machine.disasm_fn` で線形 disasm して数えた。jcc より前は `ins[:k]` (k は jcc の添字)。
  - 行 270 (`f5cf40`・165 命令): jcc `f5d0d6` より前は **3 本** (`f5d02f`・`f5d04a`・`f5d0c5`)。関数全体は **5 本** (jcc の後の 2 本は `f5d122`・`f5d15d`)。
  - 行 271 (`f5d510`・2601 命令): jcc `f5d782` より前は **1 本** (`f5d76c`)。jcc の後は 109 本 (うち `f5d83f` は §2-2 の注意の対象)。関数全体は **110 本**。
  - 行 271 の jcc より前の数 (1 本) は、`judge_3574.py` の出力 (`間接 call 1 件`) とも一致する。
  いずれも IR に対応する call が無い。vtable の load だけが残る。
- 違い: D15 の記述は「call ブロックが空 (pc store のみ)」。今回は IR ブロックが空ではなく、vtable の load が **call の戻り値の位置に入る**。
  件数の SSA 値になるため、判定 (N の入口判定) に影響する。D15 の変種 (候補) として扱う。
- DEFECTS 行案 (採番は PM 判断。本 PR は `docs/DEFECTS.md` を変更しない): 「メモリ間接 call の戻り値が、呼出し先オブジェクトの先頭 8 B (vtable ポインタ) の load で置き換わる。call は脱落し、load だけ残る。ループ件数・分岐の比較値に使われると、入口判定が消える」。
  検出信号: 機械語の `call qword ptr [reg+N]` の戻り値 `eax` の後続 cmp/test に対応する IR の icmp が無く、同じ関数に `load [obj]` → `add 2^32` の定型がある。

## 5. 受入条件の判定 (issue #3574)

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 行 270・271 の比較値の SSA 対応を確定し、真陽性 / 偽陽性を判定して REPORT に書く | 達成 | §2 (両行とも真陽性。比較値の対応は「call 脱落・件数は vtable 由来」) |
| 2. 行 255 の呼び先 `ippsZero_8u` (`dsp_ippv2.dll`・slot 0x15E0A48 → 0x15F34A0) の公開仕様 (pDst から len バイトを 0 で埋める) を照合し、REPORT_3492 §5 に書く。`dsp_ippv2.dll` は素材 `fl-win64` に無いため、取得可否を確認し、無ければ公開仕様の出典を書く。 | 達成 (照合結果は本 REPORT の §3 (b) に書いた。公開仕様の出典は上記 URL。`dsp_ippv2.dll` は素材に無い (`.dll` 0 件)。`REPORT_3492` §5 は未 merge の枝にあり、本 PR からは書けない。その枝への転記は §6 の行) | §3 (a)・(b) |
| 3. 判定方法と測定 commit・入力 sha256 を REPORT に書く | 達成 | §1・§7 |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 255: `[0x15f34a0]` が `dsp_ippv2.dll` の `ippsZero_8u` であること (§3 (A))。`dsp_ippv2.dll` は素材に無く、export は未照合。公開 API の契約を前提に置いた | 行 255 の偽陽性が条件付き (前提 (A) が残る) | 親 #3492 (実行時の値・DLL の照合は再測定扱いのため子 issue は起票しない) |
| `REPORT_3492` §5 への転記 (受入 2 の文言の書き先。その枝は未 merge) | 親の REPORT に §3 (b) の同定が無い | 親 #3492 |
| 行 270・271 の関数 (`f5cf40`・`f5d510`) の件数の実行時の影響 (§2-3 の推定) | 実行結果への影響は未測定 | 親 #3492 |
| D15 の変種 (戻り値が vtable ポインタに置換) の DEFECTS 行案の採番 | 類型の登録が未了 | PM 判断 (issue #3574 へのコメントで報告) |

## 7. 測定 commit と差分

- 測定 commit: `dc71eecfa` (判定材料 `tools/m11/trap_triage/judge_3574.py` を追加した commit。REPORT より前)。
- 測定 commit から本 REPORT を含む HEAD までの `tools/m11` のコード差分 (md 以外): `git diff dc71eecfa HEAD -- tools/m11 ':(exclude)*.md'` = 0 行 (本 PR の差分は md と `docs/DOC_MAP.md` のみ)。
- 分岐元 (merge-base) `5b1f9dffc` からの `tools/m11` の差分は `judge_3574.py` の 165 行追加のみ (`git diff --stat 5b1f9dffc dc71eecfa -- tools/m11`)。origin/main は分岐後に進んでいる。
- 数値の再現: §1 の 4 コマンド。`work/` は gitignore 対象で commit しない。
- 差し戻し対応 (文言と数の修正) で、§3・§4 の機械語の数は PE (§1 の sha256 と一致) から `ldmach` で再計数し直した。判定コード・測定 commit は変えていない。
- IR 側 (`work-m11`) は、この修正の素材に無かった。IR 側の記述 (BLK-term・preds・icmp の有無) は測定時の記録のままで、この修正では再確認していない。
