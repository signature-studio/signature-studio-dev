# PY-111 (#2929): channels.getStepParam の step 構造体 (note) の生成経路・既定値・param 8 の PE 確定

親: #2879 (PY-100)。前段: `REPORT_PY100.md` §4・§8 (PE 実測・未解決の移管)、`REPORT_PY39_2548.md` の PY-184 節 (note 字段・列挙式)、`REPORT_APPENDIX_3310.md` (V の書込み元)。
本ファイルは PY-111 の run の実測のみ。全体の要約は `REPORT.md`。

## 結論

1. **note の生成経路を PE で確定した。** `channels.setGridBit` (handler `0xd5b580`) は enqueue した後、thunk `0xd5b4d0` が `0x12d4100(grid, step, value, 1, 100)` を呼ぶ。`0x12d4100` が「既存の note が無く、value > 0 (または flag 0x1234fd0 が真)」のとき note を 1 個作る。これが grid bit の正体。
2. **既定値の PE 照合。** note の書込みは PE の即値・定数として読めた。param 0 = 60、2 = 64、3 = 120、4 = 64 は stub の既定値と一致 (2〜4 は init `0x1062210` の推定に依存。§2.4)。param 1 は setGridBit の即値 100 と一致する。fillEachNSteps は 4 番目の引数 (既定 100) を clamp して渡す (§3 行 1・#3747 で反映済み)。**param 5・6 は PE の値が 128 (stub は 64。init の推定に依存)**。**param 7 は開始 tick = step × V** (stub は 0)。**param 8 = 0** (PE の書込み `0x12d42ac`。stub に無く、従来は -1)。
3. **param 8 の書込み元を確定した** (`0x12d42ac`: `mov byte [note+0x11], 0`。creation path の無条件書込み)。既定値は 0。
4. C provider と mock の既定値を PE の値に合わせた (`provider/fl_engine.c`・`host/fl_mock.mjs`)。`channels_diff` diffs 0。fillEachNSteps の 4 番目の引数の反映は未モデル (子 #3747)。
5. **未確定**: init 関数 `0x1062210` を container の vtable 経由で呼ぶ点 (vtable の基点は RIP 相対の参照から見つからず)、フラグ `0x1234fd0` の値、V の実行時値 (静的 24 のまま)。下の §8。

## 1. 測定の入力と再現

- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` (1.5 秒)。DATA 4 本も同じ要領で展開 (`fetch_inputs.sh` の入力)。`<展開先>` = `$RUNNER_TEMP/fl-win64`。
- PE の ImageBase は `0x400000`。`analysis/flapi/pe_disasm.py` の VA はこの base を含む。
- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>`。
- handler の特定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py setGridBit fillEachNSteps setStepParameterByIndex` (handler 本体 `0xd5b580`・`0xd5b7b0`・`0xd5cec0`)。
- 参照の列挙: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_xref.py <VA>` (1 件あたり約 32 秒)。

## 2. 生成経路 (PE 実測)

### 2.1 呼出し連鎖

| 段 | VA | 読み |
|---|---|---|
| handler | `0xd5b580` (setGridBit) | `iii\|i` を解析。4 番目の任意引数の既定値は 0 (`0xd5b5b8`)。index・step・value・4 番目を enqueue (`0xd843d0`・`0xd5b674`) |
| thunk | `0xd5b4d0` | `0x1005730(index)` で channel を解決 (失敗は -4)。`[obj+0x7ac]` (grid) が非 0 なら `0x12d4100(grid, step, value, 1, 100)` (`0xd5b544`)。**5 番目の引数は即値 100** (`mov byte [rsp+0x20], 0x64` @`0xd5b53f`) |
| 生成 | `0x12d4100` | 下の 2.2 |

- 参考: fillEachNSteps (`0xd5b7b0`) の thunk は `0xd5b6e0` で、`0xff91d0(obj, n, start, len)` を経て `0x12d4100` を step ごとに呼ぶ。`len` は 4 番目の引数 (既定 100 = `0xd5b7fc`)。これは setGridBit と同じ生成関数を使う。`len` は `clamp(·, 0, 0x7f)` されて (`0xd5b761`) `0xff91d0` の r9 になり、`[rbp+0x47]` に入り (`0xff91e5`)、`0xff9354` で `0x12d4100` の 5 番目の引数 (= param 1 の値) になる。よって fillEachNSteps で作る note の param 1 = clamp(4 番目の引数, 0, 127)。

### 2.2 `0x12d4100` の生成条件

1. `tick = step × V`。`V = [slot 0x15e25f8]` (PY-185 の静的値 24。`REPORT_APPENDIX_3310.md`)。`ebx = tick + V`。
2. 範囲 `[tick, tick + V)` の既存 note を列挙 (`0x12df210`・`0x12df530`)。chanId (`word [note+6]`) が channel の `+0x794` と一致するものについて、
   - フラグ `0x1234fd0` が真なら、`note+0x13` の bit 0x20 を `value == 0` で立て、`value != 0` で下ろす (`0x105f380` 相当)。一致数 `edi` を数える。
   - フラグが偽で `value == 0` なら、その note を削除 (`0x1060370`)。
3. `edi > 0` なら終了。`edi == 0` で、`value > 0` またはフラグ `0x1234fd0` が真のとき **creation path** (`0x12d4224`)。
4. 終了時、`0x12d41f8`〜 の後で `r9b` (`[rbp+0x3b]`) が非 0 なら `0x12d68c0(obj)` を呼ぶ (後処理。未読)。

### 2.3 creation path の書込み (PE 実測)

note 本体は `[rbp+0x44]` のスタック上に作り、最後に `[r13+8]` の vtable slot (`0x12d42bb`) で container に登録する。

| 順 | 命令 (VA) | 書込み | param |
|---|---|---|---|
| 1 | `call [vt+0x10](container, &note)` (`0x12d422f`) | 下の 2.4 の init (`0x1062210`) | 2・3・4・5・6 |
| 2 | `[rbp+0x59] = clamp(5th 引数, 0, 0x7f)` (`0x12d424c`) | `note+0x15` | 1 |
| 3 | `[rbp+0x44] = step × V` (`0x12d424f`) | `note+0x0` (dword) | 7 |
| 4 | `[rbp+0x4c] = 0` (`0x12d4255`) | `note+0x8` (dword・長さ 0 → 終端は start + 1) | — |
| 5 | `[rbp+0x48] = channel[+0x9c] + 0x4000` (`0x12d4272`) | `note+0x4` (dword) | — (stub 外) |
| 6 | `if value == 0 && flag → 0x105f380(&note, 1)` (`0x12d4293`) | `note+0x13` bit 0x20 | — |
| 7 | `call 0x1062200(·, &note, 60)` (`0x12d429a`) | `word [note+0xc] = 60` | 0 |
| 8 | `[rbp+0x55] = 0` (`0x12d42ac`) | `byte [note+0x11] = 0` | **8** |
| 9 | `call [vt+8](container, &note)` (`0x12d42bb`) | 登録 | — |

- 1 と 2 の順序は PE 上 1 → 2 (init → clamp)。2 は init の後なので、`note+0x15` は init が書いた値を上書きする (init の dword の byte 1 は最終的に clamp の値)。
- `0x1062200` は `mov word [rdx+0xc], r8w; ret` (1 命令)。

### 2.4 init `0x1062210` (container の vtable slot +0x10 と読む)

`0x1062210(container=rcx, note=rdx)` の本体 (`0x1062210`〜`0x106223c`):

```
call [rsi](note, [container+0x10])       ; 既定の 0 初期化相当 (呼出し先は .bss の関数ポインタ。未読)
byte [note+0x10] = 0x78   (120)          ; param 3
byte [note+0x12] = 0x40   (64)           ; param 2
dword [note+0x14] = G                    ; G = [0x154a0f8] = 0x80806440
```

- `G` の byte: `+0x14` = 0x40 (param 4 = 64)、`+0x15` = 0x64 (後で 2.3-2 の clamp で上書き)、`+0x16` = 0x80 (param 5 = 128)、`+0x17` = 0x80 (param 6 = 128)。
- `G` は RIP 相対の書込みが 0 件 (`pe_xref.py 0x154a0f8`: hits 1 = `0x1062233` の読みのみ・stores 0)。静的値をそのまま既定値とみなせる。
- `0x1062210` は `0x1053d88` と `0x1053f90` の 2 つの表 (同じ 13 entries の並び。`[0x1053d88]` が `0x1062210`) に現れる。表の基点は RIP 相対 `lea` の参照 (`pe_xref.py 0x1053d78`・`0x1053d88` ともに 0 件) では見つからなかった。**よって `0x12d422f` の vtable slot が `0x1062210` であることは未確定**。根拠は、(a) 関数の引数形 (`rcx=container`, `rdx=note`, `[container+0x10]` を使う) が一致する、(b) 書く既定値 (120・64・G の byte 0 = 64) が stub の param 2〜4 と一致する、の 2 点。
- `[rsi]` の呼出し先は .bss の関数ポインタ (実行時に設定される)。静的には読めないため、「0 初期化」は推定。param 2〜6 は `0x1062210` の 3 書込みで全て決まるので、この推定は既定値の判定に影響しない。

## 3. param と既定値 (PE 照合)

| param | 構造体 field | PE の書込み | PE の値 | stub (REPORT_PY100 §3) | 判定 |
|---|---|---|---|---|---|
| 0 | +0xc word | `0x1062200` (`0x12d429a`) | 60 | 60 | 一致 |
| 1 | +0x15 byte | `0x12d424c` (clamp) | setGridBit: 即値 100。fillEachNSteps: `clamp(4 番目の引数, 0, 0x7f)` (§2.1) | 100 | setGridBit は一致。fillEachNSteps は 4 番目の引数 (clamp 後) を反映 (#3747・`channels_diff` で検査) |
| 2 | +0x12 byte | init `0x1062210` | 64 | 64 | 一致 (init の推定に依存) |
| 3 | +0x10 byte | init `0x1062210` | 120 | 120 | 一致 (同上) |
| 4 | +0x14 byte | init (G の byte 0) | 64 | 64 | 一致 (同上) |
| 5 | +0x16 byte | init (G の byte 2) | **128** | 64 | **不一致** (PE 優先。init の推定に依存。§2.4) |
| 6 | +0x17 byte | init (G の byte 3) | **128** | 64 | **不一致** (PE 優先。init の推定に依存。§2.4) |
| 7 | +0x0 dword | `0x12d424f` | **step × V** (V = 24) | 0 | **不一致** (開始 tick。step 0 だけ 0) |
| 8 | +0x11 byte | `0x12d42ac` | **0** | (なし。従来 -1) | **確定** (書込み元あり) |

- param 7 は PY-78 節の字段で「開始 tick」(`0x130f31a`・`0x12df33a` が読む)。よって既定値は note の位置で決まる (step × V)。`V` は静的値 24 (`REPORT_APPENDIX_3310.md`)。実行時の V は未確定 (§8)。
- param 1 の由来: setGridBit は PE の即値 100 (`0xd5b4d0` が `0x12d4100` を呼ぶ `0xd5b53f`)。`fillEachNSteps` の既定 (`0xd5b7fc`) も 100 だが、4 番目の引数で変わる (未モデル。§2.1・§3 行 1)。

## 4. 実装 (C provider と mock)

- `provider/fl_engine.c`: `step_def[9] = {60, 100, 64, 120, 64, 128, 128, 0, 0}`。`prm == 7` は `pos * 24`。`prm` の範囲を 0..8 に広げた (9 以上と負は -1)。
- `host/fl_mock.mjs`: `STEP_V = 24`・`STEP_DEF = [60, 100, 64, 120, 64, 128, 128, 0, 0]`・`stepParam` は同じ規則。
- 不変: 構造体の有無 (grid bit が 1 の step)・範囲外 -1・`padsStride` 等の引数検査 (PY-100 の規則)。

## 5. 検証の追加 (channels_diff の穴)

- 既存の `channels_diff` は step 0 の param しか読んでおらず、param 7 (step × V) の差を検出できなかった。ネガティブコントロール (`STEP_V` を 24 → 25 に変えた mock) では PASS のままだった。
- そこで `tests/channels_diff.mjs` に `setGridBit [0, 5, 1]` と、step 5 と step 7 (未設定) の `getStepParam` / `getCurrentStepParam` (param 1・6・7・8) を 7 件追加した (呼出し 214 → 221)。

## 6. 検証 (実測)

- 測定 commit: `f0f222952` (`fix(python): getStepParam の note 既定値を PE の生成経路に合わせる (PY-111)`)。コードを変えた最後の commit。worktree `ws-2929` (branch `2929-py111-step-note-pe`、base `origin/main` = `5ec4aef07`) で実測。
- 入力: `fl-win64` の PE と DATA 4 本 (`block24429`・`block24430`・`block25159`・`block24618`) を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf`、各 2 秒未満)。`toolchain-emsdk` を `$RUNNER_TEMP/toolchain` に展開し `EMSDK_ENV=<展開先>/emsdk/emsdk_env.sh` (emcc 6.0.12)。`fetch_inputs.sh` rc 0 (0.82 秒)。`work/` は main の作業ツリーの取得結果を symlink (gitignore 対象外のため commit しない)。
- CPython wasm: `build_cpython_wasm.sh` rc 0 (2 分 34.199 秒。main の作業ツリーで実施)。worktree では `dist/` を複製して使った。

| 検査 (f0f222952) | コマンド (`tools/python` で実行) | 結果 | 所要 |
|---|---|---|---|
| provider build | `bash provider/build.sh` | rc 0 (`flprov.wasm` 64904 B) | 0.670 秒 |
| flpy link | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 | 4.041 秒 |
| 件数・ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 162・unimplemented 273・mcp_static 60) | 0.223 秒 |
| C と mock の差分 | `node tests/channels_diff.mjs` | PASS (calls 221・diffs 0・grid_calls 1200・grid_true 30・grid_diffs 0) | 0.042 秒 |
| 48 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (soft_error 0・raised 0・host_calls 37425・callback_roundtrip true) | 1.120 秒 |
| 48 tool (mock) | `node tests/all_tools.mjs` | 48/48 ok (host_calls 37425) | 1.043 秒 |
| ネガティブコントロール | `host/fl_mock.mjs` の `STEP_V` を 24 → 25 | `channels_diff` rc 1 (`AssertionError: channels/playlist 差分 2 件`)。元の 24 に戻すと PASS | 0.2 秒 |

- 計測直前 `uptime` の load average 0.22 / 0.81 / 0.51 (nproc 4)。
- 差分 0 の証跡: `git diff f0f222952 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `0` (本 REPORT と `docs/DOC_MAP.md` の commit は、コードの範囲に入らない)。
- 検証範囲: 実 FLEngine (PE の本物の実行) との値の比較はしていない。C provider と mock の一致、PE 逆アセンブルの読みの一致のみ。範囲外: 実機での既定値の実測、V の実行時値、vtable 基点 (§8)。
- KPI: 起動・GUI に関わらない PR のため対象外。

## 7. 受入条件の状態 (#2929)

- [x] 構造体 (note) を作る経路 (grid bit・fillEachNSteps) を PE で確定し、既定値の PE 照合を §3 に残す (§2・§3)。
- [x] param 8 (+0x11) の既定値と書込み元を PE で確定 (既定 0・書込み `0x12d42ac`・§2.3)。
- [x] 確定した既定値と生成条件を `provider/fl_engine.c` と `host/fl_mock.mjs` に反映し、`tests/channels_diff.mjs` diffs 0 (§6)。
- [x] `FL_ENGINE=wasm node tests/all_tools.mjs` 48/48 ok (§6)。
- [x] fillEachNSteps の 4 番目の引数 (既定 100・clamp 0..127) を note の param 1 に反映 (#3747・§3 行 1)。`channels_diff` に 4 番目 (37・200→127・-5→0・既定 100) の検査を追加し diffs 0。反映を外すと FAIL (ネガティブコントロール)。
- 補足: REPORT_PY100 §8 の「`fl_table.c` 行 61 の np=6」は解消済み。`provider/gen/fl_table.c` の getStepParam は `np=4`・`"iiaii"` で、#2927 (`46f5a0079`) が直した。本 run では表を変えていない。

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| init `0x1062210` を `call [container vtable + 0x10]` で呼ぶ点の確定 (vtable の基点) | param 2〜6 の既定値の根拠が「引数形と stub 一致」の推定 | PR 本文の未解決表 (次の PE 作業で確定) |
| `[rsi]` の init 内の呼出し先 (.bss の関数ポインタ) | 「0 初期化」の推定。param 2〜6 の結論には影響しない | PR 本文の未解決表 |
| フラグ `0x1234fd0` の値 (creation path の分岐条件) | value == 0 の setGridBit で note を作るか | PR 本文の未解決表 |
| V (`[0x15e25f8]`) の実行時値 (静的 24 のまま) | param 7 の値 (step × V) | #3311 (PY-186。`REPORT_APPENDIX_3310.md` の未解決表から追記) |
