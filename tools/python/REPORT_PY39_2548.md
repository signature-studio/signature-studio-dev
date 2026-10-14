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
