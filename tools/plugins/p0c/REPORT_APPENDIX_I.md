# tools/plugins/p0c REPORT 付録 I (§21)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本節は #3439 (P0c-21) の実測。
> 前提の経緯は `REPORT_APPENDIX_E.md` §14.3 (0x5e12b0 の初出) と `REPORT_APPENDIX_H.md` §18.6・§19.3 (未解決の起票先)。

## 21. #3439: 0x5e12b0 の ucomiss 被演算子・flags を接続し census に入れる (測定 commit `14731ce2c`)

### 21.1 原因 (機械語と RetDec IR の突合)

- 機械語 (VA 0x5e12b0): `ucomiss xmm0, xmm1` → `ja` → `movaps xmm0, xmm1` → `ret`。戻り値は xmm0 で、意味は `(xmm0 > xmm1) ? xmm0 : xmm1` (非順序は xmm1)。
- RetDec の raw IR (`work/k80.final.ll`) は `call void @__asm_ucomiss(i128 %5, i128 %4)` を残すが、被演算子は `xor i128 0, 0` の placeholder、flags (CF/ZF) は `xor i1 0, 0` の placeholder で、`or i1 %6, %7` が分岐に使われる。
  - (1) `k80_argfix.py` [C] は `=\s*call` の形だけを helper として数えるため、戻り値の無い `call void @__asm_ucomiss` が接続先から外れていた。
  - (2) flags の placeholder を接続する pass が無かった。
- 結果、関数は引数ゼロ (`define i64 @function_5e12b0()`) になり、k80abi の status は abi-mismatch (未割当 xmm0・xmm1)。

### 21.2 修正 (関数名の指定なしの一般 pass)

- `k80_argfix.py` [C]: 戻り値の無い `call void @__asm_*` も被演算子の接続先にする。`K80_NO_VOIDHELPER=1` で外せる。
- `k80_argfix.py` [D] `fix_ucomi_flags` (新規): `call void @__asm_(u)comis(s|d)(i128 A, i128 B)` の後の同じ block にある `or i1 %F1, %F2` を探し、F1 と F2 が placeholder で他で使われないときだけ、
  - `CF = fcmp ult a, b` (a<b または非順序)、`ZF = fcmp ueq a, b` (a==b または非順序) に接続する。
  - `CF|ZF` は `a<=b または非順序` で、jbe/ja の判定値。RetDec の分岐の極性には依存しない。
  - A/B が未接続 (`xor i128 0, 0`) のとき、placeholder が or 以外で使われるときは触らない (fail-closed)。`K80_NO_UCOMI_FLAGS=1` で外せる。
- `tools/shared/lift/libkio/kio_fix.py` の `xmm_fix` は DSM の jcc 極性に依存する。p0c の lift には DSM が無いため流用せず、同じ考え方を placeholder の形で書いた。
- 修復後 IR: 引数 `(i64 %in.xmm1.bits, i64 %in.xmm0.bits)`、`%8 = or i1 %ucf.K.cf, %ucf.K.zf`。`llvm-as` 通過。

### 21.3 検証 (測定 commit `14731ce2c`・origin/main 起点の worktree `ws-3439`・`work/` 無しから)

素材: `fl-win64` (`extracted/block18983_PE.bin`)。RetDec は `[RETDEC]` (`lift_ranges.sh` の既定。`docs/REFERENCES.md`)。llvm-as・clang は llvm-18 を PATH に置いた。

| コマンド | rc | 所要 | 開始 load (1 分値) | 結果 |
|---|---:|---:|---:|---|
| `kernel_table.py` → 80 kernel の `lift_ranges.sh` (`PLUG_CANON_ALLOCA=1`) | 0 | 3.96 s | 0.44 | `k80.final.ll` 80 defines |
| `p0c4_abi_e2e.py 2000` | 0 | 29.1 s | 0.44 | `run=68 ok=68 sig11=0`・`[5b]` 戻り値 2001/2001 一致・gate `0x5e12b0 ok かつ buf_diff=0` 通過 |
| `p0c2_e2e.sh 2000` | 0 | 52.6 s | 0.56 | `== p0c2 e2e OK ==` |
| `p0c3_e2e.sh 2000` | 0 | 51.6 s | 0.79 | `== p0c3 e2e OK (構造修復 3 kernel bit-exact + 回帰 0) ==` |

- 基準 (修正前・同じ origin/main `730320c46` の detached worktree で同手順): `run=67 ok=67 sig11=0`・`argfix helper_xmm=16`。
- 修正前後の差: `helper_xmm 16 → 18`。`helper_xmm_fixed` は新しい xmm 引数を追加したときだけ +1 する (`k80_argfix.py` の `fix_helper_operand_xmm`。同じ引数への接続は `continue` で数えない)。0x5e12b0 で追加された引数は `%in.xmm0.bits`・`%in.xmm1.bits` の 2 本で、+2 はその 2 本に対応する (movaps は新しい引数を増やさない)。`p0c4` の CSV 行を比べると、追加は 0x5e12b0 の 1 行だけで、他 67 kernel の ret_diff・buf_diff・status は変わらない。

**census の buf_diff は 0x5e12b0 では自明に 0 になる。** この kernel は出力バッファに書かず、戻り値 (xmm0) は k80_diff が比べる rax ではないため、flags の正しさは census からは見えない。そこで `ucomi_ret_check.py` (新規) を追加した。機械語を mmap(RWX) に置いて ctypes で呼んだ戻り値と、修復後 IR を clang で実行した戻り値 (`select i1 <分岐条件>, xmm1, xmm0`) を bit 比較する。入力は特殊値 121 組 (±0・±inf・NaN・非正規化数の組合せ)・乱数 1879 組・末尾 1 組の計 2001 組。native の機械語は `0f2ec177030f29c8c3` (ucomiss・ja +3・movaps・ret)。

### 21.4 負論対照 (pass を外すと FAIL)

| 対照 | 操作 | 結果 |
|---|---|---|
| (a) [C] void helper | `K80_NO_VOIDHELPER=1 python3 p0c4_abi_e2e.py 2000` | `[FAIL] function_5e12b0 の引数が xmm0/xmm1 の 2 本になっていない: []`・rc 1 (`[5b]` で停止) |
| (b) [D] ucomiss flags | `K80_NO_UCOMI_FLAGS=1 python3 p0c4_abi_e2e.py 2000` | `mismatch=1014` / 2001 (例: a=0x0, b=0x3f800000 で native 0x3f800000・IR 0x0)・rc 1 |

(b) は census の buf_diff では検出されない (21.3 のとおり)。戻り値試験だけが検出する。

### 21.5 DEFECTS.md 行案 (PM 判断・WORKFLOW §5 により直接編集しない)

| 仮 ID | 層 | 症状 (silent) | 根本原因 | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|
| (案) ucomiss の被演算子・flags の落ち | fe | 2 引数の fp 比較の結果が常に a (または常に b) になる。引数ゼロの IR で ABI 不一致 | RetDec raw lift が ucomiss の被演算子を戻り値の無い call の placeholder に残し、flags を `xor i1 0,0` に落とす | IR の `call void @__asm_ucomiss` の被演算子が `xor i128 0,0`、分岐条件が placeholder だけ | `fix_ucomi_flags` (CF/ZF → fcmp ult/ueq) と [C] の void 接続 |

### 21.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec raw lift のどの段が被演算子・flags を落とすかは未特定 (一般 pass で補った) | 同型の誤りを他 kernel で自動検出できない | #3281 [P0c-20] |
| xmm 戻り値 kernel の census 判定は未汎用化 (k80_diff は rax のみ比べる。0x5e12b0 だけ `ucomi_ret_check.py` で検証) | xmm 戻り値の他 kernel は戻り値を検証しない | #3513 [P0c-22] |
| `or i1 CF,ZF` 以外の jcc (jb・je・jp など) の flags は未接続 (fail-closed) | 現 census に該当 kernel は無い | #3281 [P0c-20] (同 issue へのコメントで記録) |

### 21.7 検証範囲

- 測定 commit: `14731ce2c` (測定に使ったコード)。その後の commit は REPORT・DOC_MAP と、`p0c4_abi_e2e.py` のコメント 1 行 (`REPORT_APPENDIX_H §20` → `REPORT_APPENDIX_I §21`) だけ。
- `git diff 14731ce2c HEAD -- tools/plugins/p0c ':!*REPORT*'` の出力: `p0c4_abi_e2e.py` の 199 行目のコメント 1 行の `-`/`+` 組のみ。
- 同ファイルを `ast.dump` で比べると、14731ce2c 版と HEAD 版は一致 (コメントは AST に入らない)。実行されるコードは測定時と同じで、測定値は現 HEAD に有効 (WORKFLOW §6)。
- 未実行: `p0c_e2e.sh` の全段 (kernel_matrix を含み数分)、`p0c4_nega.py`。`k80_argfix.py` を使う p0c2 / p0c3 / p0c4 の経路は 21.3 で実行済み。

## 22. #3513: 戻り値が xmm0 の kernel を戻り値試験の対象に入れる (測定 commit `9c38a83e4`・基準 origin/main `4868fc52b`)

### 22.1 原因と方針

- census の ret_diff は `nat` が rax から読む値と IR の `ret` を比べる。xmm0 で返す kernel では rax は戻り値ではないため、比較は意味を持たない (0x5e12b0 は 2000/2000 の不一致)。
- RetDec IR の `ret` は xmm0 を表さない。例: 0x5e1280 は `ret i64 %6` (%6 は `function_409df0` の変換結果で、機械語は rax を書かず buffer へ store する)、0x5e03f0 は `ret i64 %2` (`xor i64 0,0`)。汎用の xmm0 判定は IR 側の接続 (pass) が要る。**子 issue #3573 [P0c-23] に分離**。
- 本節で行ったこと: (1) `k80abi.py` が kernel ごとの戻り slot `ret_slot` を機械語の書込みから決める。(2) `k80_diff.py` は `ret_slot=xmm0` の kernel で rax を比べず `ret_diff=-1` を出す (buffer 比較と nat/ir の呼出しは従来どおり)。(3) `p0c4_abi_e2e.py` の受入 ⑤: `ret_slot=xmm0` の kernel の集合が戻り値試験 [5b] の対象 (`UCOMI_FIX`) と一致しなければ FAIL。

### 22.2 分類規則 (機械語のみ・fail-closed)

`ret_slot_of()` (`k80abi.py`)。kernel 内の全命令の書込みオペランドを見る (capstone `access`)。

- rax 系 (rax/eax/ax/al/ah) を書き、xmm0 を書かない → `rax`
- xmm0 を書き、rax 系を書かず、メモリへの書込み (store) を持たない → `xmm0`
- rax 系も xmm0 も書かない → `none` (戻り値を書かない)
- それ以外 (rax と xmm0 を両方書く / xmm0 を書いて store を持つ) → `unknown` (未判定。rax 比較を従来どおり続ける)

| ret_slot | kernel 数 (80) | census ok | 内訳 |
|---|---:|---:|---|
| rax | 13 | 12 | — |
| none | 23 | 14 | rax・xmm0 を書かない kernel の内訳: store なし 17 (ok 8) / store あり 6 (ok 6) |
| unknown | 43 | 41 | rax と xmm0 を両方書く 38 (ok 36) / xmm0 を書き store を持つ 5 (ok 5) |
| xmm0 | 1 | 1 | 0x5e12b0 |

数え方: kernel = `k80abi.json` の 80 エントリ (kernel_table の 80 実装)。census ok = `p0c4_abi_e2e.py 2000` の CSV で status=ok の行 (68)。内訳の `unknown` の 5 件は 0x5decb0・0x5df270・0x5df340・0x5e03f0・0x5e1280 (子 issue #3573 の対象)。

### 22.3 検証 (測定 commit `9c38a83e4`・detached clean worktree で全段を再生成)

素材: `fl-win64` (`extracted/block18983_PE.bin`)・`toolchain-retdec` (`[RETDEC]`)。llvm-18 を PATH に置いた。load は各 run 終了時の 1 分値 (開始時の値は記録していない)。

| コマンド | rc | 所要 | load (終了時 1 分値) | 結果 |
|---|---:|---:|---:|---|
| `kernel_table.py` → 80 kernel の `lift_ranges.sh` (`PLUG_CANON_ALLOCA=1`) → `f80_assess.py` (clean HEAD `9c38a83e4`。lift の所要は同手順の初回 ws-3513 で 4.1 s、clean 側は未計測) | 0 | — | — | `k80.final.ll` 80 defines |
| `p0c4_abi_e2e.py 2000` (clean HEAD `9c38a83e4`) | 0 | 31.2 s | 0.75 | `run=68 ok=68 sig11=0`・`⑤` xmm0 1 件 = [5b] 対象 `0x5e12b0`・`[5b]` 2001/2001 一致 |
| `p0c4_abi_e2e.py 2000` (基準 `4868fc52b`) | 0 | 36.9 s | — | `run=68 ok=68 sig11=0` |
| `p0c2_e2e.sh 2000` (`9c38a83e4`) | 0 | 56.6 s | 0.96 | `== p0c2 e2e OK ==` |
| `p0c3_e2e.sh 2000` (`9c38a83e4`) | 0 | 55.9 s | 0.37 | `== p0c3 e2e OK (構造修復 3 kernel bit-exact + 回帰 0) ==` |

- 基準との差分: 修正前後の census 表 (status=ok の 68 行) を `diff` で比べると、差は `0x5e12b0` の `ret_diff` のみ (`2000` → `-1`)。他 67 kernel の ret_diff・buf_diff・status は同一。

  ```
  -   0x5e12b0   sse           2000        0    0.0000 ok
  +   0x5e12b0   sse             -1        0    0.0000 ok
  ```

検証 HEAD `086c474f2` での再現 (差し戻し後・同じ手順を clean checkout で実行。`git diff 9c38a83e4 086c474f2 -- tools/plugins/p0c ':!*REPORT*'` の出力は空)。

| コマンド | rc | 所要 | load (終了時 1 分値) | 結果 |
|---|---:|---:|---:|---|
| kernel_table.py → 80 kernel の `lift_ranges.sh` (`PLUG_CANON_ALLOCA=1`) → `f80_assess.py` | 0 | 4 s (lift) | 0.18 | `k80.final.ll` 80 defines・`ret_slot` rax 13 / none 23 / unknown 43 / xmm0 1 |
| `p0c4_abi_e2e.py 2000` | 0 | 34 s | 0.55 | `run=68 ok=68 sig11=0`・`⑤` xmm0 1 件 = `0x5e12b0`・`[5b]` 2001/2001 一致 |
| `p0c2_e2e.sh 2000` | 0 | 53 s | 0.80 | `== p0c2 e2e OK ==` |
| `p0c3_e2e.sh 2000` | 0 | 52 s | 0.99 | `== p0c3 e2e OK (構造修復 3 kernel bit-exact + 回帰 0) ==` |

同じ HEAD での負論対照: `K80_NO_UCOMI_FLAGS=1` で `mismatch=1014` (2001 中)・rc 1。`K80_NO_RETSLOT=1` で `[FAIL] 0x5e12b0 戻り値試験 [5b] の対象だが ret_slot が xmm0 でない (#3513)`・rc 1。

### 22.4 負論対照 (数値)

| 対照 | 操作 | 結果 |
|---|---|---|
| (a) xmm0 戻り値の破壊 | `K80_NO_UCOMI_FLAGS=1 python3 p0c4_abi_e2e.py 2000` | `[ucomi_ret] ... mismatch=1014` (2001 中)・`[FAIL] 戻り値が native と不一致 (1014 / 2001)`・rc 1 |
| (b) 分類の破壊 | `K80_NO_RETSLOT=1 python3 p0c4_abi_e2e.py 2000` | `[FAIL] 0x5e12b0 戻り値試験 [5b] の対象だが ret_slot が xmm0 でない (#3513)`・`[FAIL] 受入基準未達`・rc 1 |

(a) は #3439 の記録 (`mismatch=1014`) と同値。(b) は分類を外すと gate が落ちることを示す。

### 22.5 検証範囲

- 測定 commit: `9c38a83e4` (コードを変えた最後の commit)。その後の commit は REPORT のみ。
- `git diff 9c38a83e4 HEAD -- tools/plugins/p0c ':!*REPORT*'` の出力は空 (コード差分 0)。
- 範囲外: `0x5e12b0` 以外の xmm0 戻り値の正しさは未検証 (`ret_slot` は機械語の書込みから推定した分類で、戻り値の意味は見ていない)。`unknown` 43 件の戻り値 slot は未確定 (rax 比較を従来どおり続けるため、その ret_diff は意味を持たない)。
- 未実行: `p0c_e2e.sh` の全段 (kernel_matrix)、`p0c4_nega.py`。

### 22.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| IR に xmm0 の戻り値を接続する pass が無く、xmm0 戻り値の汎用判定ができない (現状は 0x5e12b0 だけ [5b] で判定) | xmm0 で返す kernel の戻り値は census で判定されない | #3573 [P0c-23] |
| `unknown` 43 件 (xmm0 を書き store を持つ 5 件 と、rax と xmm0 を両方書く 38 件) の戻り slot が未確定 | 戻り slot の誤分類は gate の対象外。rax 比較の ret_diff は従来どおり意味を持たない | #3573 [P0c-23] |

### 22.7 判定表: `unknown` 43 件の戻り slot (#5229・代替条件 R6)

測定 commit: `93628ce3c` (main 起点。コード変更なし・本節は REPORT のみ。`git diff 93628ce3c HEAD -- tools/plugins/p0c ':!*REPORT*'` の出力は空)。素材 `fl-win64` と `toolchain-retdec` (実在確認済み)。`kernel_table.py` (80・45・10,886 B) → 80 kernel の `lift_ranges.sh` (`PLUG_CANON_ALLOCA=1`・rc 0・80 defines) → `f80_assess.py` (rc 0) → `k80abi.py` (rc 0) の順で再生成した。`ret_slot` は rax 13 / none 23 / unknown 43 / xmm0 1 (§22.2 と一致)。

呼出し site の列は前 run の `kernel_matrix.py 12` (n=43・8 分 16 秒・rc 0) の実測を引く。本 run では再測定していない。`ret_used` は rax だけを見るため、xmm0 で返す kernel はここでは判定できない。

判定の方針: 推定で分類しない。呼出し側で戻り値の読みが確認できなかった kernel は「未確認」とする。`k80abi.py` の分類は変えない。

| kernel | 担当 | 呼出し site (前 run 実測) | ret_used | 判定 |
|---|---|---|---|---|
| 0x5de5a0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5de710 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5de8e0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5deb10 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5decb0 | #4544 (xmm0 を書き store を持つ 5 件) | — | — | #4544 で判定 (本節の対象外) |
| 0x5dee90 | 本 issue | 0x6bf0d4 (間接 `call qword ptr [rax]`) | ret_used=False (rax のみ見る) | 未確認 (間接呼出しで戻り値を読めない) |
| 0x5df040 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5df270 | #4544 (xmm0 を書き store を持つ 5 件) | — | — | #4544 で判定 (本節の対象外) |
| 0x5df340 | #4544 (xmm0 を書き store を持つ 5 件) | — | — | #4544 で判定 (本節の対象外) |
| 0x5df4d0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5df610 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5df750 | 本 issue | 0x6e17fc (別 plugin 領域・読めず) | ret_used=False (rax のみ見る) | 未確認 (呼出し先の読み直しが要る) |
| 0x5df860 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5dfa40 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e03f0 | #4544 (xmm0 を書き store を持つ 5 件) | — | — | #4544 で判定 (本節の対象外) |
| 0x5e05b0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0680 | 本 issue | 0x5e231a (直後が引数準備) | ret_used=False (rax のみ見る) | 未確認 (戻り値の読みが無い) |
| 0x5e06e0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0760 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e07b0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0830 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0890 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e08d0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0930 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0980 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e09f0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0a70 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0b10 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0b70 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0bb0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0c00 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0d80 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e0ea0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e1010 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e11a0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e1210 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e1280 | #4544 (xmm0 を書き store を持つ 5 件) | — | — | #4544 で判定 (本節の対象外) |
| 0x5e12c0 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e1330 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e1490 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e1590 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e1780 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |
| 0x5e1870 | 本 issue | なし (141 plugin の呼出し site 0 件) | — | 未確認 (呼出し側なし・rax と xmm0 を機械語で区別不能) |

集計: 43 件 = #4544 担当 5 件 + 呼出し site あり 3 件 (判定は全て未確認) + 呼出し側なし 35 件 (全て未確認)。戻り値か scratch かの判定 0 件。

#### 原条件 1 (機械語の意味で確定) の判定

未達 (理由: 上記の実測。呼出し site があるのは 43 件中 3 件で、機械語の線形走査だけでは rax (ポインタ増分) と xmm0 (作業値) を区別できない)。原条件の残りは #4544 の受入として残す。
