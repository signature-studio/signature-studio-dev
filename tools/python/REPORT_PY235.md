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
- **書換えの有無と値**: `T = [obj+0x30]`、`0xc62db0(T, eventId, &[rbp+0x28])` の戻り `al` (= `idx >= 0`) が真 (found) のとき、`[rbp+0x5b8]` = `[rbp+0x2c]` = **hi32(arr[idx].value)**。`arr = [T+8]`、value の qword は `[arr + 16*idx + 8]`。`[rbp+0x2c]` は `0xc62db0` が書いた qword の上位 dword。後続の vtable 呼出し (`call [rbx+8]`) へは rcx = obj しか渡されず、`&[rbp+0x2c]` は渡されない (ただし callee が obj 経由で任意の内容を書く可能性は別途未確定)。caller は `al != 0` で 0x104a9cd へ飛び、0x104a938 の `vt[+0x30]` 呼出しを通らない。
- **not found** (`idx < 0`): `0xc61250` は書かない。caller は `al == 0` で 0x104a938 へ進み、`vt[+0x30]` の戻りで `[rbp+0x5b8]` を置き換える。
- **`0xc62db0`** (呼出し先は `0xc626e0`・`0xc62630` の 2 つだけ): `K = 0xc626e0(T)`、`idx = 0xc62630(T, eventId, K)`。`idx >= 0` なら `[rdi]` = qword `[arr + 16*idx + 8]`、else `[rdi]` = 0。
- **`0xc62630`** (`T` の hash 表): `arr = [T+8]`、`n = [arr-8]`、`slot0 = sext32(K) & (n-1)`、線形探査。`key` (u32 `[entry+0]`) == -1 で `~slot` (負) を返す。`key == K` かつ `Y.vt[+0x18](Y, [entry+4], eventId)` が真で `slot` を返す。`n == 0` は `-2^63`。
- **`0xc626e0`**: `Y = [T+0x18]`、`K = ((Y.vt[+0x20]() & 0x7fffffff) + 1) & 0x7fffffff`。
- **閉じない部分** (runtime 値): (a) `Y.vt[+0x20]` の戻り (K)、(b) `Y.vt[+0x18]` の照合結果、(c) hash 表 `T` の内容、(d) `[obj+0x38]` の `vt[0]` (lookup 前に呼ばれ、戻りは捨てられる)・`vt[+8]` (write 前に呼ばれ、戻りは捨てられる) が `T` を書換えるか。式は `T` と `Y` の vtable 戻り値を含み、edx だけでは閉じない。
- **0xc62780 は本経路に入らない**: 本体内の `call 0xc62780` は 0xc62e49 の 1 件のみで、0xc61250 の直接の子ではない (`0xc62720` は挿入側で、同じく本経路の子ではない)。
- 検証: `analysis/py235_0xc61250_write.py` (33 ok・0 FAIL・rc 0)。入力は `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'`)。測定 commit `8d15d54d4` (スクリプトを追加した最後のコード commit)。`git diff 8d15d54d4 HEAD -- tools/python/analysis tools/python/host tools/python/provider tools/python/tests` は REPORT の変更のみで空。load avg `0.00 0.05 0.05`。

## 早期 exit (-1 の出口)

- **gate** (0x1046d83〜0x1046d8d): `rax = [0x15e1890]` (pointer)・`cmp byte [rax], 0`・`jne 0x104cc72` で -1。
  - 実体: `.data` の pointer 変数 `0x15e1890` の初期値は `0x13e7628`。そこが gate フラグ本体の 1 byte で、初期値は 0 (ファイル内の値で確認)。
  - 参照: `objdump -d -M intel` の線形走査で `# 0x15e1890` を読む命令は 58 件 (`mov rax` 56・`mov rdx` 1・`mov r8` 1)。58 件すべて読出しで、RIP 相対の store は 0 件 (`analysis/py251_gate_refs.py` §1)。
  - 書込み (フラグ本体への store): 2 箇所。どちらも `mov byte [rax], 1` で、0 を書く store は無い。
    - 0x11c7615 (`mov rax,[0x41a274]; mov byte [rax],1`)。含む関数は 0x11c71b0 (`push rbp` から)。呼出し元は 0x11c88d3 (`call 0x11c71b0`) の 1 件。
    - 0x1262970 (`mov rax,[0x37ef19]; mov byte [rax],1; ret`)。直接の call・RIP 相対参照・data 内の qword 参照はいずれも 0 件。呼出し元は間接 (vtable 等) と推定するが未確定。
  - 意味: フラグは 1 を書く store しか持たず、PE 上は 0→1 の一方向に見える。`general.processRECEvent` の全 eventId を -1 にする (`0x1046d8d`)。フラグ 1 の意味 (処理停止・再入ガード等) は、0x11c71b0 の vtable 呼出し先と 0x11c88d3 の周辺の意味づけが要るため未確定。
- **`(eventId & 0xffff) == 8` の -1 経路** (0x10471b6〜0x10471f9)。PE の分岐から、次の 5 条件がすべて真のとき -1 (`jmp 0x104cc72`) になる (`analysis/py251_gate_refs.py` §2 で assert)。
  1. 0x104711f〜0x1047129: `[0x15e2878]` のフラグが非 0 (`je 0x1047294` を取らない)。
  2. 0x104714b: `0x663bf0(...)` の戻り値が負 (0x1047150 `jge 0x1047288` を取らない)。
  3. 0x1047158〜0x104718c: index (`eventId >> 16` 相当。範囲外は -1) が 0 以上 (`jl 0x10471fe` を取らない)。
  4. 0x10471b4: `0xffac50(obj)` が真 (`je 0x10471fe` を取らない)。`obj` は `0xfe8bb0(index)` の戻り値。
  5. 0x10471c4: `(eventId & 0xffff) == 8` (`jne 0x10471fe` を取らない)。
  - 未確定: `0x663bf0` と `0xffac50` の中身の条件、`[0x15e2878]` の意味・書込み元。runtime 値が要るため、成功経路の式からは外したまま (#3777)。
  - PY-392 (#4832) で追加した PE 事実 (`analysis/py392_flag_runtime.py`・18 ok・0 FAIL): (a) `0x663bf0` は `[rcx+8]` の qword 配列 (長さ `[rcx+0x10]`) の線形探索で、`rdx` と一致する添字を返し、無ければ -1。条件 2 の「戻り値が負」は「`rdx` = eventId の qword が配列に無い」と同値。(b) `0xffac50(obj)` は `[obj+0x160]` が 0..7 で、かつ mask (byte `0xffacd8` = `0x32`) の bit が立つときだけ即 偽 (0xffacc9)。それ以外 (範囲外・bit 0) は `0x12f9ed0` の戻り値を回す loop (0xffac8d〜) に入り、その真偽で決まる (loop 本体は未読)。(c) `[0x15e2878]` は pointer で、指す先 `0x16baf90` の初期値は 0。`0x15e2878` を読む命令は 23 件。`0x16baf90` を RIP 相対で指す命令は 0 件 (レジスタ経由の書込み元は未特定)。(d) gate の 1 書込みのうち `0x11c761c` は `0x11c71b0` の内側で、直前 (0x11c7610) に `0x976f40` の呼出しがある。store が実行される条件 (分岐) は未確定。`0x11c71b0` の呼出し元は `0x11c88d3` の 1 件。`0x1262970` は vtable (`V+0x60`) の setter で、getter `0x1262950` (vt+0x48) と同じ pointer 0x15e1890 を読み書きする対。
  - 残り (未確定): (a) の配列 `[rcx+8]` の内容 (runtime)・(b) `0x12f9ed0` の戻り値と loop 本体の真偽・(c) `0x16baf90` の間接書込み元・(d) gate 1 を立てる呼出しの意味。受入 1・2 は部分達成 (#4832)。
  - PY-398 (#4859) で追加した PE 事実 (`analysis/py398_gate_flow.py`・35 ok・0 FAIL): gate の pointer は `0x13e7628` (`.data`・初期値 0)。gate 書込み `0x11c761c` は `0x11c7507: je 0x11c7604` の分岐 (`[rbp+0xdc]` = `(([rbp+0xd8]|[rbp+0xd4])&1)-1`) で飛ばされ得る。`0x11c71b0` の呼出しは `0x11c88d3` の 1 件 (`[0x16bcc00]` != 0 のときだけ)。`0x12f9ed0` は `[0x196eb60]` の配列長 (`[ptr-8]`・0 ポインタなら 0) を返し、`0xffac50` の loop 上限はこの長さ。`0x15e2878` を読む命令は 23 件で、読出しのみ (直接の書込みは無い)。runtime 値 (`0x13e7628` の内容・`0x196eb60` の配列・`0x16baf90` の書込み元) は静的に確定しない。
- 共通 prefix (入口〜0x1047424) の -1 出口は上の 2 箇所だけ (CFG)。prefix からの store は入口の 1 件のみ。
- 測定 commit (PY-398 の最後のコード変更): `bb40d5156` (py398 の summary 文言と本 REPORT の件数)。`FL_WIN64_DIR=/tmp/opencode/fl-win64 python3 analysis/py398_gate_flow.py` → 35 ok・0 FAIL・rc 0・7.3 秒。`py392_flag_runtime.py` → 18 ok・0 FAIL・rc 0。load avg `0.69 0.23 0.08` (測定直前の `uptime`)。素材は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で `$FL_WIN64_DIR/extracted/` に展開。

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

## PY-252 (#3778): 固定 4 族の戻り値式

- 固定 4 族 (0x40000000→0x104c2a6・0x40000001→0x104c4af・0x40000002→0x104c64f・0x40000005→0x104c919) の `[rbp+0x5b8]` の store 8 件は、すべて `flags` (`[rbp+0x5c0]`・3 番目の引数 r8d) のガードの内側にある。
  - `0x20` ガード: 0x104c2c4/0x104c4cd/0x104c672/0x104c91f。右辺は `cvtsi2sd(value)`・`mulsd`・`[obj+0x3bc]−[obj+0x3b8]`・`call 0x40c660` (`cvtsd2si`)・`[obj+0x3b8]+eax`。
  - `0x2` ガード: 0x104c3e0/0x104c564/0x104c760/0x104c9d0。右辺は global の読出し (0x104c3ee・0x104c56b・0x104c767・0x104c9dd)。
  - 右辺の store VA: 0x104c311・0x104c3f0 (0x40000000)・0x104c51a・0x104c56d (0x40000001)・0x104c6ba・0x104c769 (0x40000002)・0x104c984・0x104c9e6 (0x40000005)。
- **確定した式**: `flags & 0x22 == 0` のとき 4 族は store 0 件で 0x104cc65 → ret に届き、戻り値 = value。CFG で固定 4 族の到達集合 (503 VA) に `lea 0x104a924` は無い。
- **未確定**: `flags & 0x22 != 0` の右辺は engine 状態 (`obj+0x3b8`・`obj+0x3bc`・global) と定数 `0x104ccd8` (= 2^-30) に依存するため、静的な式は閉じられない。これらは code 2 (未実装) のまま。
- 実装: `host/fl_mock.mjs` の `recPassFamily(e, f)`・`provider/fl_engine.c` の `rec_pass_family(e, f)` (3 番目の引数 flags を読む)。`tests/general_diff.mjs` に固定 4 族の境界を追加 (flags 0x1c・0x1 は `& 0x22 == 0` で成功、0x2・0x20 は code 2)。mock と C の一致を見る差分テストで、戻り値の値そのものは検査しない。
- 測定 commit: `f5d656a4f` (main 取り込み merge)。これ以降の commit は REPORT_PY235.md のみ (`git diff f5d656a4f HEAD --stat` が REPORT_PY235.md だけ・コード差分 0)。load avg は測定中 `0.74` (4 コア)。
  - 本 PR の HEAD 前 (`ce6b07dfb`) からの差分は main 側由来で、`fl_engine.c` の `FL_H(...)` が 208→224 (+16)。内訳は PY-246 の `FL_H(ui, up/down/left/right/cut/copy/paste/insert/delete/enter/escape/yes/no/nextWindow/selectWindow)` 15 件と PY-243 の `FL_H(launchMapPages, setMapItemTarget)` 1 件。本 PR の `rec_pass_family` 関連は `FL_H` を増やさない (0 増分)。
  - `bash provider/build.sh`: rc 0。`fl_table.c: 435 関数, ハンドラ 224`。`EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh` (emsdk 6.0.12 を上流から install)。
  - `build_cpython_wasm.sh`: rc 0 (`/tmp/opencode` のコピーで実行。`tools/legal` も同じ場所にコピーして後処理を通した)。`FLPY_SKIP_TABLE=1 build_flpy.sh`: rc 0 (下記補足の一時コピーで実行。出力 `flpy.js` 120442 B・`flpy.wasm` 5923520 B・`flpy.data` 3293169 B、5.9 秒)。
  - `node tests/general_diff.mjs`: `{"calls":56,"diffs":0,"PASS":true}` (0.11 秒)。
  - `node tests/provider_check.mjs`: `{"functions":435,"implemented":224,"unimplemented":211,"mcp_static":60,"PASS":true}`。208→224 の +16 は上記 main 側の `FL_H` 増分と一致。
  - `node tests/ui_state_diff.mjs`: `{"calls":109,"diffs":0,"PASS":true}` (0.05 秒)。`ui_browser_diff.mjs`: `{"ok_calls":8,"bad_calls":5,"diffs":0,"browserOp":3,"PASS":true}` (0.04 秒)。`channels_diff.mjs`: `{"calls":238,"grid_calls":1200,"diffs":0,"grid_diffs":0,"PASS":true}` (0.08 秒)。
  - `node tests/launchmap_diff.mjs`: `{"calls":18,"diffs":0,"PASS":true}` (main 側由来・0.04 秒)。`node tests/ui_keys_diff.mjs`: `{"calls":26,"diffs":0,"PASS":true}` (main 側由来・0.04 秒)。
  - `FL_ENGINE=wasm node tests/all_tools.mjs`: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` (rc 0)。
  - `analysis/py235_process_rec_families.py` (`FL_WIN64_DIR` の PE・素材 `fl-win64` 展開): 31 ok・0 FAIL・rc 0 (固定 4 族のアドレス渡し非到達を assert に追加)。
  - 補足: `build_flpy.sh` は上流 emsdk の `emsdk_env.sh` が `EMSDK_DIR` を unset するため `set -u` で落ちる (23 行目)。再現は `source` 直後の `echo "$EMSDK_DIR"` が unset になること。本測定では `tools/python` と `tools/shared`・`tools/legal` を `/tmp/opencode/pyt/tools/` にコピーし、コピー側の `build_flpy.sh` の 23 行目だけを退避・復元に変えて実行した (`_EMSDK_KEEP="$EMSDK_DIR"; source ...; EMSDK_DIR="$_EMSDK_KEEP"`)。`work/` とリポジトリ内のスクリプトは変えていない。リポジトリの修正は本 PR の範囲外。
- KPI: 起動・GUI に関わらない PR のため、製品 KPI は記載しない。

## PY-349 (#5249 / 親 #4616): flags & 0x20 ガード内 store の右辺 (固定 4 族)

- 対象: 固定 4 族 (0x40000000・0x40000001・0x40000002・0x40000005) の `flags` ([rbp+0x5c0]) の `test eax, 0x20` ガード内の store 4 件 (0x104c311・0x104c51a・0x104c6ba・0x104c984)。`flags & 0x2` の側は対象外。
- **確定した式** (4 族で同形。`analysis/py349_flags20_rhs.py` が 4 族とも VA・命令形・定数を assert):
  - `v` = `[rbp+0x5b8]` (int32)。`a` = `[obj+0x3b8]`・`b` = `[obj+0x3bc]`。
  - `t` = `(double)(int32)v × C × (double)(int32)(b − a)`。`b − a` は 32 bit (`sub eax, dword ptr [rcx+0x3b8]`)。
  - `C` = `[0x104ccd8]` = 2^-30 (mulsd の rip 相対先。`0x104ccd8` の 8 byte は `0x3e10000000000000`)。
  - `r` = `cvtsd2si(t)` (`call 0x40c660` は `cvtsd2si rax, xmm0; ret`・64 bit)。
  - 格納値 = `low32(a + r)` (`mov ecx, [obj+0x3b8]`・`add ecx, eax`・`mov [rbp+0x5b8], ecx`)。
- **obj の出所**: 族ごとに `obj = *(*(*G) + off)` (G は .data の pointer 変数・2 段 deref の後に off)。

| 族 | store VA | G (.data) | off | obj 退避先 |
|---|---|---|---|---|
| 0x40000000 | 0x104c311 | 0x15e2eb8 | 0x9e0 | [rbp+0x3a0] |
| 0x40000001 | 0x104c51a | 0x15e14a0 | 0x808 | [rbp+0x398] |
| 0x40000002 | 0x104c6ba | 0x15e2eb8 | 0xb28 | [rbp+0x390] |
| 0x40000005 | 0x104c984 | 0x15e2eb8 | 0x778 | [rbp+0x2b8] |

- **未確定** (静的には閉じない): `*(*G)` の実行時値と、`obj` の `[obj+0x3b8]`・`[obj+0x3bc]` の中身 (エンジン状態)。式は `a`・`b`・`v` を変数として残す。
- 実装 (mock/C の 0x20 分岐) はこの子の範囲外。受入はこの式の確定のみ。親 #4616 に残る。
- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/py349_flags20_rhs.py` (fl-win64 の block00031_PE.bin・capstone/pefile)。結果は全 assert ok・rc 0。既存の `analysis/py235_process_rec_families.py` も同じ PE で 31 ok・0 FAIL・rc 0 (再実行)。
- KPI: 起動・GUI に関わらない PR のため、製品 KPI は記載しない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| gate フラグ (0x13e7628) の意味 (1 を書く 2 箇所のうち 0x1262970 の呼出し元が間接で未確定)・`0x663bf0`・`0xffac50`・`[0x15e2878]` の中身 | gate 0 を仮定した成功経路の前提。実行時に gate が 1 の場合の挙動が未確定 | #3777 (PY-251、残り) |
| 固定 eventId 4 族の `flags & 0x22 != 0` の右辺 (`obj+0x3b8`・`obj+0x3bc`・global・定数 2^-30) | `flags & 0x22 == 0` の成功経路だけ実装。0x20/0x2 のとき code 2 | #4616 (PY-349) |
| 0x70000000 族・index 族 (eventId < 0x10000000) の戻り値式 (`0xc61250` の書換え式は #4585 で確定。残りは `T` の表内容と vtable 戻り値) | 2 族が code 2 (未実装) | #3779 (PY-253) |

