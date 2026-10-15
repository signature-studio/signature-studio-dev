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

## 4. 検証 (測定 commit `034cab74a`・コミット済み HEAD)

- 測定 commit は main (`058984fa0`) を取り込んだ merge commit `034cab74a`。前回測定 (`66994c4d0`) 以降に main 側で `tools/python/provider` が変わったため、測り直した。競合は `provider/build.sh` の `EXPORTED_FUNCTIONS` だけで、本 PR の `_fl_engine_set_safe_edit` と main の `_fl_engine_grid_items_probe` を両方残した。
- 素材: `fl-win64` を `tar --zstd -xf` で展開 (実測 real 5.425 秒)。展開先 `$RUNNER_TEMP/fl-win64`。`fetch_inputs.sh` で `work/` に入力を置いた。
- emsdk 6.0.12 は upstream から `emsdk install` / `activate` で入れ、`[EMSDK]` の位置に置いた (`toolchain-emsdk` は本 run の素材に無かった)。
- `provider/build.sh` (実測 real 1.598 秒)・`build_cpython_wasm.sh` (実測 real 4 分 33 秒)・`build_flpy.sh` (`FLPY_SKIP_TABLE=1`・real 6.461 秒) を作って `provider_check` と `all_tools` を回した。
- `node tests/playlist_diff.mjs`: `{"calls":23,"diffs":0,"mock_state_steps":8,"PASS":true}` (偽の状態の節 5 呼出しも差分 0・`lock` 不変を assert)。real 0.050 秒。
- `node tests/provider_check.mjs`: `{"functions":435,"implemented":155,"unimplemented":280,"mcp_static":60,"PASS":true}`。real 0.369 秒。
- `FL_ENGINE=wasm node tests/all_tools.mjs`: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}`。real 2.110 秒。
- ミューテーション: mock の `if (!st.safeEdit) throw UNSAFE();` を外す → `unsafe 差分 3 件` で FAIL (exit 1)。C 側の `if (!safe_edit) return fl_err(...)` を外す → 同じく `unsafe 差分 3 件` で FAIL (exit 1)。どちらも戻すと PASS。
- 実行直前の load average は `1.33 1.60 0.83` (`/proc/loadavg`)。並列 1。
- 差分確認: `git diff 034cab74a HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis` の出力は 0 行 (本 REPORT の commit のみ。測定後のコード変更は無い)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 準備判定の実行時値 (`.bss` のガード 3 件と `C.VMT[0x48]` = `0x1262950`) は未測。mock は真を既定にした | 実機で偽になる経路 (-2) の発生条件は未確認。準備前の呼出しの実機差は、mock の既定 (真) に依る | 未起票 (PM 判断。PY-94 の `safeToEdit` 実機値の確定 (#2830・CLOSED) と併せる) |
| 0x125da90 の C の構築 (`0x410320` 経由の NewInstance) を、ctor の全経路で読んでいない | `[B+8]` が常に非 0 かは静的には確定していない (両生成箇所とも非 0 の VMT を入れる) | 未起票 (実行時の追跡で確認する) |
