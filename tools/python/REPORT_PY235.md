# tools/python REPORT: PY-235 general.processRECEvent の 0x1046a30 の戻り値式 (#3701, 親 #3002)

> 前段: `tools/python/REPORT_PY126.md` (呼出し鎖と out の構造)・`analysis/py126_process_rec_chain.py`。
> 既知類型との関係: 該当なし (lift ではなく PE の直接逆アセンブルと CFG 解析。docs/DEFECTS.md の類型は対象外)。

## 結論

- **戻り値は `[rbp+0x5b8]` (int32) で、入口の `edx` (value) が初期値**。0x104cc65 で `[rbp+0x584]` へ複写されて返る。`-1` は初期値で、出口 0x104cc72 へ直接飛ぶ経路で返る。
- **成功経路の式を確定 (R-other 族)**: 共通 gate `*(0x15e1890)` が 0、eventId が R-other 族 (下の表)、かつ `(eventId & 0xffff) != 8` のとき、戻り値 = value。根拠: R-other 族の entry 0x104caae から到達する `[rbp+0x5b8]` の store は 0 件、アドレス渡し (`lea` 0x104a924) に到達せず、0x104cc65 を通らずに ret・0x104cc72 へ行く辺も無い (CFG)。
- **mock/C に実装** (`host/fl_mock.mjs` の `recPassFamily`・`provider/fl_engine.c` の `rec_pass_family`)。成功経路だけ value を返し、未確定の族と `(eventId & 0xffff) == 8` は code 2 (未実装 error) を返す。
- **未確定** (子 issue へ): gate の意味 (#3777)・`(eventId & 0xffff) == 8` の -1 条件 (#3777)・固定 eventId 4 族の式 (#3778)・0x70000000 族と index 族の式 (#3779。`0xc61250` の書換え式は #4585 で確定 (下記)。残りは表と仮想呼出しの runtime 値)。

## 族の分岐 (PE VA)

eventId は `[rbp+0x5b0]` (0x1046d65 で入口から格納)。分岐は `0x1047424`〜`0x1047492` の比較列で、`analysis/py235_process_rec_families.py` §1 が 11 件の命令を assert する。

| 族 | eventId | 分岐 VA | 行先 | `[rbp+0x5b8]` の mov 件数 (CFG 到達) | 状態 |
|---|---|---|---|---|---|
| 固定 | 0x40000001 | 0x1047436 `je` | 0x104c4af | 2 (0x104c51a・0x104c56d) | 未確定 (#3778) |
| 固定 | 0x40000000 | 0x104745f・0x1047465 | 0x104c2a6 | 2 (0x104c311・0x104c3f0) | 未確定 (#3778) |
| 固定 | 0x40000002 | 0x1047471 `je` | 0x104c64f | 2 (0x104c6ba・0x104c769) | 未確定 (#3778) |
| 固定 | 0x40000005 | 0x104747c `je` | 0x104c919 | 2 (0x104c984・0x104c9e6) | 未確定 (#3778) |
| R-other | [0x10000000, 0x40000000) ∪ {0x40000003, 0x40000004} ∪ (0x40000005, 0x70000000) ∪ [0xf0000000, 2^32) | 0x104745f・0x104748c | 0x104caae | 0 | **確定** (成功経路・下記) |
| 0x70000000 族 | [0x70000000, 0x80000000) ∪ [0x80000000, 0xf0000000) | 0x1047446・0x1047492 | 0x104aa87 | 15 (CFG。lea 0x104a924 に到達) | 未確定 (#3779) |
| index 族 | [0, 0x10000000) | 0x1047456 | 0x1047497 | 55 (CFG。lea に到達)。範囲外 `index = eventId >> 16` は 0x10474b9 で -1 | 未確定 (#3779) |

- 固定 4 族の store 右辺 (例: 0x104c4d4〜0x104c51a) は `flags & 0x20` の分岐で `cvtsi2sd` (value)・`mulsd` (定数 `[rip+0x7f4]`)・`[obj+0x3bc]−[obj+0x3b8]`・`call 0x40c660`・`[obj+0x3b8]+eax` の式になる。`flags & 0x2` の分岐は global の読出し (0x104c56d)。どちらも engine 状態 (`obj`・`[0x…]`) に依存するため、静的な式は #3778 で閉じる。
- R-other 族の entry 0x104caae は、`[rbp+0x52f]`・`[rbp+0x5c0]` (flags) の分岐を含むが、store を持たない (CFG で 0 件)。flags は戻り値に影響しない。

## `0xc61250` の書換え (#4585 / 親 #3779 受入 1)

- **呼出し元**: 0x104a92b の 1 箇所。`edx` = eventId (`[rbp+0x5b0]`)、`rcx` = obj (`*(0x15e3510)`)、**`r8` は書込み先のアドレス** (`lea r8, [rbp+0x5b8]` の結果 `&[rbp+0x5b8]`)。書換え値は `r8` の値に依存しない。
- **書換えの有無と値**: `T = [obj+0x30]`、`0xc62db0(T, eventId, &[rbp+0x28])` の戻り `al` (= `idx >= 0`) が真 (found) のとき、`[rbp+0x5b8]` = `[rbp+0x2c]` = **hi32(arr[idx].value)**。`arr = [T+8]`、value の qword は `[arr + 16*idx + 8]`。`[rbp+0x2c]` は `0xc62db0` が書いた qword の上位 dword で、後続の vtable 呼出しは触らない。caller は `al != 0` で 0x104a9cd へ飛び、0x104a938 の `vt[+0x30]` 呼出しを通らない。
- **not found** (`idx < 0`): `0xc61250` は書かない。caller は `al == 0` で 0x104a938 へ進み、`vt[+0x30]` の戻りで `[rbp+0x5b8]` を置き換える。
- **`0xc62db0`** (呼出し先は `0xc626e0`・`0xc62630` の 2 つだけ): `K = 0xc626e0(T)`、`idx = 0xc62630(T, eventId, K)`。`idx >= 0` なら `[rdi]` = qword `[arr + 16*idx + 8]`、else `[rdi]` = 0。
- **`0xc62630`** (`T` の hash 表): `arr = [T+8]`、`n = [arr-8]`、`slot0 = sext32(K) & (n-1)`、線形探査。`key` (u32 `[entry+0]`) == -1 で `~slot` (負) を返す。`key == K` かつ `Y.vt[+0x18](Y, [entry+4], eventId)` が真で `slot` を返す。`n == 0` は `-2^63`。
- **`0xc626e0`**: `Y = [T+0x18]`、`K = ((Y.vt[+0x20]() & 0x7fffffff) + 1) & 0x7fffffff`。
- **閉じない部分** (runtime 値): (a) `Y.vt[+0x20]` の戻り (K)、(b) `Y.vt[+0x18]` の照合結果、(c) hash 表 `T` の内容、(d) `[obj+0x38]` の `vt[0]` (lookup 前に呼ばれ、戻りは捨てられる)・`vt[+8]` (write 前に呼ばれ、戻りは捨てられる) が `T` を書換えるか。式は `T` と `Y` の vtable 戻り値を含み、edx だけでは閉じない。
- **0xc62780 は本経路に入らない**: 本体内の `call 0xc62780` は 0xc62e49 の 1 件のみで、0xc61250 の直接の子ではない (`0xc62720` は挿入側で、同じく本経路の子ではない)。
- 検証: `analysis/py235_0xc61250_write.py` (33 ok・0 FAIL・rc 0)。入力は `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'`)。測定 commit `8d15d54d4` (スクリプトを追加した最後のコード commit)。`git diff 8d15d54d4 HEAD -- tools/python/analysis tools/python/host tools/python/provider tools/python/tests` は REPORT の変更のみで空。load avg `0.00 0.05 0.05`。

## 早期 exit (-1 の出口)

- **gate** (0x1046d83〜0x1046d8d): `rax = [0x15e1890]` (pointer)・`cmp byte [rax], 0`・`jne 0x104cc72` で -1。`block00031_PE.bin` 全体で `0x15e1890` を RIP 相対で読む命令は 58 件 (`objdump -d -M intel` の線形走査。`mov r64, [rip+X]` の形で、内訳は `mov rax, [rip+X]` が 56 件・`mov rdx` と `mov r8` が各 1 件。RIP 相対の解決は次命令 + disp)。意味と書込み元は未確定 (#3777)。
- **`(eventId & 0xffff) == 8` の経路** (0x10471b6〜0x10471f9): index ≥ 0 かつ `0x663bf0` の戻り値・`[0x59b752]`・`0xffac50(obj)` の真偽が揃うと -1 (`jmp 0x104cc72`)。runtime 条件つきのため、成功経路の式からは外した (#3777)。
- 共通 prefix (入口〜0x1047424) の -1 出口は上の 2 箇所だけ (CFG)。prefix からの store は入口の 1 件のみ。

## 手段

- 展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` (約 3 秒)。`$ARTIFACTS_DIR` の実在を確認してから展開した。
- 再現: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/py235_process_rec_families.py` (30 assert)。CFG は関数内の直接 `jmp`/`jcc`・`ret` だけで張る (間接 jmp は 0 件を assert)。
- 解析の仮定: callee は戻る (例外で抜けない)。callee が `[rbp+0x5b8]` を書くのは `lea r8, [rbp+0x5b8]` (0x104a924) を通した場合だけ (関数内の `lea` は 1 件のみ、rbp 自己ポインタは `[rbp+0x298]` に 1 件保存されるが読まれない)。

## 実装と検証

- 変更: `host/fl_mock.mjs` (`general.processRECEvent`・`recPassFamily`)・`provider/fl_engine.c` (`h_general_processRECEvent`・`rec_pass_family`)・`tests/general_diff.mjs` (成功経路 5 件・族外 4 件・個数違い 2 件)・`tests/provider_check.mjs` (`pe235` 1 件を実装扱い。実装数 162→163・未実装数 273→272)・`analysis/py235_process_rec_families.py`。
- 測定 commit (main 取り込み 4 回目の後): `3a69f624c` (コードを変えた最後の commit)。以降はこの REPORT と PR 本文の変更のみ。`git diff 3a69f624c HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis` の出力は 0 行。
- main 取り込み (4 回目・`ac7ca0637`): merge commit `3a69f624c`。競合は `tests/provider_check.mjs` の判定式と件数だけ。main の `pe133`・`pe143` と PR の `pe235` の両方を残した。件数は main 側 175/260 + pe235 1 = 実装 176・未実装 259。`fl_table.c` のハンドラも 176。
- main 取り込み (3 回目・`795ab6c51`): main `091e4a7b6` を merge。`git diff --stat f1cf42357 795ab6c51 -- (同じ範囲)` は 8 files, +767 −12 (main 側の `host/fl_mock.mjs`・`provider/fl_engine.c`・`tests/arrangement_diff.mjs`・`tests/launchmap_diff.mjs`・`tests/provider_check.mjs`・`analysis/flapi` の probe 3 本)。競合は `tests/provider_check.mjs` の判定式と件数だけで、両側の集合を残した (main の `pe138` を含め、PR の `pe235` を加えた。件数は main の 171/264 + pe235 1 = 実装 172・未実装 263)。
- 前回までの取り込み: 1 回目 `8861ba46d` (main `2c52cdf74`)・2 回目 `6556fa7a5` (main `e2cefb36a`)。どちらも `provider_check.mjs` の判定式と件数だけが競合した。
- VA 修正 (`9d39f39ad`): 族表の固定 `0x40000001` の `je` を `0x1047436` に直した (`0x1047431` は `cmp eax, 0x40000001`)。解析スクリプトの §1 も同じ VA に直した。
- 測定 (コードは `3a69f624c` と同一。測定中の `/proc/loadavg` は `0.42`〜`2.74` (4 コア)):
  - 入力: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。`fl-win64.tar.zst` から `*block24429_DATA.bin`・`*block24430_DATA.bin`・`*block25159_DATA.bin`・`*block24618_DATA.bin`・`*block00031_PE.bin` の 5 件を展開 (2.8 秒)。`fetch_inputs.sh` rc 0。
  - emsdk: 上流の `emsdk install 6.0.12` と `activate` を導入し、`[EMSDK]` の位置に symlink (`docs/REFERENCES.md` §4)。
  - `bash provider/build.sh`: rc 0。`fl_table.c: 435 関数, ハンドラ 176`。
  - `build_cpython_wasm.sh` rc 0 (4 分 24 秒) → `FLPY_SKIP_TABLE=1 build_flpy.sh` rc 0 (6.1 秒)。`build_flpy_static.sh` rc 0 (6.6 秒)。
  - `node tests/provider_check.mjs`: `{"functions":435,"implemented":176,"unimplemented":259,"mcp_static":60,"PASS":true}`。
  - `node tests/general_diff.mjs`: `{"calls":52,"diffs":0,"PASS":true}`。
  - `node tests/ui_state_diff.mjs`: `{"calls":58,"diffs":0,"PASS":true}`。
  - `node tests/ui_browser_diff.mjs`: `{"ok_calls":8,"bad_calls":5,"diffs":0,"browserOp":3,"PASS":true}`。
  - `node tests/channels_diff.mjs`: `"calls":238`・`"diffs":0`・`"PASS":true` (main 側で出力項目が増えた。判定は diffs 0・PASS)。
  - `FL_ENGINE=wasm node tests/all_tools.mjs`: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` (rc 0)。
  - wasm 差分テスト (`grep -l createWasmEngine tests/*.mjs`・`all_tools` を除く 25 本): 25 本全て rc 0。PASS 判定があるもの 24 本 (diffs 0 または fails 0 で PASS)。`static_bench.mjs` は bench 値のみで PASS 判定なし (`build_flpy_static.sh` の後に実行)。
  - `analysis/py235_process_rec_families.py`: 30 ok・0 FAIL・rc 0。`objdump -d -M intel` で `1047431: cmp eax,0x40000001`・`1047436: je 0x104c4af` を確認。`# 0x15e1890` を読む命令は 58 件。
  - ネガティブコントロール: `host/fl_mock.mjs` の `(e & 0xffff) !== 8` を `!== 9` に変えると `general_diff.mjs` が AssertionError (rc 1)。元に戻すと `{"calls":52,"diffs":0,"PASS":true}` で、`git diff -- tools/python/host` は空。
- 前回の測定 (コードは `9d39f39ad` と同一。`all_tools` 直後の `/proc/loadavg`: `2.51 1.75 0.86`):
  - `bash provider/build.sh` (emsdk 6.0.12 を上流から導入し `[EMSDK]` の位置に配置): rc 0。`fl_table.c: 435 関数, ハンドラ 172`。
  - `node tests/general_diff.mjs`: `{"calls":52,"diffs":0,"PASS":true}`。
  - `node tests/ui_state_diff.mjs`: `{"calls":58,"diffs":0,"PASS":true}`。
  - `node tests/ui_browser_diff.mjs`: `{"ok_calls":8,"bad_calls":5,"diffs":0,"browserOp":3,"PASS":true}`。
  - `node tests/channels_diff.mjs`: `{"calls":238,"diffs":0,"grid_calls":1200,"grid_true":30,"grid_diffs":0,"PASS":true}`。
  - `node tests/provider_check.mjs`: `{"functions":435,"implemented":172,"unimplemented":263,"mcp_static":60,"PASS":true}`。`build_cpython_wasm.sh` (4 分 35 秒 rc 0) の後に `FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0) を実行してから測定。入力は `FL_WIN64_DIR` の 4 ブロック (`block24429/24430/25159/24618`) と `block00031_PE.bin` (`fl-win64` から展開)。
  - `FL_ENGINE=wasm node tests/all_tools.mjs`: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` (rc 0・2.2 秒)。
  - wasm 差分テスト (`grep -l createWasmEngine tests/*.mjs` の 24 本。`all_tools` を除く): 24 本全て rc 0 (diffs 0・PASS)。`static_bench.mjs` は `build_flpy_static.sh` (rc 0) の後に実行して rc 0 (bench 値のみで PASS 判定なし)。`sig_arity_probe.mjs` は probe で PASS 判定なし。
  - `analysis/py235_process_rec_families.py` (`FL_WIN64_DIR` の `block00031_PE.bin`): 30 ok・0 FAIL・rc 0。
  - VA の検証: `objdump -d -M intel block00031_PE.bin` で `0x1047424`〜`0x1047492` を逆アセンブルし、`0x1047431: cmp eax, 0x40000001`・`0x1047436: je 0x104c4af` を確認。
  - gate の件数: 同じ objdump 出力で `# 0x15e1890` を読む命令は 58 件 (`mov rax` 56・`mov rdx` 1・`mov r8` 1)。
  - ネガティブコントロール (HEAD `9d39f39ad` で再実施): `host/fl_mock.mjs` の `(e & 0xffff) !== 8` を `!== 9` に変えると `general 差分 1 件` (AssertionError・rc 1) で落ちる (`[0x10000008, 9, 0]` が mock は 9、C は code 2)。元に戻した後は `{"calls":52,"diffs":0,"PASS":true}` で、`git diff -- tools/python/host` は空。
- 前回 (HEAD `6556fa7a5`・main 取り込み 2 回目): `provider_check` 169/266・`general_diff` 52/0・`ui_state_diff` 58/0・`all_tools` 48/48 (全て PASS)。main 取り込み 3 回目で件数が 172/263 に変わった。
- 前回の前回 (HEAD `8861ba46d`・main 取り込み 1 回目): `provider_check` 166/269・`all_tools` 48/48・`general_diff` 52/0・`ui_state_diff` 58/0 (全て PASS)。
- 前回の測定 (HEAD `470e2d8e0`・main 取り込み前・load avg 0.00):
  - `bash provider/build.sh`: rc 0 (1.05 秒)。`fl_table.c: 435 関数, ハンドラ 163`。
  - `node tests/general_diff.mjs`: `{"calls":52,"diffs":0,"PASS":true}` (0.05 秒)。
  - `node tests/provider_check.mjs`: `{"functions":435,"implemented":163,"unimplemented":272,"mcp_static":60,"PASS":true}` (0.37 秒)。CPython wasm (`build_cpython_wasm.sh` 4 分 07 秒 rc 0・`FLPY_SKIP_TABLE=1 build_flpy.sh` 6.2 秒 rc 0) の後に実行。
  - `analysis/py235_process_rec_families.py`: 30 ok・0 FAIL・rc 0 (0.1 秒)。
  - `FL_ENGINE=wasm node tests/all_tools.mjs`: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` (rc 0・2 秒)。`general.processRECEvent` を呼ぶ箇所は `tests/` に無い (grep)。
- KPI: 起動・GUI に関わらない PR のため、製品 KPI は記載しない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| gate `*(0x15e1890)` の意味と書込み元・`(eventId & 0xffff) == 8` の -1 条件 (`0x663bf0`・`[0x59b752]`・`0xffac50`) | gate 0 を仮定した成功経路の前提。実行時に gate が 1 の場合の挙動が未確定 | #3777 (PY-251) |
| 固定 eventId 4 族 (0x40000000・0x40000001・0x40000002・0x40000005) の store 8 件の右辺 | 4 族が code 2 (未実装)。provider_check の件数はこの族を含まない | #3778 (PY-252) |
| 0x70000000 族・index 族 (eventId < 0x10000000) の戻り値式 (`0xc61250` の書換え式は #4585 で確定。残りは `T` の表内容と vtable 戻り値) | 2 族が code 2 (未実装) | #3779 (PY-253) |
