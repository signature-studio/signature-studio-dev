# PY-73 (#2547): channels.incEventValue・channels.midiNoteOn の PE 意味論 (途中記録)

親: #2500 (PY-70)。兄弟: #2499 (selectOneChannel)、#2544 (processRECEvent)、#2548 (setStepParameterByIndex)。前段: `tools/python/REPORT_PY39.md`。
既知類型との関係: 該当なし (lift 作業ではない。逆アセンブルによる解析)。

## 結論

- 2 関数の**引数書式・戻り経路・例外 code と文言**を PE から確定した。`midiNoteOn` の範囲外は内部 code `-4` (文言 `Index out of range`)、状態ゲートは `-2` (`Operation unsafe at current time`)。
- **未確定**: `incEventValue` の戻り値の型と値 (下位関数 `0x1051330` の出力が int か float ビット列か不一致)、`incEventValue` と `midiNoteOn` の副作用 (本体の `0x1051330`・`0x10002a0` の大半が未読)。推測では実装しない方針により、`provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/channels_diff.mjs` は変更 0 件。
- 受入条件は 4 件中 1 件のみ部分達成。PR は `Refs #2547`。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (実測 4.1 秒)。対象は `extracted/block00031_PE.bin`。
- 逆アセンブル: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (PY-39 の補助をそのまま使用)。
- 文言の読み出し (本 PR で追加): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_errmsg_probe.py` → 終了 0・4 件すべて OK・実測 0.032 秒 (load average 0.10、並列 1)。
- ネガティブコントロール: 分岐先 VA を 1 バイトずらす (`0xd82d18`→`0xd82d19`) と `lea ではない` で終了 (FAIL を確認)。
- 測定 commit: `18d7bb4b` (`pe_errmsg_probe.py` の最終変更 (docstring を `$ARTIFACTS_DIR` 表記にした 1 行)。コードを変えた最後の commit)。
- 差分 0 の証跡: `git diff 18d7bb4b HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。本 REPORT を含む後続 commit は docs (本ファイルと `docs/DOC_MAP.md`) のみ。
- 検証範囲: PE の逆アセンブルと文言のみ。wasm・mock・C provider の実行 (`all_tools.mjs`) は未実行 (コード差分 0)。範囲外の主張はしない。

## 1. incEventValue (ハンドラ 0xd58ef0・書式 `Ii|d`)

| 項目 | PE 実測 (VA) |
|---|---|
| 引数解析 | 間接呼出し `[rax]` で `fmt` = `rip+0x58` (`Ii|d`)。eventId → `[rbp+0x3c]` (int)、step → `[rbp+0x38]` (int)、res → `[rbp+0x30]` (double) (0xd58f06-0xd58f1c) |
| 既定値 | `movabs rax, 0x3fa5555555555555` (= 1/24) を res に先に置く (0xd58ef8)。PY-15 の既定値修正と一致 |
| 解析失敗 | 戻り値 ≤ 0 で `call 0xd82c20(ecx=0)` (0xd58f5b) |
| 成功 | `0x1051330(ecx=eventId, edx=step, xmm2=(float)res, r9=0, [rsp+0x20]=0x7fffffff)` (0xd58f49)。戻り値 eax を**そのまま** PyLong に変換 (`[0x88b329]` 経由、0xd58f57)。`0xd82c20` は通らない |
| 範囲外 code | incEventValue 自体に検査は無い。検査は下位関数 1-b の内部にある (未確定) |

1-b. 下位関数 `0x1051330` (eventId=ecx、step=edx、res=xmm2、ptr=r9、value=`[rbp+0xb0]`)。読めた範囲:
- `[rbp+0xb0] == 0x7fffffff` (sentinel) なら `0x1046a30(eventId, 0, 2)` で現在値を取る (0x1051388-0x10513a3)。incEventValue は必ず sentinel を渡すため、呼出し側は現在値を持たない。
- `0x1050f90(eventId, &lo, &hi)` を呼ぶ。`0x1050f90` は配列 `[rcx+8]` を要素先頭の int (`[item+0]`) で二分探索する (0x1050fb4-0x1051014)。出力は `[rbp+0x28]`・`[rbp+0x24]` と戻り値 r13 (flags)。
- `eventId >= 0x10000000` で別経路 (0x1051523-0x1051531、`0x40000005` との比較あり)。
- flags の bit 1 (`test r13b, 2`、0x10513ad) で二分岐。立つ側は `step == 0` (0x10513b5) と `step != 0` (0x105149d) で分かれ、どちらも `res` と現在値から新しい値を作り、定数 `[rip+...]` で上下限を clamp して `[rbp+0x2c]` に書く。立たない側 (0x105151e 以降) は未読。
- **戻り値の不一致点**: 終端 0x10516dc は `mov eax, dword [rbp+0x2c]` (int として読む) だが、同じ `[rbp+0x2c]` へは `movss` (float) で書く箇所がある (0x10513df・0x1051489・0x1051498・0x1051514)。int と float ビット列のどちらが API の戻り値かは、本 run では確定できない。

## 2. midiNoteOn (ハンドラ 0xd5c800・書式 `iii|i`)

| 項目 | PE 実測 (VA) |
|---|---|
| 引数解析 | `iii|i`: indexGlobal → `[rbp+0x4c]`、note → `[rbp+0x48]`、velocity → `[rbp+0x44]`、channel → `[rbp+0x40]` (既定 -1 = `0xffffffff`、0xd5c808) |
| 解析失敗 | 戻り値 ≤ 0 で `0xd82c20(ecx=0)` (0xd5c8d5 経路) |
| 状態ゲート | `call 0x11d1430` の結果 `al` が偽なら内部 code `-2` (0xd5c861-0xd5c868) → `0xd82c20(-2)`。`0x11d1430` は global → vtable `[+0x88]` を呼ぶだけで、述語の意味は未確定 |
| 範囲検査 | `0 <= indexGlobal <= [obj+0x10] - 1` (obj = `*(*(0x8859a7))`、0xd5c86a-0xd5c886)。外れると `-4` (0xd5c8cc) → `0xd82c20(-4)` |
| 副作用 (範囲内のみ) | `call 0x63a730` の xmm0 に定数 `[rip+0x41]` を掛け、`*(double*)(*[0x884601])` に書く (0xd5c88b-0xd5c89f)。`0x63a730` と書込み先は未確定 |
| 要素取得 | `0xfe8bb0(*[0x88596e], indexGlobal)` → item (PY-39 REPORT の観測では範囲外で 0) |
| 本体 | `0x10002a0(rcx=item, edx=note, r8d=velocity, r9d=channel)` (0xd5c8c3)。戻り値は捨てる (0xd5c8c8) |
| 成功時の戻り | `eax = 0` → `0xd82c20(0)` → `0xc38bc0` (static 変数 `[rip+0xa7f719]` を返す。Py_None と推定、未実測) |

2-b. 本体 `0x10002a0` の読めた範囲:
- note の bit 31 (`0x80000000`) で分岐 (0x100032d)。立つ側は下位 31 bit を note とし、velocity ≤ 0 なら `[rbp+0x104]` に `-velocity`、そうでなければ `[rbp+0xf9]`、`(note >> 16) & 0xff` を `[rbp+0xfc]` に置いて 0x100050d へ (未読)。
- 立たない側 (0x100037e 以降): velocity ≤ 0 で 12 byte の要素の 0 番か 1 番を選ぶ (`[0x5e0413]` 基準、0x100037e-0x1000397)。以降は未読。
- channel (r9) の扱いは未読。

## 3. 戻り code と例外文言 (0xd82c20 の負の code 分岐)

`pe_errmsg_probe.py` の実測。FL_E 対応は `provider/fl_api.h` の定義と文言の一致で決めた (推定)。

| 内部 code | PE の文言 (VA) | FL_E (fl_api.h) | 本 PY の使用箇所 |
|---|---|---|---|
| -1 | `Unspecified error` (0xd82e24) | 2 (RuntimeError) | 確認のみ |
| -2 | `Operation unsafe at current time` (0xd82e44) | 3 (RuntimeError) | midiNoteOn の状態ゲート |
| -3 | `Range error` (0xd82e74) | 4 (IndexError) | 確認のみ |
| -4 | `Index out of range` (0xd82e8c) | 4 (IndexError) | midiNoteOn の範囲外 |

- `0xd82c20(ecx=0)` は先に `call [0x860485]` を呼び、非 NULL なら 0 (NULL) を返す (0xd82c3c-0xd82c50)。例外が既に立っていれば伝播させる分岐と読める (推定: `PyErr_Occurred`、未確認)。
- 負の code の文言は `PyErr_SetString` 相当の呼出し (`[0x861bf2]`) で、例外型は `*(*(*(0x85e38a)))` (0xd82daf-0xd82db9)。

## 4. 未解決 (次 run で決める。いずれも同 issue #2547 で継続)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| incEventValue の戻り値の型 (int か float ビット列か) と値。`0x1051330` の `[rbp+0x2c]` への書込み経路の統一 | provider の戻り値を決められない | #2547 (次 run) |
| `0x1051330` の flags bit 1 == 0 の経路 (0x105151e 以降) と `0x1046a30`・`0x1050f90` の出力の意味 | incEventValue の副作用と範囲外 code が未確定 | #2547 |
| midiNoteOn の本体 `0x10002a0` (note bit 31 経路・channel の扱い・note-on の状態変化) と `0x63a730`・書込み先 | midiNoteOn の副作用が未確定 | #2547 |
| `0x11d1430` の述語 (`[+0x88]` の vtable 先) | -2 ゲートの条件が未確定 | #2547 |
| 件数の出所 `0x8859a7` と要素配列の出所 `0x88596e` が同一オブジェクトか | 範囲検査と要素取得の整合が未確認 | #2547 |

## 5. 受入条件 (#2547) の判定

- [ ] 2 関数の戻り値・範囲外 code・副作用を PE 解析箇所つきで REPORT に残す — **部分達成**。書式・戻り経路・midiNoteOn の範囲外 (-4)・ゲート (-2) と文言は確定。incEventValue の戻り値の型と、両関数の副作用は未確定 (§1・§2・§4)。
- [ ] `provider/fl_engine.c` と `host/fl_mock.mjs` に 2 関数を実装 — **未達** (意味論が未確定。根拠の無い推測実装はしない)。
- [ ] `tests/channels_diff.mjs` の呼出し列に追加し、mock と C の diffs 0 — **未達** (実装 0 件のため対象なし)。
- [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok — **未実行** (コード差分 0 のため、再測定の対象外)。

## 6. 次 run への提案

- `0x1051330` の戻り値の型を先に確定する (`[rbp+0x2c]` の全書込み箇所を列挙し、int と float のどちらで読まれるかを見る)。
- `0x11d1430` の vtable 先 (`[+0x88]`) を解決し、-2 の条件を確定する。
- midiNoteOn は `0x10002a0` の note-on 経路で、channel の状態が変わる箇所 (書込み先オブジェクトのフィールド) を特定する。
- 確定した事項ごとに REPORT に追記し、provider 実装は意味論が揃った関数から行う。
