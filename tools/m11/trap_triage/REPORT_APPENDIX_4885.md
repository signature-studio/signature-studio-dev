# #4885 付録: 証拠表の行 67・68・71〜74 の件ごとの判定 (#3502 の子)

本付録が #4885 の判定の正本。結論は `REPORT_718.md` §4l に要約する。

## 1. 結果

- 母数 6 (証拠表 `strict_evidence.tsv` のデータ行 67・68・71・72・73・74)。
- 真陽性 5 (68・71・72・73・74)。偽陽性 0。保留 1 (67)。行 72 は #5805 で真陽性 (構造) に確定 (正本 `REPORT_APPENDIX_5805.md`)。
- 偽陽性率は母数 288 の判定が終わるまで書かない。

## 2. 入力と再現

- 入力 IR: `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`。`597757f4…` の系統は使っていない)。
- 入力 PE: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 再現 (`tools/m11` で実行。生成物は `work/` 配下・gitignore):

```sh
python3 guard699/scan_guard.py work/boot_final.ll --pe work/extracted/block00031_PE.bin --report work/strict.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe work/extracted/block00031_PE.bin --report work/strict.json --out work/strict_evidence.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll work/strict_evidence.tsv work/extracted/block00031_PE.bin 67 74
```

- 実測 (本 run・測定 commit は PR 本文参照): `scan_guard.py` で strict 288・dropped 1380・jcc 25618 (4.1 s)。`strict_evidence.py` で TSV 288 行 (12.0 s)。`judge_ctx.py 67 74` は 0.25 s・rc 0。
- アドレス換算: PE の ImageBase は `0x400000`。機械語の RIP 相対 `0x15E2218` は IR の定数 `18752024` (= `0x11E2218`) と同じ G。
- 機械語は `objdump -D -b binary -mi386:x86-64` で、`.text` の RVA `0x1000` をファイル位置 `0x400` に写して逆アセンブルした。

## 3. 判定基準

REPORT_718 §4g・付録 3502 と同じ。加えて幅 (メモリ読みのビット幅) を確認する。
- 真陽性: jcc の被演算子の count 源 (IR で同じ load 連鎖) と段数・幅が機械語と IR で一致し、IR に入口判定が無く、jcc の脱出先 T が機械語で到達可能。
- 偽陽性: jcc が機械語の命令列だけで不成立、または同じ値の同等判定が IR 側の直前にある。
- 保留: 段数・幅・脱出先・SSA 同一性のいずれかが確定しない。

## 4. 件ごとの判定

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 根拠 |
|---|---|---|---|---|
| 67 | function_12cfce0 | 12cfd97 → 12cfdb7 / 12cfd9e | **保留** | 幅が不一致。機械語は `rax=[G]` (qword 読み)、`rax=[rax]` (qword)、`edx=[rax+0x10]` (dword)。IR B は `%26 = load i32 (G)` (**dword で G を読む**)、`%27 = sext`、`%28 = +16`、`%30 = load i32`。G は機械語で 8 byte のポインタとして読まれ、IR は 4 byte として読む。同じ object を指すかは未確定 (REPORT_APPENDIX_3564 §8 の「K を i32 で読む」型と同じ)。加えて P (12cfd48) の `slt load[%17-8],1` と機械語の `jle 12cffcb` (12cfd4b) の対応も未確定。 |
| 68 | function_12cfce0 | 12cfdcb → 12cfe2f / 12cfdd4 | **真陽性** | 機械語 `ebx=0 (xor eax); cmp ebx, r13d` で、`r13d = [[rsi+0x28]+0x14]-1`。`rsi = 0x193FCE0 + 192*arg1` (`lea (%rax,%rcx,8)`、rcx = 24*arg1)。IR の `%7 = 192*arg1 + 22281440+40` = 同じ table の `+40` 位置で、`%8` がその pointer、B の `%53 = load i64 [%8]`、`%54 = %53+20`、`%56 = load i32` が count (`[[rsi+0x28]+0x14]`)。段数 2・幅 (qword→dword) とも一致。`rsi` は jcc まで書き換えられない (12cfd1e 以降の `%rsi` 使用は 12cfd2d・12cfdba の読みだけ)。B (12cfdb7) → L (12cfdd4) は `br` のみで、L の判定は `function_12df530` の戻り値のビット判定 (`%62`) で count 判定の入口ではない。脱出先 T (12cfe2f) は機械語の `jg` taken 先と一致する。count=0 のとき IR は L の本体 (12cfde9 以降) を回る。 |
| 71 | function_12d2df0 | 12d2e2f → 12d2f0c / 12d2e3a | **真陽性** | 機械語 `rax = [call 12e1a20 の戻り値 +0x14]` (qword, 12d2e15)、`ebx = [rax+0x14]-1` (dword, 12d2e23・12d2e26)。IR B は `%6 = call 12e1a20()`、`%7 = %6+20`、`%9 = load i64 [%8]` (qword)、`%10 = %9+20`、`%12 = load i32` (dword) で、段数 2・幅 (qword→dword) とも一致。`ebx` は `[rbp+0x50]` 経由だが、`%13` が `rbx.0` の初期値になる。L (12d2e3a) の入口判定は `%25 = icmp ult i32 %24, 2^28` (`function_12df530` の戻り値 +4) で count 判定ではない。背面判定 `%55` は `rbx-1` の末尾判定 (`%51`・`%54`)。count=0 のとき IR は本体を回る。脱出先 T (12d2f0c) は機械語の `jg` taken 先と一致する。 |
| 72 | function_12d3da0 | 12d3dea → 12d3e0c / 12d3df1 | **真陽性 (構造)** (#5805 で確定。正本は `REPORT_APPENDIX_5805.md`) | 件ごとの根拠は `REPORT_APPENDIX_5805.md` §5 を参照。 |
| 73 | function_12d4480 | 12d4500 → 12d454e / 12d450b | **真陽性** | 機械語: `mov %r8,%rbx` (12d448a) で `ebx = arg3`、`test %sil,%sil; je 12d44f6` (12d44a4) で arg4 の低 byte が 0 の経路に入る。12d44f6 で `esi = ebx`、`cmp [rbp+0x20] (=0), esi; jg 12d454e` (12d4500)。count は `esi-0+1 = arg3+1`。IR: P (12d4480) の `br i1 %4, 12d44f6` (`%4 = icmp eq (trunc arg4), 0`) が同じ分岐。B (12d44f6) は入口判定なしで `%.pre = arg3+1` を `%rsi.1.in` に入れ、L (12d450b) の末尾 `trunc(%14) != 0` で回る (post-test)。段数 0 (`arg3` 直接)。幅は、機械語が `ebx`・`esi` (32 bit)、IR が L 先頭の `and %rsi.1.in, 4294967295` で 32 bit に丸めるため一致する (count = low32(arg3)+1 mod 2^32 の同じ値)。arg3 の low32 が負 (-2^31〜-1) のとき機械語は `jg` で脱出し、IR は後判定で本体を 1 回回る。 |
| 74 | function_12d6730 | 12d6771 → 12d6859 / 12d677e | **真陽性** | 機械語 `mov 0x698384(%rip),%rcx` (RIP → VA 0x196EAE8) で pointer を読み、`mov 0x10(%rcx),%r13d` (dword)、`sub 1`。`ebx = eax = 0 (xor)`。IR B は `%4 = load i64 (22473448)`。22473448 = 0x156EAE8 → VA 0x196EAE8 で同じ global、`%5 = %4+16`、`%7 = load i32`、`%8 = zext`。段数 2・幅 (qword→dword) 一致。L (12d677e) の判定は `%21 = icmp eq (load i8 [%.reload+8 ... +169]), 0` (要素のバイト判定) で count 判定ではない。count 判定 (`%48 = r13-1`) は後段の `dec_label_pc_12d6849` にあり、入口判定ではない。脱出先 T (12d6859) は機械語の `jg` taken 先と一致する。 |

## 5. 補足

- 行 67 の保留は、機械語が G を qword で読むのに対し IR は i32 で読むため。段数は同じに見えるが、幅が一致しないので count 源の同一性を確定できない。行 69 (`cmp esi`、同じ G の読み) も同じ幅の不一致があり、本 run の対象外だが同型と見られる (REPORT_APPENDIX_3502 の行 69 は「真陽性 (照合済)」だが、幅の確認は本 run で初めて行った。次 run で再確認する)。
- 偽陽性率は母数 288 の判定が終わるまで書かない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 67 の G の幅 (機械語 qword・IR i32) の同一性、P 前段ガードとの対応 | 1/6 件の真偽が未確定 | #3502 (Refs) |
| 行 69 の幅 (G の qword・dword) の再確認 (本 run の対象外) | 判定 REPORT_APPENDIX_3502 の再検証が要る | #3502 (Refs) |
| 真陽性 5 件 (68・71・72・73・74) の到達性 (count=0 が実行時に来るか) | 実害は未確認 | #3502 (範囲外) |

## 7. 追加判定 (run 2・行 76〜78・81〜84)

- 母数 7 件 (行 76・77・78・81・82・83・84)。真陽性 2 (76・77)。偽陽性 0。保留 5 (78・81・82・83・84)。
- 入力と再現: §2 と同じ (`work-m11` の `boot_final.ll` sha256 `69c774de…`・`block00031_PE.bin`)。scan strict 288・TSV 288 行を再現。
- 判定基準は §3 と同じ。加えて、機械語の count 源の段数 (メモリ参照の回数) を IR の load 連鎖と突き合わせた。

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 根拠 |
|---|---|---|---|---|
| 76 | function_12df9d0 | 12df9f7 → 12dfa18 / 12dfa00 | **真陽性** | 機械語 `r14d = [rbx+0x14]-1` (dword)、`cmp ecx(=0), r14d; jg 12dfa18`。count 源は `[arg1+20]` (dword)。IR B `%2 = load i32 [arg1+20]` と段数 1・幅 (dword) が一致。IR は B から L へ無条件に入り、L 末尾の post-test で回る。count=0 のとき機械語は jg で脱出、IR は本体を 1 回回る。脱出先 12dfa18 は機械語の jg 先と一致 (epilogue)。 |
| 77 | function_12dfe90 | 12dfeca → 12dff38 / 12dfed3 | **真陽性** | 機械語 `rcx=[rbp+0x28]` (arg1) → `r13d = [rcx+0x14]-1` (dword)、`ebx=0; cmp ebx, r13d; jg 12dff38`。IR B の `%6 = load i32 [arg1+20]` が同じ count。段数 1・幅 (dword) 一致。IR は入口判定なしで L に入る。脱出先 12dff38 は機械語 `mov 0x10(%rsi),%ebx` (IR T の `%51 = load [%3+16]`) と一致。 |
| 78 | function_12e21a0 | 12e227e → 12e22b7 / 12e2285 | **保留** | count 源は一致 (`[[g]+0xd34]` の呼び出し戻り値、IR `ea6e30(%19)`・`+3380`)。ただし IR 側には入口判定 `P: icmp slt count, 1` (12e221e) があり、そのスキップ先は 12e22d2 で、機械語 jg の先 12e22b7 と異なる。同値の判定が直前にあるので偽陽性寄り。脱出先が一致しないため、確定できない。 |
| 81 | function_1310300 | 13103e8 → 1310460 / 13103f1 | **保留** | count 源は一致 (`[[rsp]+0x818]` の `[base+20*rax]`、dword。IR `%58 = 20*rax + base` の `load i32`)。脱出先 1310460 は IR T (`rax+1`・`r13-1`) と一致。ただし jcc 左辺の `edx` (索引) は、IR B が `rcx.0 = 0` を置く値と SSA で対応するかが確認できていない。 |
| 82 | function_1311050 | 13110b2 → 1311118 / 13110bb | **保留** | 機械語の count は間接呼び出し `call [rax+0x28]` の戻り値 (`r13d = eax-1`)。IR B の count は `arg+2800` 起点の load 連鎖 (`%11 = load+2^32`) で、呼び出しの戻り値ではない。源が同じ値かは未確認。 |
| 83 | function_13114d0 | 1311555 → 13115b7 / 131155c | **保留** | 機械語は `rcx = qword [0x15E2218]` → `rcx = qword [rcx]` → `esi = dword [rcx+0x10]` (参照 2 段、幅 qword)。IR B は `%23 = load i32 [18752024]` (dword 1 段) の値を `+16` の番地に使う。段数と幅の両方が一致しない。行 67 と同型の幅の不一致に、段数の不一致が加わる。 |
| 84 | function_13114d0 | 1311737 → 1311784 / 131173e | **保留** | 段数が不一致の疑い。機械語は `rcx = qword [0x15E0E00]` → `rcx = qword [rcx]` → `esi = dword [rcx+0x10]` で、間接参照が 2 段。IR B は `%129 = load i64 [18746880]` の後に `+16` の `load i32` で、1 段しか参照していない。機械語の count 源 (2 段目の `[X]`) が IR に現れていない。 |

- 脱出先の照合: 76・77 の T は機械語の jcc taken 先 (`12dfa18`・`12dff38`) と一致。78・81・84 の T は機械語の先と一致するか確認できず、保留の根拠になっている。
- 偽陽性率は母数 288 の判定が終わるまで書かない。

## 8. 未解決 (run 2 時点・保留 6 件)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 67・83: 機械語の qword 読みと IR の i32 読みの幅の不一致 (同型) | 2 件の真偽が未確定 | #4885 (Refs) |
| 行 78: IR の入口判定 (12e221e) のスキップ先と機械語 jg 先の不一致 | 1 件 (偽陽性寄り) が未確定 | #4885 (Refs) |
| 行 81: jcc 左辺 `edx` と IR の `rcx.0` の SSA 同一性 | 1 件の真偽が未確定 | #4885 (Refs) |
| 行 82: count 源が間接呼び出し `[rax+0x28]`・IR は `arg+2800` 起点の load 連鎖 | 1 件の真偽が未確定 | #4885 (Refs) |
| 行 84: 機械語の 2 段参照 (`[[g]]`) と IR の 1 段参照の不一致 | 1 件の真偽が未確定 (IR の count 源が誤りの可能性) | #4885 (Refs) |
| 行 69: 幅の再確認 (前 run から継続) | REPORT_APPENDIX_3502 の再検証が要る | #3502 (Refs) |
| 真陽性 7 件 (68・71・72・73・74・76・77) の到達性 (count=0 が実行時に来るか) | 実害は未確認 | #3502 (範囲外) |
