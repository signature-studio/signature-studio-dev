# PY-117 (#2959): muteTrackLock の準備判定 (call [rax+0x98]・偽なら -2) の呼出し先を逆アセンブルで確定し、C・mock に入れる

親: #2027 (PY-102)。前段: `tools/python/REPORT_PY61.md` §3 (core 0xd56510)・`tools/python/REPORT_PY102.md` §5・`tools/python/REPORT_PY94.md` (`general.safeToEdit` は同じ式)。
既知類型との関係: 該当なし (lift の欠陥ではない。C・mock の未モデル)。

## 結論

- 準備判定 `call [rax+0x98]` (0xd56535) の呼出し先を **VMT[0x98] = 0x1262b80** と確定した。`general.safeToEdit` (PY-94) と同じ式 (`[[[0x15e4790]]+8]` の vtbl `+0x98`) である。
- 真偽条件 (0x1262b80 の逆アセンブル): 真 ⇔ `byte[*0x15e04a8]==0` && `byte[*0x15e0ff0]==0` && `!C.VMT[0x48]()` && `dword[*0x15e30f8 + 0x168] <= 0`。3 つのガードは `.bss` 側で、PE の静的内容には無い (実行時値は未測。§2)。
- C・mock に、準備判定が偽のとき `FL_E_UNSAFE` (code 3・文言 "Operation unsafe at current time") を返す経路を入れた。判定は index・value の検査より先 (PE 0xd56510 の順: -2 → 0 → -4)。偽のとき lock は変えない。
- 試験用に `setSafeEdit` を足し (mock: `st.safeEdit`・wasm: `fl_engine_set_safe_edit`)、`tests/playlist_diff.mjs` に偽の状態の差分検査を入れた。

## 受入条件の判定

| # | 受入条件 (issue #2959) | 判定 | 根拠 |
|---|---|---|---|
| 1 | `0xd56535` の呼出し先を特定し、真偽の条件を REPORT に書く | **達成** | §1・§2。`tools/python/analysis/flapi/py117_ready_pred.py` (各段を assert。全段 PASS) |
| 2 | 偽のとき `playlist.muteTrackLock` が `FL_E_UNSAFE` を返す (C と mock) | **達成** | `provider/fl_engine.c` (muteTrackLock)・`host/fl_mock.mjs`。§3 |
| 3 | `playlist_diff.mjs` に準備前の呼出しを加え、C と mock の差分 0 | **達成** | `tests/playlist_diff.mjs` の偽の状態の節 (5 呼出し)。差分 0。§4 |
| 4 | `provider_check.mjs`・`FL_ENGINE=wasm all_tools.mjs` (48/48) が通る | **達成** | §4 |

## 1. 呼出し先の確定 (PE 逆アセンブル・静的)

| 段 | VA | 内容 |
|---|---|---|
| this の源 | 0xd56521〜0xd5652f | `this = [[[G]]+8]`。G = `0x15e4790` (.data) |
| B (singleton) | 0x976a90 → ctor 0x976b60 | 遅延生成。ctor は `+0x8` を 0 にするだけ (C は入れない) |
| C の生成 | 0x1263540・0x1264100 | `call 0x976a90` の後、`0x125da90(class=[0x125b0f8], dl=1)` の戻り値を `[B+8]` へ格納 |
| C の確保 | 0x125da90 → 0x410320 | `dl>=0` のとき `call [VMT-0x30]` (= NewInstance `0x40f960`)。確保した C を初期化して返す |
| C の VMT | `[0x125b0f8]` = `0x125b1c0` | クラス参照の定数 (.text 内) |
| 呼出し先 | **VMT[0x98] = 0x1262b80** | 0xd56535 の `call [rax+0x98]` |

`[B+8]` への格納は 2 箇所 (0x1263540 と 0x1264100) だけで、どちらも同じ VMT を使う。他の `[G 経由 +8]` 書込みの候補 (0xedff9f・0xeef1a1・0x11c44cc) は、`+8` の前に `+0x8c`・`+0x20` の参照があり B の `+8` ではない。

## 2. 準備判定の真偽条件 (0x1262b80)

```
真 ⇔ byte[*0x15e04a8]==0 && byte[*0x15e0ff0]==0 && !C.VMT[0x48]() && dword[*0x15e30f8 + 0x168] <= 0
```

- `*0x15e04a8` = `0x16baff0`・`*0x15e0ff0` = `0x16baff1` (同じ `.bss` オブジェクトの byte 0・1)。`*0x15e30f8` = `0x15f7190` (`.bss`)。
- PE の静的内容では、`.bss` 側の値は未設定。実行時の値は**未測**。mock は PY-94 と同じく真 (`safeEdit: true`) を既定にした。
- `C.VMT[0x48]` = `0x1262950` は未読 (§5)。

## 3. C・mock の変更 (commit `66994c4d0`)

- 順序: 引数の型検査 (dispatch・code 5) → 準備判定 (偽なら code 3) → index 範囲 (code 4) → value。PE 0xd56510 の順 (`[rbx+0x60] = -2` → 準備判定 → `1 <= index <= 500`) と一致させた。
- `FL_E_UNSAFE = 3` (`provider/fl_api.h`)。文言は `src/fl_api.py` と `analysis/flapi/pe_errmsg_probe.py` の "Operation unsafe at current time"。
- `general.safeToEdit` と同じ変数 (C: `safe_edit`・mock: `st.safeEdit`) を読むので、両者の値は常に一致する。
- 試験用の setter は本番の FL API ではない (`setSafeEdit`)。既定値 (真) は `fl_engine_reset` と mock の初期値のまま。

## 4. 検証 (測定 commit `3983af6b9`・コミット済み HEAD)

- 測定 commit は main (`f4d8cf90e`) を取り込んだ merge commit `3983af6b9` (取り込みは 5 回目。競合解消は watchdog の依頼)。
- 競合は 2 回とも片側の追加どうしの衝突。1 回目 (`ffb17f14d`): `provider/build.sh` の `EXPORTED_FUNCTIONS` と `docs/DOC_MAP.md` の REPORT 表。2 回目 (`f4d8cf90e`): `provider/build.sh` の `EXPORTED_FUNCTIONS` と `host/fl_provider.mjs` (`setSafeEdit` の隣に main の `setLoop`)。いずれも両側を残した (`_fl_engine_set_safe_edit` は `_fl_engine_reset` の直後)。`fl_engine.c`・`fl_mock.mjs` は自動 merge。`muteTrackLock` の C と mock の判定が残ることを grep で確認した。
- 素材: `fl-win64` の `extracted/` だけを `$ARTIFACTS_DIR` から `$RUNNER_TEMP` に展開 (real 4.764 秒)。`toolchain-emsdk` は本 run の素材に無かったため、[EMSDK] 6.0.12 を upstream から `install` / `activate` で入れ、`build_cpython_wasm.sh` が直接 source する [EMSDK] の位置へ symlink した。`FL_WIN64_DIR=$RUNNER_TEMP` で `fetch_inputs.sh` を回し `work/` に入力を置いた (real 0.424 秒)。
- ビルド (実測 real・exit 0): `provider/build.sh` 1.475 秒・`build_cpython_wasm.sh` 4 分 29.660 秒・`build_flpy.sh` 7.102 秒。`3983af6b9` では `provider/build.sh` を作り直した (exit 0)。CPython・flpy の入力は main の取り込みで変わっていない。
- `node tests/provider_check.mjs`: `{"functions":435,"implemented":171,"unimplemented":264,"mcp_static":60,"PASS":true}` (real 0.354 秒)。
- `node tests/playlist_diff.mjs`: `{"calls":72,"diffs":0,"mock_state_steps":8,"PASS":true}` (real 0.054 秒)。
- `FL_ENGINE=wasm node tests/all_tools.mjs`: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` (real 2.111 秒)。
- main 側で変わった diff テスト (同じ mock・C を通る): `channels_diff` `{"calls":238,"loop_cases":9,"loop_event_true":51,"diffs":0,"grid_calls":1200,"grid_true":30,"grid_diffs":0,"PASS":true}`・`device_diff` `{"calls":11,"link_calls":6,"rejects":4,"midi_out":10,"diffs":0,"PASS":true}`・`mixer_diff` `{"calls":69,"diffs":0,"PASS":true}`・`ui_state_diff` `{"calls":58,"diffs":0,"PASS":true}`。
- ミューテーション (`3983af6b9` で再測): mock の guard を外す (`if (false) throw UNSAFE();`) → `unsafe 差分 3 件` の AssertionError で FAIL (exit 1)。C の guard を外して `provider/build.sh` で作り直す → 同じく `unsafe 差分 3 件` で FAIL (exit 1)。元に戻して作り直すと `playlist_diff` は PASS。
- 直列 1 本。テスト開始時の load average は `0.32 1.03 0.67` (`/proc/loadavg`)。
- 差分確認: `git diff 3983af6b9 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis` の出力は 0 行 (本 REPORT の commit のみ。測定後のコード変更は無い)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 準備判定の実行時値 (`.bss` のガード 3 件と `C.VMT[0x48]` = `0x1262950`) は未測。mock は真を既定にした | 実機で偽になる経路 (-2) の発生条件は未確認。準備前の呼出しの実機差は、mock の既定 (真) に依る | 未起票 (PM 判断。PY-94 の `safeToEdit` 実機値の確定 (#2830・CLOSED) と併せる) |
| 0x125da90 の C の構築 (`0x410320` 経由の NewInstance) を、ctor の全経路で読んでいない | `[B+8]` が常に非 0 かは静的には確定していない (両生成箇所とも非 0 の VMT を入れる) | 未起票 (実行時の追跡で確認する) |
