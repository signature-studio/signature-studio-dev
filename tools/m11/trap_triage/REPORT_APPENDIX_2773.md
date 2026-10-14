# REPORT_APPENDIX_2773 — REPORT_679 §10 の全文 (#2773 2 回目, 親 #739)

本文は `REPORT_679.md` §10 (要約)。ここは §10 の全文 (本 PR で新規に書いた全文。既存記述の分割移動ではない)。

## 10. 根本原因: 4fa210 の件数 0 ガードの脱落 (D19 同型) (#2773 2 回目, 親 #739)

既知類型との関係: **D19** (`docs/DEFECTS.md` D19・件数 0 のループで本体が 1 回以上実行される。ループ先頭の `cmp; jg exit` が脱落し do-while 形になる)。
修復は `guard4fa210/m11_guard4fa210.py` (D19 の `guard699` と同型の IR pass)。

### 10-1 結論 (先出し)

1. **終了条件 (周回が止まらない理由・推定)**: `4fa210` は件数 `r14 = u32 [p+16]` の線形探索。原典 `4fa23c`〜`4fa23f` に件数 0 のガード
   (`cmp esi, r14d; jg 0x4fa28e` → `xor ebx,ebx` で戻り値 0) がある。lift IR (`dec_label_pc_4fa210`) はこのガードが無く、入口から本体へ直行する。
   件数 0 では本体の 1 回目で範囲外 (`idx < len` が不成立) になり `47a250` を呼ぶ。減算 `r14 - 1` は 0 から `0xFFFFFFFF` へ回り、約 2^32 回の周回に入る。
   以上は IR と原典からの推定。周回数の計装による実測は未実施 (REPORT_679 §3 は周回数未計測と明記。#739 の周回数 probe も入口回数のみで未達)。
2. **例外 object が解放されない理由 (推定。FreeMem 0 は #513 の実測)**: `47a250` は原典では `411e60` (raise) を呼んで戻らない。lift では戻って続行するため、
   周回のたびに `448d40` (Exception.Create) → ClassCreate → GetMem で object を作ると推定され、どれも解放されない (FreeMem 0)。原典では raise が呼出し元の
   例外経路へ unwind するので、周回は起きない。
3. **修復**: 入口に `icmp eq i32 %9, 0` → `ret i64 0` を復元する (§10-4)。修復の効果 (構成 A の halt0 の減少・既定構成の kind 不変) は §10-2 の表が正本。
4. **未解決**: no-return の raise が戻り値として扱われる点 (既知類型に無い。§10-5)。修復後も unit 101 に oob が残る理由。

### 10-2 実測 (survey の集計、n=1)

測定基準は各 commit の `unit101_2773.sh` (`git archive`・IR 再生成・build・unit survey)。1 構成 57〜64 s (4 コア runner、直列)。

| 構成 | 測定 commit | 4fa210 ガード | unit 101 kind (0x41037d) | halt0 unit | ok / oob / miss / other |
|---|---|---|---|--:|---|
| A: m11_win.c を 035274be 版 (trace 3 行なし), ON | 04fafae6 + m11_win.c | なし (ネガコン) | halt0 (23,053,163) | 55 | 827 / 11 / 48 / 0 |
| A + 修復, ON | 04fafae6 + 修復 pass (scratch) | あり | oob (2) | 6 | 864 / 23 / 48 / 0 |
| G: 04fafae6 そのまま, ON | 04fafae6 | なし | oob (1) | 8 | 864 / 21 / 48 / 0 |
| main 相当, ON | 875eba29 | なし | oob (1) | 7 | 867 / 19 / 47 / 1 |
| 修復 commit, ON | 7a0989c4 | あり | oob (1) | 7 | 867 / 19 / 47 / 1 |
| main 相当, OFF | 875eba29 | なし | ok (0x41032e 1) | 7 | 872 / 14 / 47 / 1 |
| 修復 commit, OFF | 7a0989c4 | あり | ok (0x41032e 1) | 7 | 872 / 14 / 47 / 1 |

- ON・OFF の定義: ON = `M11_OV_CLASSCREATE=1` (`unit101_2773.sh` の既定)、OFF = `M11_OV_CLASSCREATE=0` (`m11_build.sh` の既定。REPORT_679 §8 の手順)。本付録の「既定」は build の既定 (OFF) を指す。
- ON で 875eba29 と 7a0989c4 の全 unit を比べると、kind は 0 unit が異なる (`frames` のパス文字列を除く)。OFF も同じく 0 unit が異なる。
- 鮮度 (測定後の差分): `git diff 7a0989c4 HEAD -- tools/m11/m11_build.sh tools/m11/guard4fa210 tools/m11/m11_ov.c tools/m11/m11_win.c tools/m11/m11_post.py tools/shared` は 0 行。`tools/m11/trap_triage/unit101_2773.sh` は 1 行 (`M11_OV_CLASSCREATE=1` → `M11_OV_CLASSCREATE=${OVC:-1}`)。既定 1 は測定時の固定値 1 と同値で、測定値は変わらない。
- 「A」は 04fafae6 の `m11_win.c` だけを 035274be の版に戻した構成 (§9 と同じ)。
- 「A + 修復」は 04fafae6 の tree に修復 pass と build の 3 行を当てた scratch 木 (コミットなし)。`unit101_2773.sh` の commit 指定では再現できない。当てた内容は pass の本体と `m11_build.sh` の guard699 直後の 3 行 (本 PR の `tools/m11/m11_build.sh` と同じ)。HEAD (875eba29) では同じ差し替えをしても unit 101 は oob のままで、halt0 は再現しない (§10-6)。
- 修復 pass の検査 (実 IR): on → `changed=True`・`cond_after=guarded`、もう一度 on → `changed=False` (冪等)、off → 元の IR と `cmp` で一致 (双方向)。

### 10-3 原典との突合 (1 コマンド)

```sh
cd tools/m11/trap_triage && FL_WIN64_DIR=<fl-win64 の展開先> uv run --with capstone --with pefile python3 disasm_fn.py 4fa210 47a250
```

- `4fa210`: `4fa232 mov r14d,[rcx+0x10]` → `4fa236 sub r14d,1` → `4fa23c cmp esi,r14d` → `4fa23f jg 0x4fa28e` (件数 0 で成立し、`4fa28f xor ebx,ebx` で戻り値 0)。
  `4fa289 test r14d,r14d; jne 4fa248` が周回の終了条件。件数 0 のとき `r14d = 0xFFFFFFFF` となり、`jne` が成立し続ける。
- `47a250`: `47a28f call 448d40` (Exception.Create) → `47a297 call 411e60` (raise) → `47a2a1 call 412d60` (後始末) → `ret`。
- IR (`dec_label_pc_4fa210`): 入口ブロックは `store …; br label %dec_label_pc_4fa248` で終わり、ガードが無い。`4fa25d` の `call 47a250` の後は `br` で続行する。
- ガードの同値 (修復の条件 `icmp eq i32 %9, 0` の根拠): 原典の `cmp esi, r14d; jg` は esi = 0 (IR のエントリ `store i64 0, ptr %rsi.0.reg2mem`)、r14d = count-1 (符号付き 32 bit) で、`0 > count-1` は count == 0 のほか count ≥ 2^31+1 でも成立する。修復の `%9` はエントリの `load i32 [list+16]` (= count) なので、count == 0 だけを見る。count ≥ 2^31+1 は件数として想定外の大きさで、本修復の対象外。ガードはエントリでのみ評価される (ループ後は `dec_label_pc_4fa282.dec_label_pc_4fa248_crit_edge` が rsi を +1 して 4fa248 へ戻り、ガードを通らない)。IR の突合は `work-m11` の `boot_final.ll` で行った。

### 10-4 修復 (`tools/m11/guard4fa210/m11_guard4fa210.py`)

- 入口ブロックの末尾の `br` を次の形に置換する (件数が 0 なら戻り値 0)。`%g4fa = icmp eq i32 %9, 0` → `br i1 %g4fa, label %dec_label_pc_4fa210_g4fa, label %dec_label_pc_4fa248`、ガード辺は `ret i64 0`。
- `m11_build.sh` の guard699 の直後に配線 (`M11_GUARD4FA210=off` で脱落状態に戻す)。想定形でなければ exit 1 (fail-closed)。
- ネガコン: §10-2 の A 構成の 1 行目 (修復なし) と 2 行目 (修復あり) を比べる。同じ構成で pass の有無だけが違う。

### 10-5 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| no-return の raise (`47a250` → `411e60`) が戻り値として lift され、後続が続行する。既知類型 (DEFECTS.md) に該当項が無い | 件数 0 以外の例外経路でも同型の周回と object 未解放が起きうる。FreeMem 0 の原因 (§10-1 の 2) はこの点 | #739 (親) へ提案。新類型の登録は PM 判断 |
| 修復後の A 構成でも unit 101 に oob が残る (件数 0 の経路の残り。件数は §10-2) | 1 unit が trap で止まる。残りの原因は未切り分け | #739 |
| 修復後の A 構成で halt0 unit が残る (件数は §10-2) | 本件の範囲外 | #739 |

### 10-6 §9 の仮説の訂正

- §9-1 の「wasm の関数 index がずれる」仮説は**否定**した。E1: A 構成に分岐しない import を 1 つ足す (`GetVersionExW` の `volatile` ガードの中) と、halt0 のまま (23,053,163)。
  G (import 1 つ・MessageBoxA が呼ぶ) と E1 (import 1 つ・GetVersionExW が呼ぶ) は defined 関数の index 割り当てが同じはずだが、結果は oob と halt0 で異なる。
- HEAD (875eba29) では A 構成でも unit 101 は oob で、§9 の halt0 は再現しない。halt0 の出る条件は 04fafae6 時点の周辺コードに依っていた。
  trace 3 行で oob と halt0 が分かれる機構は未確定のまま。ただし halt0 の本体は §10-1 の周回であることが修復で確かめられた。
