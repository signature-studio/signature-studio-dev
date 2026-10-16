# #5751 付録: 証拠表の行 233〜240 (8 件) の件ごとの判定 (M11-N266・真陽性 8・偽陽性 0・保留 0)

本付録が #5751 の判定の正本。結論は `REPORT_718.md` §4m の要約行に載せる。判定の基準は `REPORT_APPENDIX_3564.md`・`REPORT_APPENDIX_5689.md` と同じ (構造判定・到達性は範囲外)。

## 1. 結果

- 母数 8 (証拠表 `strict_evidence.tsv` のデータ行 233〜240)。
- 真陽性 8 (233〜240)、偽陽性 0、保留 0。
- 偽陽性率は母数 288 の判定が終わるまで書かない。count = 0 の実行時到達性は未測定。
- 訂正 (2 回目 run): 前 run (PR #5760) は 236・237 を保留とし、IR の back-edge counter を `stack_var_-192`・`-188` と書いた。これは外側ループ (`e255d0`・`e25822` の G の index 側) の counter で、誤りだった。内側ループ (`L=e25618`・`L=e2586a`) の back-edge counter は `stack_var_-184` (`e257ac`)・`stack_var_-180` (`e259eb`) であり、機械語の count 源 G と同一 SSA で対応する。判定はこれに基づき真陽性とした。

## 2. 入力と再現

- 素材指定: 本文の `oc_artifacts: fl-win64 work-m11 work-liftdiff` (`work-m11` → `tools/m11/work/`・`fl-win64` → `extracted/`。`docs/WORKFLOW.md` §11)。
- 判定時の入力 (展開の事実): `tools/m11/work/boot_final.ll` (19,787,837 B・sha256 `69c774de…`)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。`ir_conditions.json` は work-m11 に無く、判定では使っていない。
- 再現 (2 回目 run・foreground): `scan_guard.py --report` 4.671 s (`time` の real) で strict 288 (fn・jcc は §3 と一致)。`strict_evidence.py --out` で TSV 288 行 (ヘッダ除く)。`judge_ctx.py <IR> <TSV> <PE> 236 237` は rc 0 (121 行)。関数 `function_e25550` の全命令を `ldmach.Machine` で逆アセンブルし、`[rbp+0xa8]`・`[rbp+0xbc]`・`[rbp+0x30]`・`[rbp+0x34]` の読み書きを確認した。
- 測定 commit: `58ee21f1e` (origin/main)。判定に使ったコード (`tools/m11/guard699/`・`tools/m11/ldfix/ldmach.py`・`tools/m11/trap_triage/strict_evidence.py`・`judge_ctx.py`) は `git diff 58ee21f1e origin/main` で 0 行。
- 作業ファイルは `tools/m11/work/` (gitignore・未コミット)。

## 3. 件ごとの判定

判定基準: 機械語の jcc の左辺 (count − 1 側) と IR の back-edge の counter が同じ G (呼び出しと deref の段数・幅) から来ること、かつ IR の loop 先頭に入口判定が無く末尾が後判定 (do-while) であること。このとき count = 0 で IR は本体を 1 回回り、機械語は脱出先 T へ直行する (真陽性・構造判定)。

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 233 | function_de43b0 | de46a9 → de46c6 / de46b4 | 真陽性 | 機械語 `ecx` = [rbp+0x54] (index) で count = index+1。IR の L の counter `rcx.0` は B で `index+1` (`%140`・`%141`) に設定され、back-edge `%146` で減る。L に入口判定が無く、後判定 (`%150`)。index は [rbp+rax*4+0x44] の配列添字として機械語・IR の両方で同一 |
| 234 | function_e24ee0 | e24f09 → e24f89 / e24f12 | 真陽性 | 機械語 `r13d` = call 12f9ed0 の結果 − 1。IR の counter `r13.0.in` は `%3 + 2^32` (低 32 bit = 結果)、back-edge `%40` で減る。L e24f12 に入口判定が無い (B から無条件に e24f12) |
| 235 | function_e24ee0 | e24f2d → e24f76 / e24f36 | 真陽性 | 機械語 `rsi` = [call 12f9ec0(ecx)+0x14]、`r14d` = [rsi+0x14] − 1。IR `%7` = call 12f9ec0(-60)、`%10` = load [%7+20]、`%13` = load [%10+20] で G が一致。counter `r14.0` は back-edge `%34` で減る。L e24f36 に入口判定が無い |
| 236 | function_e25550 | e25607 → e257c7 / e25618 | 真陽性 | 機械語 e255d0〜e255f5: `[rbp+0xa8]` = G = [call 12f9ec0([rbp+0xbc])+0x14]、`[rbp+0x30]` = [G+0x14] − 1 (count − 1)。jcc e25607 は `[rbp+0xb8]` (inner index) > count − 1 で T=e257c7 へ。IR B=e255d0 の `%17` = call 12f9ec0(-44)、`%20` = load [%17+20] = G、`%23` = load i32 [G+20] → `stack_var_-184`。-44 は `[rbp+0xbc]` (初期値 0・e257c7 で +1 と e257c8 の add が対応)。L=e25618 の counter `-184` は back-edge `e257ac` (`%60` = -184 − 1) で減る。L e25618 に入口判定が無い (B から無条件) |
| 237 | function_e25550 | e25859 → e25a06 / e2586a | 真陽性 | 236 と同じ構造の別の枝。機械語 e25822〜e25847: `[rbp+0xa8]` = G' = [call 12f9ec0([rbp+0xbc])+0x14]、`[rbp+0x34]` = [G'+0x14] − 1。IR B=e25822 の `%72` = call 12f9ec0(-44.1)、`%75` = load [%72+20] = G'、`%78` = load i32 [G'+20] → `stack_var_-180`。L=e2586a の counter `-180` は back-edge e259eb (`%117` = -180 − 1) で減る。L e2586a に入口判定が無い |
| 238 | function_e25ef0 | e25f1c → e25f6f / e25f25 | 真陽性 | 機械語 `r14d` = [[call 12e1a20 +0x14] +0x14] − 1。IR `%0` = call 12e1a20、`%3` = load [%0+20+...]、`%6` = load [%5] で同じ 2 段・幅 (i64→i32)。counter `r14.0` は back-edge `%37` で減る。L e25f25 に入口判定が無い (B から無条件) |
| 239 | function_e26510 | e26541 → e265eb / e2654e | 真陽性 | 機械語 `r13d` = call 12f9ed0 の結果 − 1。IR の counter `r13.0.in` は `%1 + 2^32`、back-edge `%44` で減る。L e2654e に入口判定が無い (B から無条件) |
| 240 | function_e26510 | e2656c → e265d4 / e26575 | 真陽性 | 機械語 `rbx` = [call 12f9ec0(index)+0x14]、`r14d` = [rbx+0x14] − 1。IR `%6` = call 12f9ec0(-80)、`%9` = load [%6+20]、`%12` = load [%11] で G が一致。counter `r14.0` は back-edge `%38` で減る。L e26575 に入口判定が無い (count の判定は要素の判定 `%19` だけ) |

## 4. 訂正の経緯

- 前 run (PR #5760) の 236・237 の保留理由 (「back-edge counter `stack_var_-192`・`-188` の出所が未追跡」) は誤り。`-192`・`-188` は外側ループ (`e257c7`・`e25a06` で減る) の counter で、内側の判定 (jcc の count) とは対応しない。内側の counter は `-184`・`-180` で、機械語の G と同一 SSA で対応する (§3 の 236・237 の行)。
- 外側ループの count (`[rbp+0x2c]`・`[rbp+0x28]`・`-188`・`-192`) は本判定の対象外。内側 jcc の判定は内側 count のみで決まる。

## 5. 範囲

- 判定の入力は work-m11 の IR に限る。現 main の `m11_e2e.sh --full` 出力では未確認。
- count = 0 の実行時到達性は範囲外。
- `m11_ov.c`・`docs/DEFECTS.md`・`guard699/`・`ldmach.py` は変更していない。
