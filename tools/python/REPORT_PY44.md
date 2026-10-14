# PY-44 (#1671): playlist 未実装 38 関数の所属確定と引数対応

親: #1344 (PY-34)・前段: #1673 (PY-34 の調査)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- playlist 38 関数の PyMethodDef 所属を**確定した**。PE 内の同名入口 (`selectAll`・`deselectAll` ほか) は playlist 以外の配列 (channels・mixer・patterns) のものと分離できた。
- playlist の PyMethodDef 配列は 1 本 (`0x1114ac8`、42 行)。42 行すべてが `flapi_table.json` の playlist と一致し、表に無い・表から漏れた名前は 0 件。
- 38 関数の (引数・戻り値・範囲 code) のうち、**所属は PyMethodDef 配列で確定**したが、引数・戻り値の意味と範囲 code は未決定 (表 `flapi_table.json` の値は本 run で独立検証していない。下表は表の転記)。
- `provider/fl_engine.c` へのコード変更は 0 件。実装は子 issue へ (下記「未解決」)。

## 測定

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に `tar --zstd -xf` で展開 (5.7 秒・load 測定なし)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- 対象: `extracted/block00031_PE.bin`。
- 測定 commit (コード差分の最終): 本 PR の commit (下記 `git log`)。解析は `30a7b5b4` (main) 時点の表で実行。

### 所属確定 (`tools/python/analysis/flapi/pymethoddef_scan.py`)

```
ARRAY start=0x1114ac8 rows=42 best=playlist(42/42) playlist_hits=42
ARRAY start=0x1115ea8 rows=31 best=channels(31/31) playlist_hits=2
ARRAY start=0x1116ea8 rows=72 best=mixer(72/72) playlist_hits=14
ARRAY start=0x1118550 rows=11 best=patterns(11/11) playlist_hits=2
```

- 「best」は配列の名前集合のうち所属モジュールの表に含まれる件数 (含まれる数/配列の名前数)。4 配列とも全名前が所属モジュールの表に含まれる (playlist 42/42・channels 31/31・mixer 72/72・patterns 11/11)。表の側に配列に無い名前があるかは見ていない (playlist は `table not in array: []` で 0 件を確認済み)。
- 同名 `selectAll`・`deselectAll` は channels 配列 (`0x1115ea8`) と patterns 配列 (`0x1118550`) にもあるが、それぞれ別モジュールの入口。playlist 配列 (`0x1114ac8`) の 42 件が playlist の入口。

### 引数対応 (`tools/python/analysis/flapi/playlist_membership.py`)

playlist 配列の 42 行を表と突き合わせた結果。未実装 38 件の一覧 (fn = 実関数 VA、flags = PyMethodDef の METH フラグ):

| 関数 | fn | flags | 表の引数 | 表の戻り | 表の doc |
|---|---|---|---|---|---|
| `isTrackMuted` | 0xd56160 | 1 | index:int | bool | Get track mute state |
| `muteTrack` | 0xd56330 | 3 | index:int, value:int=-1 | None | Toggle track mute state |
| `isTrackMuteLock` | 0xd56490 | 1 | index:int | bool | Get track mute lock state |
| `muteTrackLock` | 0xd565c0 | 1 | index:int | None | Toggle track mute lock state |
| `isTrackSolo` | 0xd566f0 | 1 | index:int | bool | Get track solo state |
| `soloTrack` | 0xd56830 | 3 | index:int, value:int=-1, inGroup:bool=False | None | Toggle track solo state |
| `isTrackSelected` | 0xd56a40 | 1 | index:int | bool | Get track selected state |
| `selectTrack` | 0xd56b60 | 1 | index:int | None | Set track selected state |
| `selectAll` | 0xd56d00 | 4 | — | None | Select all tracks |
| `deselectAll` | 0xd56dd0 | 4 | — | None | Deselect all tracks |
| `getTrackActivityLevel` | 0xd56ea0 | 1 | index:int | float | Get track activity level |
| `getTrackActivityLevelVis` | 0xd56f10 | 1 | index:int | float | Get track visual activity level |
| `getDisplayZone` | 0xd56f80 | 4 | — | int | Get display zone number |
| `lockDisplayZone` | 0xd57030 | 1 | index:int, value:int | None | Lock display zone |
| `liveDisplayZone` | 0xd57200 | 3 | left, top, right, bottom, duration:int=0 | None | Live display zone |
| `getLiveLoopMode` | 0xd57370 | 1 | index:int | int | Get live loop mode |
| `getLiveTriggerMode` | 0xd573e0 | 1 | index:int | int | Get live trigger mode |
| `getLivePosSnap` | 0xd57450 | 1 | index:int | int | Get live pos snap |
| `getLiveTrigSnap` | 0xd574c0 | 1 | index:int | int | Get live trig snap |
| `getLiveBlockStatus` | 0xd57550 | 3 | index:int, blockNum:int, mode:int=midi.LB_Status_Default | int | Get live block status |
| `getLiveStatus` | 0xd57670 | 3 | index:int, mode:int=midi.LB_Status_Default | int | Get live status |
| `getLiveBlockColor` | 0xd57740 | 1 | index:int, blockNum:int | int | Get live block color |
| `triggerLiveClip` | 0xd57860 | 3 | index:int, subNum:int, flags:int, velocity:int=-1 | None | Trigger live clips |
| `refreshLiveClips` | 0xd57a20 | 4 | — | None | Refresh live clips |
| `incLivePosSnap` | 0xd57b50 | 1 | index:int, value:int | None | Increase live pos snap |
| `incLiveTrigSnap` | 0xd57cd0 | 1 | index:int, value:int | None | Increase live trig snap |
| `incLiveLoopMode` | 0xd57e50 | 1 | index:int, value:int | None | Increase live loop mode |
| `incLiveTrigMode` | 0xd57fd0 | 1 | index:int, value:int | None | Increase live trig mode |
| `getVisTimeBar` | 0xd580f0 | 4 | — | int | Get time bar |
| `getVisTimeTick` | 0xd58110 | 4 | — | int | Get time tick |
| `getVisTimeStep` | 0xd58130 | 4 | — | int | Get time step |
| `liveTimeToBlockNum` | 0xd58150 | 1 | time:int | int | Live time to block number |
| `liveBlockNumToTime` | 0xd581a0 | 1 | index:int | int | Live block number to time |
| `getSongStartTickPos` | 0xd581f0 | 4 | — | int | Get song start tick position |
| `scrollTo` | 0xd58490 | 1 | a, b, c, d (int) | None | Scroll to |
| `getPerformanceModeState` | 0xd585d0 | 4 | — | bool | Get performance mode state |
| `selectTool` | 0xd58670 | 1 | (表の sig が null) | (不明) | Select playlist tool |

- 表の引数名・戻り型は `flapi_table.json` の転記。PyArg 書式文字列との照合は本 run では未実施。
- `selectTool` は表の `sig` が null。REPORT_PY34 で指摘した「書式 `i` と flapi の `() -> None` が合わない」は未確定のまま。
- `scrollTo` の `a/b/c/d` は表で名前が無い。意味は未確定。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 38 関数の戻り値の意味 (特に `getVisTime*`・`getLive*Mode` 等の int/bool の値域) | 実装の戻り値が決まらない | 子 issue (下記) |
| 範囲 code (`RANGE`/`WRONG_PARAM` の境界) | 異常系の挙動が決まらない | 子 issue |
| `selectTool` の引数 (表 sig が null・書式 `i` との不一致) | 実装前に要確認 | 子 issue |
| `scrollTo` の `a/b/c/d` の意味 | 実装前に要確認 | 子 issue |
| `fl_engine.c` 実装・`provider_check.mjs` 件数更新・mock との diff 0・`all_tools` 48/48 | 受入条件の残り | 子 issue (下記) |

子 issue は 1 件に集約する (残りは同一の作業単位: 逆アセンブルで意味論を決め、実装・mock・検査までを 1 PR で閉じる)。

## 検証

- 再現: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pymethoddef_scan.py` および `playlist_membership.py` (いずれも foreground、数秒)。
- 配列の件数・所属は上記出力と一致 (`playlist_membership.py` 2 回実行の出力が `cmp` で同一)。
- 表の突合: playlist 表 42 件 = 配列の playlist 名 42 件 (`table not in array: []`、`not in table` 0 件)。
- 負の対照: 配列の開始 VA を 1 件ずらす (`--start 0x1114ac0`) と `rows=0` となり、表 42 件すべてが `table not in array` になる (確認済み)。
- コード差分の確認コマンドと結果は PR 本文の検証欄に記載。
- `all_tools.mjs` 48/48: 本 PR ではコード差分 0 のため再測定しない (`docs/WORKFLOW.md` §6)。

## 範囲外

- 戻り値・範囲 code の確定は行っていない。推測による実装はしない。
- mock (`host/fl_mock.mjs`) と C provider への追加はしていない。
