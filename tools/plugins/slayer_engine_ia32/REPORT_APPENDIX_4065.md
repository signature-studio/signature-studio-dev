# REPORT_APPENDIX_4065: x87 native ランナーの終了コード化と 12 本の初期実測 (PLG-G2-41)

親 issue: #3715 (PLG-G2-31)。 本付録の対象 issue: #4065。

## 1. 変更 (受入条件 2)

`x87_fn_native.c` に次の 2 つを足した。

- 入力行が 10 字未満のとき、黙って読み飛ばさず exit 7 にする (従来は `continue` で行が消え、exit 0 で出力が欠けた)。
- 出力の `write` が 0 以下を返したとき exit 8 にし、部分書込みは続けて書く (従来は戻り値を見ずに exit 0)。

既存の差分試験 (`x87_fn_diff.py`) は変わらず PASS した (§3)。

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

## 3. 検証 (測定 commit 7c841dee9・検証 HEAD 7c841dee9)

測定 commit (コードを変えた最後の commit) は `7c841dee9` (main `0c17f8fc3` 取り込みの merge)。検証 HEAD も `7c841dee9` で、以降に積むのは付録と PR 本文だけ。
`git diff 7c841dee9 HEAD -- tools/plugins/slayer_engine_ia32 ':!*REPORT_APPENDIX*'` は 0 行 (差分 0)。
この merge で main 側の `x87_fn_diff.py` が変わり、`TARGETS` に `fn_10005d20` (gen `mixed`・200 行) が入った。 本付録の全試験は、この merge の後の tree で測った。
素材: `fl-win64` (`extracted/block22434_PE.bin`) を `$RUNNER_TEMP/fl-win64/` に、`toolchain-emsdk` を `$RUNNER_TEMP/emsdk-root/emsdk/` に展開 (emcc 6.0.12)。 `oc_artifacts: fl-win64 toolchain-emsdk`。
load は各試験の開始時の load1 (`uptime`、または試験スクリプトが出した値)。

| 試験 | 結果 | 所要 |
|---|---|---|
| `lift_text.py` (block22434) 1 回 | rc 0。 pass1 object 1404643 B・被覆 61654 / 73002 B (84.46%)。 最終 (pass2) object 1490401 B・被覆 62320 / 73002 B (85.37%)・未被覆 10682 B・functions 472・insns 21354 | real 22.95 s (user 22.06 s・sys 0.88 s・load1 0.29 開始時) |
| `x87_fn_diff.py` (既定) | PASS (rc 0)。 5 本 × 行数 = 16200 行。 fn_10002ee0 bit 一致 3890/4000 (97.25%)・fn_10005400 bit 一致 3405/4000 (85.12%)・fn_1000b6c1 4000/4000・fn_1000b936 4000/4000・fn_10005d20 200/200。 構造 (eax・x87 深さ) 不一致 0 (5 本とも) | build native 0.05 s・wasm emcc 9.80 s・run native 0.333 s・wasm(node) 0.578 s・load1 before run 0.61。 試験全体 real 16.03 s (user 15.35 s・sys 0.90 s) |
| `x87_fn_diff.py --nega` | 1 bit 反転を検出 (15495 → 15494)・ネガコン OK (rc 0) | real 5.09 s (user 4.92 s・sys 0.15 s・load1 0.54 開始時) |
| `x87_fn_diff.py --nega-lower` | fn_10002ee0 で 4000/4000 行の float32 不一致を検出・ネガコン OK (rc 0) | real 14.03 s (user 13.54 s・sys 0.61 s) |
| 合成入力 (短い行 `abc`) | rc 7 | 未計測 (rc のみ) |
| 合成入力 (出力先の open 失敗: 存在しないディレクトリ) | rc 6 | 未計測 (rc のみ) |
| 合成入力 (出力先 `/dev/full` へ write: ENOSPC) | rc 8 | 未計測 (rc のみ) |
| 正常入力 (`x87_fn_diff.py` の `scen.txt` 16200 行) | rc 0・出力 60,377,400 B | real 0.32 s |

合成入力の数え方: 入力 image と scen は `x87_fn_diff.py` が作った `work/x87fn/` のものを使い、ネイティブ (`gcc -m32`・x87_fn_native.c) を直接起動した。

TARGETS の追加 (受入条件 3 の一部): `fn_1000b6c1`・`fn_1000b936` (main 取り込みで入った既存の追加) と `fn_10005d20` (同じ merge で入った) の 3 本は、構造 (eax・x87 深さ) の全行一致を上の試験で確認した。 `fn_10002ee0`・`fn_10005400` は bit 一致が 100% ではないが、構造の不一致は 0 行 (従来どおり)。

**注意**: pass2 の object の大きさが、付録の旧測定 (`6bd7bd91f`: object 1162447 B・被覆 85.37%) と一致しない。被覆率は一致するが object は約 328 KB 大きい。原因は未確認 (lift_text.py の差分は無い)。 本 PR の受入条件には無関係のため、未解決に書く。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 12 本の原因分析 (SIGSEGV 6 本・wasm 境界外 6 本) | 受入条件 1 未達 | #4087 ([PLG-G2-44]) |
| TARGETS 外の残りの候補の追加と構造の全行一致 (本 PR で 3 本追加済み) | 受入条件 3 一部達成 | #4088 ([PLG-G2-45]) |
| `lift_text.py` pass2 の object が旧測定 (`6bd7bd91f`: 1162447 B) より約 328 KB 大きい。 被覆率は同じ 85.37% | 本 PR の受入条件には無関係。 再現性の確認が必要 | 未解決。 起票先は PM 判断 (新規子 issue は起票しない) |

oc_artifacts: fl-win64 toolchain-emsdk
