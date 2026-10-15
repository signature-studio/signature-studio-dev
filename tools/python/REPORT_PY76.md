# PY-76 (#2563): channels.setChannelPitch の C provider・mock 実装と差分検査

前段: `tools/python/REPORT_PY72.md` (PE 意味論の正本。判定順・status → 文言、追加解析 PY-75 / PY-77 / PY-170 の節)。既知類型との関係: 該当なし (lift 作業ではない。実装と差分検査)。親: #2542 (PY-72)。

## 実装

| 箇所 | 内容 |
|---|---|
| `provider/fl_engine.c` `h_channels_setChannelPitch` | 判定順は REPORT_PY72 の callback `0xd5a720` どおり: index 範囲外 → `Index out of range` (FL_E_RANGE 4) → value (float32) の NaN → `Unspecified error` (FL_E_UNSPECIFIED 2) → pitchUnit。unit 2 は `N = clamp(cvtsd2si(value), 1, 48)` を `Chan.pitch_n` に書く。成功は None |
| `host/fl_mock.mjs` | 同じ判定順。`argF` (float 引数・`Math.fround`)、`cvtSi64` (64bit・最近接偶数丸め。範囲外と inf は INT64_MIN → clamp で 1)。channel に `pitchN` (既定 2) |
| `tests/channels_diff.mjs` | setChannelPitch の呼出し 15 件 (unit 0/1/2・int64 範囲外 1e30・未知 unit 7・NaN・index 範囲外・型違い・引数不足/過多)。負例 `[9, 0.5]` は両側で code 4 を assert |
| `tests/provider_check.mjs` | 新集合 `pe76` (PE で判定順を確定した 1 関数)。main の集合 (`pe120` #2984・`pe172` #3219) と併存させ、実装 144・未実装 291 (`gen_provider.py --check-handlers` のハンドラ数 144 と一致)。エラー code の assert 3 件 |

- 既定 `pitch_n = 2` は reset 関数 `0xfe9090` 由来 (REPORT_PY72 §PY-77 受入 E)。chan との同一性は未確定で、モデルの仮定。
- 同じ集合の `pe39` は「channels.setChannelPitch は未確定のため含めない」と明記されているため、新集合 `pe76` に分けた。

### 未モデル (C と mock で同一)

- unit 0/1 の状態書込み: 戻り値と code は PE どおり。状態は変えない。確定済み: pitch の書込み先 `[chan+0x174]` (PY-170 / #3213)、`0x1046a30` の key 下位 16bit 0・2・3・8 の書込み先 (PY-175 / #3252)、bb の生成元 `0xf82a10` (PY-176 / #3253)。未確定: 書込みに進む条件 (`0x1051720` の戻り値 2 の経路。表 T0 `[0x16bacd8]` と 10519c6 枝の副作用 → #3287・#3288) と `0x1046a30` の残りの枝 (→ #3282)。
- guard (大域オブジェクト O の vtable `+0x98`): 常に真とみなす。status -2 の経路は出ない (→ #3212)。
- 通知 PostMessageW (msg 0x550 / 0x562): 送らない。送信元と hwnd の由来は PY-77 (#3214) で確定。受け手 (window proc の分岐先) は未確定 (→ #3440)。通知の直接呼出しの判定 `0x525ec0` の比較対象は未確定 (→ #3268)。
- useGlobalIndex = 1: 一覧 A/B を同一扱い (両者の要素型は未確定。→ #3371)。

## 測定

- 測定 commit: `e2023b505` (コードを変えた最後の commit)。`origin/main` (`5536d48ec`) の取り込み merge `395da6392` の後に、provider のコメント 1 行 (m2) を直した。前回の測定 commit は `38fa1159c` (`origin/main` `298fd8223` の merge)。
- merge の競合は `tests/provider_check.mjs` の 1 件のみ。本 PR の集合 `pe76` と main の `pe172` (#3219) を両方残し、件数を impl 144・unimpl 291 に直した。main の取り込みで `tools/python/{provider,host,tests}` に main 側の変更が入ったため、`38fa1159c` の実測は使わず再測定した。
- 素材: `$HOME/artifacts/fl-win64.tar.zst` の実在を確認し、`extracted/block00031_PE.bin` と DATA 4 本 (`block25159`・`block24429`・`block24430`・`block24618`) を `$RUNNER_TEMP/fl-win64/extracted` へ展開 (2.8 秒)。`FL_WIN64_DIR` をこれに向けた。`FL_MAC_DIR` は無いので `fetch_inputs.sh` は win64 の DATA block 経路を取った。emsdk は `/opt/emsdk` (`[EMSDK]`) を使い、`toolchain-emsdk` は展開していない。
- wasm の build (`e2023b505` で順に実行。全て rc 0):
  - `fetch_inputs.sh`: rc 0 (0.47 秒)
  - `build_cpython_wasm.sh`: 4 分 8 秒 (248 秒)
  - `FLPY_SKIP_TABLE=1 build_flpy.sh`: 6.1 秒
  - `provider/build.sh`: 1.34 秒、警告 0、ハンドラ 144 (`--check-handlers` 通過)
- 検証 (測定 commit = `e2023b505`。直列。検証開始時の load average 2.49 (1 分値。直前の CPython build を含む)):

| 検証 | 結果 | 所要 |
|---|---|---|
| `node tests/channels_diff.mjs` | 183 呼出し・diffs 0・PASS | 0.085 秒 |
| `node tests/provider_check.mjs` | functions 435・implemented 144・unimplemented 291・mcp_static 60・PASS | 0.362 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (host_calls 37425・callback_roundtrip true) | 1.636 秒 |
| `node tests/all_tools.mjs` (JS mock) | 48/48 ok (host_calls 37425・callback_roundtrip true) | 1.695 秒 |
| flprov のみで動く差分テスト 14 本 (`ui_state_diff` 33 呼出し・`general_diff` 41・`screen_diff` 32・`ui_display_diff` ok 12・bad 11・`arrangement_diff` 25・`arrangement_selection_diff` 8・`mixer_diff` 59・`transport_diff` 7・`device_diff` 8・`ilmcp_diff` 32・`playlist_diff` 23・`step_item_diff` 5929・`ui_diff` 17・`midi_path_diff` 30 case) | 全て diffs 0・PASS | 各 51〜64 ms |
| `node tests/launchmap_diff.mjs` (main 由来の `pe120`) | 3 呼出し・diffs 0・PASS | 0.055 秒 |
| `node tests/patterns_group_diff.mjs` (main 由来の `pe172`・#3219) | 14 呼出し・diffs 0・PASS | 0.053 秒 |

- 負例 (`6e61656f` で採取した両側の実出力。`38fa1159c` と `e2023b505` でも `channels_diff`・`provider_check` の assert が通過): `[0, NaN, 2]` → code 2 (`Unspecified error`)、`[9, NaN, 2]` → code 4 (index が先)、`[9, 0.5]` → code 4、`[0, "x"]` → code 5、`[0]` → code 5。`[2, 47.5, 2]` と `[2, 1e30, 2]` は戻り値が両側で一致 (N の観測口は無く、比較は戻り値と code だけ)。
- 差分の証跡: `git diff e2023b505 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (測定後の commit はこの REPORT の更新だけ)。

## 受入条件 (#2563)

- [x] `provider/fl_engine.c` に `h_channels_setChannelPitch`: NaN → Unspecified error、index 範囲外 → Index out of range、pitchUnit 0/1/2 の分岐 (unit 0/1 の効果は未モデル。上記)
- [x] `host/fl_mock.mjs` に同じ判定順
- [x] `tests/channels_diff.mjs` に setChannelPitch を追加し diffs 0。負例 1 件を assert
- [x] `tests/provider_check.mjs` の集合に追加し、実装数を更新 (`pe76`。上記)
- [x] `FL_ENGINE=wasm node tests/all_tools.mjs` 48/48 ok
- [x] 検証結果 (所要・load・PASS/FAIL) を本 REPORT に残す

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 0/1 の状態書込みの条件: `0x1051720` の戻り値 2 の経路 (表 T0 `[0x16bacd8]` の hook と item・K、10519c6 枝の副作用) と `0x1046a30` の残りの枝 (負の key・key 1/5/6/7/9 以降・flags 0x3e9)。確定済みは上記の書込み先 | pitchUnit 0/1 で状態が変わらない (戻り値は PE どおり) | #3287 [PY-182]・#3288 [PY-183]・#3282 [PY-181] |
| guard の O と判定入力 this・X の実体 | status -2 (Operation unsafe at current time) が出ない | #3212 [PY-169] |
| 通知 PostMessageW (msg 0x550 / 0x562) の受け手 (window proc の分岐先)・通知の直接呼出しの判定 `0x525ec0` の比較対象 | 通知は送らない。直接呼出しの判定が未モデル | #3440 [PY-197] (新規・#3214 の子)・#3268 [PY-178] |
| reset obj と chan の同一性・一覧 A/B の要素型 | N 既定 2 の適用範囲・useGlobalIndex=1 が未モデル | #3371 [PY-190] |
| getChannelPitch 未実装 | unit 2 の N を API から観測できない (channels_diff は戻り値と code だけを比べる) | #1514 [PY-36] |
