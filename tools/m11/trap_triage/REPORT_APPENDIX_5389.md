# REPORT_APPENDIX_5389: strict 候補の証拠表 行 78・81〜84 の保留 5 件の判定理由 (#5389)

REPORT_718 §4o の正本。親 #4886 (分割元)・前 run の停止報告 (#5389 コメント) の表を、判定理由つきで整理し直したもの。

## 1. 結論

- 母数 5 (証拠表 行 78・81・82・83・84)。真陽性 0・偽陽性 0・保留 5。
- 5 件とも保留のまま確定しない。理由は件ごとに異なる (§3)。
- 件 83・84 は機械語と IR で段数・幅が一致しない。lift 段の欠陥か、IR 側の解釈の誤りかは、本 issue では確定しない。PM 判断 (`oc-pm-decision` R7 既定案): 判定は保留のまま、lift の挙動と既存の数値は変えず、「未確定」と明記する (`.github/prompts/pm.md` の R7 ①〜④ に従う)。
- 偽陽性率は母数 288 の判定が終わるまで書かない。

## 2. 入力と再現

- **本 run の素材**: `fl-win64` と `work-m11` (ともに素材ディレクトリ `ARTIFACTS_DIR` に実在)。`work-m11` のアーカイブ内の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`) を `tools/m11/work/boot_final.ll` に展開して照合した (`tools/m11/work/` は gitignore)。
- PE: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B・sha256 `b2c64da4…`)。本 run で展開して逆アセンブルした。
- 測定 commit: `e5261de58` (origin/main)。本 PR はコードを変えていない。`git diff e5261de58 HEAD -- tools/m11/guard699 tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_dump.py` = 0 行。
- 再実行 (本 run・foreground・各 1 回。commit は `6ec088555` 系統で、コードは `e5261de58` と同一): `scan_guard.py --report` 4.45 s で strict 288 (dropped 1380・jcc 25618)。`strict_evidence.py --out` 14.7 s で TSV 288 行 (ヘッダ除く 288 件)。`judge_dump.py <IR> <TSV> 78 84` 0.2 s で 78・81〜84 の IR 本文を出力 (rc 0)。strict 288 と TSV 288 行は REPORT_718 §4a と一致する。
- 機械語の照合: `objdump -D -b binary -mi386:x86-64` で PE の `VA - 0x400C00` (= ImageBase 0x400000 + 0x1000 − 0x400 の差) から切り出した (本 run・§3b)。

## 3. 件ごとの判定

| 行 | 関数 | jcc・脱出先 | 判定 | 理由 |
|---|---|---|---|---|
| 78 | function_12e21a0 | `12e227e: jg 12e22b7` | 保留 | 機械語は count を 2 回読む (逆アセンブル確認・§3b)。1 回目の入口 guard `12e2228: jle 12e22d2` と 2 回目の `12e227e: jg 12e22b7` の間に `call 417fc0`。IR 側は jcc 近傍の `%47 = icmp eq i32 %46, 0` (`lh=12e2285`・`blk=12e222e`) で、`%46` の SSA を遡って機械語の count と同じ値かは未確認。 |
| 81 | function_1310300 | `13103e8: jg 1310460` | 保留 | 機械語は `[(%rsp)+0x818]+20*rax` の dword を読んで `-1` (`13103db`〜`13103df`・逆アセンブル確認)。IR 側は `%59 = add i64 %58, %27` (`%58 = 4*(20*rax 由来)`・`%27 = load i64 [arg1+2072]` の先頭ポインタ) で、`%61 = load i32 [%59]` が count 相当。jcc 左辺 (`%78`〜`%91` の icmp 連鎖) との SSA 対応は未追跡。 |
| 82 | function_1311050 | `13110b2: jg 1311118` | 保留 | 機械語の count は間接呼び出し `13110a1: call *0x28(%rax)` の戻り値 (逆アセンブル確認・§3b)。IR 側は `%13 = call i64 @function_43aae0(...)` (`ce0n11_function_1311050` 付き) の戻り値が `%14 = icmp sle i64 %13, %rsi.0.reload` 等に使われる。機械語の jcc の被演算子 `ebx`・`r13d` との同一性は未追跡。`arg+2800` 起点の load 連鎖は別の値で、同じ源とは言えない。 |
| 83 | function_13114d0 | `1311555: jg 13115b7` | 保留 (読み出し回数・幅の不一致) | 機械語は読み出し 3 回 (逆アセンブル確認): `131153f: mov 0x2d0cd2(%rip),%rcx` で RIP 相対 cell `0x15E2218` を qword で読み、`1311546: mov (%rcx),%rcx` でその先を qword で読み、`1311549: mov 0x10(%rcx),%esi` で `+0x10` を dword で読む。IR 側 (`dec_label_pc_131153d`・行 98340 付近) は読み出し 2 回: `%23 = load i32 inttoptr (i64 18752024)` (= `0x11E2218`・ImageBase 分 `0x400000` のずれで対応) で cell を i32 で読み → `%25 = add nsw i64 %24, 16` → `%27 = load i32 [%26]` で `+16` を i32 で読む。読み出し回数 (3 回と 2 回) と cell の幅 (qword と i32) が異なる。この差が lift 段の欠陥か、IR 解釈の誤りかは未確定。 |
| 84 | function_13114d0 | `1311737: jg 1311784` | 保留 (読み出し回数の不一致) | 機械語は読み出し 3 回 (逆アセンブル確認): `1311721: mov 0x2cf6d8(%rip),%rcx` で RIP 相対 cell `0x15E0E00` を qword で読み、`1311728: mov (%rcx),%rcx` でその先を qword で読み、`131172b: mov 0x10(%rcx),%esi` で `+0x10` を dword で読む。IR 側 (行 98500 付近) は読み出し 2 回: `%129 = load i64 inttoptr (i64 18746880)` (= `0x11E0E00`) で cell を i64 で読み → `%130 = add i64 %129, 16` → `%132 = load i32` で `+16` を i32 で読む。83 と同じ読み出し回数の差。jcc 近傍 (`lh=131173e`) の `%158 = icmp eq i32 %157, 0` と `%157` の SSA 対応は未追跡。差の扱いは 83 と同じく未確定。 |

## 3b. 機械語の照合 (本 run・fl-win64 の `block00031_PE.bin`)

jcc の VA と飛び先は逆アセンブル結果と一致した。`call` 先と RIP 相対先は、ファイル内の位置から計算した VA。

| 項目 | 機械語 (VA) | 確認 |
|---|---|---|
| 78 入口 guard | `12e2228: jle 12e22d2` | 一致 |
| 78 2 回目 | `12e227e: jg 12e22b7` | 一致 |
| 78 間の call | `12e2258: call 417fc0` (ファイル位置 `ee1658`) | 一致 |
| 81 | `13103e8: jg 1310460`・count は `13103db`〜`13103df` | 一致 |
| 82 | `13110a1: call *0x28(%rax)`・`13110b2: jg 1311118` | 一致 |
| 83 | `1311555: jg 13115b7`・`131153f: mov 0x2d0cd2(%rip)` → RIP 先 `15E2218`・`1311549: mov 0x10(%rcx),%esi` | 一致 |
| 84 | `1311737: jg 1311784`・`1311721: mov 0x2cf6d8(%rip)` → RIP 先 `15E0E00`・`131172b: mov 0x10(%rcx),%esi` | 一致 |

## 4. 機構の型

- 読み出し回数・幅の不一致 (83): 機械語は読み出し 3 回 (cell の qword → その先の qword (`mov (%rcx),%rcx`) → `+0x10` の dword)。IR は読み出し 2 回 (cell の i32 → `+16` の i32)。読み出し回数と幅の差が lift 段の欠陥か IR 解釈の誤りかは未確定。`ldfix/REPORT_2794.md` の類型と同型かは未確認。
- 84: 機械語は 83 と同じ読み出し 3 回 (cell の qword → その先の qword → `+0x10` の dword)。IR は読み出し 2 回 (cell の i64 → `+16` の i32)。RIP 先 `0x11E0E00` と IR の `load i64 inttoptr (i64 18746880)` は同じ先頭を指す。jcc 近傍の SSA 対応は未追跡で、83 と同じく未確定。
- SSA 同一性の未確定 (78・81): count の源は同じ見込みだが、jcc の左辺と IR の icmp の値の対応を追っていない。
- 間接呼び出し (82): count が `call *0x28(%rax)` の戻り値。IR 側は `function_43aae0` の戻り値を使うが、機械語の被演算子との同一性は未追跡。

## 5. 未解決

- 行 78・81・82: jcc 左辺と IR の SSA 対応 (78 は count 2 回読みの同一性) を追う。IR は `tools/m11/work/boot_final.ll` で照合可能 (本 run で照合済みの範囲は §3)。
- 行 83・84: 段数・幅の不一致が lift 段の欠陥か、IR 側の解釈の誤りか。PM 判断 (`oc-pm-decision` R7) により保留のまま「未確定」と明記する (§1)。
