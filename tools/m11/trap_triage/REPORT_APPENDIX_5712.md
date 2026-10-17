# #5712 付録: 証拠表の保留 8 件 (行 139・149・151・152・154・156・157・158) の件ごとの判定 (M11-N261・部分達成)

親 #5689 の付録 `REPORT_APPENDIX_5689.md` §8 (正本) の保留 8 件を、`work-m11` の `boot_final.ll` (sha256 `69c774de…`) と `fl-win64` の `block00031_PE.bin` で再確認した。判定規則は `REPORT_718.md` §3 (変更していない)。

## 1. 結果

- 母数 8 (保留 8 件)。
- 真陽性 2 (139・152)・偽陽性 0・保留 6 (149・151・154・156・157・158)。
- 親 §8 の判定 (真陽性 12) と合わせると、母数 20 のうち真陽性 14・偽陽性 0・保留 6。
- 偽陽性率は書かない (母数 288 の判定が終わるまで書かない)。

## 2. 再現と入力

- `scan_guard.py --report` で strict 288 (fn 数・jcc 数は親 §3 と同じ)、`strict_evidence.py --out` で TSV 288 行 (ヘッダ除く)。
- 文脈ダンプ: `judge_ctx.py <IR> <TSV> <PE> 139 158` (rc 0・62,983 B・`tools/m11/work/judge_ctx_5712.txt`・未コミット)。
- 機械語の逆アセンブル: `LD_M11_PE=<extracted>/block00031_PE.bin python3 trap_triage/disasm_fn.py <VA>`。
- 測定 commit: `f82959016` (origin/main)。判定に使うコード (`tools/m11/guard699/`・`trap_triage/strict_evidence.py`・`trap_triage/judge_ctx.py`) は本 PR で変更していない。
- `m11_ov.c`・`tools/m11/guard699/`・RetDec 本体は変更していない。

## 3. 件ごとの判定

| 行 | 関数 | 判定 | 根拠 |
|---|---|---|---|
| 139 | function_699640 | 真陽性 | count = `byte [rcx+0x74]`。`rcx` は `mov rcx, [rbp+0x38]` で、`[rbp+0x38]` は prologue `mov [rbp+0x38], rcx` (rcx = arg1) でしか書かれない。よって count = `[arg1+116]`。IR B の `%16 = arg1+116` → `load i8` (`%18`) が同じ値。ループ先頭 L の icmp は `arg1+117` (別バイト) で、count の入口判定は無い。jg → 699be2 = IR T |
| 149 | function_6cefb0 | 保留 | 機械は `mov rax, [rip+0xf26fda]` (8 バイト読み) → `mov edx, [rax+0x10]` (4 バイト)。IR は `load i32` (グローバルの 4 バイト) を `sext` して `+16`。ポインタ読みの幅が一致しない。IR の `sext` が機械の 8 バイト読みと同じ値を指すかは未確認 (型 iii) |
| 151 | function_72e2d0 | 保留 | count = `call [rax+0x28]` の戻り値 (仮想呼び出し)。呼び先オブジェクトは `[rax]` で、IR 側の `call function_840690` と同じ呼び先かは未確認 (型 ii) |
| 152 | function_72e2d0 | 真陽性 | count = `[rsi+0x10]`。`rsi` は 72e609 `call 0x40f9e0` の戻り値 (72e60e `mov rsi, rax`)。IR の `%119 = call function_40f9e0` (block 72e600) と同一。機械の `mov ebx,[rsi+0x10]` (72e6a9) → `sub ebx,1` → 72e6b1 `cmp 0, ebx` / `jg 72e74a` (count = 0 で脱出) は、IR の `%145 = %119+16` → `load i32` (`%147`) → `%148` (zext) の同じ値に対応する。IR の 72e6a7→72e6c1 は無条件で、`%148` に対する入口 icmp が無い (`dec_label_pc_72e6c1` の先頭は無条件のループ本体)。よって 139 と同じ型の、入口判定のない真陽性。rsi の同一性 (機械語を `disasm_fn.py 0x72e2d0` で列挙して確認): 72e60e `mov rsi, rax` から 72e6a9 `mov ebx,[rsi+0x10]` までの間の命令は、72e611 `mov eax,[rbp+0x54]` / 72e614 `mov [rbp+0x4c],eax` / 72e617 `jmp 72e690` / ループ 72e619〜72e6a1 (`mov rbx,rax`・`call 0x8406b0`・`call 0x840690`・`call 0x50a830`・`call 0x840c90`・`call 0x40faa0`・`mov [rbp+0x58],rax` 等) / 72e6a7 `xor eax,eax`。この区間に `rsi` を書く命令 (`mov rsi,…`・`pop rsi`・`lea rsi,…`) は無い。`call` は rsi を書き換えない (Win64 では rsi は非揮発性で、呼び先が保存する) |
| 154 | function_76e900 | 保留 | count = `r8d` (= arg3)。76e93e の経路では 76e946 まで `r8` は書かれない。ループ先頭 L に arg3 の入口判定は無い。一方 IR P の `icmp sgt arg3, rax0` は 76e924 側の分岐の判定で、機械の 76e93e 経路に対応するかは未確認 (型 i) |
| 156 | function_776630 | 保留 | count = `esi` (776712 `mov r14d, esi`)。prologue で esi は書かれず、呼び出し元の esi を引き継ぐ。出所は呼び出し元の確認が要る (型 ii) |
| 157 | function_7776a0 | 保留 | count = `movzx r13, byte [rbx+0x3de]`。`rbx = rcx = arg1` (prologue `mov rbx, rcx`) で、count = `[arg1+990]`。IR B の `%2 = arg1+990` → `load i8` (`%4`) が同じ値。機械は count を 0〜255 の範囲で扱い、IR の loop 初期値は count+1。ただし jcc が発火し得ないという値域上の観点は規則 (§2) の外側のため、判定には使わない (親 §8.2 と同じ扱い。規則の組み込みは PM 判断) |
| 158 | function_7778a0 | 保留 | count = `movzx r9, byte [rcx+0x3de]`。`rcx` は関数先頭で書かれず arg1 のまま。count = `[arg1+990]`。IR B の `%0 = arg1+990` → `load i8` (`%2`) が同じ値。157 と同じ理由で保留 |

## 4. 保留の理由 (型)

- 149 (型 iii): 読み幅 (8 バイト対 4 バイト) の同一性。
- 151 (型 ii): 仮想呼び出しの呼び先。
- 154 (型 i): 76e918 の分岐と 76e93e 経路の対応。
- 156 (型 ii): 呼び出し元の `esi`。
- 157・158 (型 i に近いが規則の定義の問題): 同一値 (`arg1+990`) は確定した。判定には jcc の値域上の観点が要る。規則に組み込むかは PM 判断。

## 5. 未解決

- 保留 6 件 (149・151・154・156・157・158) の判定。前段の確認は上記 §4 の型ごと。
- 157・158 の規則判断: 値域上 jcc が発火しない観点を REPORT_718 §3 に組み込むかは PM 判断 (起票先: 親 #5689)。
- 起票先: 本 issue #5712 の残件 (親 #5689 の付録 §8 の保留と同じ)。新規の子 issue は起票しない (前段の確認は同じ issue 内で続けられる)。

## 6. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe ../../extracted/block00031_PE.bin --report work/strict.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe ../../extracted/block00031_PE.bin --report work/strict.json --out work/strict_evidence.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll work/strict_evidence.tsv ../../extracted/block00031_PE.bin 139 158
# 152 の IR 抽出 (function_72e2d0 の本体。判定では %119・%145・%147・%148 を見る。書式は tools/m11/ldfix/REPORT_735.md と同じ。本 run では boot_final.ll が無く再実行していない)
cd work && awk '/^define .*function_72e2d0\(/{p=1} p{print} p&&/^}/{exit}' boot_final.ll > fn_72e2d0.ll && grep -nE '%(119|145|147|148) = ' fn_72e2d0.ll
# 152 の機械語 (72e2d0 の逆アセンブル。72e60e〜72e6b6 を見る)
cd .. && LD_M11_PE=../../extracted/block00031_PE.bin python3 trap_triage/disasm_fn.py 0x72e2d0 | awk '/  72e(5f|6[0-9a-f])[0-9a-f]:|  72e74[0-9a-f]:/'
```

`oc_artifacts: fl-win64 work-m11`。`work-m11` は `tools/m11/work/` で展開し、`fl-win64` は `$RUNNER_TEMP/extracted/` に展開する (いずれも gitignore)。
