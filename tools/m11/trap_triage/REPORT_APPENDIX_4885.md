# #4885 付録: 証拠表の行 67・68・71〜74 の件ごとの判定 (#3502 の子)

本付録が #4885 の判定の正本。結論は `REPORT_718.md` §4l に要約する。

## 1. 結果

- 母数 6 (証拠表 `strict_evidence.tsv` のデータ行 67・68・71・72・73・74)。
- 真陽性 4 (68・71・73・74)。偽陽性 0。保留 2 (67・72)。
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
| 72 | function_12d3da0 | 12d3dea → 12d3e0c / 12d3df1 | **保留** | count 源は一致する。機械語 `esi = dword [0x193FD34 + 192*edx] - 1` (`movslq %edx`・`shl 3`・`lea (rsi,rsi,2)`・`mov (%rax,%rsi,8)`)。IR の `%10 = load i32 [%9]`、`%9 = 22281524 + 192*arg2` (`%7`・`%8`) と同じ table・同じ段数・同じ幅。しかし IR の内側 L (12d3df1) は一致時だけ `rsi` を減らす構造 (`%24 = rsi-1` は 12d3e02 にあり、L の入口判定は `icmp eq %15, %20` のバイト比較)。機械語 jcc の左辺 `eax` (= 索引 `ebx`、12d3de6) と IR の `rax.0` (12d3e02 で +1 される) の SSA 同一性、および jcc taken 先 12d3e0c が外側カウンタ (`rcx` = 9 から減る、12d3db2) と内側末尾のどちらに対応するかが未確定。 |
| 73 | function_12d4480 | 12d4500 → 12d454e / 12d450b | **真陽性** | 機械語: `mov %r8,%rbx` (12d448a) で `ebx = arg3`、`test %sil,%sil; je 12d44f6` (12d44a4) で arg4 の低 byte が 0 の経路に入る。12d44f6 で `esi = ebx`、`cmp [rbp+0x20] (=0), esi; jg 12d454e` (12d4500)。count は `esi-0+1 = arg3+1`。IR: P (12d4480) の `br i1 %4, 12d44f6` (`%4 = icmp eq (trunc arg4), 0`) が同じ分岐。B (12d44f6) は入口判定なしで `%.pre = arg3+1` を `%rsi.1.in` に入れ、L (12d450b) の末尾 `trunc(%14) != 0` で回る (post-test)。段数 0 (`arg3` 直接)。幅は、機械語が `ebx`・`esi` (32 bit)、IR が L 先頭の `and %rsi.1.in, 4294967295` で 32 bit に丸めるため一致する (count = low32(arg3)+1 mod 2^32 の同じ値)。arg3 の low32 が負 (-2^31〜-1) のとき機械語は `jg` で脱出し、IR は後判定で本体を 1 回回る。 |
| 74 | function_12d6730 | 12d6771 → 12d6859 / 12d677e | **真陽性** | 機械語 `mov 0x698384(%rip),%rcx` (RIP → VA 0x196EAE8) で pointer を読み、`mov 0x10(%rcx),%r13d` (dword)、`sub 1`。`ebx = eax = 0 (xor)`。IR B は `%4 = load i64 (22473448)`。22473448 = 0x156EAE8 → VA 0x196EAE8 で同じ global、`%5 = %4+16`、`%7 = load i32`、`%8 = zext`。段数 2・幅 (qword→dword) 一致。L (12d677e) の判定は `%21 = icmp eq (load i8 [%.reload+8 ... +169]), 0` (要素のバイト判定) で count 判定ではない。count 判定 (`%48 = r13-1`) は後段の `dec_label_pc_12d6849` にあり、入口判定ではない。脱出先 T (12d6859) は機械語の `jg` taken 先と一致する。 |

## 5. 補足

- 行 67 の保留は、機械語が G を qword で読むのに対し IR は i32 で読むため。段数は同じに見えるが、幅が一致しないので count 源の同一性を確定できない。行 69 (`cmp esi`、同じ G の読み) も同じ幅の不一致があり、本 run の対象外だが同型と見られる (REPORT_APPENDIX_3502 の行 69 は「真陽性 (照合済)」だが、幅の確認は本 run で初めて行った。次 run で再確認する)。
- 行 72 の保留は、count 源は一致するが、IR の内側ループが一致時にだけカウントを減らす構造で、機械語 jcc の比較対象と IR の SSA 対応が未確定なため。
- 偽陽性率は母数 288 の判定が終わるまで書かない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 67 の G の幅 (機械語 qword・IR i32) の同一性、P 前段ガードとの対応 | 1/6 件の真偽が未確定 | #3502 (Refs) |
| 行 72 の jcc 左辺 (索引) と IR の rax.0 の SSA 同一性、taken 先の対応 | 1/6 件の真偽が未確定 | #3502 (Refs) |
| 行 69 の幅 (G の qword・dword) の再確認 (本 run の対象外) | 判定 REPORT_APPENDIX_3502 の再検証が要る | #3502 (Refs) |
| 真陽性 4 件 (68・71・73・74) の到達性 (count=0 が実行時に来るか) | 実害は未確認 | #3502 (範囲外) |
