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
