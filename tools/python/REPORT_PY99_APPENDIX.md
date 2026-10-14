# PY-99 付録 (#2874): call 0x10469f0 の本体式・7 件の戻り値式・経路列挙

親: #2788 (PY-88)。前段: `REPORT_PY41_APPENDIX.md` の PY-88 節。既知類型との関係: 該当なし (逆アセンブルの読解のみ)。
本付録は `REPORT_PY41_APPENDIX.md` の 250 行上限のため別置きした。末尾の `## PY-99 (#2874)` 節 (経路列挙) も同じ理由でここに置く (main 取り込みで PY41 付録が 244 行になったため)。

## 結論

- `call 0x10469f0` の本体 (17 命令・0x10469f0〜0x1046a1d) は `edx + rint(2^-30 · ecx · (r8d − edx))` を返す。rint は `call 0x40c660` (`cvtsd2si rax, xmm0`・最近接偶数)、2^-30 は RIP 相対 qword 0x1046a20。
- 7 件の呼出しの ecx (= 読み時点の `[rbp+0x5b8]`) は、すべて入口 store 0x1046d6b の edx (`d_in`) に帰着する。よって 7 件の戻り値は `e = edx_in` の式になる。
- 式が閉じたのは 4 件 (`e` と定数のみ)。残り 2 件は edx・r8d が SLOT 依存 (0x104a48f・0x104b843)、1 件は `call 0x7a0c20` の戻り値に依存 (0x1049b31)。未確定 3 件は子 #3085・#3087 へ。

## 逆アセンブル (0x10469f0 の本体・`analysis/py99_call10469f0.py` の実測出力)

| VA | 命令 | 読み |
|---|---|---|
| 0x10469f0 | `push rbx` | |
| 0x10469f1 | `sub rsp, 0x20` | |
| 0x10469f5 | `mov ebx, edx` | b = edx |
| 0x10469f7 | `cvtsi2sd xmm0, ecx` | (double)ecx |
| 0x10469fb | `mulsd xmm0, qword ptr [rip + 0x1d]` | · K。K = 0x1046a20 = 2^-30 (実測 9.313225746154785e-10) |
| 0x1046a03 | `sub r8d, ebx` | r8d = r8d − edx (32bit) |
| 0x1046a06 | `cvtsi2sd xmm1, r8d` | |
| 0x1046a0b | `mulsd xmm0, xmm1` | ecx·K·(r8d − edx) |
| 0x1046a0f | `call 0x40c660` | rint = `cvtsd2si rax, xmm0` |
| 0x1046a14 | `add ebx, eax` | ebx = edx + rint (32bit・wrap) |
| 0x1046a16〜0x1046a1d | `mov eax, ebx` / `add rsp,0x20` / `pop rbx` / `ret` | 戻り値 = eax |

## 7 件の戻り値式 (`py88_out.txt` の CALL 行。e = edx_in)

| 呼出し VA (call 命令) | ecx | edx | r8d | 戻り値 |
|---|---|---|---|---|
| 0x1047714 | e | 0 | 0x3200 | rint(2^-30·e·12800) |
| 0x1047964 | e | 0 | 0x3200 | rint(2^-30·e·12800) |
| 0x1047d93 | e | −4800 (0xffffed40) | 4800 (0x12c0) | −4800 + rint(2^-30·e·9600) |
| 0x1049b2c | e | 0 | X − 1 (X = `call 0x7a0c20` の戻り値・未確定) | rint(2^-30·e·(X−1)) ※X 未確定 |
| 0x104a48f | e | −M | M (M = M32[M64[G[0x15e44c8]] + SLOT[rbp+0x56c]·4]・未確定) | −M + rint(2^-30·e·2M) ※M 未確定 |
| 0x104b300 | e | 0 | 0x3e80 (16000) | rint(2^-30·e·16000) |
| 0x104b83e | e | A (SLOT[rbp+0x5c0] 系・未確定) | B (同じ基底・未確定) | A + rint(2^-30·e·(B−A)) ※A・B 未確定 |

- ecx の e の根拠: 7 件の ecx 読み (0x1047706・0x1047956・0x1047d82・0x1049b1d・0x104a47a・0x104b2f2・0x104b7f9) は、すべて到達 store が 0x1046d6b の 1 件・値は `d_in` (`py99_slot_paths.py` の出力)。前向き検算も mismatch 0。
- 注意: `[rbp+0x5b8]` は lea で取られている (0x104a924)。lea を間接書込み (may-write) とみなして検査した (`py99_slot_paths.py --lea-write`): lea から直接 store を経ずに届く `[rbp+0x5b8]` の読みは 0 件 (30 件のうち 0・lea から届く節点 155 件)。7 件の ecx 読みもこの 30 件に含まれ、影響を受けない。書込み幅は 0x5b8 の 1 スロットと仮定 (0xc61250 本体は未読・表は #3087)。
- e の値 (呼出し元が 0x1046a30 に渡す edx) は本付録の対象外 (PY-53 #1911 の範囲)。

## 検証

- 測定 commit: `69530065` (`analysis/py99_call10469f0.py`・`analysis/py99_slot_paths.py` の最後のコード commit)。`git diff 69530065 HEAD -- tools/python/analysis/py99_call10469f0.py tools/python/analysis/py99_slot_paths.py tools/python/analysis/py88_writes.py tools/python/analysis/py53_dispatch.py tools/python/analysis/py60_objdump_check.py` は 0 行。main 取り込みで `analysis/` に入った他 PR の新規ファイルは本節のスクリプトから import されない (`py99_slot_paths.py` は `py88_writes`、`py88_writes` は `py64_branch_regions` のみ)。
- `cd tools/python && python3 analysis/py99_call10469f0.py work/py64/extracted/block00031_PE.bin` → 14 命令の期待列・K=2^-30・rint=`cvtsd2si` の 3 項目すべて一致、`PASS`、exit 0。
- 同 `--negctl` (期待列の 1 命令を `sub ebx, eax` に変更) → `FAIL`、exit 1 (検出力あり)。
- `python3 analysis/py99_slot_paths.py work/py53/fn.txt 0x1047706 0x1047956 0x1047d82 0x1049b1d 0x104a47a 0x104b2f2 0x104b7f9` → 7 件すべて `store 0x1046d6b ... : d_in`、`forward cross-check: n=7 mismatch=0`、exit 0。
- `python3 analysis/py99_slot_paths.py work/py53/fn.txt --lea-write` → `lea-write: lea ['0x104a924'] から直接 store を経ずに届く節点 155、[rbp+0x5b8] の読み 0 / 30`、exit 0 (節点 155 > 0 は検査が動いている確認)。

## 限界

- 7 件の戻り値は閉じた式ではない (`e` と未確定 3 件)。数値は出していない。
- `call 0x7a0c20` の本体は未読 (#3087)。SLOT 依存の A・B・M は未閉 (#3085)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1049b31 の X = `call 0x7a0c20` の戻り値・本体 | 7 件のうち 1 件の式 | #3087 (PY-160) |
| 0x104a48f の M (`SLOT[rbp+0x56c]` 依存) と 0x104b843 の A・B (`SLOT[rbp+0x5c0]` 依存) | 7 件のうち 2 件の式 | #3085 (PY-158) |
| e の呼出し元の値 (0x1046a30 の入口 edx) | 7 件の数値 | #1911 (PY-53)・既存 |

## PY-99 (#2874): 後ろ向き CFG 経路列挙で `[rbp+X]` の読みの到達 store を出す (受入 1・3 は #3085・#3086 へ移管。範囲縮小後の `Closes #2874`)

親: #2788 (PY-88)。前段: `REPORT_PY41_APPENDIX.md` の PY-88 節 (線形の後ろ向きスライス) と PY-64 (式照合)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。

### 結論

- 経路列挙を実装し、印つきの `[rbp+X]` 読み 116 件 (SLOT? 86・ACC?⚠ 30) すべてに適用した (`analysis/py99_slot_paths.py`)。到達 store を分岐先つきで出した。入口 (IN) まで届く読みは 0 件。
- 値の確定は未達。格納値が閉じた式になった読みは 0 件で、残りは別の読みへの依存 (63 件) か入口レジスタ (32 件)。
- 突合: 線形で一意な読み (印なし) 55 件は、到達 store が線形の直前 store 1 件で式も一致 (mismatch 0)。前向きの検算 (store から前向きに届く読みを列挙) も 171 件すべてで後ろ向きと一致 (mismatch 0)。
- py88 の合流印は保守的だった。ACC (`[rbp+0x5b8]`) の 30 件は、経路上では全件 0x1046d6b (入口 edx) の 1 store にだけ届く。SLOT? 86 件のうち 85 件は線形 store が到達集合に入り、1 件 (0x104b7ec) は入らない (下記)。
- issue の「79 読み」は書込み単位の件数 (直接式 SLOT? 49 と ACC?⚠ 30 の和。うち 20 件は両方に入る) で、読み単位ではない。読み単位 (読み位置 × スロット、重複除去) は T 116 件 + U 55 件 = 171 件。

### 測定条件

- 測定 commit: `69530065` (`analysis/py99_slot_paths.py` の最後のコード commit。`--lea-write` の追加を含む)。`41a6d7af` で測った 171 読みの結果は、`69530065` で再測定して一致した。前段の測定 commit は `7e6c748a` (py88_writes.py・py64_check_expr.py の最後の変更)。`git diff 7e6c748a HEAD -- tools/python/analysis/py88_writes.py tools/python/analysis/py64_check_expr.py tools/python/analysis/py53_dispatch.py tools/python/analysis/py64_branch_regions.py tools/python/analysis/py60_objdump_check.py` の出力は 0 行。`git diff 69530065 HEAD -- tools/python/analysis/py99_slot_paths.py tools/python/analysis/py88_writes.py tools/python/analysis/py53_dispatch.py tools/python/analysis/py60_objdump_check.py` の出力は 0 行 (main 取り込み後の `analysis/` の差分は他 PR の新規ファイルで、本節の測定は読まない)。
- 素材: `oc_artifacts: fl-win64`。`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'` は 1.58 秒 (展開前後で一致)。
- 逆アセンブル: 既存の `work/py53/fn.txt` (fn=4664)。
- 実行: `python3 analysis/py99_slot_paths.py work/py53/fn.txt --lea-write > work/py99/paths.txt 2> work/py99/summary.txt` (exit 0・`time` の real 0.53 秒)。load average (1 分値): 0.21 (22:08:55)。
- CFG: 関数内の jcc/jmp の辺 614・間接 jmp 0 件。`python3 analysis/py60_objdump_check.py work/py64/extracted/block00031_PE.bin work/py53/fn.txt` は objdump 614 辺・agree 614・disagree 0 (exit 0)。

### 結果 (読み 171 件。65 書込みの式の評価に現れた `[rbp+X]` の読みを (読み位置, X) で重複除去)

| 区分 | 件数 | 内訳・注 |
|---|---|---|
| T: py88 が印つき (SLOT? / ACC?⚠) | 116 | SLOT? 86・ACC?⚠ 30 (30 件はすべて `[rbp+0x5b8]`) |
| T・到達 store 1 件・格納値が閉じている | 0 | |
| T・到達 store 1 件・値は入口レジスタ | 32 | ACC 30 件 (0x1046d6b の edx) と他 2 件 |
| T・到達 store 1 件・値に別の読みが残る | 63 | 格納値に SLOT[...] 等が残る (限界の行を参照) |
| T・到達 store 1 件・非 mov (kill) | 3 | `and`/`add` 等で同アドレスを書く。値は `OP:<命令>` |
| T・分岐 (到達 store 複数) | 18 | 2 件が 17・3 件が 1。各 store に届いた分岐先 VA を出力 |
| T・入口 (IN) まで届く | 0 | |
| T・到達 store 0 件 | 0 | |
| T・addr-taken (lea で取られた X) | 30 | X = 0x5b8 のみ (`lea r8, [rbp + 0x5b8]` @0x104a924) |
| U: py88 の線形結果が一意 (印なし) | 55 | 突合で match 55・mismatch 0 |

### 突合 (独立算法の検算)

- 線形で一意な U 55 件: 経路列挙の到達 store が py88 の線形 store 1 件に一致し、式も一致。**一致 55・不一致 0**。
- 前向きの検算 (各 store から前向きに届く読みを列挙し、後ろ向きの結果と比べる): 171 件。**不一致 0**。
- SLOT? 86 件の線形 store (@VA) は、到達集合に 85 件で入る。例外は 0x104b7ec (`[rbp+0x5c0]`)。線形 store は 0x104a8a9 の `and dword ptr [rbp+0x5c0], 0xffffffdf` (非 mov) だが、経路はこれを通らず 0x1046d71 (`mov [rbp+0x5c0], r8d`・入口 r8) に届く。
- ACC?⚠ 30 件は、経路上では全件 0x1046d6b の 1 store のみ。線形の合流印が付いても、到達 store は一意なことがある。

### ネガティブコントロール

- (a) 分岐辺を全部落とした CFG (`--negctl fallthrough`): 171 読みのうち **115 件** で到達 store 集合・IN・到達不能が変わった (T では 114 件が到達 store 0 件)。検出力あり。exit 0 (診断モード)。
- (b) U の先頭 1 件の期待式を書き換える (`--negctl expect`): 突合は match 54・**mismatch 1**。exit 1 (期待どおり)。

### 限界

- 格納値が別の読み (SLOT[...] 等) に依存する 63 件と、入口レジスタに帰着する 32 件は値を閉じていない。経路列挙は store までで、格納レジスタの値の合流は越えていない。
- `[rbp+0x5b8]` (ACC) は lea で取られている。間接書込み (0xc61250 経由) は lea を may-write とみなして検査した (`--lea-write`): lea から直接 store を経ずに届く ACC 読みは 0 件 (lea から届く節点 155 件)。よって ACC 30 件の結論は変わらない。ただし書込み幅は 0x5b8 の 1 スロットと仮定しており、0xc61250 本体は未読。
- 対象は py88 と同じく dword/qword の `[rbp+X]` 書込みのみ (byte/word の部分書込みは見ない)。call は `[rbp+X]` を書かないと仮定 (addr-taken の X を除く)。
- 0x104caae の r9d 引数 (`call 0x12df2a0`) は対象外。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 格納値が別の読みに依存する 63 件 (T) の閉じた式 | 受入 1 の残り | #3085 (PY-158) |
| 入口レジスタに帰着する 32 件 (ACC 30 件を含む) の引数の意味・全件の式表 | 受入 3 | #3086 (PY-159) |
| 0xc61250 本体の書込み幅 (0x5b8 の 1 スロット超への書込み)。lea 経由で届く ACC 読みは 0 件と検査済み | 0x5b8 以外のスロットの読みの到達 | #3087 (PY-160) |
| 0x104caae の r9d 引数 (`call 0x12df2a0`) | 受入 2 の一部 | #3087 (PY-160) |
| 0x104b7ec の SLOT? 印の線形 store が真の到達 store でない例 (1 件) | py88 の印の解釈 | #3085 (PY-158) |
