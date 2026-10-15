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

## 3. 検証 (測定 commit 712e8a993・検証 HEAD 712e8a993)

測定 commit (コードを変えた最後の commit) は `712e8a993` (main `9c0dfadc9` 取り込みの merge)。検証 HEAD も `712e8a993` で、以降に積むのは付録と PR 本文だけ。
`git diff 712e8a993 HEAD -- tools/plugins/slayer_engine_ia32 ':!*REPORT_APPENDIX*'` は 0 行 (差分 0)。
PR の main に対する実コード差分は `git diff origin/main HEAD -- tools/plugins/slayer_engine_ia32 ':!*REPORT_APPENDIX*'` の 1 ファイル (`x87_fn_native.c` 8 行追加・2 行削除) のみ。
素材: `fl-win64` の `extracted/block22434_PE.bin` (sha256 `84b64c43…de724a9`) を `$RUNNER_TEMP/fl-win64/extracted/` に、`toolchain-emsdk` を `$RUNNER_TEMP/emsdk-root/emsdk/` に展開 (emcc 6.0.12)。
load は各試験の開始時の load1 (`uptime`、または試験スクリプトが出した値)。

| 試験 | 結果 | 所要 |
|---|---|---|
| `lift_text.py` (block22434) を 2 回 | 2 回とも rc 0・出力一致 (時間の行を除く)。pass1 object 1404643 B・被覆 61654 / 73002 B (84.46%)。最終 (pass2) object 1490401 B・被覆 62320 / 73002 B (85.37%)・未被覆 10682 B・functions 472 | 1 回目 real 12.90 s、2 回目 real 12.62 s (user 12.03 s・sys 0.58 s・load1 0.45) |
| `x87_fn_diff.py` (既定) | PASS。 fn_10002ee0 bit 一致 3890/4000 (97.25%)・fn_10005400 bit 一致 3405/4000 (85.12%)。 構造 (eax・x87 深さ) 不一致 0 | build native 0.12 s・wasm emcc 12.94 s・run native 0.106 s・wasm 0.132 s・load1 before run 0.75 (試験全体 real 14.45 s・user 21.72 s・sys 10.53 s・load1 0.41 開始時) |
| `x87_fn_diff.py --nega` | 1 bit 反転を検出 (7295 → 7294)・ネガコン OK (rc 0) | real 1.18 s (user 1.06 s・load1 0.85 開始時) |
| `x87_fn_diff.py --nega-lower` | fn_10002ee0 で 4000/4000 行の float32 不一致を検出・ネガコン OK (rc 0) | real 5.99 s (user 5.72 s・load1 0.86 開始時) |
| 合成入力 (短い行 `abc`) | rc 7 | 未計測 |
| 合成入力 (出力先の open 失敗: 存在しないディレクトリ) | rc 6 | 未計測 |
| 合成入力 (出力先 `/dev/full` へ write: ENOSPC) | rc 8 | 未計測 |
| 正常入力 (`x87_fn_diff.py` の `scen.txt` 8000 行) | rc 0・出力 22,096,000 B | 未計測 |

合成入力の数え方: 入力 image と scen は `x87_fn_diff.py` が作った `work/x87fn/` のものを使い、ネイティブ (`gcc -m32`・x87_fn_native.c) を直接起動した。

**注意**: pass2 の object の大きさが、付録の旧測定 (`6bd7bd91f`: object 1162447 B・被覆 85.37%) と一致しない。被覆率は一致するが object は約 328 KB 大きい。原因は未確認 (lift_text.py の差分は無い)。本 PR の受入条件には無関係のため、未解決に書く。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 12 本の原因分析 (SIGSEGV 6 本・wasm 境界外 6 本) | 受入条件 1 未達 | #4087 ([PLG-G2-44]) |
| 通せる関数を `TARGETS` に入れ、構造の全行一致を確かめる | 受入条件 3 未達 | #4088 ([PLG-G2-45]) |
