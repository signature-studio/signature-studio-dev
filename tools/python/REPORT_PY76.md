# PY-76 (#2563): channels.setChannelPitch の C provider・mock 実装と差分検査

前段: `tools/python/REPORT_PY72.md` (PE 意味論の正本。判定順・status → 文言、追加解析 PY-75 / PY-77 / PY-170 の節)。既知類型との関係: 該当なし (lift 作業ではない。実装と差分検査)。親: #2542 (PY-72)。

## 実装

| 箇所 | 内容 |
|---|---|
| `provider/fl_engine.c` `h_channels_setChannelPitch` | 判定順は REPORT_PY72 の callback `0xd5a720` どおり: index 範囲外 → `Index out of range` (FL_E_RANGE 4) → value (float32) の NaN → `Unspecified error` (FL_E_UNSPECIFIED 2) → pitchUnit。unit 2 は `N = clamp(cvtsd2si(value), 1, 48)` を `Chan.pitch_n` に書く。成功は None |
| `host/fl_mock.mjs` | 同じ判定順。`argF` (float 引数・`Math.fround`)、`cvtSi64` (64bit・最近接偶数丸め。範囲外と inf は INT64_MIN → clamp で 1)。channel に `pitchN` (既定 2) |
| `tests/channels_diff.mjs` | setChannelPitch の呼出し 15 件 (unit 0/1/2・int64 範囲外 1e30・未知 unit 7・NaN・index 範囲外・型違い・引数不足/過多)。負例 `[9, 0.5]` は両側で code 4 を assert |
| `tests/provider_check.mjs` | 新集合 `pe76` (PE で判定順を確定した 1 関数)。実装数 131 → 132、未実装 304 → 303。エラー code の assert 3 件 |

- 既定 `pitch_n = 2` は reset 関数 `0xfe9090` 由来 (REPORT_PY72 §PY-77 受入 E)。chan との同一性は未確定で、モデルの仮定。
- 同じ集合の `pe39` は「channels.setChannelPitch は未確定のため含めない」と明記されているため、新集合 `pe76` に分けた。

### 未モデル (C と mock で同一)

- unit 0/1 の状態書込み: 戻り値と code は PE どおり。状態は変えない。PY-170 (#3213) で書込み先は `[chan+0x174]` と確定したが、書込みに進む条件 (`0x1051720` の戻り値 2 の生成元) と `0x1046a30` の全経路は未確定 (#3252・#3253)。
- guard (大域オブジェクト O の vtable `+0x98`): 常に真とみなす。status -2 の経路は出ない。
- 通知 PostMessageW (msg 0x550 / 0x562): 送らない。
- useGlobalIndex = 1: 一覧 A/B を同一扱い (両者の要素型は未確定)。

## 測定

- 測定 commit: `6e61656f` (コードを変えた最後の commit。`feat(python): setChannelPitch の C provider・mock 実装と差分検査 (PY-76)`)。
- 素材: `fl-win64.tar.zst` から `extracted/block00031_PE.bin` と DATA 4 本 (`block25159`・`block24429`・`block24430`・`block24618`) を `$RUNNER_TEMP/fl-win64` へ展開 (2.6 秒)。`toolchain-emsdk.tar.zst` を `$RUNNER_TEMP/emsdk` へ展開 (2.6 秒、emsdk 6.0.12)。`FL_WIN64_DIR`・`EMSDK_DIR`・`EMSDK_ENV` をこれに向けた。
- wasm の build (順に実行。全て rc 0):
  - `fetch_inputs.sh`
  - `build_cpython_wasm.sh`: 3 分 53 秒
  - `FLPY_SKIP_TABLE=1 build_flpy.sh`: 20.7 秒
  - `provider/build.sh`: 0.9 秒、警告 0、ハンドラ 132 (`gen_provider.py --check-handlers` も通過)
- 検証 (HEAD = `6e61656f`。直列。開始時 load average 0.24、終了時 0.30 (1 分値)):

| 検証 | 結果 | 所要 |
|---|---|---|
| `node tests/channels_diff.mjs` | 183 呼出し・diffs 0・PASS | 0.049 秒 |
| `node tests/provider_check.mjs` | functions 435・implemented 132・unimplemented 303・mcp_static 60・PASS | 0.339 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (host_calls 37425・callback_roundtrip true) | 1.616 秒 |
| `node tests/all_tools.mjs` (JS mock) | 48/48 ok (host_calls 37425・callback_roundtrip true) | 未計測 |

- 負例 (両側の実出力): `[0, NaN, 2]` → code 2 (`Unspecified error`)、`[9, NaN, 2]` → code 4 (index が先)、`[9, 0.5]` → code 4、`[0, "x"]` → code 5、`[0]` → code 5。`[2, 47.5, 2]` と `[2, 1e30, 2]` は戻り値が両側で一致 (N の観測口は無く、比較は戻り値と code だけ)。
- 差分の証跡: `git diff 6e61656f HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (測定後の commit はこの REPORT と DOC_MAP の追加だけ)。

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
| unit 0/1 の状態書込み (`[chan+0x174]`)。書込みの条件 (`0x1051720` の戻り値 2 の生成元) と `0x1046a30` の全経路 | pitchUnit 0/1 で状態が変わらない (戻り値は PE どおり) | #3252 [PY-175]・#3253 [PY-176] |
| guard の O と判定入力 this・X の実体 | status -2 (Operation unsafe at current time) が出ない | #3212 [PY-169] |
| 通知 PostMessageW (msg 0x550 / 0x562)・reset obj と chan の同一性・一覧 A/B の要素型 | 通知内容・N 既定 2 の適用範囲・useGlobalIndex=1 が未モデル | #3214 [PY-171] |
| getChannelPitch 未実装 | unit 2 の N を API から観測できない | #1514 [PY-36] |
