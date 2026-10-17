# REPORT_APPENDIX_6208: 証拠表の行 78 の判定 (#6208・#5845 の子)

REPORT_718 §4o の正本 (#6208 分)。判定は**確定 0 件・保留 1 件** (行 78)。真陽性 0・偽陽性 0。
偽陽性率は母数 288 の判定が終わるまで書かない。

## 1. 結論

- 行 78 (`function_12e21a0`・`12e227e: jg 12e22b7`・機械 `ee167e`) は**保留**。
- 段数差 (機械語 3 段・IR 2 段) は本 run で再確認した。lift 段の欠落か IR 解釈の差かは**未確定**のまま (`REPORT_APPENDIX_5845` と同じ)。同型の既判定は `ldfix/results/manual_verdicts_510.jsonl` の TRUE_DROP (`11d47c0`・`100a3d0`)。
- 残る論点: IR は count2 == 0 でループに入り、機械語は飛ばす。count2 == 0 が**到達するか** (`[Q+0xd34]` の値域と `function_417b70` の副作用) で真陽性か偽陽性かが決まる。到達は未確認のため、保留とする。PM 判断に戻す。

## 2. 入力と再現

- 素材: `fl-win64` (`block00031_PE.bin`) と `work-m11` (`tools/m11/work/boot_final.ll`) を本 run で展開した (`work/` は gitignore 対象)。IR の sha256 は `69c774de…` で一致。
- 本 run で IR の `%46` の SSA 追跡 (§3 の表) と、機械語の rip 相対先の換算 (§3 の cell) を実施した。scan_guard / judge_dump の再実行は本 run では行っていない (前 run の結果を引き継がない。下記の数値は IR と機械語の直接読みだけ)。
- 測定 commit: `b912d309f` (origin/main)。本 PR はコードを変えていない (`git diff b912d309f HEAD -- tools/m11/guard699 tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_dump.py` の出力は 0 行)。
- 素材: `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)、`work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774de…`)。どちらも REPORT_APPENDIX_5845 と一致。使った系統は `69c774de…` (`597757f4…` は素材に無い)。
- 再現 (foreground・各 1 回・rc 0): `scan_guard.py` で strict 288 (4.4 s)、`strict_evidence.py` で TSV 288 行 (13.1 s)、`judge_dump.py <IR> <TSV> 78 78` (rc 0)。
- 逆アセンブル: `objdump -D -b binary -mi386:x86-64`・file offset = VA − 0x400C00。

## 3. 機械語と IR の対応 (行 78)

| 項目 | 機械語 (file offset) | IR (`function_12e21a0`) |
|---|---|---|
| count1 (入口 guard) | `ee1621`〜`ee1638`: `[cell]`→P, `[P]`→Q, `[Q+0xd34]` を `call 0xaa6230` (= `function_ea6e30`) | `%4 = load i32 [cell]` (幅 i32)→`%5` sext→`%8 = load i64 [P+3380]`→`%14 = ea6e30(%8)`→`%16 slt 1` (`dec_label_pc_12e221e`) |
| count2 (ループ前) | `ee1667`〜`ee166e`: 同じ 3 段 (qword) | `%29 = ea6e30([P+3380])` (`dec_label_pc_12e222e`) |
| ループ guard | `ee167c: cmp %esi,%ebx`・`ee167e: jg ee16b7` (esi = count2−1、ebx = 0 始まり)。count2 ≤ 0 のとき `jg` が成立してループを飛ばす | `%46` の SSA 追跡 (下記): `rsi.0` の初期値は `%30 = %29 + 2^32` の下位 32 bit、すなわち `low32(count2)`。`%45 = rsi.0 + 0xffffffff`、`%46 = trunc %45 to i32`、`%47 = icmp eq %46, 0`、`%48 = !%47` で `12e2285` に戻る (`dec_label_pc_12e2285`) |

`%46` の追跡 (IR 直読み):
- count2 = k > 0: `%46` は k−1 から 1 ずつ減り、0 で脱出する (k 回で終わる)。
- count2 = 0: `rsi.0` = `0xffffffff` から始まり、`%46` が 0 になるまで約 2^32 回まわる。IR は count2 == 0 でもループに入る。
- 機械語は `ee167e: jg` で count2 ≤ 0 のときループを飛ばす。

この分岐条件の差 (IR は count2==0 でループに入り、機械語は飛ばす) が、§4 の count==0 の論点の根拠。

- 読み出し段: 機械語は 3 段 (`[cell]`・`[P]`・`[Q+0xd34]`)、IR は 2 段 (`[cell]` を i32 で読み、その値を pointer として `+3380` を読む)。`[P]` の deref が IR で脱落し、cell の幅も i32 に縮んでいる。
- cell の換算: 機械語 `ee15f7: mov 0x3013ca(%rip),%rax` の実効アドレスは RVA `0x11e35c8` (命令 RVA `0xee21f7` (= file `0xee15f7` + 0xc00、`.text` の RawPtr `0x400` → VA `0x1000`) + 長さ 7 + disp `0x3013ca`)。これは IR の `inttoptr (i64 18757064)` = `0x11e35c8` と一致する。VA は `0x15e35c8` (ImageBase `0x400000` 付き)。ee1685 の参照も同じ RVA `0x11e35c8`。
- objdump の `# 0x11e29c8` は、命令を file offset `0xee15f7` のまま計算した値 (`0xee15f7 + 7 + 0x3013ca`)。RVA 換算の命令アドレス (`0xee21f7`) と違う座標で計算しているため、差は `0xc00` (`.text` の file→RVA のずれ)。ImageBase `0x400000` のずれではない。
- よって「同じ cell」は RVA で一致する。機械語が cell を pointer 2 段で読む同型は `ldfix/results/manual_verdicts_510.jsonl` の TRUE_DROP (`11d47c0`・`100a3d0`) と同じ形で、同型の根拠として扱う。
- 呼び出し `ee1644`〜`ee1658` (`0x173c0` = `function_417fc0` → `function_417b70`) の中で、`[Q+0xd34]` を書く経路は未確認。count1 と count2 が機械語で一致するかは、この呼び出しの副作用に依存する。

## 4. 残る論点 (PM 判断)

- 機械語では count2 が 0 のとき `jg` で脱出する (ループを飛ばす)。これは §3 の機械語の事実。
- IR では count2 == 0 でもループに入る (§3 の `%46` 追跡)。この分岐条件の差が、count==0 を論点にする根拠。ただし count2 == 0 が実際に到達するかは、本 run の追跡では決まらない。
- count2 が 0 になるかどうか (`[Q+0xd34]` の要素数の値域と、`function_417b70` が書き換えるか) が決まれば、真陽性 (構造) か偽陽性かが決まる。
- 確認できれば: count==0 が到達 → 真陽性 (構造)。到達しない → 偽陽性。
- 未解決: count2 == 0 の到達 (`[Q+0xd34]` の値域・`function_417b70` の副作用)。行 78 は #6208 の受入条件の一部のため、追跡先は #6208 自身とする (#6208 は open のまま残る。親 #5845 の残件は行 81・82)。子は起票しない・1 件の確認に収まるため。
