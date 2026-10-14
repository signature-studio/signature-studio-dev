# PY-34 (#1344): playlist 未実装 38 関数の実機意味論 (調査結果)

親: #1336 (PY-32)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- playlist 38 関数の意味論は**本 run では未決定**。C provider (`provider/fl_engine.c`) へのコード変更は 0 件。
- 決められなかった理由: 同じ関数名の PyMethodDef 入口が PE 内に複数あり (下表)、どれが playlist 所属かの対応が未確定。
  戻り値・引数の意味も逆アセンブルを関数ごとに読まないと確定しない。推測実装は行わない。
- 残りは子 issue に分割する (下記「分割先」)。

## 測定 (ハンドラ入口の所在)

- 素材: `fl-win64` (`$HOME/artifacts/fl-win64.tar.zst`) を `tar --zstd -xf` で展開し、`extracted/block00031_PE.bin` を対象にした。
- 解析補助: `tools/python/analysis/flapi/pe_handler_probe.py` (既存)。実行は foreground、所要は数秒。
- 生成物: `work/playlist_probe.txt` (gitignore 対象・commit しない)。
- 38 関数すべてに少なくとも 1 件の入口が見つかった (名前の文字列は PE 内に存在)。
- 入口が複数ある名前 (同名が別モジュールにも存在すると推定。所属は未確定): `selectAll` 4 件・`deselectAll` 4 件・`getTrackColor` `isTrackSolo` `soloTrack` `isTrackMuted` `muteTrack` `isTrackMuteLock` `selectTrack` `isTrackSelected` 各 2 件。
- 入口が 1 件のみの名前: 残りの多く (例: `getDisplayZone` `lockDisplayZone` `liveDisplayZone` `triggerLiveClip` `scrollTo` `selectTool`)。

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
- [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok を維持 — 未達ではないが、コード差分 0 のため再測定は要らない。
