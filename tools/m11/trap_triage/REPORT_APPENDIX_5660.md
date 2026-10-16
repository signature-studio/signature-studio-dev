# #5660 付録: 証拠表の行 119〜158 の件ごとの突合 (M11-N252・部分達成: 判定 0 件・突合表まで)

本付録が #5660 の突合の正本。結論は `REPORT_718.md` §4l (行 119〜158 の要約行) に要約する。

## 1. 結果

- 母数 40 (証拠表 `strict_evidence.tsv` のデータ行 119〜158)。
- 確定した真陽性 0 件、確定した偽陽性 0 件、**保留 40 件**。偽陽性率は書かない (母数 288 の判定が終わるまで書かない)。
- 入口判定の本数 (loop_head の `icmp`): 0 本 9 件 (124・136・141・143・145・146・147・151・156)、1 本 12 件、2 本 17 件、3 本 1 件、6 本 1 件 (合計 40)。
  前 run の注記 (10 件と 0 件の不一致) は、本 run で `strict_evidence.tsv` の列 `ir_loop_head_icmp` から数え直した値に置き換える。

## 2. 入力と測定 commit

- 入力: `work-m11` の `tools/m11/work/boot_final.ll` (19,787,837 B・sha256 `69c774de…`。記録と一致)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 実行 (本 run・foreground): `scan_guard.py --report` で strict 288、`strict_evidence.py --out` で TSV 288 行 (ヘッダ除く)、`judge_ctx.py <IR> <TSV> <PE> 119 158` で文脈ダンプ (rc 0・約 130 KB・`tools/m11/work/` 配下、未コミット)。
- 測定 commit: `f195a93a9` (origin/main の取り込み時点)。判定に使うコードは本 PR で変更していない: `git diff f195a93a9 HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行 (本 PR は REPORT・付録のみ)。
- `m11_ov.c`・`m11` 本体・RetDec は変更していない。

## 3. 突合表 (40 件・機械語 jcc 直前の cmp と IR の loop_head 入口判定)

判定欄は全件『保留』。理由は §4。

| 行 | 関数 | jcc → 脱出先 / L | 機械語 (jcc 直前の cmp) | IR の loop_head 入口 icmp (本数 / 先頭) | 判定 |
|---|---|---|---|---|---|
| 119 | function_670fd0 | 671947 → 6719b1 / 67194e | `cmp ebx, ecx` | 2 本 / `%317 = icmp eq i64 %rbx.3.reload, 0` | 保留 |
| 120 | function_67e0a0 | 67e0d3 → 67e1bc / 67e0de | `cmp eax, edi` | 1 本 / `%32 = icmp slt i64 %r10.0, %r11.1.reload` | 保留 |
| 121 | function_67e2b0 | 67e2e3 → 67e3c5 / 67e2ee | `cmp eax, edi` | 1 本 / `%32 = icmp slt i64 %r10.0, %r11.1.reload` | 保留 |
| 122 | function_67e4b0 | 67e4e3 → 67e5ca / 67e4ee | `cmp eax, edi` | 1 本 / `%32 = icmp slt i64 %r10.0, %r11.1.reload` | 保留 |
| 123 | function_67ec50 | 67f484 → 67f779 / 67f48f | `cmp dword ptr [rbp + 0x108], ebx` | 1 本 / `%208 = icmp slt i64 %206, %207` | 保留 |
| 124 | function_682170 | 6822f3 → 6823b6 / 682300 | `cmp ebx, r13d` | 0 本 / `(入口 icmp なし)` | 保留 |
| 125 | function_682460 | 68265d → 68268b / 682664 | `?` | 2 本 / `%144 = icmp eq i32 %143, 0` | 保留 |
| 126 | function_682ae0 | 682c16 → 682c66 / 682c26 | `cmp eax, r13d` | 3 本 / `%63 = icmp eq i8 %62, 0` | 保留 |
| 127 | function_682ae0 | 682c94 → 682cca / 682ca4 | `cmp eax, r13d` | 2 本 / `%103 = icmp eq i32 %102, 0` | 保留 |
| 128 | function_682ae0 | 682d93 → 682dc2 / 682da8 | `cmp eax, edx` | 2 本 / `%178 = icmp eq i32 %177, 0` | 保留 |
| 129 | function_682ae0 | 682fc4 → 68302f / 682fd9 | `cmp eax, esi` | 2 本 / `%253 = icmp eq i32 %252, 0` | 保留 |
| 130 | function_682ae0 | 683125 → 683146 / 683133 | `cmp eax, esi` | 2 本 / `%294 = icmp eq i32 %293, 0` | 保留 |
| 131 | function_691270 | 6913b7 → 6913ee / 6913c0 | `cmp r13d, r14d` | 2 本 / `%44 = icmp eq i32 %43, 0` | 保留 |
| 132 | function_691480 | 6915b0 → 6915e7 / 6915b9 | `cmp r13d, r14d` | 2 本 / `%39 = icmp eq i32 %38, 0` | 保留 |
| 133 | function_692b20 | 692b79 → 692be4 / 692b82 | `cmp eax, r9d` | 1 本 / `%24 = icmp eq i8 %23, 0` | 保留 |
| 134 | function_693b30 | 693b7d → 693c9d / 693b8a | `cmp ebx, r14d` | 1 本 / `%26 = icmp sgt i64 %21, %25` | 保留 |
| 135 | function_694010 | 6942d7 → 69442b / 6942e2 | `cmp dword ptr [rbp + 0x2c], esi` | 1 本 / `%110 = icmp slt i64 %109, %104` | 保留 |
| 136 | function_6971f0 | 6972d0 → 6974cc / 6972db | `?` | 0 本 / `(入口 icmp なし)` | 保留 |
| 137 | function_698420 | 6984f8 → 6986ae / 698503 | `?` | 1 本 / `%30 = icmp eq i8 %29, 0` | 保留 |
| 138 | function_698860 | 6988cb → 6989df / 6988d8 | `?` | 1 本 / `%25 = icmp eq i8 %24, 0` | 保留 |
| 139 | function_699640 | 699a40 → 699be2 / 699a4b | `?` | 1 本 / `%157 = icmp eq i8 %156, 0` | 保留 |
| 140 | function_6c8f60 | 6c8fed → 6c904b / 6c900c | `cmp eax, r10d` | 6 本 / `%30 = icmp slt i64 %29, 0` | 保留 |
| 141 | function_6c9100 | 6c9116 → 6c9182 / 6c911f | `cmp r8d, r11d` | 0 本 / `(入口 icmp なし)` | 保留 |
| 142 | function_6c9100 | 6c914f → 6c9174 / 6c9156 | `cmp eax, esi` | 2 本 / `%40 = icmp eq i32 %39, 0` | 保留 |
| 143 | function_6c9190 | 6c91a4 → 6c9209 / 6c91ab | `cmp r8d, ebx` | 0 本 / `(入口 icmp なし)` | 保留 |
| 144 | function_6c9190 | 6c91dc → 6c91fd / 6c91e4 | `cmp eax, esi` | 2 本 / `%39 = icmp eq i32 %38, 0` | 保留 |
| 145 | function_6cd9c0 | 6cd9ef → 6cdb95 / 6cd9fc | `cmp ebx, r13d` | 0 本 / `(入口 icmp なし)` | 保留 |
| 146 | function_6cd9c0 | 6cda3a → 6cdb84 / 6cda47 | `cmp eax, r9d` | 0 本 / `(入口 icmp なし)` | 保留 |
| 147 | function_6cdbb0 | 6cdbe7 → 6cded2 / 6cdbf2 | `?` | 0 本 / `(入口 icmp なし)` | 保留 |
| 148 | function_6cdbb0 | 6cdc35 → 6cdebd / 6cdc42 | `?` | 1 本 / `%24 = icmp sgt i32 %23, 16` | 保留 |
| 149 | function_6cefb0 | 6ceff0 → 6cf0da / 6ceffb | `cmp eax, edx` | 2 本 / `%21 = icmp eq i32 %20, 2147483647` | 保留 |
| 150 | function_70ce80 | 70cea4 → 70cef1 / 70ceab | `cmp ebx, edi` | 2 本 / `%21 = icmp eq i32 %20, 0` | 保留 |
| 151 | function_72e2d0 | 72e3a5 → 72e5ef / 72e3b2 | `?` | 0 本 / `(入口 icmp なし)` | 保留 |
| 152 | function_72e2d0 | 72e6b6 → 72e74a / 72e6c1 | `?` | 1 本 / `%153 = icmp slt i32 %152, 1` | 保留 |
| 153 | function_75a180 | 75a251 → 75a2a1 / 75a263 | `cmp dword ptr [rbp + 0xb4], ebx` | 2 本 / `%16 = icmp eq i32 %15, 0` | 保留 |
| 154 | function_76e900 | 76e952 → 76e977 / 76e95b | `cmp eax, r10d` | 2 本 / `%22 = icmp eq i32 %21, 0` | 保留 |
| 155 | function_775da0 | 77619c → 7761fd / 7761a5 | `cmp ebx, r13d` | 2 本 / `%196 = icmp eq i32 %195, 0` | 保留 |
| 156 | function_776630 | 77671a → 7768c9 / 776727 | `cmp ebx, r14d` | 0 本 / `(入口 icmp なし)` | 保留 |
| 157 | function_7776a0 | 7776bb → 777700 / 7776c4 | `cmp esi, r13d` | 2 本 / `%26 = icmp eq i32 %25, 0` | 保留 |
| 158 | function_7778a0 | 7778af → 777915 / 7778b8 | `cmp eax, r9d` | 2 本 / `%27 = icmp eq i32 %26, 0` | 保留 |

## 4. 保留の理由 (型)

- (i) 機械語の被演算子 (`ebx`・`eax` 等) が、IR の入口判定の被演算子 (`%rbx.3.reload`・`%r10.0`・`%26` 等) と同じ SSA 値かを、reg2mem の store/load を遡って確かめていない。レジスタ名の一致だけでは根拠にしない (§4c)。
  該当: 119〜122・125〜134・137〜140・142・144・148・149・152・154・155・157・158 (27 件)。
- (ii) 入口判定が 0 本 (124・136・141・143・145・146・147・151・156)。『入口判定が無い』は真陽性の必要条件の一部でしかなく、機械語の jcc が同じ値で脱出先に行くことの確認 (SSA 追跡) が要る。前 run までに、入口判定の有無だけで確定したもの (§4g・§4k) は撤回した経緯がある。ここでは確定しない。
- (iii) 機械語の被演算子が stack 変数・メモリ経由 (123 `[rbp+0x108]`・135 `[rbp+0x2c]`・153 `[rbp+0xb4]`)。store/load の追跡が未了。
- (iv) 150 は jcc 直前に `cmp qword ptr [rip+...], 0` があり、被演算子が 2 段ある。同じ比較の対応を確かめていない。
- 型の境界: 型は jcc 直前の被演算子の出所で振り分けた。入口 icmp が 0 本の行は (ii)、被演算子が stack・メモリ経由の行は (iii)、`cmp qword ptr [rip+...]` が絡む行は (iv)、残りは (i)。153 は入口 icmp が 2 本あるが、被演算子が `[rbp+0xb4]` のため (iii) に入る (i) には入れない。
- 表の `?` の 9 行 (機械語 cmp を本 run で未抽出): 125・137・138・139・148・152 は (i) に入る (入口 icmp の被演算子は表に確定済み・機械語側の被演算子が未抽出)。136・147・151 は入口 icmp が 0 本なので (ii) に入る。(i) 27 + (ii) 9 + (iii) 3 + (iv) 1 = 40。
- 未確認の前提: 脱出先 T の経路が IR 上で到達可能か (count = 0 の実行時到達) は未測定 (範囲外)。

## 5. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe ../../extracted/block00031_PE.bin --report work/strict.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe ../../extracted/block00031_PE.bin --report work/strict.json --out work/strict_evidence.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll work/strict_evidence.tsv ../../extracted/block00031_PE.bin 119 158
```

`oc_artifacts: fl-win64 work-m11` が要る。`work-m11` は `tools/m11/work/`、`fl-win64` は `extracted/` に展開される (いずれも gitignore)。

## 6. 未解決 (残りの件ごと判定)

- 40 件 (行 119〜158) の SSA 追跡による件ごとの判定。起票先: 子 issue (`[M11-N256]`・親 #5660)。次 run は本付録 §3 の表の行を、§4 の (i)〜(iv) の型ごとに追う。
- 親 #1654 の行 99〜118 は別 issue の担当のまま (本 issue の範囲外)。
