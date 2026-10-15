# PY-215 (#3568): device linked 系 8 関数の PE 意味論と C provider 実装 (縮小: 1 件実装・7 件未確定)

親: #3494 (PY-206)
既知類型との関係: 該当なし (lift 作業ではない)
製品 KPI: 対象外 (起動・GUI に関わらない)

## 結論

- 対象 8 関数の本体 VA を FLEngine PE (`block00031_PE.bin`) から引き、PyArg 書式・引数範囲・分岐を逆アセンブルで読んだ (§1)。
- **全分岐を PE で確定できたのは `device.getLinkedChannel` (PE 0xd75d30) の 1 件だけ**。これを `provider/fl_engine.c` と `host/fl_mock.mjs` に実装した。連動表は空と仮定 (§3)。
- 残り 7 件は **未確定** (§1 の表・§4 の未解決表)。時間切れにより縮小。`Closes #3568` は不可 (親判断)。
- issue 本文の前提 (「戻り値・status 経路 (`-6` を含む)」) は、読んだ分岐では `-6`/`-7` が出る経路を確認できなかった。読んだ 8 関数の範囲では、-1 入力の経路は `-1` の戻り値か status `-8` (Plugin not valid)。`-6`/`-7` の発生箇所は helper 側 (未読) にある。

## 1. 8 関数の VA 表

登録行は `provider/gen/fl_table.c`。entry は FLEngine PE の PyMethodDef、本体は逆アセンブルの関数先頭。書式 VA は PyArg 書式文字列の位置 (生バイトで読んだ)。

| 関数 (fl_table 行・arity/nreq・戻り型) | entry | 本体 VA | PyArg 書式 (VA) | 確定した分岐と戻り値・status | 状態 |
|---|---|---|---|---|---|
| findEventID (331・2/1・`i`) | 0x151d280 | 0xd75b60 | `i\|i` (0xd75bb8)。2 つ目の既定 0 ([rbp+0x28]) | PyArg 成功 → 0xf8c8e0(a, b) の戻り値を PyLong (0xd75b98〜0xd75ba8)。失敗 → 0xd82c20(eax) (0xd75baa) | **未確定** (0xf8c8e0 未読) |
| getLinkedChannel (338・1/1・`i`) | 0x151d2e0 | **0xd75d30** | `I` (0xd75ddc) | PyArg 失敗 → 0xd82c20(eax=0) (0xd75dce)。**index == -1 → -1** (0xd75d5b→0xd75dc0)。index ≥ 0 → 連動表を末尾から走査 (件数 obj+0x10、要素 +0x10 が index に一致 → 0xf8cae0(要素+8, …) の出力 +1 を PyLong)。**一致なし・表が空 → status 1 → None** (0xd75dbd→0xd75dce→0xd82c20) | **-1 と None の経路を確定** (表の供給元は仮置き: §3) |
| getLinkedInfo (339・1/1・`i`) | 0x151d320 | 0xd75ed0 | `I` (0xd75f38) | PyArg 失敗 → 0xd82c20(eax) (0xd75f2c)。**index == -1 → -1** (0xd75f1c)。index ≥ 0 → 0x1050f90(index, &o1, &o2) の bool (al) を PyLong (0xd75f0d〜0xd75f18) | -1 確定。else は **未確定** (0x1050f90 は +0 キーの二分探索で、not-found の戻り未読) |
| getLinkedParamName (340・1/1・`s`) | 0x151d300 | 0xd75de0 | `I` (0xd75ecc) | **index == -1 → status -8 (0xd75e6b→0xd75e72→0xd82c20)**。-8 の文言は "Plugin not valid" (0xd82f3c。REPORT_PY61 §4-2)。index ≥ 0 → 0x104f580 → 0x41c420 → 0x414000 → 文字列 (0xd75e2b〜0xd75e69) | -1 → -8 確定。else は **未確定** (0x104f580 未読) |
| getLinkedValue (341・1/1・`f`) | 0x151d2a0 | 0xd75bc0 | `I` (0xd75c30) | **index == -1 → double -1.0** (0xd75c08。定数は VA 0xd75c28 を読んで -1.0 を確認)。index ≥ 0 → 0x1051170(index, 0x7fffffff, 1) → PyFloat (0xd75bf0〜0xd75c06)。失敗 → 0xd82c20(eax) (0xd75c1d) | -1 → -1.0 確定。else は **未確定** (0x1051170 未読) |
| getLinkedValueString (342・1/1・`s`) | 0x151d2c0 | 0xd75c40 | `I` (0xd75d28) | **index == -1 → status -8** (0xd75cca→0xd75cd1→0xd82c20)。index ≥ 0 → 0x1046a30(index, 0, 2) → 0x104d2b0 → 0x41c420 → 0x414000 → PyUnicode (0xd75c83〜0xd75cc2) | -1 → -8 確定。else は **未確定** (helper 未読) |
| isDoubleClick (348・1/1・`b`) | 0x151d3a0 | 0xd76060 | `i` (0xd76184) | device 取得 0xd77da0 (0xd76088) → 0xd843d0 (dispatch、0xd76109)。戻り status [rbp+0x80] == 0 → [rbp+0x88] を変換して返す (0xd7610e〜0xd76129)。≠0 → 0xd7612f (status 経路) | **未確定** (dispatch 0xd843d0 と status 経路未読。戻り型 `b` の変換未確定) |
| linkToLastTweaked (350・4/2・`i`) | 0x151d4c0 | 0xd76c90 | `ii\|iI` (0xd76ea4)。PyMethodDef flags=3 (METH_KEYWORDS あり)。3 つ目の既定 0 ([rbp+0xa4])、4 つ目の既定 -1 ([rbp+0xac]) | 4 つ目が -1 のとき [グローバル] の値で置換 (0xd76d43〜0xd76d4c)。device 取得 0xd77da0 (0xd76cc1)。kw 解析の呼出し (0xd76d2a) の後の分岐 (0xd76d32) | **未確定**。fl_table の `iibi` と PE `ii\|iI` は型が不一致 (3 番目 `b` vs `i`、4 番目 `i` vs `I`) |

補足:
- 逆アセンブル基点は `analysis/flapi/pe_handler_probe.py` と `analysis/flapi/pe_disasm.py` (`FL_WIN64_DIR` 指定)。書式文字列は生バイトで読み直した (probe の表示だけに頼らない)。
- 引数名 (linkToLastTweaked の `controlIndex`・`channel`・`eventID`・`globalLink`) は `REPORT_PY15.md` (kw 名と拒否件数) と `REPORT_PY16.md` (eventId の既定 `midi.REC_None`) の経緯どおり。PE 側の 4 つ目の既定 -1 は `globalLink` 相当。
- 戻り値の型 (`i`・`f`・`s`・`b`) と arity は `provider/gen/fl_table.c` の行に従う (getLinkedValue は `f`、名前系は `s`)。
- **getLinkedChannel・getLinkedInfo・getLinkedValue の参照する表の global は別の RIP 相対アドレス** (0xd75d5d・0x1050fb4・0x1050fa8 付近)。同一表かどうかは未確定。

## 2. 実装した関数: device.getLinkedChannel

- C (`provider/fl_engine.c`): `FL_H(device, getLinkedChannel)`。`-1` → `fl_ret_i(-1)`。それ以外 → `fl_ret_none`。device・link の割当 (`dev_assigned` / `link_assigned`) は見ない (PE 0xd75d30 に -6/-7 の分岐が無い)。
- mock (`host/fl_mock.mjs`): 同じ意味論 (`argI(a, 0, 0)` が -1 なら -1、それ以外は undefined = None)。`arity(a, 1, 1)`。
- 「なし」の確認: PE 0xd75d30 は device getter 0xd77da0 を呼ばない (連動表はグローバル直参照)。よって assigned/unassigned の両方で同じ結果。

## 3. 未確定事項と仮置き

| 項目 | 状態 | 扱い |
|---|---|---|
| 連動表 (getLinkedChannel が走査する表) の件数と要素の供給元・初期状態 | **未確定** | **仮置き: 表は空 (件数 0)**。よって index ≥ 0 は not-found → status 1 → None。C と mock の両方で同じ仮置き |
| 一致時の 0xf8cae0 の出力 (`o2 + 1` の意味) | 未確定 | 実装なし (表が空なので到達しない前提) |
| not-found の status 1 → None | PE 確定 (eax = PyArg 成功の 1 が残る経路。この経路に call は無い)。0xd82c20 の「status ≥ 0 → None」は REPORT_PY61 §4 の行に依る | 確定扱い |
| 書式 `I` と fl_table の `i` | 差は int32 範囲外の値 (`I` は overflow 検査なし) | 境界値のみ。実害なしと判断 |
| None 引数 (`getLinkedChannel(None)`) | A_INT / argI は None を既定値 (0) として扱う。PyArg `I` は None を拒否 (PE 0xd75d3b) | 既存の全 device/channel 関数と同じ差。本 PR では直さない |

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 連動表の供給元・初期状態 (getLinkedChannel の表・getLinkedInfo の二分探索表) | getLinkedChannel の index ≥ 0 (None 仮置き)、getLinkedInfo 全体 | 子 issue (親: #3568) |
| 0xf8cae0 (一致時の出力) と 0x1050f90 の not-found 戻り (0x105103e 以降) | getLinkedChannel の一致経路、getLinkedInfo の else | 子 issue (親: #3568) |
| 0x1051170 (getLinkedValue)・0x1046a30/0x104d2b0 (getLinkedValueString)・0x104f580 (getLinkedParamName) の意味 | 3 関数の index ≥ 0 の戻り値 | 子 issue (親: #3568) |
| findEventID の 0xf8c8e0 | findEventID 全体 | 子 issue (親: #3568) |
| isDoubleClick の dispatch 0xd843d0 と status 経路 0xd7612f、戻り型 `b` の変換 | isDoubleClick 全体 | 子 issue (親: #3568) |
| linkToLastTweaked の書式不一致 (fl_table `iibi` と PE `ii\|iI`) と 4 つ目 -1 の置換先 (グローバル)、kw 解析 (0xd76d2a) の後の分岐 | linkToLastTweaked 全体。引数型の変換の誤りの恐れ | 子 issue (親: #3568) |
| `-6`/`-7` の発生箇所 (issue 本文の前提) | 読んだ 8 関数の確定分岐には無い。helper 側に有るかは未確定 | 子 issue (親: #3568) |
| 縮小: 8 関数中 1 件のみ実装。`Closes #3568` は不可 | 親が issue の範囲を判断 | 親 (PR 本文に明記) |
| 兄弟 PR #3570 の手法 (`REPORT_PY206.md`) は時間切れで未参照 | 手法の差の確認が未了 | PR 本文 |

## 5. 検証

測定 commit: `d911ecb97` (`feat(python): device getLinkedChannel を PE 0xd75d30 の意味論で C provider・mock に実装 (PY-215, #3568)`。コードを変えた最後の commit)。基点: `origin/main` = `1d04852b0`。検証 HEAD: 本 REPORT の commit。`git diff d911ecb97 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 REPORT と DOC_MAP だけが後続)。

素材: fl-win64 は `tar --zstd -xf <artifacts>/fl-win64.tar.zst -C <展開先>` (5.6 秒)。emsdk は `toolchain-emsdk.tar.zst` を展開 (3.7 秒) し、provider の build は `EMSDK_ENV=<展開先>/emsdk/emsdk_env.sh` で実行。`build_cpython_wasm.sh` と `build_flpy.sh` は既定の emsdk (`[EMSDK]`、同じ 6.0.12) を使った。

| 検査 | コマンド | rc | 所要 | 結果 |
|---|---|---|---|---|
| 入力取得 | `FL_WIN64_DIR=<展開先> bash fetch_inputs.sh` | 0 | 0.3 秒 | win64 の DATA block から midi.py・utils.py・MCPTools.pyc。fl-stubs は git clone |
| CPython wasm | `bash build_cpython_wasm.sh` | 0 | 246.6 秒 | libpython3.12.a・python.wasm |
| flpy | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | 0 | 6.2 秒 | flpy.js/wasm/data (表は追跡済みを使用) |
| provider ビルド (変更前) | `bash provider/build.sh` | 0 | 14.8 秒 | flprov.js/wasm |
| provider ビルド (変更後) | `bash provider/build.sh` | 0 | 1.4 秒 | 警告なし |
| provider_check (変更前) | `node tests/provider_check.mjs` | 0 | 0.36 秒 | functions 435・**implemented 168**・unimplemented 267・PASS |
| provider_check (変更後) | `node tests/provider_check.mjs` | 0 | 0.37 秒 | functions 435・**implemented 169**・unimplemented 266・PASS (+1) |
| device_diff (変更前) | `node tests/device_diff.mjs` | 0 | 0.05 秒 | calls 11・rejects 4・midi_out 10・diffs 0・PASS |
| device_diff (変更後) | `node tests/device_diff.mjs` | 0 | 0.05 秒 | calls 11・link_calls 6・rejects **7** (+3)・linked_channel `[-1,null,null,-1,null,null]`・**diffs 0**・PASS |
| all_tools (wasm・変更前) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 0 | 2.1 秒 | total 48・**ok 48**・soft_error 0・raised 0 |
| all_tools (wasm・変更後) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 0 | 2.1 秒 | total 48・**ok 48**・soft_error 0・raised 0 |
| all_tools (JS mock・変更後) | `node tests/all_tools.mjs` | 0 | 2.1 秒 | total 48・**ok 48** |

ネガティブコントロール: `host/fl_mock.mjs` の `device.getLinkedChannel` の -1 の戻り値を -2 に一時変更 → `node tests/device_diff.mjs` は **rc 1** (差分 2 件: dev/link 両方の assigned・unassigned で mock -2 / wasm -1 を検出)。元に戻し、`sha256sum` が変更前と一致 (c9d5ef8c…) することを確認してから commit した。

## 6. main 取り込み後の再測定 (PR #3848 の競合解消)

PR #3848 は main (`f4d8cf90e`) が先に進んだため競合した。rebase・force は使わず、`origin/main` を merge した (merge commit `1a66791d4`)。競合は `tests/provider_check.mjs` の実装判定の行と件数だけで、main 側の判定 (`pe132` など) を残し、本 PR の `pe215` を足した。件数は main の 171 / 264 から **172 / 263** になる。

測定 commit (コードを変えた最後の commit): `1a66791d4` (merge)。`git diff 1a66791d4 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本節の commit は REPORT だけ)。

| 検査 | コマンド | rc | 結果 |
|---|---|---|---|
| provider ビルド | `bash provider/build.sh` | 0 | flprov.js / flprov.wasm 生成 |
| provider_check | `node tests/provider_check.mjs` | 0 | functions 435・implemented **172**・unimplemented 263・PASS |
| device_diff | `node tests/device_diff.mjs` | 0 | linked_channel `[-1,null,null,-1,null,null]`・**diffs 0**・PASS |
| all_tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 0 | total 48・**ok 48**・host_calls 37,425 |
