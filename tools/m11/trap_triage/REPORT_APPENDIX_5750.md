# #5750: 証拠表の行 226〜232 (母数 7) の件ごとの判定

判定: 母数 7 件のうち確定 3 件 (真陽性 3・偽陽性 0)、保留 4 件 (228・229・230・231)。226 は #5780 で確定 (§7)。受入 1 (全件の真偽判定) は未達。
偽陽性率は母数 288 の判定が終わるまで書かない。

## 1. 測定条件

- 測定 commit: `58ee21f1e` (origin/main)。`git diff 58ee21f1e HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/` の出力は本 PR の REPORT 追記のみ (コード変更 0 行。本文末尾の確認コマンドを参照)。
- 入力 IR: `work-m11` の `tools/m11/work/boot_final.ll` (19,787,837 B・sha256 `69c774de…`。REPORT_718 §4a・§4f と一致)。
- 入力 PE: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 再生成: `scan_guard.py --report` で strict 288 (REPORT_718 §3 と一致)。`strict_evidence.py` で TSV 288 行。
- 証拠ダンプ: `trap_triage/judge_ctx.py <IR> <TSV> <PE> 226 232` (rc 0・26 KB)。
- 機械語の確認: `ldmach.Machine.disasm_fn` で関数 `ddf630`・`de2280`・`de4000`・`ddcd00` の prologue と、count 源のストア命令 (`[rbp+0x50]`・`[rbp+0x6c]`・`[rbp+0x1f8]`・`[rbp+0x1d0]`・`[rbp+0xc0]`) を列挙した。
- IR の確認: 関数ごとの定義行 (`%61`・`%73`・`%632`・`%22`・`stack_var_-184` の store/load) を読んだ。

## 2. 判定基準

REPORT_APPENDIX_3564 §基準 と同じ (構造判定)。
- 機械語の count 源と IR の count 源が、同じ G・同じ段数・同じ幅で、IR の入口判定が無く末尾が後判定 (do-while) なら、count が 0 以下で IR が本体を回り、機械語は脱出先へ直行する。真陽性 (構造)。count = 0 の実行時到達性は未測定。
- 機械語の jcc が機械語の命令列だけで不成立なら偽陽性。
- IR の入口判定が同じ値・同じ述語で存在すれば偽陽性。述語か被演算子が違うものは保留 (同等と言えない)。

## 3. 件ごとの判定

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 226 | function_ddcd00 | ddce04 → ddd130 / ddce0f | **真陽性 (構造・arg4 ≤ 0 の域)** | 機械語: `count = arg4 − 1` (ddcd5b〜ddcd61 で `[rbp+0x6c]` を 1 減算)。ddce04 `jg` は `0 > count` (signed) = arg4 ≤ 0 で脱出 (本体を飛ばす)。IR: `%22 = arg4 − 1`、入口 `%52 = icmp ult 0, %22` (`stack_var_-184` の初期値 0)。arg4 ≤ 0 では `%22` が符号なしで大きい値になり入口が真で本体を回る。arg4 = 1 は両者とも本体を飛ばし、arg4 ≥ 2 は両者とも本体に入る。食い違いは arg4 ≤ 0 の域だけ。arg4 ≤ 0 の実行時到達性は未測定 (§7) |
| 227 | function_ddf630 | ddf8cc → ddf922 / ddf8d3 | **真陽性 (構造)** | 機械語: `ecx = [[[rbp+0x50]+8]+0x10] − 1` (`[rbp+0x50]` は ddf686 で arg1 を格納)。jcc は `0 > ecx` (signed) = count ≤ 0 で脱出。IR B (ddf8b0): `%139 = zext [[arg1+8]+16]` を `rcx.0` に格納。両者は同じ G・段数 (2)・幅 (i32)。L (ddf8d3) に入口判定は無く、末尾 `icmp eq (rcx−1), 0` の後判定。count = 0 で IR は本体を 1 回以上回る |
| 228 | function_ddf630 | ddfb8c → ddff13 / ddfb97 | 保留 | count の源は 227 と同じ `[[arg1+8]+16]` だが、IR の L (ddfb97) の入口判定は `slt stack_var_-264.ph, ([arg1+208]−2)` で、loop 変数が機械語の rbx ではない。脱出先 ddff13 の末尾も `rsi.0.ph` の判定。counter 対応が未確定 |
| 229 | function_ddf630 | de036c → de0b96 / de0379 | 保留 | 機械語の count は `[[rbp+0xc0]+0x14] − 1`。`[rbp+0xc0]` は de03bc・de0898・de0bfe でも書かれるため、ループ内で源が変わる。IR の L (de0379) の判定は `icmp ult (load+%671), %stack_var_-320` で count の判定ではない。源と述語の同一性が未確定 |
| 230 | function_de2280 | de25bc → de267e / de25c7 | 保留 | 機械語の count は `[rbp+0x1f8]` (定数 3 の経路と `[rbp+0x200]` の経路がある)。IR の count は `min(%107, 3) + 1` (`%spec.select`)。前者の定数経路と後者の値の同一性が未確認 |
| 231 | function_de2280 | de2799 → de285b / de27a4 | 保留 | 230 と同型。機械語の count は `[rbp+0x1d0]`、IR は `min(%149, 3) + 1` (`%spec.select19`)。同一性が未確認 |
| 232 | function_de4000 | de404f → de407e / de4058 | **真陽性 (構造)** | 機械語: `rcx = call de3ff0(rbx=arg1)`、`r8d = [rax+0x10] − 1`。jcc は `0 > r8d` (signed) = count ≤ 0 で脱出。IR B (de4032): `%13 = call de3ff0(arg1)`、`%17 = zext [%13+16]` を `r8.0` に格納。同じ呼出し・同じ段数・同じ幅。L (de4058) に count の入口判定は無く、de4072 の末尾 (`r8−1 ≠ 0`) が後判定。count ≤ 0 で IR は本体を回り、機械語は de407e へ直行する |

## 4. 保留の型

- 228・230・231: IR のループ変数 (`stack_var_-264`・`rsi`・`%spec.select`) が機械語の counter (`rbx`) と対応しない。
- 229: 機械語の count 源 (`[rbp+0xc0]`) がループ内で書き換えられる。IR の判定は count ではない。

保留 5 件の SSA 追跡 (機械語の被演算子と IR の被演算子を同じ値に結ぶ) は未完。起票先: #5750 (本 issue。Refs)。

## 5. 未解決

- 行 228・229・230・231 (保留 4 件): 上記 §4 の型ごとに SSA 追跡を続ける。起票先: #5750 (本 issue。子 issue は新規に起票しない)。
- count = 0 (真陽性 2 件) の実行時到達性は未測定。`docs/DEFECTS.md` の類型への対応は PM 判断。
- 範囲外: `m11_ov.c`・`docs/DEFECTS.md`・`tools/m11/guard699/`・`RetDec` 本体は変更しない (受入 3)。

## 6. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe <block00031_PE.bin> --report work/strict_5750.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe <block00031_PE.bin> --report work/strict_5750.json --out work/strict_evidence_5750.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll work/strict_evidence_5750.tsv <block00031_PE.bin> 226 232
```

出力は `work/` (gitignore) に置き、commit しない。

## 7. #5780: 行 226 の判定 (真陽性・構造)

- 測定 commit: 本 PR のコード変更は REPORT のみ (`tools/m11/guard699/`・`tools/m11/ldfix/`・`tools/m11/trap_triage/*.py` は 0 行)。
- 入力: `work-m11` の `work/boot_final.ll` (19,787,837 B・sha256 `69c774de…`。§1 と一致)、`fl-win64` の `extracted/block00031_PE.bin`。
- 再生成: `scan_guard.py --report` で strict 288、`strict_evidence.py` で TSV 288 行 (§1・§6 と一致)。
- 機械語: `LD_M11_PE=<PE> trap_triage/disasm_fn.py ddcd00` の全 243 行。
- IR: `@function_ddcd00` (boot_final.ll の定義 421256〜421537 行) の B・L・T ブロック。

判定方法 (§2 の基準と同じ):
1. 機械語 `ddcd5b`〜`ddcd61`: `[rbp+0x6c]` (= arg4、`ddcd4f` で格納) を 1 減算して `count = arg4 − 1` とする。
2. 機械語 `ddce04: jg ddd130`: `0 > count` (signed) で関数末尾へ脱出 (arg4 ≤ 0)。`ddce1a: jge ddce92`: `0 ≥ count` で本体を飛ばす (arg4 = 1)。`count ≥ 1` (arg4 ≥ 2) は本体に入る。
3. IR: `%22 = add i32 arg4, −1` (count と同じ値)。入口 `%52 = icmp ult i32 0, %22` (`stack_var_-184` の初期値 0 を `ddcd00` の store で確認)。`%22` が負 (arg4 ≤ 0) のとき符号なしで大きい値になり、入口が真で本体を回る。
4. 比較: arg4 ≥ 2 は両者とも本体に入る。arg4 = 1 は両者とも本体を飛ばす。arg4 ≤ 0 だけ食い違う (機械語は脱出、IR は本体)。
5. 呼出し元 `function_de10c0` の 2 箇所 (426874・426972 行) は `arg4` を `%208`・`%277` (`ashr exact` 32 bit) から渡す。

判定: 真陽性 (構造)。count = arg4 − 1 の同一性、入口判定の位置、食い違う値域 (arg4 ≤ 0) を確定した。

未解決: arg4 ≤ 0 が `function_de10c0` 経由の実行で到達するかは未測定。`docs/DEFECTS.md` の類型への対応は PM 判断。
