# #5773 付録: 証拠表の行 228・230・231 (母数 3) の件ごとの判定 (部分達成: 真陽性 2・偽陽性 0・保留 1)

本付録が #5773 (親 #5750) の判定の正本。`REPORT_APPENDIX_5750.md` §3 の 230・231 (保留) はここで確定した。判定の基準は `REPORT_APPENDIX_5750.md` §2 と同じ (構造判定)。

## 1. 結果

- 母数 3 (証拠表 `strict_evidence.tsv` のデータ行 228・230・231)。
- 真陽性 (構造) 2 (230・231)、偽陽性 0、保留 1 (228)。
- 偽陽性率は母数 288 の判定が終わるまで書かない。count = 0 の実行時到達性は未測定。

## 2. 測定条件

- 測定 commit: `7a90f082c` (`git diff 7a90f082c origin/main -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` は 0 行)。
- 入力 IR: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774de…`。REPORT_APPENDIX_5750 §1 と一致)。
- 入力 PE: `fl-win64` の `extracted/block00031_PE.bin`。
- 再生成: `guard699/scan_guard.py --report` で strict 288、`strict_evidence.py` で TSV 288 行 (rc 0)。`judge_ctx.py … 226 232` (rc 0・26 KB)。
- 機械語: `ldfix/ldmach.Machine.disasm_fn` で `de2280` (945 命令)・`ddf630` を列挙し、count 源の store/load・jcc・back-edge を読んだ。
- IR: `de2280`・`ddf630` の関数定義を `boot_final.ll` から切り出し、入口判定・後判定・loop 変数の定義行を読んだ。

## 3. 件ごとの判定

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 228 | function_ddf630 | ddfb8c → ddff13 / ddfb97 | 保留 | count 源 `[[arg1+8]+16]` は 227 と同じ。IR B (ddfb71) は `rbx.3 = zext [[arg1+8]+16]` を格納し、機械語の `ebx` と対応する (機械語 ddff08 `sub ebx,1`・ddff0d `jne ddfb97` ↔ IR ddfee4 `%474`・`%477`)。ただし IR の L (ddfb97) の分岐 `slt stack_var_-264, ([arg1+208]−2)` は count でなく外側の変数で決まる。IR の `rbx.3` の書込みは 2 箇所だけ (668 の初期化・934 の後判定の更新)。`slt` が偽の枝 (ddfbf7 → ddfc09) は `rbx.3` を書かない。ただし ddfc09 以降の脱出先の扱いは未追跡のため、count ≤ 0 の入口の同等性は確定できない |
| 230 | function_de2280 | de25bc → de267e / de25c7 | **真陽性 (構造)** | 機械語: `[0x200] = sext(ec − e4 − 1)` (de2570・de257c)。`cmp [0x200],3; jl` (de2583・de258b) の clamp で `[0x1f8] = min(X,3)` (de258d/de259a)。`ebx = [0x1f8]` = X。jg (de25bc) は `0 > X` (X < 0) で脱出。IR の count = X+1 なので、count ≤ 0 に当たる。IR: `%107 = ec − e4 − 1` (`%104`・`%106`)、`%spec.select = select(%107 < 3, %107, 3)`、`%109 = +1`。式・clamp・+1 が同じ。IR L (de25c7) に入口判定は無く、末尾 `rbx−1 ≠ 0` の後判定 (de2678 ↔ %125)。count ≤ 0 で機械語は de267e へ直行し、IR は本体を 1 回以上回る |
| 231 | function_de2280 | de2799 → de285b / de27a4 | **真陽性 (構造)** | 230 と同型。機械語: `[0x1d8] = sext(ec − 1)` (de2746〜de2756)、clamp `cmp 3` (de2760〜de276a)、`ebx = [0x1d0]` = X。jg (de2799) は `0 > X` で脱出。IR の count = X+1 (`%151`) なので、count ≤ 0 に当たる。IR: `%148 = load ec`、`%149 = ec − 1`、`%spec.select19 = select(%149 < 3, %149, 3)`、`%151 = +1`。IR L (de27a4) に入口判定無し、後判定 (de2855 ↔ %167)。count ≤ 0 で機械語は de285b へ直行 |

## 4. 保留の型

- 228: count 源は一致し、loop 変数 `rbx` も対応する。残る未確定は、IR の L (ddfb97) の `slt stack_var_-264` が偽のとき (ddfbf7 → ddfc09) に rbx を減らす経路の有無。機械語側の後判定は ddff0d の 1 本だけ。起票先: #5773 (本件。子 issue は切らない)。

## 5. 未解決

- 行 228 (保留 1 件): ddfbf7 → ddfc09 の枝が rbx を更新するかを SSA で追う。起票先: #5773 (Refs)。
- count = 0 (真陽性 2 件 230・231 を含む) の実行時到達性は未測定。`docs/DEFECTS.md` の類型への対応は PM 判断。
- 範囲外: `m11_ov.c`・`docs/DEFECTS.md`・`tools/m11/guard699/`・RetDec 本体は変更しない (受入 3)。

## 6. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe <block00031_PE.bin> --report work/strict_5750.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe <block00031_PE.bin> --report work/strict_5750.json --out work/strict_evidence_5750.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll work/strict_evidence_5750.tsv <block00031_PE.bin> 226 232
```

出力は `work/` (gitignore) に置き、commit しない。
