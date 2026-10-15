# #3502 付録: 証拠表の行 67〜98 の件ごとの判定 (run 2・保留 30 件の再判定)

本付録が #3502 の判定の正本。結論は `REPORT_718.md` §4k に要約する。前 run (PR #3552) の確定 2 件 (行 90・92) はそのまま。

## 1. 結果

- 母数 32 (証拠表 `strict_evidence.tsv` のデータ行 67〜98)。
- 真陽性 9 (行 69・70・75・79・85・95・96・97・98)。
- 偽陽性 4 (行 80・88・90・92)。
- 保留 19。偽陽性率は保留が残るため書かない。
- 真陽性 9 のうち、PM が IR 本文で照合したのは 3 件 (69・95・96)。残り 6 件 (70・75・79・85・97・98) は追跡結果を subagent が出し、PM は要点だけ確認した (§4 で明記)。

## 2. 判定基準

REPORT_718.md §4g と同じ。
- 真陽性: 同じ count 源 (reg2mem の store/load をたどって同じ SSA 値) に対する入口判定が IR に無く、機械語では jcc が脱出 (T) する状況で IR 側は本体を実行する経路がある。
- 偽陽性: jcc が機械語の命令列だけで不成立と分かる。または同じ値の同等判定が IR 側にある。
- 保留: 上のどちらも確定できない。構造が似ているだけでは確定しない。
- 範囲外: 実行時に count=0 が到達するか (到達性)。

## 3. 件ごとの判定

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 根拠 |
|---|---|---|---|---|
| 67 | function_12cfce0 | 12cfd97 → 12cfdb7 / 12cfd9e | 保留 | 機械語 `edx = [[G]+0x10]-1` (G = 0x15E2218 ↔ IR 18752024)。IR の count (%39) と同源と見られる。直前の P (12cfd48) に `slt load[%17-8], 1` の入口判定があり、%17 の由来が未追跡。 |
| 68 | function_12cfce0 | 12cfdcb → 12cfe2f / 12cfdd4 | 保留 | 機械語 `r13d = [[rsi+0x28]+0x14]-1`。IR の r13.0 = zext(load [%8+20]) と同源と見られるが、`[rsi+0x28]` と IR の %8 の対応が未確認。 |
| 69 | function_12d0090 | 12d00d4 → 12d0318 / 12d00df | **真陽性 (照合済)** | 機械語 `esi = [[G]+0x10]-1` (G = 0x15E2218 ↔ IR 18752024)。IR B の rsi.0 = zext(load i32 [sext(load i32 @18752024)+16]) が同じ chain。B→L は無条件。L の分岐は byte 判定のみで、body 12d00ef は count の入口判定を経ずに実行される。背面判定 12d0304 は `rsi-1` の trunc で、N=0 でも脱出せず回る。 |
| 70 | function_12d0b20 | 12d0b40 → 12d0b7b / 12d0b47 | 真陽性 (追跡のみ) | 機械語 `edi = [[G']+0x10]-1` (G' = 0x15E2510 ↔ IR 18752784)。IR B の rdi.0 = zext(load i32 [sext(load @18752784)+16]) が同源。B→L 直結。L の判定は `%19 == %8` (別条件) のみ。 |
| 71 | function_12d2df0 | 12d2e2f → 12d2f0c / 12d2e3a | 保留 | 機械語 `cmp [rbp+0x5c], ebx` (stack 変数)。IR の rbx.0 = zext(load) と同源と見られるが、stack 変数の store/load と L の背面判定の対応が未追跡。 |
| 72 | function_12d3da0 | 12d3dea → 12d3e0c / 12d3df1 | 保留 | 機械語の被演算子 `esi = table[edx*192]-1` (テーブルのフィールド)。IR の内側数 rsi.0 は preheader の load %9 由来だが、テーブルの count フィールドとの同一性が未確認。 |
| 73 | function_12d4480 | 12d4500 → 12d454e / 12d450b | 保留 | 機械語 `cmp [rbp+0x20], esi` (stack 変数)。B の `.pre` 由来の値と stack 変数の対応が未追跡。arg 対応 (ebx = arg3) も未確認。 |
| 74 | function_12d6730 | 12d6771 → 12d6859 / 12d677e | 保留 | 機械語 `r13d = [[global]+0x10]-1`、IR B の r13.0 も同源と見られる。ただし L の分岐は要素 +169 の byte 判定で、count 判定の背面ブロックの追跡が未完。 |
| 75 | function_12dd6a0 | 12dd6fa → 12dd735 / 12dd703 | 真陽性 (追跡のみ) | 機械語 `r14d = [r13+0x14]-1`、r13 は `call function_12d16a0` の戻り値。IR の count (%10 の load) も同じ call 結果。B→L 無条件で入口判定なし。 |
| 76 | function_12df9d0 | 12df9f7 → 12dfa18 / 12dfa00 | 保留 | 機械語 `r14d = [rbx+0x14]-1`、IR r14.0 = zext(load [%arg1+20]) と同形。rbx と %arg1 の入口対応 (prologue) が未確認。 |
| 77 | function_12dfe90 | 12dfeca → 12dff38 / 12dfed3 | 保留 | 機械語 `r13d = [[rbp+0x28]+0x14]-1`、IR B は r13.0 = zext(load [%arg1+20])。`[rbp+0x28]` と %arg1 の対応が未確認。構造は真陽性候補 (B→L に入口判定なし)。 |
| 78 | function_12e21a0 | 12e227e → 12e22b7 / 12e2285 | 保留 | 機械語の count は call ea6e30 の結果 -1。IR の count (%29) も同じ call 系だが、P (12e221e) に同じ call 系の `slt 1` 入口判定があり、同値か未確定。 |
| 79 | function_12f9730 | 12f97a4 → 12f98e1 / 12f97b1 | 真陽性 (追跡のみ) | 機械語 `r13d = [[call 12e1a20 の戻り値]+0x14]-1`、IR B の count も同じ call (%13) からの load 連鎖。B→L 直結で、count の判定は L 後段の `r13-1` のみ。 |
| 80 | function_1306d60 | 1306e51 → 1306e85 / 1306e63 | **偽陽性** | 機械語: 1306e38 の `mov [0x196EBD8], 14` の直後、1306e47 の `mov edx, [0x196EBD8]` で edx = 14 (同一アドレス・間に書込み・ラベルなし)。eax = 1 なので `cmp 1, 14; jg` は成立しない。jcc は機械語だけで不成立。 |
| 81 | function_1310300 | 13103e8 → 1310460 / 13103f1 | 保留 | 機械語 `r14d = [[rsp]+0x818 基底 + 20*eax]-1`、IR の %61 (load [%27+20*rax.1]) は同形。[rsp] 基底と %arg1 の対応 (prologue) が未確認。構造は真陽性候補。 |
| 82 | function_1311050 | 13110b2 → 1311118 / 13110bb | 保留 | 機械語の count は jcc 直前の vcall `call [rax+0x28]` の戻り値。IR の B には call が無く、count の SSA 源が一致しない (vcall の欠落の疑い)。 |
| 83 | function_13114d0 | 1311555 → 13115b7 / 131155c | 保留 | 機械語の N-1 は二段間接 (G → [G]+0x10)、IR の count 源 %23 は一段 (%27 = mem32[sext(%23)+16])。間接の段数が一致しない。 |
| 84 | function_13114d0 | 1311737 → 1311784 / 131173e | 保留 | 83 と同じく段数不一致 (機械語は二段、IR は一段)。 |
| 85 | function_4088d0 | 408901 → 40895b / 408908 | 真陽性 (追跡のみ) | 機械語 `rax = [G]` (qword)、`edx = [rax]` (dword)。IR の %5 = load i64 @G、%7 = load i32 %6 (rdx.0 に格納) と同じ chain。B→L 直結、入口判定なし。L 末尾 408951 の rdx-1 判定が同じ count 源。 |
| 86 | function_40ed10 | 40ed23 → 40ed40 / 40ed2c | 保留 | 構造は真陽性候補 (B はエントリで入口判定なし、L 末尾の判定は arg3 由来)。機械語の r8d (= N) と IR の %arg3 の入口対応 (prologue) が未確認。 |
| 87 | function_40edd0 | 40ede0 → 40ee04 / 40ede9 | 保留 | 86 と同じ理由 (r8d と arg3 の対応が未確認)。 |
| 88 | function_410820 | 410878 → 4108e5 / 41087a | **偽陽性** | 機械語: 410860 の `jle 410901` の fall-through でのみ 410866 に入る (r13d > 0)。410866 の call 後も r13d は非揮発レジスタとして保持される前提で、410878 の `test r13d; jle` は成立しない。IR も B の唯一の先行 41085a で `slt r13, 1` を判定済み。 |
| 89 | function_4144a0 | 4144cb → 414519 / 4144d2 | 保留 | 構造は真陽性候補 (B がエントリ、B→L 直結、L 末尾の rdi-1 判定)。機械語の ebx の入口値と IR の %arg2 の対応 (prologue) が未確認。 |
| 90 | function_416a50 | 416abd → 416ae3 / 416abf | 偽陽性 (前 run) | 機械語 `sub ebx,1` の直後の `test ebx,ebx` が CF を 0 にするため jb は成立しない。 |
| 91 | function_419400 | 4194b2 → 4194d5 / 4194b9 | 保留 | 機械語 `ecx = [rbp+0x38]-2` (メモリ値)。IR B は count を定数 -1 に畳んでおり、[rbp+0x38] との SSA 対応が取れない。 |
| 92 | function_41b7c0 | 41b7df → 41b82e / 41b7e1 | 偽陽性 (前 run) | 直前の `test r10d; jle 41b834` が count > 0 を保証し、`0 > count-1` は成立しない。 |
| 93 | function_41b850 | 41b866 → 41b887 / 41b86d | 保留 | 構造は真陽性候補 (B→L 直結、入口判定なし、L の rdi-1 判定)。機械語の rbx (= N の基底) と IR の %arg1 の入口対応 (prologue) が未確認。 |
| 94 | function_44a8c0 | 44a8d5 → 44a926 / 44a8df | 保留 | count 源 (arg3+1) は一致するが、B の `icmp eq %5, 0` と `icmp eq %4, -1` が入口の同等判定か本体内の分岐か確定できない。符号付き条件 (SF/OF) も IR に無い。 |
| 95 | function_44bc50 | 44c04a → 44c083 / 44c053 | **真陽性 (照合済)** | 機械語 `r8d = ebx-1` (44c041)、`cmp 0, r8d` (44c047)。IR B は `store rbx.1 → r8.3` (機械語 44c03e の `mov r8d, ebx` に対応)。B→L 直結で入口判定なし。L 末尾の r8.3-1 が同じ count 源。 |
| 96 | function_44bc50 | 44c19f → 44c1cd / 44c1a6 | **真陽性 (照合済)** | 機械語 `edx = [rbp+0x64]-1` (44c195-98)。P (44c18b) の `cmp [rbp+0x64], 8; jg 44c1e3` は上限の判定で、下限 (count ≥ 1) の判定ではない。IR B の %218 = zext(%202) が count で、B→L 直結。 |
| 97 | function_44bc50 | 44c2cd → 44c2fb / 44c2d4 | 真陽性 (追跡のみ) | 96 と同形。P (44c2b9) の `sgt %268, 8` は上限判定。B の %284 = zext %268 が count で、L 末尾 %299 (count-1) と同源。 |
| 98 | function_44bc50 | 44c407 → 44c435 / 44c40e | 真陽性 (追跡のみ) | 96 と同形。P (44c3f3) の `sgt %334, 8` は上限判定。B の %350 = zext %334 が count で、L 末尾 %365 と同源。 |

## 4. 判定の経路と照合の範囲

- 文脈: `tools/m11/trap_triage/judge_ctx.py` で行ごとにダンプ (機械語 jcc 前後・B・L・T・P)。ダンプは `tools/m11/work/ctx/` (gitignore)。
- 追跡: 保留 30 件を 4 組の subagent に分けて判定した (chunk A 67〜74、chunk B 75〜82、chunk C 83〜89・91、chunk D 93〜98)。各組は IR 本文 (`tools/m11/work/boot_final.ll`) を grep して追った。chunk B の初回は文脈ダンプを読めていなかったため、同じ判定基準で再実行した。
- PM 照合: 69 は B・L・背面判定 12d0304 を IR 本文で確認。95 は B の `store rbx.1 → r8.3` と L 末尾の判定を確認。96 は P の `sgt 8` が上限判定であることを確認。
- 追跡のみの真陽性 (70・75・79・85・97・98) と、機械語のレジスタ入口対応 (prologue) に依存する保留 (67・68・76・77・81・86・87・89・93) は、本 run で prologue と IR の対応を直接は確かめていない。次 run で確認する。

## 5. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe work/extracted/block00031_PE.bin --report work/strict.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe work/extracted/block00031_PE.bin --report work/strict.json --out work/strict_evidence.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll work/strict_evidence.tsv work/extracted/block00031_PE.bin 67 98
```

- 入力: `work-m11` の `boot_final.ll` (19,787,837 B)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 実行: `scan_guard.py` で strict 288・dropped 1380・jcc 25618 (4.0 s)。`strict_evidence.py` で TSV 288 行 (12.0 s)。`strict_evidence.tsv` の行番号は REPORT_718 §4g と一致。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 保留 19 件の同値判定 (機械語のレジスタ入口値と IR 引数の対応 (prologue)、stack 変数・二段間接の SSA 追跡) | 19/32 件の真偽が未確定 | #3502 (Refs。子 issue は新規に起票しない) |
| 追跡のみの真陽性 6 件 (70・75・79・85・97・98) の IR 照合 | 6 件の真陽性が未確認 | #3502 |
| 真陽性 9 件の到達性 (count=0 が実行時に来るか) | 実害は未確認 | #3502 (範囲外) |
