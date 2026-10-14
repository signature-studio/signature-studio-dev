# PY-62 (#2027): PY-61 で確定した playlist 関数のうち表で実装できる 8 件を C provider と mock に実装

親: #1971 (PY-57)。前段: #2026 (PY-61・`tools/python/REPORT_PY61.md`)。子: #2883 (PY-102・表の引数数の不一致)。既知類型との関係: 該当なし (lift 作業ではない)。起動・GUI に関わらないため製品 KPI は対象外。

## 結論

- PY-61 の未読 26 件のうち、型・範囲 code と戻り値の変換が確定し、表の引数形で実装できる **8 件**を実装した: `getTrackColor`・`isTrackMuteLock`・`getTrackActivityLevelVis`・`getLiveLoopMode`・`getLiveTriggerMode`・`getLivePosSnap`・`getLiveTrigSnap`・`muteTrackLock` (反転のみ・§2)。
- `provider/fl_engine.c`・`host/fl_mock.mjs` に実装し、`tests/playlist_diff.mjs` (42 呼出し・diffs 0) で mock と C を照合した。`tests/provider_check.mjs` の実装数は 77 → 85、未実装は 358 → 350。
- 残り 18 件は実装しない (§3)。戻り値の意味が PY-61 で未確定の helper・操作コアに依存するため。
- 既定値 (lock 0・活性度 0・各 live mode 0) は実機値を測っていない仮置き。

## 1. 実装した 8 件

VA は `REPORT_PY61.md` §2。範囲外 index は両者とも code 4 (`Index out of range`)、引数の型違い・個数違いは code 5。

| 関数 (VA) | 振る舞い (PY-61 の確定事項) | 格納先 (track 要素) |
|---|---|---|
| getTrackColor (0xd55ea0) | 色 u32 の R と B を入替え、`0xff000000` を立てて int を返す | +0x2c |
| isTrackMuteLock (0xd56490) | byte の bool | +0xd5 |
| getTrackActivityLevelVis (0xd56f10) | f32 を double にして返す | +0x60 |
| getLiveLoopMode (0xd57370) | int | +0x40 |
| getLiveTriggerMode (0xd573e0) | int | +0x44 |
| getLivePosSnap (0xd57450) | int | +0x54 |
| getLiveTrigSnap (0xd574c0) | int | +0x48 |
| muteTrackLock (0xd565c0) | 表どおり 1 引数で呼ぶと +0xd5 byte を反転する (§2) | +0xd5 |

- getLive\* の 4 件は書込み側 (`incLive*` 等) が未実装のため、mock と C では既定値 0 のまま読める。muteTrackLock だけは呼出しで反転する (`isTrackMuteLock` に反映される)。

## 2. 実装しなかった部分と差

- **muteTrackLock の `value` 引数** (binary の書式 `'i|i'`・既定 -1・-1 は反転、他は下位 1 byte を書く (`REPORT_PY61` §3))。生成表 `provider/gen/fl_table.c` の引数数は 1 (`sig.params` 由来、np=1) で、dispatch が 2 個目を code 5 で拒否する。C と mock は同じく code 5 を返す (`tests/playlist_diff.mjs` で確認)。表の不一致は §4、子 #2883 (PY-102)。
- **準備判定 (-2)**: binary は vtable 呼出し `[rax+0x98]` で準備を判定するが、その述語は未確定。mock と C は常に準備済みとして扱う。
- **getTrackColor と setTrackColor の byte 順**: `getTrackColor` は PY-61 の確定どおり R/B を入替えて返す。既存の `setTrackColor` (C・mock とも素の値を格納) は格納 byte 順を逆アセンブルしていない。そのため `setTrackColor(3, 0x123456)` の後の `getTrackColor(3)` は `0xff563412` を返す (実測・`tests/playlist_diff.mjs` の末尾)。set と get の round trip は一致しない。

## 3. 未実装の 18 件 (PY-61 で未確定)

- helper の意味が未確定 (`REPORT_PY61` §4-1・§6 の未解決): `isTrackSelected` (helper 0xd56990)・`getDisplayZone` (0xd85210)・`getLiveBlockStatus`・`getLiveStatus`・`getLiveBlockColor` (0x100c030)・`liveTimeToBlockNum` (0x1221b30)・`liveBlockNumToTime` (0x1221aa0) の 7 件。
- 操作コアが未確定: `soloTrack` (0x12e7f80・0xbd68e0)・`selectAll`/`deselectAll` (mode 4/6 の意味)・`lockDisplayZone`・`liveDisplayZone`・`triggerLiveClip`・`refreshLiveClips`・`incLivePosSnap`・`incLiveTrigSnap`・`incLiveLoopMode`・`incLiveTrigMode` の 11 件。
- 起票先: いずれも子 #2809 (PY-91)。

## 4. 表の引数数と binary の書式の不一致 (子 #2883)

`flapi_table.json` の `sig.params` 個数と `kwsig.max` が食い違う 24 件 (`sig` が空の 13 件を含む)。書式 (`kwsig.fmt`) が binary 由来のため、こちらを正とみなす見込みだが、一件ずつの突き合わせは未了。

`playlist.muteTrack` (2/3)・`playlist.muteTrackLock` (1/2)・`playlist.selectTrack` (1/2)・`channels.getStepParam` (6/5)・`channels.soloChannel` (2/3)・`mixer.armTrack` (1/2)・`mixer.enableTrack` (1/2)・`mixer.getTrackName` (1/2)・`mixer.selectTrack` (1/2)・`patterns.clonePattern` (1/2)・`device.midiOutMsg` (4/5)・`plugins.getColor` (4/5)・`plugins.getParamValueString` (5/4)・`screen.*` 11 件 (`sig` 空・`kwsig.max` 1〜6)。`screen.*` の `sig` 空は `#2554` (PY-70・positional-only の読み取り) と同じ系統の可能性があるが、未確認。

## 5. 測定

- 測定 commit (コードを最後に変えた commit): `1d71dd27` (`feat(python): implement playlist functions confirmed in PY-61 (#2027)`)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf` で実測 real 7.135 s)。emsdk は runner 同梱の `[EMSDK]` を使い、`toolchain-emsdk` の展開はしていない。
- 前段の wasm 生成 (同じ worktree・測定 commit より前のコード): `fetch_inputs.sh` で `work/` を配置、`build_cpython_wasm.sh` real 2 分 49.8 秒、`FLPY_SKIP_TABLE=1 build_flpy.sh` real 4.134 秒。
- 測定 commit での検証 (実行直前の load average 0.10、`/proc/loadavg`、並列 1、n=1):

| 検証 | 結果 | 所要 |
|---|---|---|
| `provider/build.sh` | 成功、警告 0 | real 0.591 s |
| `node tests/provider_check.mjs` | functions 435・implemented 85・unimplemented 350・PASS | real 0.236 s |
| `node tests/playlist_diff.mjs` | calls 42・diffs 0・PASS | real 0.033 s |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (host_calls 37425・callback_roundtrip true) | real 1.065 s |
| `node tests/channels_diff.mjs` | calls 107・diffs 0・PASS | real 0.034 s |
| `node tests/mixer_diff.mjs` | calls 48・diffs 0・PASS | real 0.036 s |
| `node tests/device_diff.mjs` | calls 7・rejects 4・midi_out 4・diffs 0・PASS | real 0.035 s |

- コード差分 (測定 commit から HEAD まで、C・mock・テスト): `git diff 1d71dd27 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR の後続コミットは REPORT と `docs/DOC_MAP.md` だけ)。
- `all_tools` の wasm 出力 `analysis/mcp/tool_coverage.wasm.json` は更新されない内容で、差分なし。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| muteTrackLock の `value` 引数と、表の引数数の不一致 24 件 | 2 個目の引数が C と mock で code 5 | #2883 (PY-102) |
| getTrackColor と setTrackColor の格納 byte 順 (set→get の round trip が一致しない) | 色の設定と読出しが食い違う | #2809 (PY-91)。setter の逆アセンブルを対象へ追記する必要あり |
| 残り 18 件 (§3)・準備判定 (-2)・既定値の実機値 | 受入条件の残り・初期値の正しさ | #2809 (PY-91) |
