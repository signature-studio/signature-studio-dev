# REPORT_APPENDIX_5845: strict 候補の証拠表 行 78・81・82 の保留 3 件の判定理由 (#5845)

REPORT_718 §4o の正本 (#5845 分)。親 #5389 の保留 3 件 (78・81・82) を、機械語と IR の対応づけまで追って整理した。
判定は**確定 0 件・保留 3 件**。真陽性 0・偽陽性 0。偽陽性率は母数 288 の判定が終わるまで書かない。

## 1. 結論

- 78: 機械語の count の源と IR の count の源は**読み出し段数と幅が一致しない** (機械語 3 回読み・qword、IR 2 回読み・i32/i64)。lift 段の欠陥か IR 解釈の誤りかは未確定。PM 判断 (R7 既定) により保留。
- 81: count の源 (`[arg1+0x818]+20*i` の dword) は機械語と IR で**同じ式**と確認した (§3)。ただし機械語の入口 jcc (`count-1 < 0` で脱出) に対応する判定は IR に無い。count==0 が到達するかは未確認のため、真陽性 (構造) とは確定しない。
- 82: 機械語の count は間接呼び出し `call *0x28(%rax)` の戻り値。IR の直接呼び出し `function_43aae0` は 3 引数を渡すが、定義は 2 引数で、署名が合わない。呼び出し先の同一性を IR から確認できない。

## 2. 入力と再現

- 測定 commit: `f82959016` (origin/main)。本 PR はコードを変えていない (`tools/m11/guard699`・`trap_triage/strict_evidence.py`・`trap_triage/judge_dump.py` の差分 0 行)。
- 素材: `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)、`work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774de…`)。どちらも前 run と一致。`597757f4…` の系統は素材に無く未使用。
- 再現 (foreground・各 1 回): `scan_guard.py` で strict 288、`strict_evidence.py` で TSV 288 行 (ヘッダ除く 288)。`judge_dump.py <IR> <TSV> 78 82` で 78・81・82 の IR 本文を取得。
- 機械語の照合は `objdump -D -b binary -mi386:x86-64` で PE の file offset から逆アセンブルした (file offset = VA − 0x400C00)。逆アセンブルの表示アドレス (`ee167e`・`f104a1` など) は file offset。`call 0xaa6230` の宛先は file offset `0xaa6230` = VA `0xea6e30` で、IR の `function_ea6e30` (定義あり) に対応する。

## 3. 件ごとの判定

| 行 | 関数 | jcc | 結果 | 理由 |
|---|---|---|---|---|
| 78 | function_12e21a0 | `12e227e: jg 12e22b7` (機械 `ee167e`) | 保留 (段数・幅の不一致) | 機械語は `mov cell,%rax`・`mov (%rax),%rax`・`mov 0xd34(%rax),%rcx` で count の引数を読む。cell → P → Q → `[Q+0xd34]` の 3 回読み (qword)。IR は `%31 = load i32 [cell]` → `%33 = P+3380` → `%35 = load i64 [P+0xd34]` の 2 回読みで、機械語より deref が 1 段少ない。IR の `%30` (= `ea6e30([P+0xd34])` + 2^32) が `%46` の源になる。段数不一致の疑い (lift 段) は残る。 |
| 81 | function_1310300 | `13103e8: jg 1310460` (機械 `f0f7e8`) | 保留 (入口判定が IR に無い) | count の源は一致: 機械 `f0f7d4〜f0f7db` (`[arg1+0x818]` に `20*rax` を足して dword を読み `-1`) と IR `%57 = 5*rax`・`%58 = 20*rax`・`%59 = base+%58`・`%61 = load i32` が同じ式。機械語は `sub $1,%r14d` の後に `cmp %r14d` の入口 jcc (`f0f7e8`) を持ち、count==0 のとき脱出する。IR の `dec_label_pc_13103f1` の icmp 連鎖 (`%78`〜`%91`) は `[%68+12]` の i16 値の比較 (機械 `f0f81a`・`f0f825`) で、この入口判定ではない。IR の `%r14.0` の初期値は count (`%62`、未減算) で、back edge `%102` (`%100 = r14-1` の 0 判定) だけが終了を決める。count==0 が到達するかは未確認のため、真陽性 (構造) とは確定しない。 |
| 82 | function_1311050 | `13110b2: jg 1311118` (機械 `f104b2`) | 保留 (呼び出し先の同一性が未確認) | 機械語の count は `f104a1: call *0x28(%rax)` の戻り値。`rcx` (this) だけを設定して呼ぶ。IR は `%13 = call i64 @function_43aae0(%.reload, ptr @ce0n11_function_1311050, i64 %rbx)` と直接呼び、3 引数を渡すが、定義 `function_43aae0(i64, i32)` は 2 引数。引数の数が合わないため、IR の呼び出し先が機械語の間接呼び出し先と同じとは言えない (署名不一致・REPORT_718 §11 の sigfix 類)。間接先 (vtable slot `0x28`) の実体は IR から確認できない。 |

## 4. 機構の型

- 78: 機械語の count 源は cell の 3 段 deref (qword)、IR は 2 段 (i32 + i64)。83・84 (REPORT_APPENDIX_5389 §4) と同じ「読み出し段数・幅の差」の型。`ldfix/REPORT_2794.md` の類型かは未確認。
- 81: count 源は一致。差は機械語の入口判定 (count==0 での脱出) が IR に無いこと。do-while 化の欠陥 (lift 段) の候補。count==0 が到達すれば真陽性 (構造) になり得る。
- 82: 間接呼び出しの署名と IR の直接呼び出しの署名が不一致。call 先の同一性が取れないため、判定を進められない。

## 5. 未解決

- 78: 機械語の 3 段 deref と IR の 2 段の差が lift 段か IR 解釈かの判断 (PM・R7)。
- 81: count==0 が到達するか (`[arg1+0x818]` の要素数と、入口へ入る条件 `%22`・`%52`) の確認。確認できれば真陽性 (構造) か保留かが決まる。
- 82: vtable slot `0x28` の実体 (`[0x11E07B8]→+0xaf0→+0x4f8` の型) の特定。
- 偽陽性率は母数 288 の判定が終わるまで書かない。
