# PY-62 (#2027): PY-61 で確定した playlist 関数のうち表で実装できる 8 件を C provider と mock に実装

親: #1971 (PY-57)。前段: #2026 (PY-61・`tools/python/REPORT_PY61.md`)。子: #2883 (PY-102・表の引数数の不一致。main #2927 で解消、§4)。残りの子: #3058 (PY-157・未実装 18 件と getLive\* の既定値)。setter の格納順は main の PY-113 (#2943・`tools/python/REPORT_PY113.md`) で確定し、本 PR の期待値に取り込んだ。既知類型との関係: 該当なし (lift 作業ではない)。起動・GUI に関わらないため製品 KPI は対象外。

## 結論

- PY-61 の未読 26 件のうち、型・範囲 code と戻り値の変換が確定し、表の引数形で実装できる **8 件**を実装した: `getTrackColor`・`isTrackMuteLock`・`getTrackActivityLevelVis`・`getLiveLoopMode`・`getLiveTriggerMode`・`getLivePosSnap`・`getLiveTrigSnap`・`muteTrackLock` (value -1 (省略を含む) は反転、それ以外は下位 1 byte の設定・§2)。うち `muteTrackLock` は main の PY-102 (#2883) が同じ式で先に実装していたため、merge 後の本 PR の新規は **7 件** (実装は main 側を残した)。
- `provider/fl_engine.c`・`host/fl_mock.mjs` に実装し、`tests/playlist_diff.mjs` (72 呼出し・diffs 0・PASS。本 PR の 49 件と main の PY-102 の 23 件) で mock と C を照合した。main 取り込み後 (`cf9dce6fe`) の `tests/provider_check.mjs` の実装数は 151 (main 単独の 144 + 本 PR の 7)、未実装は 284。
- setter の格納式 (main PY-113) と取得式は往復が一致する (`get(set(v)) = 0xff000000 | v`)。`tests/playlist_diff.mjs` の末尾で C と mock の両方に確定値を assert した。暫定期待値 `0xff563412` は廃止した。
- 表の引数数の不一致 (子 #2883) は main #2927 で解消した。現 head の `sig_arity_check.py` は 対象 274・一致 274・不一致 0 (§4)。
- 残り 18 件は実装しない (§3)。既定値 (lock 0・活性度 0・各 live mode 0) は実機値を測っていない仮置き。

## 1. 実装した 8 件

VA は `REPORT_PY61.md` §2。範囲外 index は両者とも code 4 (`Index out of range`)、引数の型違い・個数違いは code 5。

| 関数 (VA) | 振る舞い (PY-61 の確定事項) | 格納先 (track 要素) |
|---|---|---|
| getTrackColor (0xd55ea0) | 格納色の R と B を入替え、`0xff000000` を立てて int を返す | +0x2c |
| isTrackMuteLock (0xd56490) | byte の bool | +0xd5 |
| getTrackActivityLevelVis (0xd56f10) | f32 を double にして返す | +0x60 |
| getLiveLoopMode (0xd57370) | int | +0x40 |
| getLiveTriggerMode (0xd573e0) | int | +0x44 |
| getLivePosSnap (0xd57450) | int | +0x54 |
| getLiveTrigSnap (0xd574c0) | int | +0x48 |
| muteTrackLock (0xd565c0) | value -1 (省略を含む) で +0xd5 byte を反転、それ以外は下位 1 byte を書く (§2) | +0xd5 |

- getLive\* の 4 件は書込み側 (`incLive*` 等) が未実装のため、mock と C では既定値 0 のまま読める。muteTrackLock だけは呼出しで反転する (`isTrackMuteLock` に反映される)。
- getLive\* 4 件 (`getLiveLoopMode`・`getLiveTriggerMode`・`getLivePosSnap`・`getLiveTrigSnap`) の戻り値は field の生の int である。enum の意味と既定値 0 は PY-61 から未確定のままで、本 PR では確定していない (既定値は仮置き)。
- getTrackActivityLevelVis の「f32 を double にして返す」は型の記述である。C は `double act` をそのまま返す (丸めなし)。act は書込み側が未実装で常に 0 のため差は出ない。書込み側を入れる時に f32 への丸めを入れること。

## 2. 実装しなかった部分と差

- **muteTrackLock の `value` 引数**: binary の書式は `'i|i'` (既定 -1)。-1 は反転、他は下位 1 byte を書く (`REPORT_PY61` §3)。main #2927 で生成表 `provider/gen/fl_table.c` が kwsig 書式 (必須 1・最大 2) に合ったため、C と mock は value を受ける (`tests/playlist_diff.mjs`・§5)。
- **準備判定 (-2)**: binary は vtable 呼出し `[rax+0x98]` で準備を判定するが、その述語は未確定。mock と C は常に準備済みとして扱う。
- **setTrackColor の格納式 (解消)**: 本 PR の時点では C の setter が値を素通しで格納していたため、`setTrackColor(3, 0x123456)` の後の `getTrackColor(3)` が `0xff563412` になっていた。main の PY-113 (`REPORT_PY113.md` §2) で格納式 `stored = swap_RB(v) & 0xffffff` が確定し、main 取り込みの merge で C・mock の setter をその式に合わせた。往復は `get(set(0x123456)) = 0xff123456`、`get(set(0xff0000ff)) = 0xff0000ff` (`tests/playlist_diff.mjs` の末尾で assert)。子 #2949 (PY-114) の受入条件 3 (暫定期待値の置換) は本 PR で満たした。

## 3. 未実装の 18 件 (PY-61 で未確定)

- helper の意味が未確定 (`REPORT_PY61` §4-1・§6 の未解決): `isTrackSelected` (helper 0xd56990)・`getDisplayZone` (0xd85210)・`getLiveBlockStatus`・`getLiveStatus`・`getLiveBlockColor` (0x100c030)・`liveTimeToBlockNum` (0x1221b30)・`liveBlockNumToTime` (0x1221aa0) の 7 件。
- 操作コアが未確定: `soloTrack` (0x12e7f80・0xbd68e0)・`selectAll`/`deselectAll` (mode 4/6 の意味)・`lockDisplayZone`・`liveDisplayZone`・`triggerLiveClip`・`refreshLiveClips`・`incLivePosSnap`・`incLiveTrigSnap`・`incLiveLoopMode`・`incLiveTrigMode` の 11 件。
- 起票先: 作用の確定は親 #2809 (CLOSED) の残りの子 #2906 (PY-104・zone 系・triggerLiveClip・refreshLiveClips)・#2908 (PY-105・時間変換・solo/select・inc 系の前後処理・色の出所)・#2909 (PY-106・例外型)。C/mock の実装と getLive\* の既定値を含む残りは子 **#3058 (PY-157)**。

## 4. 表の引数数と binary の書式の不一致 (子 #2883) — main #2927 で解消

### 4-1. 定義と現行の結果

- 母集団: `analysis/flapi/flapi_table.json` の全 435 関数。比較できるのは `sig` (stub 署名。np = `sig.params` の個数) と `kwsig.max` (PE 由来の書式の最大引数数) の両方がある関数で、解消前の表 (`1d71dd27`) は 273 件、main 取り込み後の表 (`d6f17dde0`) は 274 件 (`plugins.getPresetCount` の `kwsig.max` が main で加わった)。np ≠ kwsig.max を不一致とする。定義は `analysis/flapi/sig_arity_check.py` (PY-70・#2500) と同じ。
- 再現 (2 つの表を渡す。before は解消前の表、after は head の表):

```sh
git show 1d71dd27:tools/python/analysis/flapi/flapi_table.json > "$RUNNER_TEMP/flapi_before.json"
python3 tools/python/analysis/flapi/sig_arity_check.py "$RUNNER_TEMP/flapi_before.json" tools/python/analysis/flapi/flapi_table.json
# before: 対象 273 件・一致 249・不一致 24   (1d71dd27 の表)
# after:  対象 274 件・一致 274・不一致 0    (検証 HEAD d6f17dde0 の表)
```

- 解消前 (`1d71dd27` 時点・#2927 の前) は 対象 273 件・一致 249・不一致 **24**。解消は main #2927 (`46f5a007`・表の引数個数を kwsig 書式に合わせる) による。§4-3 は解消前の 24 件の全件。
- 比較対象外 (`d6f17dde0` の表で再計数・両方の欠落の定義): `sig` が有り `kwsig.max` が無い 120 件、`sig` が無く `kwsig.max` が有る 30 件、両方無い 11 件 (計 161 件)。arity は未確認のままで、#2883 本文に追記する (PM 判断)。

### 4-2. 差し戻し時の 55 件との関係

差し戻し時の「55 件」は、`sig` 欠落 30 件を np = 0 と見なし、`kwsig.max` 欠落 1 件を max = 0 と見なして同じ比較に入れた数である (24 + 30 + 1 = 55)。前版の「`sig` が空の 13 件」は誤りで、解消前の 24 件のうち `sig.params` が空は 10 件 (`screen.*`)。

### 4-3. 解消前 (`1d71dd27` 時点) の不一致 24 件

`fmt` は `kwsig.fmt`。方向は kwsig.max と np の大小。

| # | 関数 | np (sig) | kwsig.max | fmt | 方向 |
|---|---|---|---|---|---|
| 1 | playlist.muteTrack | 2 | 3 | `i\|ii` | max > np |
| 2 | playlist.muteTrackLock | 1 | 2 | `i\|i` | max > np |
| 3 | playlist.selectTrack | 1 | 2 | `i\|i` | max > np |
| 4 | channels.getStepParam | 6 | 5 | `iiii\|i` | np > max |
| 5 | channels.soloChannel | 2 | 3 | `i\|ii` | max > np |
| 6 | mixer.armTrack | 1 | 2 | `i\|i` | max > np |
| 7 | mixer.enableTrack | 1 | 2 | `i\|i` | max > np |
| 8 | mixer.getTrackName | 1 | 2 | `i\|i` | max > np |
| 9 | mixer.selectTrack | 1 | 2 | `i\|i` | max > np |
| 10 | patterns.clonePattern | 1 | 2 | `\|ii` | max > np |
| 11 | device.midiOutMsg | 4 | 5 | `i\|iiii` | max > np |
| 12 | plugins.getColor | 4 | 5 | `i\|iiii` | max > np |
| 13 | plugins.getParamValueString | 5 | 4 | `ii\|ii` | np > max |
| 14 | screen.addTextLine | 2 | 5 | `siiii` | max > np |
| 15 | screen.addMeter | 0 | 5 | `iiii\|i` | max > np |
| 16 | screen.animateText | 0 | 1 | `i` | max > np |
| 17 | screen.blank | 0 | 2 | `ii` | max > np |
| 18 | screen.drawRect | 0 | 5 | `iiiii` | max > np |
| 19 | screen.drawText | 0 | 6 | `isiiii` | max > np |
| 20 | screen.eraseRect | 0 | 4 | `iiii` | max > np |
| 21 | screen.findTextLine | 0 | 4 | `iiii` | max > np |
| 22 | screen.removeTextLine | 0 | 2 | `i\|i` | max > np |
| 23 | screen.setScreenActiveCounter | 0 | 1 | `i` | max > np |
| 24 | screen.unBlank | 0 | 1 | `i` | max > np |

## 5. 測定 (現行: 測定 commit `d6f17dde0`)

- 測定 commit (コードを最後に変えた commit): `d6f17dde0` (merge。main を 2 回取り込んだ。(a) `10daa391b` (`5b91369dc`・競合 4 件): `provider/fl_engine.c` の `Pl` 構造体と初期化は PR 側 (超集合・memset で lock 0)、`muteTrackLock` 直前のコメントは両方残した。`host/fl_mock.mjs` の `muteTrackLock` は main 側の検査順 (argI を index 範囲検査より先に) を採用。`tests/playlist_diff.mjs` は両側が新規作成 (add/add) のため PR 側 49 呼出しを土台に main 側 23 呼出しと mock 状態遷移 (8 段) を末尾に追加。`tests/provider_check.mjs` は pe102 (main) と pl61 (本 PR) の両集合を残し、pl61 から muteTrackLock を外した。(b) `cf9dce6fe` (`d6f17dde0`・競合 1 件): `tests/provider_check.mjs` の集合 pe76 (main・`channels.setChannelPitch`) と pl61 (本 PR) を両方残し、件数を 151・284 に更新)
- コード差分: `git diff d6f17dde0 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 commit の後続は REPORT_PY62.md と `docs/DOC_MAP.md` だけ)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst` real 5.399 s・`extracted/` 25,166 件)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` で `fetch_inputs.sh` を実行した。
- emsdk: runner 同梱 `[EMSDK]` (emcc 6.0.12) を使用。`toolchain-emsdk` は展開していない (`build_cpython_wasm.sh` が `[EMSDK]` を固定で読むため)。PR 本文の `oc_artifacts` 行は素材の取得指定 (review run の再現用)。
- 前段: `fetch_inputs.sh` rc 0、`build_cpython_wasm.sh` real 4 分 0.667 s rc 0、`FLPY_SKIP_TABLE=1 build_flpy.sh` real 6.079 s rc 0。
- load average (`/proc/loadavg` の 1 分値・並列 1): 全検証の完了後 0.25。検証開始時の値は未採取。

| 検証 (`d6f17dde0`) | 結果 | 所要 (`time` の real。build・provider・all_tools は `5b91369dc` での測定) |
|---|---|---|
| `provider/build.sh` | 成功・警告 0・435 関数・ハンドラ 151 | real 1.536 s |
| `node tests/playlist_diff.mjs` | calls 72・diffs 0・mock_state_steps 8・PASS (往復 assert を含む) | real 0.111 s |
| `node tests/provider_check.mjs` | functions 435・implemented 151・unimplemented 284・mcp_static 60・PASS | real 0.377 s |
| flprov 系の diff 18 本 (`arrangement_diff`・`arrangement_selection_diff`・`channels_diff`・`device_diff`・`general_diff`・`ilmcp_diff`・`launchmap_diff`・`midi_path_diff`・`mixer_diff`・`note_enum_diff`・`patterns_group_diff`・`playlist_diff`・`screen_diff`・`step_item_diff`・`transport_diff`・`ui_diff`・`ui_display_diff`・`ui_state_diff`) | 全て rc 0・diffs 0・PASS。calls: arrangement 25・arrangement_selection 8・channels 183・device 8 (rejects 4・midi_out 5)・general 41・ilmcp 32 (state 9)・launchmap 3・midi_path 30 (lit 160)・mixer 59・note_enum 33264・patterns_group 14・playlist 72・screen 32・step_item 5929・transport 7・ui 17・ui_display 23 (ok 12・bad 11)・ui_state 33 | 未採取 (一括実行) |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・raised 0・host_calls 37425・callback_roundtrip true | real 2.289 s |
| `sig_arity_check.py` (§4-1) | before (`1d71dd27` の表) 対象 273・一致 249・不一致 24 / after 対象 274・一致 274・不一致 0 | — |

### 5-1. ネガティブコントロール (`d6f17dde0`)

1 件ずつ壊して再測定し、退避コピー (`cmp` 一致) で戻した。

| NC | 壊した箇所 | 結果 |
|---|---|---|
| NC-C: C の muteTrackLock の反転を外す | `provider/fl_engine.c` の `v == -1 ? !p->lock` → `v == -1 ? p->lock` (再ビルド) | build rc 0・`playlist_diff` FAIL・差分 2・rc 1 |
| NC-V: C の muteTrackLock の value 分岐を外す (常に反転) | `v == -1 ? !p->lock : (uint8_t)v` → `!p->lock` (再ビルド) | build rc 0・`playlist_diff` FAIL・差分 3・rc 1 |
| NC-M: mock の playlist.getTrackColor の R/B 入替えを外す | `host/fl_mock.mjs` の式 → `(u \| 0xff000000) >>> 0` | `playlist_diff` FAIL・差分 5・rc 1 |
| NC-P: C の isTrackMuteLock 行を削除 | `provider/fl_engine.c` の `FL_H(playlist, isTrackMuteLock)` 行 (再ビルド) | build rc 0 (表示ハンドラ 150・HEAD は 151。ビルドは止まらない)・`playlist_diff` FAIL・差分 11・rc 1・`provider_check` FAIL・rc 1 (`実装済みのはず: playlist.isTrackMuteLock が未実装`) |
| 復元後 | 退避コピーを戻して再ビルド | `git diff d6f17dde0 -- tools/python` の出力 0 行・`playlist_diff` PASS (72)・`provider_check` PASS (151/284) |

### 5-2. 過去の測定

`1d71dd27`・`decb212c`・`c0638cf3`・`851fbcfe`・`dea4cd91`・`5b91369dc` 時点の測定値は git 履歴 (`235ae8dc` 以前) の本ファイルに残す。本節が現行値。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 比較対象外の関数の arity (§4-1 の 161 件) | 表の arity を未確認のまま | #2883 本文への追記 (PM 判断) |
| getLive\* 4 件の戻り値の enum 意味と既定値 0 | 既定値の正しさ未確定 | #3058 (PY-157) |
| 残り 18 件 (§3)・準備判定 (-2)・既定値の実機値 | 受入条件の残り・初期値の正しさ | #3058 (PY-157)。作用の確定は #2906 (PY-104)・#2908 (PY-105)・#2909 (PY-106) |
