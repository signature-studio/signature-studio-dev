# PY-311 (#4225): 書式エンジン 0x43e240 の %.2f・%s・r9 の PE 確定 (部分達成)

親: #3379 (PY-192 系統)。前段: `tools/python/REPORT_PY183.md` §3・§5・§9、`tools/python/REPORT_PY193.md` (PY-192 の %d と 0x43aa10 は REPORT_PY183 §3 に確定済み)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- `%.2f` の呼出し鎖を確定: `0x43ecb5` (精度 0x12 で `0x43fce0`) → `0x43f800` → `0x441380` → `0x440d30` → (`0x40ef40` で 10 のべき乗を掛ける → `0x40c660` = `cvtsd2si` で整数化) → `0x440c10` (10 進の桁を書く)。
- `0x43dd60` の第 4 引数 `r9` は `0x43dd90` → `0x43dde0` (`mov rbx, r9`) → `0x43dc00` の 6 番目の引数 (`[rsp+0x28]`) → `0x43e240` の `[rbp+0x1c8]` (`mov ebx, [rbp+0x1c8]`) に届く。`0x43e240` での値の使われ方 (`0x43e2db`〜) は未確定。
- **未確定**: `%.2f` の丸め規則 (`0x440d30` 内の桁の切上げと `0x40ef40` の換算の数値的意味)、`%s` 経路 (`0x43eb1c`・`0x43eb9e` の出力規則)、`r9` の意味 (0 と 1 の 2 通りの呼出し元の差)、第 5 引数の大域の値。よって `50.00%` の正確な文字列は確定しない (REPORT_PY183 の表示例は推定のまま)。
- probe を 16 件追加 (`pct_fmt_checks()`)。`50.00%` の照合は丸め規則が確定しないため未追加。

## 測定

- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/fl-win64 --wildcards '*block00031_PE.bin'` (exit 0・22,227,016 B・`work/fl-win64/extracted/block00031_PE.bin`)。`$ARTIFACTS_DIR` の実在は `ls` で確認済み (fl-win64.tar.zst 2,324,302,252 B)。
- probe: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py183_probe.py` → 112 件 PASS・`summary: OK`・終了 0 (前回 96 件 + 追加 16 件)。0.103 秒・load average 0.02 (実測。`time` と `uptime`)。
- ネガティブコントロール: VA `0x440ec7` の `call rel32` のオペコード `e8` の次バイトを 1 ビット反転した複製で `FAIL 0x440d30 の桁生成 call 0x440c10 (0x440ec7)`・`summary: 1 FAIL`・終了 1。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `%.2f` の丸め規則 (`0x440d30` の桁の切上げ・`0x40ef40` の換算の数値的意味) | `50.00%` の正確な文字列、表示の桁数 | #4478 [PY-330] |
| `%s` 経路 (`0x43eb1c`・`0x43eb9e`) の出力規則と、`0x43dd60` の r9 の意味・第 5 引数の大域の値 | `%s` を含む表示の確定 | #4481 [PY-331] |
| REPORT_PY183 の `50.00%` 表示例の照合と probe 追加 | 受入 4 | #4478 [PY-330] |
