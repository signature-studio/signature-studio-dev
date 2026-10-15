# REPORT_APPENDIX_4065: x87 native ランナーの終了コード化と 12 本の初期実測 (PLG-G2-41)

親 issue: #3715 (PLG-G2-31)。 本付録の対象 issue: #4065。

## 1. 変更 (受入条件 2)

`x87_fn_native.c` に次の 2 つを足した。

- 入力行が 10 字未満のとき、黙って読み飛ばさず exit 7 にする (従来は `continue` で行が消え、exit 0 で出力が欠けた)。
- 出力の `write` が 0 以下を返したとき exit 8 にし、部分書込みは続けて書く (従来は戻り値を見ずに exit 0)。

既存の 2 本の差分試験 (`x87_fn_diff.py`) は変わらず PASS した (§3)。

## 2. 12 本の初期実測 (受入条件 1 の前段・未完)

素材 `block22434_PE.bin` (fl-win64) を入力に、各関数を 1 行ずつ native ランナーで実行した (`ecx = OBJ`、乱数の OBJ 窓 0x540 B、seed 4065)。

| VA | native の結果 | 出力 |
|---|---|---|
| 0x10003fe0 | SIGSEGV (rc 139) | 0 B |
| 0x100051f0 | SIGSEGV (rc 139) | 0 B |
| 0x100085a0 | SIGSEGV (rc 139) | 0 B |
| 0x100096d0 | SIGSEGV (rc 139) | 0 B |
| 0x1000a95a | SIGSEGV (rc 139) | 0 B |
| 0x1000ba05 | SIGSEGV (rc 139) | 0 B |
| 0x1000b6c1 | rc 0 | 2762 B |
| 0x1000b8a2 | rc 0 | 2762 B |
| 0x1000b8cd | rc 0 | 2762 B |
| 0x1000b8cf | rc 0 | 2762 B |
| 0x1000b8f7 | rc 0 | 2762 B |
| 0x1000b936 | rc 0 | 2762 B |

- SIGSEGV の原因 (入力の範囲・ecx 基底・絶対アドレス) は未特定。 `OBJ` 窓の外を読んでいる可能性があるが、未確認。
- native 側で落ちない 6 本の wasm 側の挙動は未実測。 issue の「wasm 側の境界外読み」は、この run では確認していない。
- `1000b6c1` が読む絶対アドレス `A_(0x10024d50)` の値は未確認。
- issue 本文が指す `REPORT_APPENDIX_3715.md` は main にも全履歴にも無い。 12 本の一覧の根拠は確認できなかった。

## 3. 検証 (測定 commit 32151b62a・検証 HEAD は同 commit)

| 試験 | 結果 | 所要 |
|---|---|---|
| `lift_text.py` (block22434) | rc 0 | - |
| `x87_fn_diff.py` | PASS。 fn_10002ee0 bit 一致 3890/4000・fn_10005400 bit 一致 3405/4000。 構造 (eax・x87 深さ) 不一致 0 | build native 0.03 s・wasm emcc 10.79 s・run native 0.101 s・wasm 0.189 s・load1 0.52 |
| `x87_fn_diff.py --nega` | 1 bit 反転を検出 (7295 → 7294) | - |
| `x87_fn_diff.py --nega-lower` | 4000/4000 行で float32 不一致を検出 | - |
| 合成入力 (短い行) | rc 7 | - |
| 合成入力 (出力先が書けない) | rc 6 | - |

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 12 本の原因分析 (SIGSEGV 6 本・wasm 境界外 6 本) | 受入条件 1 未達 | 子 issue (起票番号は PR 本文) |
| 通せる関数を `TARGETS` に入れ、構造の全行一致を確かめる | 受入条件 3 未達 | 子 issue (同上) |
