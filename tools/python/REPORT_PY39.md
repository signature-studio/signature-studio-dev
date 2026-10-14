# PY-39 (#1527): channels 操作 7 関数の PE 解析 (ハンドラ位置・書式・引数)

親: #1515 (PY-37)。前段: #1336 (PY-32, 棚卸し)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 7 関数 (selectAll / selectOneChannel / setChannelPitch / setStepParameterByIndex / midiNoteOn / incEventValue / processRECEvent) の**ハンドラ位置と引数書式は PE から確定**した。
- **意味論 (戻り値・範囲外 code・副作用) は未確定**。各ハンドラは下位関数へ薄く委譲しており、実処理の所在まで追えていない。推測では実装しない。
- 1〜6 回目は解析のみ (コード変更 0 件)。**7 回目 run で `selectAll` の経路を RetDec 逆コンパイルで確定した (経路は確定・選択値とゲートは未確定)**。選択値 (`ffac20`) の判定に依存するため、C provider と mock への実装は見送った (`c6485d55` の実装は `481bcd62` で戻した。下の「7 回目 run」節)。残り 6 関数は未実装のまま子 issue に分離した。受入条件は未達 (`Refs #1527`)。
- PY-69 (#2499): `selectOneChannel` の意味論を PE で確定し、C provider と mock に実装した (末尾の PY-69 節)。`setChannelPitch` は未確定のため子 #2542 に分けた。

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

## 7 回目 run: selectAll の経路を RetDec で確定 (選択値・ゲートは未確定・実装は見送り)

- 測定 commit: `481bcd62` (コード変更の最後の commit)。`c6485d55` で入れた selectAll の実装 (provider・mock・テスト) は `481bcd62` で `c6485d55^` (`54bacdc0`) の状態へ戻した。
- 既知類型との関係: 該当なし (意味論の読解。lift 出力は実行に使っていない)。

### 素材・ツール・測定

- 素材: `$ARTIFACTS_DIR` の `fl-win64.tar.zst` から `block00031_PE.bin` (PE のみ 2.8 秒) と `block24429/24430/25159/24618_DATA.bin` (2.8 秒) を展開。逆コンパイルは `toolchain-retdec` の `retdec-decompiler` (RetDec v5.0、[RETDEC])。emsdk は `toolchain-emsdk` ([EMSDK])。
- 経路の再現 (1 コマンド・6 範囲で 9.0 秒・関数 9 件検出):
  `FL_WIN64_DIR=<展開先> RETDEC_BIN=<[RETDEC] の retdec-decompiler> bash analysis/flapi/pe_retdec.sh <out.c> 0xd5b150-0xd5b230,0xd843d0-0xd84530,0xd5b100-0xd5b150,0x11e8670-0x11e8715,0xff8a90-0xff8b60,0xffac20-0xffacb0`
- 段ごとの再現範囲 (表の段番号に対応):

| 段 | 再現範囲 (`pe_retdec.sh` の範囲指定) |
|---|---|
| 1 | `0xd5b150-0xd5b230` (`0xd5b1a0` で途中切れするため `0xd5b230` まで必要) |
| 2 | `0xd843d0-0xd84530` |
| 3 | `0xd5b100-0xd5b150` |
| 4 | `0x11e8670-0x11e8715` |
| 5 | `0xff8a90-0xff8b60`・`0xffac20-0xffacb0` |
| 6 | 本 run の範囲に含めず未再現 (前 run の記録のみ) |

- 注意: RetDec は stack 引数を落とすことがある (`d5afc0` の `d843d0` 呼出し)。引数は `pe_disasm.py` の逆アセンブルで照合する。
- 注意: RetDec は `0x15e3a60` を定数 `g2 = 0x154528c` として読み、`ffac20` の比較先を誤る (下の 5' を参照)。RetDec の出力をそのまま採らず、逆アセンブルで照合した。

### selectAll の経路 (PE 実測。RetDec 出力と逆アセンブルの照合)

| 段 | VA | 働き | 再現 |
|---|---|---|---|
| 1. handler | 0xd5b150 | `obj = *d5e620()` → `d843d0(obj, &status, cb=0xd5b100, …)` → `d82c20(status)` を返す | 範囲 1 |
| 2. 要求ラッパ | 0xd843d0 | `*result = -2`。`obj+80` (`[rbx+0x50]`) が非 0 かつ `d84f30(obj+80)` が偽なら `0xd84500` で return (-2 のまま)。通ると要求レコード `rec` を作り、引数を `rec+24..+64`、callback を `rec+88` に格納。`425210(…,1378)` と `526190(0,&v)` を呼ぶ (中身は未読)。`*result = rec+96` | 範囲 2 (asm `0xd843f0`〜`0xd84403` で gate を確認) |
| 3. callback | 0xd5b100 | `rec+96 = -2`。`v = *(*(*0x15e4790)+8)` の先頭 byte が 0 なら return (-2 のまま)。非 0 なら `rec+96 = 0` で `0x11e8670(v)` | 範囲 3 |
| 4. 全 channel | 0x11e8670 | 先頭で選択中 channel の UI 処理 (`0x11e8280`・`0xff8b60`) を行い、`fe8bb0(g1, i)` で index 0..count-1 の全 channel に `0xff8a90(item, 1)` | 範囲 4 |
| 5. 選択フラグ | 0xff8a90 | `item+812` (byte) = `a2 != 0 ? ffac20(item) : 0` (asm `0xff8a90`〜`0xff8abe`) | 範囲 5 |
| 5'. 選択フィルタ | 0xffac20 | `p = *(qword*)0x15e3a60`。`return (*(int32*)p < 0) \|\| (*(int32*)(item+0x798) == *(int32*)p)` (asm `0xffac20`〜`0xffac43`)。**0 を返すのは `*p >= 0` かつ `item+0x798 != *p` の channel** | 範囲 5 |
| 6. 戻り値 | 0xd82c20 | status 0 → 正常 (None 扱い。`c38bc0()` は未読)。-1 Unspecified error / -2 Operation unsafe at current time / -3 Range error / -4 Index out of range。**本 run では未再現** | 前 run の記録 |

### 5' の判定 (B1: 全 channel 選択の前提)

- `0xffac20` の比較先は `*p` (ポインタ先の int32) である。RetDec の `g2` (ポインタの値 `0x154528c` を定数として読んだもの) は誤読。
- `0x15e3a60` (`.data` 内) の 8 byte はファイル内で `0x154528c` (`.data` 内の VA)。その先の int32 のファイル内初期値は **-1**。よって**ロード直後は `*p < 0` となり `ffac20` は全 channel で 1 を返す**。
- ただし、`*p` の**実行時**の書込み元と通常状態の値は未追跡 (`0x154528c` への直接参照と、`0x15e3a60` 経由の間接書込みの両方を含む)。`obj+80` の通常時の値と `d84f30`、callback の状態 byte (段 3) の通常時の値も未確定。
- したがって「全 channel sel=1」は初期値でのみ成立する前提であり、通常状態での成立は未確定。推測で FL と食い違う値を返さないため、実装は見送る。

### 実装の扱い (commit 481bcd62)

- `c6485d55` の selectAll 差分 (`provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/channels_diff.mjs`・`tests/provider_check.mjs`) を `481bcd62` で戻した。`git diff c6485d55^ 481bcd62 -- tools/python/provider tools/python/host tools/python/tests` は 0 行。
- 未モデル化 (実行時値に依存し静的解析では確定できない): (a) 段 2 の `obj+80` と `d84f30` の判定、段 3 の状態 byte。(b) 段 5' の `*p` の実行時値と `item+0x798` の意味 (初期値 -1 は確認済み)。(c) UI 側の副作用: `0xff8b60` 本体 (先頭の `ret` まで 102 命令) に `item+812` (`+0x32c`) への書込みは無い。呼出先 `0x1311d90`・`0x4232e0`・`0x1060420`・`0x423980`・`0xfdee80` は未読。

### 検証 (commit 481bcd62)

| 検査 | 結果 | 所要 |
|---|---|---|
| `bash provider/build.sh` | 成功 (ハンドラ 70) | 1.401 秒 |
| `node tests/channels_diff.mjs` | 53 呼出し・diffs 0・PASS | 0.062 秒 |
| `node tests/provider_check.mjs` | `{"functions":435,"implemented":70,"unimplemented":365,"mcp_static":60,"PASS":true}` | 0.373 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` | 2.052 秒 |
| `node tests/all_tools.mjs` (mock) | 48/48 ok・host_calls 37425 | 2.033 秒 |
| 前提: `fetch_inputs.sh` (`FL_WIN64_DIR=work/fl`) / `build_cpython_wasm.sh` / `FLPY_SKIP_TABLE=1 EMSDK_DIR=<[EMSDK]> build_flpy.sh` | 成功 | 0.612 秒 / 240.835 秒 / 6.042 秒 |

- 測定時 load average (1 分値): 0.53 (4 core)。
- 差分 0 の証跡: `git diff c6485d55^ 481bcd62 -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (測定 commit のコードは親 `54bacdc0` と同一)。本 REPORT を含む後続 commit でも `git diff 481bcd62 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行。

### 受入条件 (#1527) の状態 (7 回目 run 時点)

- [x] 7 関数の引数書式・ハンドラ位置 (1〜4 回目)
- [部分] 戻り値・範囲外 code: selectAll は経路のみ確定 (段 6 の写像は未再現)。selectOneChannel は範囲外 -4 のみ確定 (下記)。他 5 関数は未確定
- [未達] `fl_engine.c` 実装: 0 件 (selectAll は選択値とゲートが未確定のため見送り)
- [部分] mock と C の diffs 0: 既存の 53 呼出しで diffs 0。selectAll は対象外
- [x] `all_tools` 48/48 (wasm)

### selectOneChannel (7 回目 run 時点の読解。以下の訂正あり)

- 訂正 (PY-69 節): 「排他選択の副作用はこの経路では見えない」「`0x11e84a0(item+1940)` は副作用なし」は誤り。`0x11e84a0` は全件ループで `0xff8a90` を呼び、選択フラグ `+812` (`0x32c`) を書く。stack 引数の出所も PY-69 節で確定した。
- `0xd5afc0` (handler): `d843d0(*d5e620(), &status, cb=0xd5af30, …)`。index と useGlobal は stack 渡しで、RetDec では出所が落ちている。前段の `*0x15e45a8` による分岐 (`v3 >= 1`) の意味も未確定。
- callback `0xd5af30`: `rec+96 = -2`。状態 byte 判定は selectAll と同じ。`index = rec+24`、`useGlobal = rec+32`。`0x1005730(index, useGlobal, &item)`: useGlobal=0 は表 `*0x15e0128` (channel rack)、≠0 は表 `*0x15e2218`。範囲外は 0 を返し `rec+96 = -4`。成功時は `rec+96 = 0`、`0x11e84a0(item+1940)` (表アクセサ。副作用なし)、`0xffaf80(item)`。
- `0xffaf80` は `0x609710` (item+144..+156 から矩形 4 値) と `0x40c660` (double→int) を呼ぶ UI 座標計算で、選択フラグ `+812` は書かない。排他選択の副作用はこの経路では見えない。次に読む対象: `0xff8a90` の PE 内呼出元。子 [PY-69] (#2499) で扱う。

### 残り 6 関数 (本 run では未解析)

- `setChannelPitch` (0xd5aa30)・`setStepParameterByIndex` (0xd5cec0)・`midiNoteOn` (0xd5c800)・`incEventValue` (0xd58ef0)・`processRECEvent` (0xd58e00) は逆コンパイル未実施。`processRECEvent` は flapi 署名の修正が先。`setChannelPitch` は [PY-69] (#2499)、残り 4 関数は [PY-70] (#2500)。

### 次 run への提案

- selectAll: `0x154528c` (`*p` の指す int32) への書込みを追う。直接の rip 相対参照と、`0x15e3a60` を読んでから書く間接参照の両方が対象。全ての書込みが負の値に限られるなら、段 2 の `obj+80`・`d84f30` を確認してから実装を再検討する。
- 間接参照の追跡はこの run では未実施 (`pe_disasm.py` の線形走査は未知命令で止まるため、再同期が必要)。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| selectAll の選択値: `*p` (`0x154528c` の int32) の実行時の値と書込み元 (ロード時の初期値は -1) | 通常状態の値が 0 以上なら `item+0x798 == *p` の channel だけが選ばれる。実装は見送り | 未解決表のみ (親 #1527 に残す。子は起票しない) |
| selectAll のゲート: `obj+80` の通常時の値と `d84f30`、callback の状態 byte | 通常時にゲートが通るかが未確認 (通らないと -2 で何もしない) | 未解決表のみ (親 #1527 に残す) |
| `ff8b60` の呼出先 `0x1311d90`・`0x4232e0`・`0x1060420`・`0x423980`・`0xfdee80` | 選択フラグ `+812` への間接的な影響は未読 | 未解決表のみ (親 #1527 に残す) |
| `selectOneChannel` の前提ゲート `0xd5af58`・後段ゲート `0xd82c6a`・選択ゲート `0xffac20`・`useGlobalIndex>0` の表 (排他選択と stack 引数の出所は PY-69 節で確定) | 未モデル (C provider は常に選択する) | #2542 (PY-69 節の未解決表) |
| `setChannelPitch` の意味論 | 未実装 | [PY-69] #2499 |
| `setStepParameterByIndex`・`midiNoteOn`・`incEventValue` の意味論と `processRECEvent` の flapi 署名修正 | 未実装 4 件 | [PY-70] #2500 |
| `d843d0` の `425210`・`526190` (同期待ち) の中身 | 同期実行の前提 (callback 完了後に `*result` を読む) が未確認 | 未解決表のみ (親 #1527 に残す) |
| `c38bc0()`・`0xd82c20` の戻り値の写像 | None 扱いと範囲外 code の根拠が未確認 | 未解決表のみ (親 #1527 に残す) |

## PY-69 (#2499): selectOneChannel の意味論を確定

- 結論・処理経路・排他選択・未解決は [REPORT_PY69.md](REPORT_PY69.md) (250 行上限のため分割移動)。`selectOneChannel` は C provider と mock に実装済み (測定 commit は REPORT_PY69.md の検証節)。

## 追加解析 (#2548 の run): setStepParameterByIndex の呼出し経路・status・副作用

本文は `REPORT_PY39_2548.md` に分割移動した (250 行上限のため)。結論: 呼出し経路・status 表・範囲外 `-4`・param 3〜8 の副作用を PE で確定。param 0〜2・item 列挙・述語の型は未確定で、子 issue #2581 (`[PY-78]`) に移した。
