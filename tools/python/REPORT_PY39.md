# PY-39 (#1527): channels 操作 7 関数の PE 解析 (ハンドラ位置・書式・引数)

親: #1515 (PY-37)。前段: #1336 (PY-32, 棚卸し)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 7 関数 (selectAll / selectOneChannel / setChannelPitch / setStepParameterByIndex / midiNoteOn / incEventValue / processRECEvent) の**ハンドラ位置と引数書式は PE から確定**した。
- **意味論 (戻り値・範囲外 code・副作用) は未確定**。各ハンドラは下位関数へ薄く委譲しており、実処理の所在まで追えていない。推測では実装しない。
- コード変更は `provider/` `host/` `tests/` で 0 件。本 PR は解析補助スクリプトと本 REPORT のみ。受入条件は未達 (`Refs #1527`)。

## 測定

- 解析対象: `$FL_WIN64_DIR/extracted/block00031_PE.bin` (FLEngine PE、[WIN64])。`fl-win64` 素材を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で展開。
- 解析補助: `tools/python/analysis/flapi/pe_handler_probe.py` (PyMethodDef 表の名前 VA を引き、ハンドラ先頭を逆アセンブル、RIP 相対の文字列を出す)。
- 実行: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py` (終了 0・7 関数すべての表エントリを検出)。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` (実測 1.6 秒)。
- 測定 commit: `e1ee2631` (コミット済み HEAD で再実行。`pe_handler_probe.py` の最後のコード変更は `411a9ecb` の docstring 1 行のみ)。
- 差分 0 の証跡: 検証 HEAD `efb44afd` (main 取り込み後) で `git diff 41120437 efb44afd -- provider host tests` の出力は 0 行。本 REPORT を含む後続 commit も `provider/` `host/` `tests/` に触れない。
- 再実行 (efb44afd): probe 終了 0、表エントリ 11 件 (7 関数 + 重複 4 件) を検出。
- probe の出力の曖昧さ: `selectAll` は PE 内に 4 件の表エントリ (`fn=0xd56d00`・`0xd5b150`・`0xd61400`・`0xd66430`) があり、probe は module を出さない。下表の `selectAll` (`0xd5b150`・entry `0x15174a8`) は channels 側の 1 件で、flapi_kwargs.json の `modules.channels` と照合して選んだもの。`processRECEvent` も同様に `0xd58e00` (channels) と `0xd69f00` (general) の 2 件ある。

## ハンドラ位置と書式 (PE 実測)

`flapi_kwargs.json` の channels 表 (`fn_va`) と probe の結果が一致した。

| 関数 | fn_va | flags | 書式 (fmt) | kwlist | flapi 署名 |
|---|---|---|---|---|---|
| selectAll | 0xd5b150 | 4 (NOARGS) | なし | なし | `() -> None` |
| selectOneChannel | 0xd5afc0 | 3 | `i\|i` | index, useGlobalIndex | `(int, bool=False)` |
| setChannelPitch | 0xd5aa30 | 3 | `if\|iii` | index, value, pitchUnit, pickupMode, useGlobalIndex | `(int, float, int=0, int=PIM_None, bool=False)` |
| setStepParameterByIndex | 0xd5cec0 | 3 | `iiiii\|i` | index, patNum, step, param, value, useGlobalIndex | `(int×5, bool=False)` |
| midiNoteOn | 0xd5c800 | 3 | `iii\|i` | indexGlobal, note, velocity, channel | `(int×3, int=-1)` |
| incEventValue | 0xd58ef0 | 1 (VARARGS のみ) | `Ii\|d` | なし | `(int, int, float='1 / 24')` |
| processRECEvent | 0xd58e00 | 1 (VARARGS のみ) | `Iii` | なし | `() -> int` |

## 未解決 (次 run で決める)

1. **processRECEvent の引数不一致**: flapi は引数 0 だが、ハンドラは書式 `Iii` で 3 つの値を受け取り、その 3 値を下位関数へ渡している。flapi 側の署名が誤っている可能性がある。実機の呼出し例 (MCP 側の使用) で確かめるまでは確定しない。同名の `general.processRECEvent` (fn `0xd69f00`) は flapi 3 引数・書式 `Iii` で一致する。channels 側 (`0xd58e00`) だけ不一致。
2. **incEventValue**: ハンドラは `Ii|d` で受け、`res` 既定値 `0x3fa5555555555555` (= 1/24) を置いている (`movabs` で確認)。下位関数 0x1051330 の戻り規約は未解析。
3. **selectAll / selectOneChannel / setChannelPitch / setStepParameterByIndex / midiNoteOn**: ハンドラは `0xd5e620` 等の小関数を経由して呼ぶ (probe の呼び出し箇所で確認)。`0xd84740` 等の後段関数は未読。実処理の関数 (channel 配列の参照・選択状態の更新) の特定が必要。
4. 範囲外 code: 上記のどれも、範囲外時に返す code (`FL_E_RANGE` = 4 か、別の code か) は未確定。

## 次 run への提案 (同 issue で継続)

- 委譲先の関数ポインタ表 (`[rip+...]` が指す IAT 相当) を解決し、channel 配列へのアクセスを行う実関数を特定する。
- 特定できた関数ごとに、戻り値・範囲外 code を REPORT に追記してから `provider/fl_engine.c` に実装する。
- processRECEvent は flapi 署名の修正を先に行う (`analysis/flapi/` の生成元を直す。手で編集しない)。

## 受入条件の判定 (#1527)

- [ ] 7 関数の引数・戻り値・範囲外 code を PE 解析箇所つきで REPORT に残す — **部分達成** (引数書式・ハンドラ位置は残した。戻り値・範囲外 code は未確定)。
- [ ] `provider/fl_engine.c` に実装し `tests/provider_check.mjs` の実装数を更新 — **未達** (意味論未確定のため未実装。根拠の無い推測実装は避けた)。
- [ ] mock と C の diffs 0 — **未達** (実装 0 件のため対象なし)。
- [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` 48/48 — **未実行** (コード差分 0 のため再測定の対象外)。

## 追加解析 (2 回目 run): selectAll の委譲チェーン

- 測定: `FL_WIN64_DIR=tools/python/work/fl python3 analysis/flapi/pe_handler_probe.py selectAll` (`work/` は gitignore)。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`。
- 測定 (probe 出力): `0xd5b150` は先頭で `call 0xd5e620` を呼んだ後、`call 0xd843d0`・`call 0xd82c20`・`call 0x415c30` を続ける。関数全体は薄い委譲ではなく、`0xd5e620` の呼び出しの後段に `0xd843d0`・`0xd82c20`・`0x415c30` の呼び出しがある。
- 本体の記述 (`0xd5e620`・`0xd5e640`・`0xd82c20`・`0xc38bc0`・`0xd843d0` の中身) は本測定の出力に現れないため、ここには書かない。probe の出力で確認できたのは、`0xd5b150` が `call 0xd5e620` の後に `call 0xd843d0`・`call 0xd82c20`・`call 0x415c30` を呼ぶ、という呼び出し順だけである。
- 結論: selectAll の戻り値・範囲外 code は引き続き未確定。実処理の関数 (channel 要素の選択状態を書き換える箇所) は未特定。

## 受入条件 (#1527) の状態 (2 回目 run 時点)

- 未達のまま。次に読むべき対象は、`0xd5b150` の後段で呼ばれる `0xd843d0`・`0xd82c20`・`0x415c30` の本体 (測定方法を記録したうえで読む)。

## 追加解析 (3 回目 run): 後段 `0xd843d0`・`0xd82c20` の逆アセンブル

- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> [命令数]` (本 run で追加。`pe_disasm.py` のコミットを測定 commit とする)。展開は 2 回目と同じ (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`、1.7 秒)。
- `0xd5b150` の呼び出し順 (再確認): `call 0xd5e620` → 引数 `r8 = lea [rip-0x8a]` (= `0xd5b100`、未読) を置いて `call 0xd843d0` → `call 0xd82c20` (引数 `ecx` = 直前の戻り値の下位 32bit) → `call 0x415c30`。戻り値は `[rbp+0x68]` (= `0xd82c20` の `rax`) を返す。
- `0xd843d0` (引数: rcx=`[0xd5e620の戻り値]`、rdx=出力先、r8=`0xd5b100`、r9=0、スタック渡し 6 要素): `[rbx+0x50]` が非 0 なら `0xd84f30` で検査し、通らなければ `0xd84500` へ抜ける。以降は既定ブロックを `0xd841e0` で生成し、`0x4133f0` で詰め、`0x526190` で登録する。出力 `[rsi]` には `-2` (未設定の sentinel) を書く。**channel 固有の処理かは未確定** (汎用の登録・キュー投入に見える。`0x425210` の引数 `0x562` はエラー/ログ箇所の識別子と推定するが、未確認)。
- `0xd82c20` (引数 `ecx`): `ecx == 0` のとき関数ポインタ (`[rip+0x860485]`) を呼ぶ分岐がある。index 0 の特別扱いに見えるが、呼び先と戻り規約は未読。
- 結論: 後段は汎用の投入処理と検査であり、channel 配列の選択状態を書き換える箇所はまだ特定できていない。戻り値・範囲外 code は引き続き未確定。推測で `provider/fl_engine.c` に実装しない。
- 次に読む対象: `0xd5b100` (`r8` に渡される関数。選択処理の本体候補)、`0xd84f30`、`0x415c30`、`0xd5e620` の間接呼び先 (`[rip+0x881f8d]`)。

## 追加解析 (4 回目 run): `0xd5b100`・`0xd5e620`・`0xd5e640`

- 測定: `FL_WIN64_DIR=<絶対パス>/work/fl python3 analysis/flapi/pe_disasm.py <VA> [命令数]` (`FL_WIN64_DIR` は相対パス不可。`pe_disasm.py` は `$FL_WIN64_DIR/extracted/block00031_PE.bin` を読む)。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`。
- `0xd5b100` (selectAll の `r8` に渡される関数): `[rcx+0x60]` に `-2` を書く。グローバル (`[rip+0x889679]`) 経由の object の vtable `[rax+0x98]` を呼び、結果 `al` が非 0 なら `[rbx+0x60]=0` にして `0x11e8670` を呼ぶ。`0xd5b220` も同形 (呼び先 `0x11e8720`)。**sentinel `+0x60` の設定・解除の関数**と読める。選択状態の書換えかは未確定。
- `0xd5e620`: `[rip+0x881f8d]` の間接呼び出し 1 回だけの薄いラッパー (戻り値は素通し)。
- `0xd5e640`: `0xc38a10` (`lea rcx,[rip+0x7b9278]`) と `0x40feb0` (`rdx=[rip+0x23716]`、`rcx=rbx`) の戻り値を使い、`0xd5e620(rsi)` の戻り値の slot `[rax]` に `rbx` を書く。slot 書込み関数と読める。
- 結論: 選択状態を書き換える処理の所在は依然として未特定。戻り値・範囲外 code は未確定。`fl_engine.c` 実装は行わない。
- 次に読む対象: `0xc38a10`・`0x40feb0` (`0xd5e640` の戻り値の出所)、`0x11e8670`・`0x11e8720` (sentinel 解除後の呼び先)、`0xd5e620` の間接呼び先 (`[rip+0x881f8d]` の IAT 解決)。

## 追加解析 (5 回目 run): 委譲先の本体

- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (終了 0・各 1 回)。
- `0xd5e640`: `0xc38a10` の結果を `0xd5e620` に渡し、戻り値の slot `[rax]` に `rbx` を書く。`0x40feb0` の戻り値も使う。
- `0xc38a10`: ローカルに 2 つの値を置き、`0x4148b0`・`0x414200`・`0x414000` を呼ぶ。`[rip+0xa7f84c]` の間接呼び出しを経て、文字列 (`lea rcx,[rip+0x109]`) を扱う。**文字列・名前の解決に見える**。channel 配列の参照は確認できない。
- `0x40feb0`: `rcx` が非 0 なら `0x40fe90` で検査する。通らなければ `0x4096d0` を code `0xa` で呼び、`rcx` をそのまま返す。**検査失敗時の通知 (code 0xa) を出す関数の可能性**があるが、0xa が範囲外 code かは未確定。
- `0xd84f30`: `[rcx+0x2d8]`・`[rcx+0x3b8]`・`[rcx+0x2da]`・`[rcx+0x2d9]`・`[rcx+0x410]` の複数フラグを見る述語 (`al` を返す)。**channel 固有ではなく、汎用の状態判定**に見える。
- 結論: `0xd5e640` と `0xd84f30` の所在は分かったが、いずれも channel の選択状態を書き換えてはいない。範囲外 code (0xa か別か) の対応も未確定。戻り値・範囲外 code は未確定のまま。`fl_engine.c` 実装は行わない。
- 次に読む対象: `0x40fe90` (0xa を出す条件)、`0x4096d0` (code の受け取り先)、`0x11e8670`・`0x11e8720` (sentinel 解除後の呼び先)。

## 受入条件 (#1527) の状態 (3 回目 run 時点)

- [ ] 7 関数の引数・戻り値・範囲外 code を PE 解析箇所つきで REPORT に残す — **部分達成** (引数書式・ハンドラ位置・selectAll の後段の委譲は残した。戻り値・範囲外 code は未確定)。
- [ ] `provider/fl_engine.c` に実装 — **未達** (意味論未確定)。
- [ ] mock と C の diffs 0 — **未達** (実装 0 件)。
- [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` 48/48 — **未実行** (コード差分 0 のため)。

## 追加解析 (6 回目 run): 選択フラグの読み書きと全解除

- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (終了 0・各 1 回)。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`。
- `0xd5b100` (selectAll の `r8` に渡される関数): `[rcx+0x60]` に `-2` を書く。グローバル経由の object の vtable `[rax+0x98]` が真なら `[rbx+0x60]=0` にして `0x11e8670` を呼ぶ。`0xd843d0` 側から callback として渡される形なので、selectAll 本体の選択処理とは限らない。
- `0xfe8bb0`: `rcx` の配列 (件数 `[rcx+0x10]`・要素 `[rcx+8]`) から `edx` 番目を返す。範囲外は `0` を返す。
- `0xff8a90` (channel の選択フラグを書く関数): `[rbx+0x32c]` に `al` を書き、`[rbx+0x7c4]` の object の vtable `[+0x200]` を呼ぶ。`edx` が非 0 のときは `0xffac20` で検査してから書く。**選択フラグ `+0x32c` の setter と読める**。
- `0x11e8280`: 件数分 `0xfe8bb0` で要素を取り、`[+0x32c]` (選択フラグ) を見て最初に一致した添字を返す走査。**選択中 channel の検索**に見える。
- `0x11e8720`: 配列の全要素に対し `0xff8a90(item, 0)` を呼ぶ loop。**全 channel の選択を解除する処理**に見える (`deselectAll` 系の候補)。
- `0x40fe90` / `0x40feb0`: `0x40feb0` は引数が非 0 かつ `0x40fe90` の検査に通らないとき、code `0xa` で `0x4096d0` を呼ぶ。`0x4096d0` は code の下位 7bit を受けて通知する。**0xa が範囲外 code かは未確定**。
- 結論: 選択フラグの setter (`0xff8a90`)・全解除 (`0x11e8720`)・検索 (`0x11e8280`) の所在は確定。**selectAll / selectOneChannel がこれらを呼ぶかは未確認**のため、7 関数の戻り値・範囲外 code は引き続き未確定。`fl_engine.c` 実装は行わない。
- 未読 (次に読む対象): `0x11e8670` の `0xfe8bb0` 以降 (呼び出し後の戻り規約)、`0xff8a90` の `0xfdee80`、`0xffac20`、`0x410010`、`0x4096b0`。selectAll・selectOneChannel 本体 (`0xd5b150` → `0xd843d0` 以降) が `0x11e8720`・`0x11e8280` を呼ぶかの確認。
