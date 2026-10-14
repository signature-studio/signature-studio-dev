# PY-73 (#2547): channels.incEventValue・channels.midiNoteOn の PE 意味論 (途中記録)

親: #2500 (PY-70)。兄弟: #2499 (selectOneChannel)、#2544 (processRECEvent)、#2548 (setStepParameterByIndex)。前段: `tools/python/REPORT_PY39.md`。
既知類型との関係: 該当なし (lift 作業ではない。逆アセンブルによる解析)。

## 結論

- 2 関数の**引数書式・戻り経路・例外 code と文言**を PE から確定した。`midiNoteOn` の範囲外は内部 code `-4` (文言 `Index out of range`)、状態ゲートは `-2` (`Operation unsafe at current time`)。
- **未確定** (1 回目の run 時点。2 回目 (§7) で一部確定): `incEventValue` の戻り値の型と値 (下位関数 `0x1051330` の出力が int か float ビット列か不一致)、`incEventValue` と `midiNoteOn` の副作用 (本体の `0x1051330`・`0x10002a0` の大半が未読)。推測では実装しない方針により、`provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/channels_diff.mjs` は変更 0 件。
- 受入条件は 4 件中 1 件のみ部分達成。PR は `Refs #2547`。
- 2 回目の run (§7): incEventValue の戻り値の型 (flags bit1 で int / float ビット列に分岐)・範囲外 code (`0x1051330` 本体に例外経路なし)・副作用 (`0x1051330` 本体はスタック書込みのみ) を PE で確定。呼出し先 `0x1046a30` の副作用は未確定 (§7-3)。cur・lo・hi・flags の値源は未確定のため、provider・mock は未実装。
- 3 回目の run (§8): 事象表 (`0x1050f90` の探索経路) は eventId の初回参照で要素を作る遅延キャッシュと確定 (§7-4 の「初期化元」の未解決を解消。他の挿入経路は未確認)。残りは flags (`0x104d0d0`)・範囲と現在値 (`0x1046a30`)・midiNoteOn の本体と述語。provider・mock は引き続き未実装。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (実測 4.1 秒)。対象は `extracted/block00031_PE.bin`。
- 逆アセンブル: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_disasm.py <VA> <命令数>` (PY-39 の補助をそのまま使用)。
- 文言の読み出し (本 PR で追加): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_errmsg_probe.py` → 終了 0・4 件すべて OK・実測 0.032 秒 (load average 0.10、並列 1)。
- ネガティブコントロール: 分岐先 VA を 1 バイトずらす (`0xd82d18`→`0xd82d19`) と `lea ではない` で終了 (FAIL を確認)。
- 測定 commit: `18d7bb4b` (`pe_errmsg_probe.py` の最終変更 (docstring を `$ARTIFACTS_DIR` 表記にした 1 行)。コードを変えた最後の commit)。
- 差分 0 の証跡: `git diff 18d7bb4b HEAD -- tools/python/analysis/flapi/pe_errmsg_probe.py tools/python/analysis/flapi/pe_disasm.py` の出力は 0 行 (測定対象の 2 ファイル)。`18d7bb4b` 以降に main から取り込んだ他 PR のコード (`tools/python/provider` 等) は測定対象外。本 PR の commit は docs のみ。
- 検証範囲: PE の逆アセンブルと文言のみ。wasm・mock・C provider の実行 (`all_tools.mjs`) は未実行 (コード差分 0)。範囲外の主張はしない。

## 1. incEventValue (ハンドラ 0xd58ef0・書式 `Ii|d`)

| 項目 | PE 実測 (VA) |
|---|---|
| 引数解析 | 間接呼出し `[rax]` で `fmt` = `rip+0x58` (`Ii|d`)。eventId → `[rbp+0x3c]` (int)、step → `[rbp+0x38]` (int)、res → `[rbp+0x30]` (double) (0xd58f06-0xd58f1c) |
| 既定値 | `movabs rax, 0x3fa5555555555555` (= 1/24) を res に先に置く (0xd58ef8)。PY-15 の既定値修正と一致 |
| 解析失敗 | 戻り値 ≤ 0 で分岐 (0xd58f30 `jle 0xd58f5b`)。`mov ecx, eax` (0xd58f5b) で ecx = 解析の戻り値 eax (≤0) を渡し、`call 0xd82c20` (0xd58f5d) |
| 成功 | `0x1051330(ecx=eventId, edx=step, xmm2=(float)res, r9=0, [rsp+0x20]=0x7fffffff)` (0xd58f49)。戻り値 eax を**そのまま** PyLong に変換 (`[0x88b329]` 経由、0xd58f57)。`0xd82c20` は通らない |
| 範囲外 code | incEventValue 自体に検査は無い。検査は下位関数 1-b の内部にある (1 回目の記録。§7-3 で本体に例外経路が無いと確定) |

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
| 解析失敗 | 戻り値 ≤ 0 で分岐 (0xd5c856 `jle 0xd5c8d3`)。`mov ecx, eax` (0xd5c8d3) で ecx = 解析の戻り値 eax (≤0) を渡し、`call 0xd82c20` (0xd5c8d5) |
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
| midiNoteOn の本体 `0x10002a0` (note bit 31 経路・channel の扱い・note-on の状態変化) と `0x63a730`・書込み先 | midiNoteOn の副作用が未確定 | #2547 |
| `0x11d1430` の述語 (`[+0x88]` の vtable 先) | -2 ゲートの条件が未確定 | #2547 |
| 件数の出所 `0x8859a7` と要素配列の出所 `0x88596e` が同一オブジェクトか | 範囲検査と要素取得の整合が未確認 | #2547 |

## 5. 受入条件 (#2547) の判定

- [ ] 2 関数の戻り値・範囲外 code・副作用を PE 解析箇所つきで REPORT に残す — **部分達成**。incEventValue は §7 で戻り値の型と、`0x1051330` 本体の範囲外 code (例外経路なし)・副作用 (スタック書込みのみ) を確定。呼出し先 `0x1046a30` の副作用は未確定 (§7-3)。midiNoteOn は範囲外 (-4)・ゲート (-2) と文言のみ確定し、副作用は未確定 (§2・§4)。
- [ ] `provider/fl_engine.c` と `host/fl_mock.mjs` に 2 関数を実装 — **未達** (意味論が未確定。根拠の無い推測実装はしない)。
- [ ] `tests/channels_diff.mjs` の呼出し列に追加し、mock と C の diffs 0 — **未達** (実装 0 件のため対象なし)。
- [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok — **未実行** (コード差分 0 のため、再測定の対象外)。

## 6. 次 run への提案

- `0x1051330` の戻り値の型を先に確定する (`[rbp+0x2c]` の全書込み箇所を列挙し、int と float のどちらで読まれるかを見る)。
- `0x11d1430` の vtable 先 (`[+0x88]`) を解決し、-2 の条件を確定する。
- midiNoteOn は `0x10002a0` の note-on 経路で、channel の状態が変わる箇所 (書込み先オブジェクトのフィールド) を特定する。
- 確定した事項ごとに REPORT に追記し、provider 実装は意味論が揃った関数から行う。

## 7. 2 回目 run: incEventValue の戻り値の型・範囲外 code・本体の副作用の確定 (PE 実測)

測定 (commit は `e1e816c2` = origin/main 基点。コード変更 0 のため、測定 commit は基点のまま):
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (実測 5.6 秒)。`toolchain-retdec` を `$RUNNER_TEMP/retdec-root` に展開 (実測 2.6 秒)。
- RetDec: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 RETDEC_BIN=$RUNNER_TEMP/retdec-root/retdec/bin/retdec-decompiler bash analysis/flapi/pe_retdec.sh <out.c> 0x1051330-0x1051720` → 実測 7.2 秒、関数 1 件 (`0x1051330`-`0x10516f6`)。
- 逆アセンブル: `analysis/flapi/pe_disasm.py 1051330 260` (242 行、終端 `ret` は 0x10516f5)。RetDec の分岐と逆アセンブルを照合した。
- 定数の読出し (ファイルのバイト列): `0x10516f8`=0.0 (f32)、`0x10516fc`=1.0 (f32)、`0x1051700`=1.0 (f64)、`0x1051708`=100.0 (f64)。
- 文言・分岐の再照合 (fix 2 回目、`pe_disasm.py`): `0xf82484` = `movss xmm0, dword ptr [rbp+0x34]`、`0xd58f30` = `jle 0xd58f5b`、`0xd58f5b` = `mov ecx, eax`、`0xd58f5d` = `call 0xd82c20`、`0xd5c856` = `jle 0xd5c8d3`、`0xd5c8d3` = `mov ecx, eax`。§1・§2・§7-2 の記述はこれに合わせた。
- 差分 0 の証跡: 本 run のコード変更は 0。`git diff e1e816c2 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (commit `c301cb31` の時点で実行。以後の commit は docs のみ)。

### 7-1. 経路 (ハンドラ 0xd58ef0)

- 0xd58f28: 引数解析 (vtable 呼出し)。0xd58f49: `call 0x1051330` (ecx=eventId, edx=step, xmm2=res, r9=0, `[rsp+0x20]=0x7fffffff`)。0xd58f57: 戻り eax を PyLong 化して返す。0xd82c20 は解析失敗時のみ。
- **書き戻しの呼出しは無い**。ハンドラの `call` は上の 4 箇所だけ。

### 7-2. 下位関数 0x1051330 の計算 (RetDec と逆アセンブルの照合)

入力: eventId=ebx、step=esi、res=xmm6 (=xmm2)、ptr=rdi (=r9)、cur=`[rbp+0xb0]` (0x7fffffff なら `0x1046a30(eventId, 0, 2)` で置換)。
範囲: `0x1050f90(eventId, &lo, &hi)` で lo=`[rbp+0x28]`、hi=`[rbp+0x24]`、flags=戻り値 (r13)。range = max(hi-lo, 1)。

**式は ptr==0 の場合**: ハンドラは `xor r9,r9` (0xd58f3e) で ptr=0 を固定して渡すため、incEventValue から ptr≠0 の経路には到達しない。`0x1051330` 内で ptr を使うのは `test rdi,rdi` (0x10513c3・0x1051596) と、`f823f0(ptr, …)` への引数渡し 6 箇所 (0x10513f4・0x1051431・0x10514a3・0x10515c2・0x10515ff・0x105167d) のみ。ptr≠0 の `f823f0` (0xf82429 以降) はグローバル書込み `0x7388c9` と呼出し `0x63a660`・`0xbaffb0` を持つが、本節では扱わない。

分岐は flags の bit1 (`test r13b, 2`、0x10513ad) で決まる。

(A) bit1 = 1 (float 型。0x10513b3 以降): 現在値は `movss` で float として読む。
- step != 0 (0x105149d): `new = cur_f + (float)step × f823f0(ptr, res)`。`f823f0` は ptr==0 のとき xmm1 の値を xmm0 で返す (0xf823f0-0xf82408 で xmm1 を `[rbp+0x34]` に写し、0xf82484 `movss xmm0, dword ptr [rbp+0x34]` で返す)。clamp: new < 0.0 → 0.0、new > 1.0 → 1.0 (0x10514bf〜0x1051511)。
- step == 0 (0x10513bb): ptr==0 のとき `result = (float)(1 - Round(cur_f))` (0x10513c8〜0x10513df)。
- 結果は float のビット列として `[rbp+0x2c]` に書き、終端 0x10516dc の `mov eax,[rbp+0x2c]` で int として返す。

(B) bit1 = 0 (int 型。0x105151e 以降):
- 比例係数 res': eventId < 0x10000000 かつ `(eventId & 0xffff) == 0x302` なら `res' = 1.0 / range`。eventId == 0x40000005 なら `res' = 100.0 / range`。それ以外は `res' = res`。
- step != 0 (0x1051677): `k = Round(range × res')` (`cvtsd2si`、最近接偶数)。k == 0 なら `k = 1 - 2 × (res' の符号ビット)` (±1)。`new = cur + step × k`、`result = min(max(new, lo), hi)`。
- step == 0 (0x105157b、ptr==0 の場合): `pos = (float)((cur - lo) / range)`、`result = lo + Round((float)(1 - Round(pos)) × range)`。clamp は無い。

`0x40c660` は `cvtsd2si rax, xmm0` (Round)。

### 7-3. 結論 (incEventValue)

| 項目 | 確定内容 |
|---|---|
| 戻り値の型 | int (32bit)。bit1 の立つ event (float 型) では **float のビット列を int として返す**。bit1 == 0 の event では整数値。未解決 1 の「int か float か」は、event の flags で決まるという答え |
| 範囲外 code | `0x1051330` 本体に例外経路は無い (確定。`-2`・`-4` を返す経路も `0xd82c20` の呼出しも無く、分岐先は全て関数内、間接ジャンプ無し)。incEventValue の `0xd82c20` 呼出しは引数解析失敗のみ。呼出し先 `0x1046a30` 側の範囲外経路は未確定 (§7-4) |
| 副作用 | `0x1051330` 本体はスタックへの書込みのみ (確定。宛先メモリは全て `[rbp+...]`)。ハンドラにも書込みは無い。呼出しは 0x1050f90・0x1046a30・0xf823f0・0x40c660 の 4 種のみ。`0xf823f0` は ptr==0 で xmm1 の値を xmm0 で返すだけ (0xf82484)。`0x40c660` は cvtsd2si (Round)。**呼出し先の副作用は未確定**: `0x1046a30(eventId, 0, 2)` は sentinel のたびに必ず実行され、本体はロック `0x4232e0`・`0x423980` を呼び、`rax` 基準の書込み (0x1046f16・0x10472d0 ほか) を持つ (本体の大半は未読)。`0x1050f90` の副作用も未読 |

### 7-4. 残る未確定 (値源。実装はこれが決まるまで保留)

| 未確定 | 影響 | 起票先 |
|---|---|---|
| `0x1050f90` の表 (件数 `[0x5938ad]→[+0x10]`、配列 `[0x59388e]→[+8]`) の中身と初期化元。item の `[+4]`=lo、`[+8]`=hi、`[+0xc]`=flags | lo・hi・flags の値が決まらない | #2547 |
| 未登録 event の flags (`0x104d0d0`)・lo/hi (`0x1046a30(e,0,0x20)`・`(e,0x40000000,0x20)`) | 同上 | #2547 |
| 現在値 `0x1046a30(eventId, 0, 2)` の出所 (store) と getter の副作用 | cur が決まらない。provider の状態モデルに入らない | #2547 |
| midiNoteOn の本体 `0x10002a0`・`0x63a730`・`0x11d1430` (§2・§4 のまま) | midiNoteOn の副作用・ゲート条件が未確定 | #2547 |

provider・mock の実装は、上の値源 (cur/lo/hi/flags) を状態モデルとして決める run の後に行う。推測の初期値では実装しない。

## 8. 3 回目 run: 事象表は遅延キャッシュ・midiNoteOn のゲート参照 (PE 実測)

測定:
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (実測 5.6 秒)。逆アセンブルは `pe_disasm.py`、参照列挙は `pe_xref.py` (本 run で追加)。
- 測定 commit: `ef2df235` (`analysis/flapi/pe_xref.py` の追加。コードを変えた最後の commit)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_xref.py 15e4868` → 終了 0、命令 5,022,467、hits 9、stores 0、34.0 秒 (load average 0.46、並列 1)。
- ネガティブコントロール: `15e4869` (1 バイトずらし) → hits 0 (終了 0)。
- 差分 0 の証跡: `git diff ef2df235 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR の commit は REPORT と DOC_MAP のみ)。
- 表記の訂正: §7-4 の `[0x5938ad]`・`[0x59388e]` は rip 相対の disp 表記。実 VA は両方とも `0x15e4868` (次命令アドレス + disp)。値は §7 と同じ表を指す。

### 8-1. 表の実体 (VA `0x15e4868` = 表ポインタ G1、`.data`)

- G1 の再配置前の初期値は `0x193fc60` (`.bss` の静的オブジェクト P)。P は起動前ゼロ。
- G1 への rip 相対 store は 0 件。参照 9 件は全て load: `0x1050fb4`・`0x1050fd3` (`0x1050f90` の探索)、`0x10510bc`・`0x10510db`・`0x105112f` (同関数の挿入)、`0x11b35da` (初期化関数 `0x11b3500` 系の中。`0x663d80(..., r8d=0x10)` の確保結果を `[P]` へ書く)、`0x11c8107`・`0x11d3af7`・`0x11d3b0c`。
- よって表の本体は S = `[P]`。件数 = `[S+0x10]`、要素ポインタ配列 = `[S+8]`。確保直後の件数は未読 (`0x663d80` 未読)。

### 8-2. 事象表は eventId の初回参照で作られる (`0x1050f90` の実測)

- 二分探索 (`0x1050fb4`〜`0x105103c`) で見つかれば `lo = [item+4]`・`hi = [item+8]`・戻り値 = `[item+0xc]` (flags) (`0x1051019`〜`0x1051034`)。
- 見つからなければ (`0x105103e`〜`0x1051098`):
  - `flags = 0x104d0d0(eventId)` (`0x1051053`)。
  - `flags & 2 ≠ 0`: `lo = 0`・`hi = 0x100000` (`0x1051062`〜`0x1051068`)。
  - `flags & 2 = 0`: `lo = 0x1046a30(eventId, 0, 0x20)` (`0x1051075`〜`0x1051080`)、`hi = max(0x1046a30(eventId, 0x40000000, 0x20), lo + 1)` (`0x1051082`〜`0x10510a8`)。
- `0x10510aa` で同じ表を再探索し、無ければ `0x664090` で新要素を作って key = eventId・lo・hi・flags を書く (`0x105112f`〜`0x1051151`、`0x664090` の本体は未読)。戻り値は flags (`0x1051161`)。
- 結論: この探索関数の経路では、表は eventId の初回参照で要素が作られる遅延キャッシュ (他の挿入経路は未確認)。§7-4 の「表の中身と初期化元」は初期化元が「初回参照」と確定した。lo・hi・flags の値そのものは 8-3 の未確定に残る。

### 8-3. 残る未確定 (値源と midiNoteOn)

| 未確定 | 根拠 (VA) | 影響 | 起票先 |
|---|---|---|---|
| `0x104d0d0(eventId)` (flags 分類器) | `0x104d000` でオブジェクトを引き、`[+0x64]==2` で分岐。eventId の下位 16 bit と上位ビットで分岐。本体は未読 | 事象の flags (bit1 = float 型か) が決まらない | #2547 |
| `0x1046a30(eventId, sub, mode)` (汎用の照会) | mode 0x20 で範囲、mode 2 で現在値 (§7-4 と同じ)。0x590 のスタックフレームで本体の大半は未読 | lo・hi・cur が決まらない | #2547 |
| `0x664090` (挿入) と `[S+0x10]`・`[S+8]` の更新 | 挿入先の書込みは `0x105112f` の戻り先。本体は未読 | 件数・並びの正しさ | #2547 |
| midiNoteOn の述語 `0x11d1430` | `mov rax,[G3]; mov rax,[rax]; mov rax,[rax+8]; mov rcx,rax; mov rax,[rax]; call [rax+0x88]` (this = `[[G3]+8]`、vtable 経由の 1 段の間接呼出し)。G3 = VA `0x15e4790` は 2422 箇所から読まれる広域グローバル (store 0 件)。`0x11d1460` は同形で `+0x90` | -2 ゲートの条件が決まらない | #2547 |
| midiNoteOn 本体 `0x10002a0`・`0x63a730` | §2・§4 のまま | 副作用が決まらない | #2547 |

### 8-4. 受入条件への影響

- 1 件目 (戻り値・範囲外 code・副作用の REPORT 記録) は部分達成のまま。incEventValue の型・範囲外・本体副作用は §7 で確定。値源 (flags・範囲・現在値) は未確定。
- 2・3・4 件目 (provider・mock の実装、channels_diff、all_tools 48/48) は未達。値源が決まるまで実装しない。
- 次 run の提案: `0x1046a30` の mode 0x20 (範囲) 経路と `0x104d0d0` の flags 分類を読む。midiNoteOn は `[G3]+8` の vtable 先の解決が前提。
