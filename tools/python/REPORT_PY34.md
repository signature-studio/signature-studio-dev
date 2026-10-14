# PY-34 (#1344): playlist 未実装 38 関数の実機意味論 (調査結果)

親: #1336 (PY-32)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- playlist 38 関数の意味論は**本 run では未決定**。C provider (`provider/fl_engine.c`) へのコード変更は 0 件。
- 決められなかった理由: 同じ関数名の PyMethodDef 入口が PE 内に複数あり (下表)、どれが playlist 所属かの対応が未確定。
  戻り値・引数の意味も逆アセンブルを関数ごとに読まないと確定しない。推測実装は行わない。
- 残りは子 issue に分割する (下記「分割先」)。

## 測定 (ハンドラ入口の所在)

- 素材: `fl-win64` (`docs/REFERENCES.md` `[WIN64]`・`docs/WORKFLOW.md` §11) を `$RUNNER_TEMP/fl-win64` に `tar --zstd -xf` で展開し、`extracted/block00031_PE.bin` を対象にした (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)。
- 解析補助: `tools/python/analysis/flapi/pe_handler_probe.py` (既存)。38 名を 1 回の foreground 実行 (exit 0、数秒)。probe 本体 (`tools/python/analysis/flapi/pe_handler_probe.py`) は `origin/main` と差分 0。
- 生成物: `work/playlist_probe.txt` (gitignore 対象・commit しない)。
- 38 関数すべてに少なくとも 1 件の入口が見つかった。入口は合計 52 件。

### 38 関数の入口一覧 (probe 実測)

入口 = PyMethodDef から引いたハンドラの entry VA (`entry`) と、そこから辿った実関数の VA (`fn`)。`work/playlist_probe.txt` の `[名前] entry=... fn=...` 行を集計した値。

| 関数 | 入口件数 | 入口 (entry VA / fn VA) |
|---|---|---|
| `deselectAll` | 4 | 0x1516288 / 0xd56dd0 , 0x15174c8 / 0xd5b270 , 0x15188a8 / 0xd614d0 , 0x1519b70 / 0xd66560 |
| `getDisplayZone` | 1 | 0x15162e8 / 0xd56f80 |
| `getLiveBlockColor` | 1 | 0x1516408 / 0xd57740 |
| `getLiveBlockStatus` | 1 | 0x15163c8 / 0xd57550 |
| `getLiveLoopMode` | 1 | 0x1516348 / 0xd57370 |
| `getLivePosSnap` | 1 | 0x1516388 / 0xd57450 |
| `getLiveStatus` | 1 | 0x15163e8 / 0xd57670 |
| `getLiveTriggerMode` | 1 | 0x1516368 / 0xd573e0 |
| `getLiveTrigSnap` | 1 | 0x15163a8 / 0xd574c0 |
| `getPerformanceModeState` | 1 | 0x15165c8 / 0xd585d0 |
| `getSongStartTickPos` | 1 | 0x1516588 / 0xd581f0 |
| `getTrackActivityLevel` | 1 | 0x15162a8 / 0xd56ea0 |
| `getTrackActivityLevelVis` | 1 | 0x15162c8 / 0xd56f10 |
| `getTrackColor` | 2 | 0x1516128 / 0xd55ea0 , 0x1518508 / 0xd5ec60 |
| `getVisTimeBar` | 1 | 0x15164e8 / 0xd580f0 |
| `getVisTimeStep` | 1 | 0x1516528 / 0xd58130 |
| `getVisTimeTick` | 1 | 0x1516508 / 0xd58110 |
| `incLiveLoopMode` | 1 | 0x15164a8 / 0xd57e50 |
| `incLivePosSnap` | 1 | 0x1516468 / 0xd57b50 |
| `incLiveTrigMode` | 1 | 0x15164c8 / 0xd57fd0 |
| `incLiveTrigSnap` | 1 | 0x1516488 / 0xd57cd0 |
| `isTrackMuted` | 2 | 0x1516168 / 0xd56160 , 0x1518668 / 0xd5fa00 |
| `isTrackMuteLock` | 2 | 0x15161a8 / 0xd56490 , 0x15186a8 / 0xd5fc10 |
| `isTrackSelected` | 2 | 0x1516228 / 0xd56a40 , 0x1518848 / 0xd610d0 |
| `isTrackSolo` | 2 | 0x15161e8 / 0xd566f0 , 0x15185c8 / 0xd5f4e0 |
| `liveBlockNumToTime` | 1 | 0x1516568 / 0xd581a0 |
| `liveDisplayZone` | 1 | 0x1516328 / 0xd57200 |
| `liveTimeToBlockNum` | 1 | 0x1516548 / 0xd58150 |
| `lockDisplayZone` | 1 | 0x1516308 / 0xd57030 |
| `muteTrack` | 2 | 0x1516188 / 0xd56330 , 0x1518688 / 0xd5fab0 |
| `muteTrackLock` | 1 | 0x15161c8 / 0xd565c0 |
| `refreshLiveClips` | 1 | 0x1516448 / 0xd57a20 |
| `scrollTo` | 1 | 0x15165a8 / 0xd58490 |
| `selectAll` | 4 | 0x1516268 / 0xd56d00 , 0x15174a8 / 0xd5b150 , 0x1518888 / 0xd61400 , 0x1519b50 / 0xd66430 |
| `selectTool` | 1 | 0x15165e8 / 0xd58670 |
| `selectTrack` | 2 | 0x1516248 / 0xd56b60 , 0x1518868 / 0xd61250 |
| `soloTrack` | 2 | 0x1516208 / 0xd56830 , 0x15185e8 / 0xd5f650 |
| `triggerLiveClip` | 1 | 0x1516428 / 0xd57860 |

集計: 38 関数 / 入口 52 件。入口 0 件の関数はなし。入口 4 件が 2 名 (`selectAll` `deselectAll`)、入口 2 件が 8 名 (`getTrackColor` `isTrackMuted` `isTrackMuteLock` `isTrackSelected` `isTrackSolo` `muteTrack` `selectTrack` `soloTrack`)、残り 28 名は 1 件。

## 確認できた引数書式 (PyArg 書式文字列・参考)

| 関数 | 書式 (RIP 相対の文字列) | 対応する flapi 引数 |
|---|---|---|
| isTrackMuted / isTrackSolo / isTrackSelected / isTrackMuteLock / getTrackColor / getTrackActivityLevel(Vis) | `i` | `index` |
| muteTrack / soloTrack / selectTrack | `i\|i` `i\|ii` | `index, value` (soloTrack は `inGroup` を含む可能性) |
| muteTrackLock | `i\|i` | `index` (+ 任意) |
| lockDisplayZone | `ii` | `index, value` |
| liveDisplayZone | `iiii\|i` | `left, top, right, bottom, duration` |
| getLiveLoopMode / getLiveTriggerMode / getLivePosSnap / getLiveTrigSnap / liveTimeToBlockNum / liveBlockNumToTime | `i` | `index` (time 系は `time`) |
| getLiveBlockStatus | `ii\|i` | `index, blockNum, mode` |
| getLiveStatus | `i\|i` | `index, mode` |
| getLiveBlockColor | `ii` | `index, blockNum` |
| triggerLiveClip | `ii\|id` | `index, subNum, flags, velocity` |
| incLivePosSnap / incLiveTrigSnap / incLiveLoopMode / incLiveTrigMode | `ii` | `index, value` |
| scrollTo | `iiii` | `a, b, c, d` |
| selectTool | `i` | (flapi 上は引数なし。書式と不一致のため要確認) |

注: 書式文字列は関数の引数解析の証跡であり、戻り値の意味や範囲 code は含まない。
`selectTool` の書式 (`i`) は flapi の `selectTool() -> None` と合わない。対応関係は未確定。

## 分割先 (未解決)

残りは次の子 issue に分割する (親: #1344)。

- playlist 38 件 → #1671 (`[PY-44]`): PyMethodDef からモジュール所属を確定し、(引数・戻り値・範囲 code) を決め、`provider/fl_engine.c` に実装する。
  `oc_artifacts: fl-win64 toolchain-emsdk`

## 受入条件の判定 (#1344)

- [ ] 38 関数の実機意味論を決め、根拠を REPORT に残す — 未達 (本 PR は入口の所在と書式の調査まで。子 issue へ)。
- [ ] 決めた関数を `provider/fl_engine.c` に実装し、`provider_check.mjs` の実装数を更新 — 未達 (子 issue)。
- [ ] mock に追加した関数を差分検査で mock と C の diffs 0 — 未達 (子 issue)。
- [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok を維持 — 本 PR では未実行 (wasm CPython・provider のビルドが要るため)。コード差分 0 (下記「検証」) のため、直前の実測が有効。測定 commit: `4c531879` (PY-31 の記録 `FL_ENGINE=wasm node tests/all_tools.mjs` = `{"total":48,"ok":48,"soft_error":0,"raised":0,"host_calls":37425,"callback_roundtrip":true}`、2.16 秒)。

## 検証

- 測定 commit (all_tools 48/48 の直前測定): `4c531879`。
- `4c531879` から HEAD までの `all_tools.mjs` の依存先の差分: `git diff 4c531879 HEAD -- tools/python/host tools/python/provider tools/python/tests/all_tools.mjs tools/python/tests/tool_args.mjs` → **0 行**。
- 同じ範囲で `tools/python/tests` 全体には差分がある (`git diff --stat 4c531879 HEAD -- tools/python/tests`: `pyscript_scenarios.mjs` 124 行追加・4 行削除)。これは `all_tools.mjs` から import されず、`pyscript_e2e.mjs` からのみ使われるため、48/48 の判定には影響しない。
- 本 PR のコード差分: `git diff --stat cd83e84c HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 件 (本 PR は `REPORT_PY34.md` のみ)。
