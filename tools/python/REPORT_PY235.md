# tools/python REPORT: PY-235 general.processRECEvent の 0x1046a30 の戻り値式 (#3701, 親 #3002)

> 前段: `tools/python/REPORT_PY126.md` (呼出し鎖と out の構造)・`analysis/py126_process_rec_chain.py`。
> 既知類型との関係: 該当なし (lift ではなく PE の直接逆アセンブルと CFG 解析。docs/DEFECTS.md の類型は対象外)。

## 結論

- **戻り値は `[rbp+0x5b8]` (int32) で、入口の `edx` (value) が初期値**。0x104cc65 で `[rbp+0x584]` へ複写されて返る。`-1` は初期値で、出口 0x104cc72 へ直接飛ぶ経路で返る。
- **成功経路の式を確定 (R-other 族)**: 共通 gate `*(0x15e1890)` が 0、eventId が R-other 族 (下の表)、かつ `(eventId & 0xffff) != 8` のとき、戻り値 = value。根拠: R-other 族の entry 0x104caae から到達する `[rbp+0x5b8]` の store は 0 件、アドレス渡し (`lea` 0x104a924) に到達せず、0x104cc65 を通らずに ret・0x104cc72 へ行く辺も無い (CFG)。
- **mock/C に実装** (`host/fl_mock.mjs` の `recPassFamily`・`provider/fl_engine.c` の `rec_pass_family`)。成功経路だけ value を返し、未確定の族と `(eventId & 0xffff) == 8` は code 2 (未実装 error) を返す。
- **未確定** (子 issue へ): gate の意味 (#3777)・`(eventId & 0xffff) == 8` の -1 条件 (#3777)・固定 eventId 4 族の式 (#3778)・0x70000000 族と index 族の式 (#3779。アドレス渡し先 `0xc61250` が値を書換えるかが要る)。

## 族の分岐 (PE VA)

eventId は `[rbp+0x5b0]` (0x1046d65 で入口から格納)。分岐は `0x1047424`〜`0x1047492` の比較列で、`analysis/py235_process_rec_families.py` §1 が 11 件の命令を assert する。

| 族 | eventId | 分岐 VA | 行先 | `[rbp+0x5b8]` の mov 件数 (CFG 到達) | 状態 |
|---|---|---|---|---|---|
| 固定 | 0x40000001 | 0x1047431 `je` | 0x104c4af | 2 (0x104c51a・0x104c56d) | 未確定 (#3778) |
| 固定 | 0x40000000 | 0x104745f・0x1047465 | 0x104c2a6 | 2 (0x104c311・0x104c3f0) | 未確定 (#3778) |
| 固定 | 0x40000002 | 0x1047471 `je` | 0x104c64f | 2 (0x104c6ba・0x104c769) | 未確定 (#3778) |
| 固定 | 0x40000005 | 0x104747c `je` | 0x104c919 | 2 (0x104c984・0x104c9e6) | 未確定 (#3778) |
| R-other | [0x10000000, 0x40000000) ∪ {0x40000003, 0x40000004} ∪ (0x40000005, 0x70000000) ∪ [0xf0000000, 2^32) | 0x104745f・0x104748c | 0x104caae | 0 | **確定** (成功経路・下記) |
| 0x70000000 族 | [0x70000000, 0x80000000) ∪ [0x80000000, 0xf0000000) | 0x1047446・0x1047492 | 0x104aa87 | 15 (CFG。lea 0x104a924 に到達) | 未確定 (#3779) |
| index 族 | [0, 0x10000000) | 0x1047456 | 0x1047497 | 55 (CFG。lea に到達)。範囲外 `index = eventId >> 16` は 0x10474b9 で -1 | 未確定 (#3779) |

- 固定 4 族の store 右辺 (例: 0x104c4d4〜0x104c51a) は `flags & 0x20` の分岐で `cvtsi2sd` (value)・`mulsd` (定数 `[rip+0x7f4]`)・`[obj+0x3bc]−[obj+0x3b8]`・`call 0x40c660`・`[obj+0x3b8]+eax` の式になる。`flags & 0x2` の分岐は global の読出し (0x104c56d)。どちらも engine 状態 (`obj`・`[0x…]`) に依存するため、静的な式は #3778 で閉じる。
- R-other 族の entry 0x104caae は、`[rbp+0x52f]`・`[rbp+0x5c0]` (flags) の分岐を含むが、store を持たない (CFG で 0 件)。flags は戻り値に影響しない。

## 早期 exit (-1 の出口)

- **gate** (0x1046d83〜0x1046d8d): `rax = [0x15e1890]` (pointer)・`cmp byte [rax], 0`・`jne 0x104cc72` で -1。PE 全体で `0x15e1890` を読む命令は 58 件 (`mov rax, [rip+X]` の形。RIP 相対の解決は次命令 + disp)。意味と書込み元は未確定 (#3777)。
- **`(eventId & 0xffff) == 8` の経路** (0x10471b6〜0x10471f9): index ≥ 0 かつ `0x663bf0` の戻り値・`[0x59b752]`・`0xffac50(obj)` の真偽が揃うと -1 (`jmp 0x104cc72`)。runtime 条件つきのため、成功経路の式からは外した (#3777)。
- 共通 prefix (入口〜0x1047424) の -1 出口は上の 2 箇所だけ (CFG)。prefix からの store は入口の 1 件のみ。

## 手段

- 展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` (約 3 秒)。`$ARTIFACTS_DIR` の実在を確認してから展開した。
- 再現: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/py235_process_rec_families.py` (30 assert)。CFG は関数内の直接 `jmp`/`jcc`・`ret` だけで張る (間接 jmp は 0 件を assert)。
- 解析の仮定: callee は戻る (例外で抜けない)。callee が `[rbp+0x5b8]` を書くのは `lea r8, [rbp+0x5b8]` (0x104a924) を通した場合だけ (関数内の `lea` は 1 件のみ、rbp 自己ポインタは `[rbp+0x298]` に 1 件保存されるが読まれない)。

## 実装と検証

- 変更: `host/fl_mock.mjs` (`general.processRECEvent`・`recPassFamily`)・`provider/fl_engine.c` (`h_general_processRECEvent`・`rec_pass_family`)・`tests/general_diff.mjs` (成功経路 5 件・族外 4 件・個数違い 2 件)・`tests/provider_check.mjs` (`pe235` 1 件を実装扱い。実装数 162→163・未実装数 273→272)・`analysis/py235_process_rec_families.py`。
- 測定 commit: `470e2d8e0` (コードを変えた最後の commit)。以降はこの REPORT と DOC_MAP の変更のみ。`git diff 470e2d8e0 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis` の出力は 0 行。
- 測定 (HEAD `470e2d8e0`・load avg 0.00):
  - `bash provider/build.sh`: rc 0 (1.05 秒)。`fl_table.c: 435 関数, ハンドラ 163`。
  - `node tests/general_diff.mjs`: `{"calls":52,"diffs":0,"PASS":true}` (0.05 秒)。
  - `node tests/provider_check.mjs` の第 1〜2 部 (表の整合・件数): impl 163 / unimpl 272 で PASS。**第 3 部 (Python 経由の検査) は未実行**: `dist/flpy.js` (CPython wasm) が無いため。
  - `analysis/py235_process_rec_families.py`: 30 ok・0 FAIL・rc 0 (0.1 秒)。
  - `FL_ENGINE=wasm node tests/all_tools.mjs`: **未実行** (`dist/flpy.js` が要る)。`general.processRECEvent` を呼ぶ箇所は `tests/` に無い (grep)。
- KPI: 起動・GUI に関わらない PR のため、製品 KPI は記載しない。
- ネガティブコントロール: `host/fl_mock.mjs` の `(eventId & 0xffff) !== 8` を `!== 9` に変えると、`node tests/general_diff.mjs` は `general 差分 1 件` (AssertionError・rc 1) で落ちる (`[0x10000008, 9, 0]` が mock は 9、C は code 2)。元に戻した後の差分は 0 行。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| gate `*(0x15e1890)` の意味と書込み元・`(eventId & 0xffff) == 8` の -1 条件 (`0x663bf0`・`[0x59b752]`・`0xffac50`) | gate 0 を仮定した成功経路の前提。実行時に gate が 1 の場合の挙動が未確定 | #3777 (PY-251) |
| 固定 eventId 4 族 (0x40000000・0x40000001・0x40000002・0x40000005) の store 8 件の右辺 | 4 族が code 2 (未実装)。provider_check の件数はこの族を含まない | #3778 (PY-252) |
| 0x70000000 族・index 族 (eventId < 0x10000000) の戻り値式・`0xc61250` の書換え有無 | 2 族が code 2 (未実装) | #3779 (PY-253) |
| `provider_check` の第 3 部・`all_tools.mjs` (48/48) の実行 | CPython wasm (`build_cpython_wasm.sh`・`build_flpy.sh`) のビルドが要る。本 run では未実行 | #3778 (受入 4) |
