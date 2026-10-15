# tools/shared/lift/rex 付録 — 元の機械語が落ちる 73 件の切り分け (T-SH-89 / #3588)

測定 commit: `54b2272b0` (`tools/shared/lift/rex/` の最後のコード変更)。以降の差分は本付録と REPORT のみ (差分 0 の証跡は §7)。
既知類型との関係: 該当なし (lift の欠陥を示す所見は無い。元の機械語が入力の構造に合わずに落ちた case を比較から外す)。

## 1. 結論 (1 行)
元の機械語が落ちた 73 件を全件分類した (`other` 0)。未分類だった 37 件は、木の根の key (= key_of(a0)) をオブジェクトとして読む 2 つのアクセサ (31 件) と、成功経路 B の文字列ヒープポインタが 0 (6 件) で説明できる。原因は生成器の入力が REX の実オブジェクト構造を作っていないことで、比較への復帰は未実施 (§6)。受入 3 は「原因の切り分け」と「除外理由の記録」で満たす。

## 2. 方法
- `native_ref.c`: fault 時に ucontext から RIP と GPR 16 個を stderr へ出す。行は `[native] crash case=C fn=F sig=S addr=A rip=P rax=… rbx=… …`。
- `crash_class.py` (分類): 入力 (`cases.bin` の a0・a2・ctx と key_of(a0)、成功経路 B の 5 本の (cap, buf)) と fault 時のレジスタで、上から順に 1 つに分類する。
- `crash_insn.py` (独立検算): 落ちた命令を capstone で逆アセンブルし、メモリオペランドの実効アドレスを fault 時のレジスタから再計算する。非 canonical の番地は si_addr = 0 として比べる。分類の規則 (RIP の定数と key の式) を使わない。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_x64c.sh all` (`ok` が両スクリプトを呼ぶ)。

落ちた命令 (`crash_insn.py` の実測。RVA は rip − 0x30000000):

| rip (RVA) | 命令 | 件数 | 読む先 |
|---|---|---:|---|
| 0x30016160 (0x16160) | `mov rcx, [rcx]` | 24 | ctx = 0 で `[ctx+8]` (ctx-null) |
| 0x30012a50 (0x12a50) | `cmp [rcx+0x688], 0` | 19 | 木の根の key を this とする述語 |
| 0x30012b70 (0x12b70) | `mov rax, [rcx+0x690]` | 23 | 同じく this = key の getter |
| 0x3001f298 (0x1f298) | `mov rax, [rdx]` | 6 | 成功経路 0x12ed0 → 0x1f260 のコピー元 |

## 3. 分類 (73 件・fn 別。`crash_class.py` の実出力)

| 分類 | 件数 (fn=0 / fn=1) | 条件 (レジスタと入力で確認) | 原因 |
|---|---:|---|---|
| ctx-null | 24 (12 / 12) | ctx = 0 で 0x16160 が `[ctx+8]` を読む (addr 0x8) | 既存 (#2870 の分類) |
| key-deref | 28 (11 / 17) | rcx = key、addr = key+0x688 (0x12a50 が 11 件) か key+0x690 (0x12b70 が 17 件) | 木の根の key はアリーナ外の番地で、オブジェクトを指さない |
| key-noncanon | 14 (8 / 6) | rcx = key、key が非 canonical、si_addr = 0 (GP 例外) | 同上。a0 の 64 bit 乱数から key を作ったため |
| succ-null-src | 6 (6 / 0) | 0x1f298 で rdx = 0。r11 (dest) − a2 = 0x300 (4 本目 3 件: `[B+0x88]` = 0) または 0x400 (5 本目 3 件: `[B+0xb0]` = 0)。どちらも cap ≥ 0x10 のヒープ経路 | 成功経路 B の未指定フィールド (生成器が arena の 0 qword を残した) |
| timeout | 1 (0 / 1) | SIGALRM | 既存 |
| out-overrun / other | 0 / 0 | — | — |

- 未分類 37 件の内訳: key-deref は 0x12a50 の 11 件 (既存分類) を除く 17 件 (0x12b70・+0x690)、key-noncanon 14 件 (0x12a50 の 8 件・0x12b70 の 6 件)、succ-null-src 6 件。計 37 件 (fn=0 が 14、fn=1 が 23。元の分類と一致)。
- key 由来の 42 件 (key-deref 28 + key-noncanon 14) は全件 rcx = key、key はアリーナ外 (`[key+off]` の番地が未マップか非 canonical)。canonical 28 件・非 canonical 14 件。

## 4. 実測 (測定 commit `54b2272b0`・`lift_x64c.sh all` を n = 3)

| 項目 | 値 |
|---|---|
| `all` の wall (`time`) / rc | 10.40–10.62 s / 0 (3 回) |
| `ok` の elapsed | 2–3 s |
| load (1 分値、開始 → 終了) | 0.30–0.50 → 0.35–0.57 (`nproc` = 4) |
| 本検査 `ok` | 248 件・比較 175・一致 175・不一致 0・除外 73 (3 回とも) |
| `crash_class.py` | 73 件 → 上の 6 分類 (`other` 0) |
| `crash_insn.py` | rip の有る 72 件: 実効アドレスの再計算と si_addr が一致 72・不一致 0 (ALRM 1 件は rip 無し) |
| ネガコン NC1 (0x12b70 の rcx を +1) | `crash_class` の `other` 23 件 (期待 23)。`crash_insn` の不一致 17 件 (残り 6 件は非 canonical で一致) → 両方検出 |
| ネガコン NC2 (0x1f298 の rdx を 0 → 1) | `crash_class` の `other` 6 件・`crash_insn` の不一致 6 件 → 両方検出 |
| `neg-cmp` / `neg-ctx` / `neg-owner` | 期待どおり FAIL (ALL OK) |
| wasm 側の trap | `traps=0` (248 件。除外 73 件も wasm は実行するが、比較しないので結果は見ない) |

NC1・NC2 は測定 commit の stderr を一時コピーして実行した (リポジトリの生成物は変えていない)。

## 5. 判断 (受入 3)
- 除外 73 件は、元の機械語が定義された結果を返さない (fault / 時間切れ)。比較対象から外すのは既存の方針どおり (REPORT §7.3)。
- 原因は入力側。元の機械語が自分で不正な番地を読んでいるので、lift の誤りの証拠ではない。ただし wasm は同じ入力で trap しない (`traps=0`)。wasm の結果が正しいかは、この 73 件では確かめられない。
- 比較へ戻す作業 (生成器の変更) は本 PR では行わない。key 由来 42 件は木の根の key を有効なオブジェクトへ向ける規則の追加で、既存 175 件の入力分布 (seed 2733) も変わる。成功経路 6 件は #3587 (T-SH-88) の入力構成と同じ作業。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 成功経路 6 件 (B の未指定フィールド) の比較への復帰 | 比較数 175/248。#3587 の受入 2 (成功経路の入力構成) と同じ作業 | #3587 (T-SH-88) |
| key 由来 42 件 (木の根の key を有効なオブジェクトへ向ける生成規則) の比較への復帰。既存 175 件の入力分布も変わる | 比較数 175/248 | 未起票 (PM 判断。#3587 の範囲外) |

## 7. 測定後のコード差分 (差分 0 の証跡)
`git diff 54b2272b0 HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (本付録と REPORT は md のみ。HEAD = 測定 commit に後続する文書 commit)。
