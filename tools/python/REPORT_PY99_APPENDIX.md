# PY-99 付録 (#2874): call 0x10469f0 の本体式と 7 件の戻り値式

親: #2788 (PY-88)。前段: `REPORT_PY41_APPENDIX.md` の PY-99 節 (経路列挙)。既知類型との関係: 該当なし (逆アセンブルの読解のみ)。
本付録は `REPORT_PY41_APPENDIX.md` の 250 行上限のため別置きした (内容の移動ではなく新規節)。

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

- 測定 commit: `69530065` (`analysis/py99_call10469f0.py`・`analysis/py99_slot_paths.py` の最後のコード commit)。`git diff 69530065 HEAD -- tools/python/analysis` は 0 行 (後続の commit は REPORT と DOC_MAP のみ)。
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
