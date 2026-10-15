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

未確定だった `0x12df320`・`0x105f2e0`・`0x417fc0`・`0xfe8bb0` の実体、note 構造体の字段は下の PY-184 節 (#3309) で確定。V の意味は #3310。

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
- 後日: 上の未実行は PY-184 節の受入 3 で解消 (`FL_ENGINE=wasm node tests/all_tools.mjs` 48/48)。

## PY-184 追補 (#3309): 項目列挙 (PE 0x130f200) の未確定関数と note 構造体の確定

- 親: #2581 (PY-78)。本節の範囲は未確定の 4 関数と note 構造体の確定、note 列挙の判定式の mock / C 照合。V (PE の量子 `[0x15e25f8]`) の値と意味は子 PY-185 (#3310) で、本節では引数として扱う。
- 測定 (PE 逆アセンブル): `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (各 1 回・終了 0)。展開: `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` (2.8 秒)。命令数: 0x12df320 = 90・0x105f2e0 = 60・0x417fc0 = 70・0xfe8bb0 = 50・0x130f200 = 130・0x417b70 = 45・0x418190 = 30。

### 関数の実体 (PE 実測)

| VA | 実体 | PE の読み |
|---|---|---|
| `0x12df320` | note の反復子 | cursor `[rdx]`・件数 `[rcx+0x14]`・data `[rcx+8]`・stride `[rcx+0x10]`。`data + cursor*stride` の先頭 dword が閾値 `r8d` 未満なら cursor を 1 進めて要素を返す。件数以上・閾値以上なら 0 (`0x12df320`〜`0x12df34a`) |
| `0x105f2e0` | note の終端 | `[note+0] + max(sext [note+8], 1)` (32bit 加算・下限 1)。`0x105f2e0`〜`0x105f2f5` |
| `0x417fc0` | list への push (薄い thunk) | `0x417b70` (参照数つき配列の再確保) を `r9 = 件数+1` で呼ぶ。呼出し側 `0x130f394` の後で `[data + 件数*8] = note` を書く (`0x130f3a3`)。配列ヘッダは件数 qword `[data-8]`・参照数 dword `[data-0xc]` (`0x417b70` 先頭より) |
| `0xfe8bb0` | ポインタ配列の添字参照 | 件数 dword `[rcx+0x10]`・data `[rcx+8]` (8 byte 要素)。0 ≤ i < 件数 なら `data[i]`、外れは 0 (`0xfe8bb0`〜`0xfe8bd5`) |
| `0x418190` | list の解放 (空にする) | `[slot] = 0`。参照数を `lock xadd` で 1 減らし、0 になれば解放 (`0x418190`〜`0x4181c8`)。`0x130f21f` で list を空にする。後半は未読 |

### note 構造体 (項目 = note)

PY-78 節の項目と同一。列挙に使う字段:

| 字段 | 型 | 意味 | PE |
|---|---|---|---|
| +0 | dword (符号付き) | 開始 tick (start)。反復子の閾値比較・量子化に使う。param 7 の書換え先 | `0x130f31a`・`0x12df33a` |
| +6 | word (ゼロ拡張) | channel ID。channel 構造体 `+0x794` と一致する note だけ列挙 | `0x130f35c`・`0x130f361` |
| +8 | dword (符号付き) | 長さ。終端 = start + max(長さ, 1) | `0x105f2e0` |
| +0xc・+0x10〜+0x17 | word・byte | param 0〜6・8 の書換え先 (PY-78 節の表) | `0x130f4f6`〜`0x130f699` |

stride は反復子が `[container+0x10]` から読む実行時の値で、PE からは定まらない。mock / C は StepItem の大きさ 24 B で固定する (実機の stride は未実測)。

### 列挙の判定式 (`0x130f200`・確定)

```
note を pattern の container から 0x12df320 で反復 (閾値 thr = step' + V、V = [0x15e25f8])
  sq  = (note[0] / V) * V                        (idiv: 0 方向へ切捨て・32bit)
  end = max(note_end(note) [0x105f2e0], sq + V - 1)
  採用 ⇔ sq <= step' < end  かつ  word note[+6] == chanId
```

- 反復子は最初の start >= thr で止まる。note 配列は start 昇順が前提。
- 未モデル (glue): channel 探索 (`[[0x15e2218]]` の件数を走査し `channel[i]+0x794 == chanId`・無ければ空)、patNum の範囲 [0, 998]、pattern null 判定 `[[0x15e2aa0] + patNum*192 + 0x28]`。mock / C の列挙は note 配列と chanId を直接受ける。
- 件数 0 の channel 探索は PE 読みからの推定 (`0x130f22b`〜`0x130f25d`): i = 0 を `0xfe8bb0` で引いて null を参照し得る。実機の件数は 0 にならない前提で、未確認。
- `0x417b70` の参照数 (COW) は未モデル (単一参照を仮定)。

### 実装と検証 (測定 commit `dd12402917ba2a3ab6f42b02501bcf192b0a2167`)

- `provider/fl_engine.c`: StepItem の `p1[8]` を `p4[2]`・`ch` (+6)・`len` (+8) に分割 (大きさ 24 B・既存字段の位置は不変)。`note_next`・`note_end`・`note_enum` (判定式)・`fl_engine_note_enum_probe(seed, n, chan, step, V)` (seed の LCG で n 件 (<= 256) を作り start 昇順に並べて列挙)・`fl_engine_note_enum_out`。
- `host/fl_mock.mjs`: `noteGen`・`noteEnum` (C と同一の式)・`noteEnumProbe`・`noteEnumNotes` (spot 用)。`host/fl_provider.mjs`: `noteEnumProbe`。`provider/build.sh`: export 2 件を追加。
- `tests/note_enum_diff.mjs` (新規): spot 3 件 (手計算の期待値を mock で固定) と 33264 呼出し (seed 8 × n 7 × chan 6 × step 9 × V 11) の mock / wasm 照合。

### 実測 (commit `dd124029`・wasm)

- 環境: emsdk 6.0.12 (`tools/m1/flags.sh` の pin・上流から取得)。`EMSDK_ENV=<emsdk>/emsdk_env.sh bash provider/build.sh` が exit 0。load average 1.25 (測定時 00:53)。
- `node tests/note_enum_diff.mjs` → `{"calls":33264,"nonempty":5869,"spot":3,"diffs":0,"PASS":true}` (0.857 秒)。nonempty は列挙が 1 件以上の呼出し数 (検査の力の確認)。
- ネガティブコントロール: `int64_t l = it->len < 1 ? 1 : it->len;` を `int64_t l = it->len;` にして build → `note 列挙の差分 48 件` で AssertionError。元に戻して build → PASS。
- 既存: `node tests/step_item_diff.mjs` → `{"calls":5929,"spot":5,"diffs":0,"PASS":true}`。`node tests/channels_diff.mjs` → `{"calls":170,"diffs":0,"PASS":true}`。
- 受入 3: `FL_ENGINE=wasm node tests/all_tools.mjs` → `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` (1.98 秒)。入力は `fetch_inputs.sh` (FL_WIN64_DIR の DATA block 4 件)、`build_cpython_wasm.sh` (CPython 3.12.1 wasm・約 4.5 分)、`build_flpy.sh` (flpy.js)。

### 未解決

- V (PE `[0x15e25f8]`) の値と意味・書込み元: PY-185 (#3310) の範囲。
- `channels.setStepParameterByIndex` の handler への接続: #3311 (未接続のまま)。
- 参照数 (COW)・`0x418190` の後半・件数 0 の channel 探索の実機確認: 本 PR では未モデル (PE 読みの推定)。新規の子 issue は起票しない (PR 本文の未解決表に記載)。
