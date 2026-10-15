# PY-39 追補 (#2548): setStepParameterByIndex の PE 解析 (REPORT_PY39.md から分割移動)

親: #1527 (PY-39)。本体は `REPORT_PY39.md`。本ファイルは 250 行上限のため、#2548 の run の節を `REPORT_PY39.md` から移した (Git 履歴に残す)。

## 追加解析 (#2548 の run): setStepParameterByIndex の呼出し経路・status・副作用

- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (各 1 回・終了 0)。展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` (実測 2.9 秒)。
- 測定 commit: `438ec321` (origin/main 取り込みの merge commit。`analysis/flapi/pe_disasm.py` は `1bb996f0` から変更なし (`git diff 1bb996f0 HEAD -- tools/python/analysis/flapi/pe_disasm.py` の出力 0 行))。
- 差分 0 の証跡: `git diff 438ec321 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `0` (0 行・測定 commit から後は REPORT と docs/DOC_MAP.md のみ変更)。範囲に解析補助 `tools/python/analysis` (`pe_disasm.py` を含む) を入れている。
- 差し戻し対応での再測定 (測定 commit `438ec321` で実行): `pe_disasm.py` の出力行数 (`wc -l`) は `0xd5cec0` 85 行・`0xd843d0` 153 行・`0xd841e0` 40 行・`0xd82c20` 130 行・`0xd84290` 30 行 (いずれも終了 0)。修正前の HEAD (`c1c73a65`・`pe_disasm.py` は同一) で取った `0xd5cec0`・`0xd843d0`・`0xd82c20` の出力と `cmp` で一致。下表の追記はこの結果による。

### 呼出し経路 (PE 実測)

| 段 | VA | 読み取った内容 |
|---|---|---|
| ハンドラ | 0xd5cec0 | 結果 struct `[rbp+0x80]` を初期化。書式 `iiiii\|i` を解析し 6 値 (index, patNum, step, param, value, useGlobalIndex) を受ける。解析成功時のみ `0xd843d0` を呼ぶ (`0xd5cfd2`。同じ関数の `lea r8,[rip-0x182]` (`0xd5cf7b`) で r8 に callback `0xd5ce00` を置く) |
| 委譲 | 0xd843d0 | `[out+0]` を `-2` で初期化。ctx `[rbx+0x50]` が非 0 で述語 `0xd84f30` が偽なら `0xd84500` で `-2` のまま戻る (callback は呼ばない)。通ると `0xd841e0` で新規オブジェクト obj を作る (obj+8 = 元の ctx)。obj の `+0x18`〜`+0x40` に 6 値、`+0x58` に callback (r8) を格納し、`0x526190` に (`0xd84290`, obj) の組を渡して登録する。最後に `[out+0]` へ `[obj+0x60]` (status) を書く |
| callback | 0xd5ce00 | status を `-2` にする。`[vtable+0x98]` の述語が偽なら status `-2` のまま戻る。真なら `0x1005730(index, useGlobal>0, &obj)` で範囲チェック。失敗で status `-4`。成功で status `0` にして `0x130f740(obj.[+0x794], patNum, step, param, value)` を呼ぶ |
| step 換算 | 0x130f740 | `step` に `[G1]` を乗じて `0x130f3d0` へ渡す (`imul`) |
| 本体 | 0x130f3d0 | `0x130f200` で対象 item 群を list に集める。list[0] の field を読んで `delta = value - field` を求め、全 item の field に加算 (param 別の clamp は下表) |
| 戻り値変換 | 0xd82c20 | status を Python 側の戻り値・例外に変換 (下表) |

呼出しは直接の `call` 連鎖ではなく間接経路: `0xd843d0` が obj を登録 (`0x526190`) → 登録された `0xd84290` が `call [rbx+0x58]` (rcx = obj) で callback `0xd5ce00` を呼ぶ薄い thunk。**`0x526190` が登録済みの組をいつ・どの経路で呼ぶかは未読**。

`0x1005730` の範囲チェック: `useGlobal > 0` なら配列 A (件数 `[0x5dcad3]`)、それ以外は配列 B (件数 `[0x5da9a8]`) を使う。index が `[0, 件数-1]` の外なら false。

### status と文字列 (PE 内の文字列を直接読んだ)

| status | 文字列 | 発生箇所 (実測) |
|---|---|---|
| 0 | `OK` | callback 成功経路 (0xd5ce00 の `[rbx+0x60]=0`)。`0xd82c20` の status 0 の分岐は戻り値の節を参照 |
| -1 | `Unspecified error` | 0xd82c20 の分岐 (0xd82d03) |
| -2 | `Operation unsafe at current time` | 文字列は 0xd82d18。status -2 のまま戻る条件は 3 つ: (a) 0xd843e9 で out を `-2` に初期化。(b) 0xd843f0〜0xd84403: ctx `+0x50` が非 0 で述語 `0xd84f30` が偽なら callback を呼ばず `0xd84500` で戻る。(c) callback の述語 `[vtable+0x98]` が偽 (0xd5ce00) |
| -3 | `Range error` | 0xd82d2a。この経路の上流 (どの呼出しが -3 を立てるか) は未読 |
| -4 | `Index out of range` | `0x1005730` が false (0xd5ce75 の `[rbx+0x60]=-4`) |
| -5〜-8 | 別文字列 (本文未読) | 0xd82c9d 以降の分岐 (0xd82d4e・0xd82d60・0xd82d72・0xd82d84)。上流の発生箇所は未読 |
| その他 (-9 以下) | `Unknown error` | 0xd82d96 の分岐 (0xd82d9a の lea) |

戻り値の経路 (`0xd82c20`・PE 実測。`0xc38bc0` は global の値を返すだけで、None に相当すると推定):
- status 0: `0xd82c3c`〜`0xd82c43` で `mov rax,[0x860485]` → `call [rax]` (先頭 slot の関数) を呼ぶ。その戻り値が非 0 なら `0xd82c4a` で `0` を返す (例外なし)。戻り値が 0 なら下の status ≥ 0 の経路へ進む。
- status ≥ 0 (status 0 で上の戻り値が 0 の場合を含む): `0xd82c5c` で `0xc38bc0` を返す (None と推定)。
- status < 0: `0xd82c6a`〜`0xd82c86` で `[[0x861b1f]+8]` の vtable `+0x88` の述語を見る。偽なら `0xd82dd0` で `0xc38bc0` (None) を返し、例外は立たない。真なら上表の文字列を `0x4135e0` で設定する。例外型は未確認。

### 範囲外・空振り

- index が配列の範囲外: status `-4` (上記)。
- `0x130f200` の channel ID 探索 (`[elem+0x794] == chanId`) で見つからない・patNum が `[0, 998]` の外・pattern が null: `0x130f3b0` / `0x130f3a7` で空 list を返す。`0x130f3d0` は件数 0 なら書換えをしない。status は 0 のまま (副作用なし)。分岐の読みから導いた結論で、実機での確認は未実施。

### 副作用 (読めた範囲)

item の field と clamp (`0x130f5f8`〜`0x130f68c` で確認):

| param | 差分計算の読出し | 書込み (`+= delta` 後) |
|---|---|---|
| 0 | word `+0xc` (符号付き) | 書込み分岐は未読 |
| 1 | byte `+0x15` | 書込み分岐は未読 |
| 2 | byte `+0x12` | 書込み分岐は未読 |
| 3 | byte `+0x10` | byte、clamp `[0, 0xf0]` |
| 4 | byte `+0x14` | byte、clamp `[0, 0x80]` |
| 5 | byte `+0x16` | byte、clamp `[0, 0xff]` |
| 6 | byte `+0x17` | byte、clamp `[0, 0xff]` |
| 7 | dword `+0x0` | dword `+= delta` (clamp なし)。delta≠0 のとき `0x12df760` を呼ぶ (0x130f6a0) |
| 8 | 差分なし (`delta = value` の直値) | byte `+0x11 = low8(value)` (`0x130f68c`。param 8 との対応は推定) |
| その他 | 差分なし (ebx=0) | 書換えなし |

後処理: `[global]≠0` で `0xe39560`、`[global+0xa9]≠0` で `0x1307760` (未読。通知・再描画と推定)。最後に list を `0x418190` で解放。

### 未解決 (次回の着手点)

1. param 0・1・2 の書込み分岐 (`0x130f582`・`0x130f5aa`・`0x130f5d1`) と param 8 の対応を未読。
2. item 列挙 `0x12df320`・長さ `0x105f2e0`・list 追加 `0x417fc0` の意味。換算用グローバル `G1` (`[rip+0x2d2ead]` の乗算、step 換算) と `G2` (`[rip+0x2d32ce]`、item 位置の `idiv` 換算) の値。
3. 述語の型: callback の `[vtable+0x98]` (status -2 の条件)・早期 return の述語 `0xd84f30` (ctx `+0x50`)・`[vtable+0x88]` (負の status で例外を立てるか)。`general.safeToEdit` 相当と推定するが未確認。`0x526190` が登録済みの `0xd84290` を呼ぶ機構も未読。
4. `0x4135e0` (メッセージ設定) と `0x414000` の実体。
5. param 番号の意味 (flapi 署名の docs との照合) は未実施。mock 側に pattern の note モデルが無いため、実装には note 列の表現も要る。

### 受入条件 (#2548) の状態 (#2548 の run・差し戻し対応後)

- [x] 呼出し経路・status 表・範囲外 code (`-4`)・param 3〜8 の副作用を PE 解析箇所つきで REPORT に残す (#2548 の受入 1 を、この範囲に縮小した)。param 0〜2 の書込み・item 列挙・述語の型は未確定のまま残す。
- 移管: 元の受入 2 (`provider/fl_engine.c`・`host/fl_mock.mjs` の実装)・受入 3 (`tests/channels_diff.mjs` の diffs 0)・受入 4 (`FL_ENGINE=wasm node tests/all_tools.mjs` 48/48) と、未解決 3 件 (param 0〜2 の書込み分岐、item 列挙と `G1`・`G2`、述語の型) は子 issue #2581 (`[PY-78]`・親: #2548) へ。

## PY-78 追補 (#2581): 項目書換え規則 (param 0〜8) の確定と provider / mock 実装

- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py 0x130f3d0 330`・`0x130f200 130` (各 1 回・終了 0)。展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` (2.9 秒)。
- 測定 commit: `add61c2c` (実装の最後の commit)。

### 呼出し (PE 実測)

`0x130f740` (`[G]` の値を step に乗じる) → `0x130f3d0(chanId, patNum, step', param, value)`。`0x130f3d0` は `0x130f200` で項目 list を作り、list が空なら何もしない (`0x130f6fd`)。以下は list が非空のとき。

- delta: param 0〜7 は `value - (list[0] の字段)` (`0x130f41f`〜`0x130f4e4`)。param 8 は delta = value。それ以外は書換えなし (`ebx = 0` で `0x130f68f` へ)。
- 書換え: 全項目 `list[i]` (`0x130f4f6`〜`0x130f699`) に規則を適用する。

| param | 字段 (項目の +off) | 型 | 書換え | 分岐 (PE) |
|---|---|---|---|---|
| 0 | +0xc | word (符号付き) | += delta・clamp [0, 0x83] | 0x130f582 |
| 1 | +0x15 | byte | += delta・clamp [0, 0x80] | 0x130f5aa |
| 2 | +0x12 | byte | += delta・clamp [0, 0x80] | 0x130f5d1 |
| 3 | +0x10 | byte | += delta・clamp [0, 0xf0] | 0x130f5f8 |
| 4 | +0x14 | byte | += delta・clamp [0, 0x80] | 0x130f61c |
| 5 | +0x16 | byte | += delta・clamp [0, 0xff] | 0x130f640 |
| 6 | +0x17 | byte | += delta・clamp [0, 0xff] | 0x130f664 |
| 7 | +0x0 | dword | += delta (clamp なし)。delta ≠ 0 のとき `0x12df760` を呼ぶ (`0x130f6a0`。呼出し先は未読) | 0x130f688 |
| 8 | +0x11 | byte | 代入 = value の低 8 bit (delta を使わない) | 0x130f68c |

clamp は `v <= 0 → 0`、`v > hi → hi` (`0x130f58c`〜`0x130f59c` 等の形)。書換え後に `[global]≠0` で `0xe39560`、`[global+0xa9]≠0` で `0x1307760` を呼ぶ (`0x130f6cb`〜`0x130f6fc`。実体は未読・未モデル)。

### 換算用の値 (旧節の G1・G2 の訂正)

RIP 相対の参照先 (次命令アドレス + disp) を計算し直すと、`0x130f744` (step 乗算)・`0x130f2f5` (step 加算)・`0x130f313` (idiv の除数)・`0x130f323` (imul の乗数)・`0x130f339` (start 加算) は**すべて同じ slot `0x15e25f8`** を読み、その指す int (offset 0) を使う。旧節の「G2 (`0x2d32ce`) は item 位置の idiv 換算」は誤り (idiv の除数は同じ slot の値で、G2 は乗数)。値の意味と書込み元は子 PY-185 (#3310)。

### 項目列挙 `0x130f200` (構造。意味は未確定)

- 引数: rcx = 出力 list・edx = chanId・r8d = patNum・r9d = step'。list は `0x418190` で初期化する。
- channel: `[[0x15e2218]]` の件数 `[obj+0x10]` を走査し、`0xfe8bb0(obj, i)` の `[+0x794] == chanId` となる i を取る。見つからない・範囲外は空 list (`0x130f3b0`)。
- pattern: 0 ≤ patNum ≤ 998 (`0x3e6`) で、`[[0x15e2aa0] + patNum*192 + 0x28]` が非 null。
- note: `0x12df320(pattern, &cursor, step' + V)` を戻り値 0 まで反復。各 note で `start = (note[0] / V) * V`、`end = max(0x105f2e0(note), start + V - 1)` を求め、`start <= step' < end` かつ `word [note+6] == chanId` のとき `0x417fc0` で list に push する。

未確定: `0x12df320`・`0x105f2e0`・`0x417fc0`・`0xfe8bb0` の実体、note 構造体の字段 (長さを含む)、V の意味 (→ #3309・#3310)。

### 述語・登録 (未確定。#3311)

callback `0xd5ce00` の `[vtable+0x98]`、早期 return の述語 `0xd84f30` (ctx+0x50)、負 status の例外判定 `[vtable+0x88]`、`0x526190` が登録した組を呼ぶ機構、`0x12df760`・`0xe39560`・`0x1307760` の実体。

### 実装と検証 (commit `add61c2c`)

- `provider/fl_engine.c`: `StepItem` (字段位置は上表)・`step_item_write`・`step_items_set`・検査用の読出し口 `fl_engine_step_item_probe` (`provider/build.sh` の export に追加)。`channels.setStepParameterByIndex` の handler はまだ無い (未接続。#3311)。
- `host/fl_mock.mjs`: 同じ規則 (`itemWrite`・`itemsSet`) と `stepItemProbe`。`host/fl_provider.mjs` に `stepItemProbe` を追加。
- `tests/step_item_diff.mjs` (新規): PE 実測の要点を手計算で 5 件固定し、param -1〜9 × 値 11 通り × 種 7×7 の 5929 呼出しを mock と C で照合。
- 実測: `node tests/step_item_diff.mjs` → `{"calls":5929,"spot":5,"diffs":0,"PASS":true}`。`node tests/channels_diff.mjs` → `{"calls":170,"diffs":0,"PASS":true}` (既存挙動は不変)。
- 規則を崩すと落ちることの確認: param 3 の clamp を `0xf0` から `0xf1` に変えて build すると `step_item_diff` が AssertionError で落ち、戻すと PASS した。
- 差分 0 の確認: `git diff add61c2c HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `0` (本節以降の変更は本 REPORT だけ)。
- `FL_ENGINE=wasm node tests/all_tools.mjs`: 未実行。CPython 3.12.1 の wasm build (`build_cpython_wasm.sh`) と `fetch_inputs.sh` の入力が worktree に無く、本 run では回らなかった。本 commit は dispatch 表と既存 handler を変えない (追加は export 1 件と内部関数のみ)。

## PY-185 (#3310): 換算値 V (slot 0x15e25f8) の確定

- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_step_v.py` (測定 commit `a9bf0957a` で再実行: 終了 0・0.57 秒・load average 0.06/0.33/0.23 (実行前)・4 core)。全出力は本節の数値の出所。
- 補助測定 (測定 commit `a9bf0957a`・同じ展開先・終了 0): `pe_xref.py 0x15e25f8` (hits 189・stores 0・100.4 秒)、`pe_xref.py 0x15e2600` (ネガティブコントロール。slot を 1 つずらした対象。hits 35・stores 0・100.6 秒)、`pe_slot_writers.py 0x15e25f8 0` (候補 6 件・100.5 秒)、`pe_slot_writers.py 0x15e25f8 8` (候補 7 件・100.8 秒)。上の 4 本は同時実行の時間。単独の実行 (`f320cc061` 時) は `pe_xref` 61.8〜62.4 秒・`pe_slot_writers` 58.7・59.4 秒。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` (2.6 秒)。
- 測定 commit: `a9bf0957a` (`pe_step_v.py` の docstring 2 行の修正。解析の出力は `f320cc061` と同一)。差分 0 の証跡は下の「差分 0 の証跡」節。

### slot の初期化 (静的)

- slot `0x15e25f8` は `.data` (file 0x11e0ff8)。静的値は **`0x15d89c4` (ポインタ)**。`.bss` ではないので、ロード直後から値を持つ。
- RIP 相対の参照は読込み 189 件のみ。書込み 0 件・`lea` 0 件 (`pe_xref.py 0x15e25f8`)。slot 自体は実行中に書き換えられない (RIP 相対で見える範囲)。
- 指す構造体 T (base `0x15d89c0`) の静的内容: `+0` (X) = 96、`+4` (V) = **24** (slot の指す int)、`+8` = 96、`+0xc` = 4。`[0x15d898c]` = 4 (steps per beat の定数)。`0x15452a8` の表も `[16, 4, 96]` で、PPQ 96 と整合 (`general.getRecPPQ` 既定 96・PY-119)。

### V の書込み元と式 (PE 実測)

- 更新関数 F = `0x13111a0` (引数 ecx = c)。`0x13111bf call 0x1311050(c)` の戻り値 X' を使う。
  - `0x13111dc mov [T+0], eax` (X := X')。`0x13111e2 shr eax, 2`。`0x13111e5 mov [T+4], eax` (**V := X' >> 2**)。
  - `0x1311205` で `[T+8] = V × [0x15d898c] (=4)`。`0x13112c8` で `[T+0xc]` に eax を書く (直前の `0x13112a1 call 0x1311030` の後。戻り値の式は未追跡)。
- `pe_xref.py 0x15d89c0` の store は `0x13111dc` の 1 件のみ (X の書込み元は F だけ)。
- V (`0x15d89c4`) への **RIP 相対の直接 store は `0x13111e5` の 1 件** (`pe_xref.py 0x15d89c4,0x15d89c8,0x15d89cc,0x15d89d0` の stores 3 = V・T+8・T+0xc)。slot 経由の間接書込みは次の節の候補で、窓内の候補はすべてスロット由来でない (範囲は次の節)。
- F の呼出し元 (E8 rel32 の線形スキャン): 9 件 (`0xecccb0`・`0xece999`・`0xf46a20`・`0xf4ee3b`・`0xf4f7d2`・`0x11ca6bf`・`0x11d4042`・`0x1362d78`・`0x1365758`)。
  - 引数 = X 自身 (`[0x15e01c8]` → T+0): 4 件 (`0xecccb0`・`0x11ca6bf`・`0x11d4042`・`0x1365758`)。この 4 件は X を「同じ値で再計算」する形。
  - 他: `0xf46a20` は `[[0x15e0db0]]` (`.bss` 0x196eb38 の int)、`0xece999` は `0x43aae0` の戻り値、`0x1362d78` はスタック引数、`0xf4ee3b`・`0xf4f7d2` は未追跡。

### 0x1311050 (X' の算出。PE 実測)

- 記法: `[a]` は a 番地の qword を読むこと。O = `[0x15e13b8]` (静的値 `0x196edd0`・`.bss`)、候補の list L = `[[O]+0xaf0]+0x4f8`。件数は vtable `+0x28`、項目は vtable `+0x18`、項目の値は `0x43aae0(項目, 0x7fffffff)`。
- ゲート: `*O == 0` なら候補を見ず **X' = c** (引数のまま)。O の指す `.bss` は静的に読めない。
- ゲートを通るとき: c 以下の最大候補 (floor)・c 以上の最小候補 (ceil) を集め、`|c - floor| < |c - ceil|` なら floor、それ以外は ceil。c と一致する候補があれば c (`0x1311118`〜`0x1311159`)。
- 候補集合の項目の意味 (`0x43aae0`・vtable `+0x18`) は未確定。

### V への間接書込みの判定 (pe_slot_writers の候補 13 件・#3390 の差し戻し対応)

- 列挙: `pe_slot_writers.py 0x15e25f8 0` (V 側。候補 6 件) と `... 8` (T+0xc 側。候補 7 件)。候補は「slot を `mov reg,[slot]` で読んだ直後 0x40 バイト内の `mov [reg+disp],…`」で、レジスタの一致は見ていない (近接の検出)。
- 判定: 各候補の store の基底レジスタを、直前の命令の逆アセンブルで手で追った (再現: `pe_disasm.py <関数の先頭 VA> <命令数>`。例: `0xe862f6` (関数 `0xe863b7` の先頭)、`0x12cfce0`、`0x1309250`)。

| 候補 VA | 書込み | 基底の出所 (実測) | 判定 |
|---|---|---|---|
| 0xe863b7 | `mov [rbx],ecx` | `0xe862fb mov rbx,rcx` (関数入口の第 1 引数)。窓内で rbx の再代入なし。slot の読込み先は rax (0xe86377) | 引数 (呼出し元は未追跡) |
| 0x1062890 | `mov [rcx],dl` | 0x1062868 の ret の後の別関数 (leaf)。rcx はその第 1 引数 | 関数境界越え |
| 0x11e7e10 | `mov [rax],ecx` | `0x11e7df3 mov rax,[0x15e3000]` で再ロード。slot (0x11e7dfa) は rcx に入り `imul` の値だけ | 別の大域 |
| 0x11e7e53 | `mov [rcx],edx` | `0x11e7e41 mov rcx,[0x15e1068]` で再ロード (0x11e7e32 の call で slot 読込みの rcx は失われる) | 別の大域 |
| 0x11fcb5f | `mov [rax],ecx` | `0x11fcb4f mov rax,[0x15e0450]` で再ロード (slot 読込み 0x11fcb27 の rax は 0x11fcb3d で上書き) | 別の大域 |
| 0x130927c | `mov [rdi],eax` | rdi は窓 0x300 内で代入なし (項目の引数。同関数で `[rdi+0x11]` を読む)。slot (0x1309263) は r8 に入り `idiv [r8]` の除数 | 引数 (呼出し元は未追跡) |
| 0xe4eb8e | `mov [rdx+8],ecx` | `0xe4eb8a mov rdx,[rbp+0x30]` で再ロード (slot 0xe4eb72 の rdx は `add r8d,[rdx]` の値読みのみ) | スタックのローカル |
| 0xe4ebaf | `mov [rdx+8],ecx` | `0xe4ebab mov rdx,[rbp+0x30]` で再ロード (slot 読込みは別の分岐) | スタックのローカル |
| 0xe64661 | `mov [rax+8],ecx` | `0xe6464d`・`0xe64654` で rax = `[[rbp+0xad8]+0x58c]` に再代入 (slot 0xe6463e の rax は上書き) | 別の構造体 |
| 0x11b3748 | `mov [rax+8],ecx` | `0x11b3736 mov rax,[0x15e0fd0]` (大域)。slot (0x11b373d) は rcx に入り `add ecx,ecx` の値 | 別の大域 |
| 0x12cff43 | `mov [rsi+8],eax` | `0x12cfeb3 lea rsi,[rcx+rdx*4]` (配列要素)。slot (0x12cff29) は rcx に入り `idiv` の除数 | 配列要素 |
| 0x12cff48 | `mov [rsi+8],0` | 同上 (rsi = 0x12cfeb3) | 配列要素 |
| 0x12cff67 | `mov [rsi+8],eax` | 同上。slot (0x12cff59) は rdx に入り `imul` の係数 | 配列要素 |

- 結論: 13 件すべてで、store の基底レジスタは slot の読込み先ではない。slot を読んだ後の値は `idiv`・`imul`・`add`・`cvtsi2sd` の値としてだけ使われる。
- 範囲: 窓 0x40 バイト内の `mov [reg+0]`・`mov [reg+8]` に限る。引数で渡された基底 (0xe863b7・0x130927c) の呼出し元、窓外・呼出しを跨ぐ間接書込み、`mov` 以外の書込み形式 (`add`・`movss`・`rep stos` 等) は未追跡 (下の未解決表)。

### V の意味と既定値

- `0x130f740`: `step' = step × V` (`mov eax,[V]; imul eax,r8d`)。`0x130f200` の `start = (note[0] / V) × V` (PY-78 節) と合わせ、**V は step 1 つあたりの tick 数**と読める。
- `V = X / 4`。`4` は `shr eax,2` の定数 (かつ steps per beat)。`X` は PPQ 相当 (既定 96)。
- **既定値 = 24** (`.data` の静的初期値 = `T+4`。X の既定 96 から `96 / 4`)。
- 実行時の既定: F が最初に呼ばれたとき、ゲートが通れば X は候補にスナップされる。ゲートの実行時値と 9 呼出し元の引数の出所 (上の未追跡分) は未確定。ゆえに「実行時に V が 24 のままか」は未確定。

### ネガティブコントロールと差分 0 の証跡

- ネガティブコントロール (測定 commit `a9bf0957a`): 対象 slot を 1 つずらした `pe_xref.py 0x15e2600` は hits 35。実 slot `0x15e25f8` は hits 189。対象 VA の参照を数えるため、対象を変えると hits が変わる。
- 差分 0: `git diff a9bf0957a HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `0` (測定 commit から HEAD まで。この REPORT の commit は REPORT だけを変える)。`f320cc061` からの差分は `pe_step_v.py` の docstring 2 行 (`a9bf0957a`) のみ。

### 未解決 (次回の着手点)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ゲート `*[0x15e13b8]` の実行時値 (初期化元) と候補集合の項目の意味 (`0x43aae0`) | 実行時の V が 24 のままかどうか | #3311 (V を使う handler の前提として追記) |
| F の呼出し元 9 件のうち引数の出所が未追跡の 5 件 (`0xf46a20`・`0xece999`・`0x1362d78`・`0xf4ee3b`・`0xf4f7d2`) | 同上 | #3311 |
| step 換算 (`step × V`) を `provider/fl_engine.c`・`host/fl_mock.mjs` に入れ、diffs 0 を保つ (受入条件 3 の移管) | 未接続 | #3311 |
| V のアドレスを引数で渡す経路を含む、窓 0x40 の外・呼出しを跨ぐ間接書込み (`0xe863b7`・`0x130927c` の引数の呼出し元を含む。`mov` 以外の書込みも未追跡) | V の実行時値が 24 から変わる可能性 | #3311 (未追跡として追記) |
