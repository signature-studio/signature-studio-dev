# PY-31 (#1329): mixer 残り 57 関数の扱いの決定

親: #941 (PY-21)。前段: #1136 (PY-25, closed) で mock 定義のある mixer 18 関数を C 実装・`mixer_diff` (diffs 0) 済み。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 残り mixer 57 関数は **今回は実装しない (対象外・分割先 #941)**。mock (`host/fl_mock.mjs`) に意味論が無く、MCP tool からも一切呼ばれていないため、実装すると根拠の無い推測実装になる。
- mock に意味論を先に足す案は採らない。MCP の利用が 0 件のため、mock に足す動機がない。実機の挙動確認 (FL 26.1.7 PE) が要るので、PY-32 (#1336) と同じく別途の実機調査 issue で扱う。
- コード変更は 0 件 (`provider/` `host/` `tests/` は未変更)。本 PR は決定と根拠の記録のみ。

## 測定 (根拠)

- flapi mixer 公開数 75。C 実装済み 18 (`FL_H(mixer, *)` の定義)。未実装 57。
- mock (`host/fl_mock.mjs`) に定義がある mixer.* は 18 件で、すべて C 実装済み (mock-only の未実装 0 件)。
- MCP (`tools/python/analysis/mcp/MCP_TOOLS.md`) が使う mixer 関数 18 件はすべて C 実装済み (MCP 側の未実装 0 件)。
- 未実装 57 件のうち MCP 利用 0 件・mock 定義 0 件。

## 未実装 57 件 (分割先 #941)

afterRoutingChanged armTrack automateEvent deselectAll enableTrack enableTrackSlots getActiveEffectIndex getAutoSmoothEventValue getEqBandCount getEqBandwidth getEqFrequency getEqGain getEventIDName getEventIDValueString getEventValue getLastPeakVol getPluginMixLevel getPluginMuteState getRecPPS getSlotColor getSongStepPos getSongTickPos getTrackColor getTrackCount getTrackDockSide getTrackInfo getTrackPeaks getTrackPluginId getTrackRecordingFileName getTrackStereoSep isTrackArmed isTrackAutomationEnabled isTrackEnabled isTrackMuteLock isTrackMuted isTrackPluginValid isTrackRevPolarity isTrackSlotsEnabled isTrackSolo isTrackSwapChannels linkChannelToTrack linkTrackToChannel remoteFindEventValue revTrackPolarity selectAll selectTrack setActiveTrack setEqBandwidth setEqFrequency setEqGain setPluginMixLevel setPluginMuteState setSlotColor setTrackNumber setTrackStereoSep swapTrackChannels trackNumber

## 受入条件の判定 (#1329)

- [x] 残り mixer 関数の扱いを決める — 対象外 (今回非実装)・分割先 #941。理由は上記。
- [-] 意味論を決めた関数を `mixer_diff` に追加し diffs 0 — 決めた関数が 0 件のため対象なし。既存 `mixer_diff` は 48 calls・diffs 0 で PASS (下記)。
- [x] `node tests/provider_check.mjs` PASS — 実装数 70 のまま (変化なし)。
- [x] `FL_ENGINE=wasm node tests/all_tools.mjs` 48/48 ok — 維持。

## 検証 (測定 commit = 4c531879 = origin/main。コード差分 0 のため、以下は現 HEAD 上の再現)

- 環境: runner 4 vCPU、load average 2.82 (開始時)。`fl-win64` を `$RUNNER_TEMP/fl-win64` に展開し `FL_WIN64_DIR` に設定。`fetch_inputs.sh` rc=0。`build_cpython_wasm.sh` rc=0 (4 分 9 秒)。`build_flpy.sh` (`FLPY_SKIP_TABLE=1`) rc=0 (6.1 秒)。`provider/build.sh` rc=0 (1.5 秒)。

| コマンド | 結果 | rc | 所要 |
|---|---|---|---|
| `node tests/provider_check.mjs` | `{"functions":435,"implemented":70,"unimplemented":365,"mcp_static":60,"PASS":true}` | 0 | 0.37 秒 |
| `node tests/mixer_diff.mjs` | `{"calls":48,"diffs":0,"PASS":true}` | 0 | 0.06 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | `{"total":48,"ok":48,"soft_error":0,"raised":0,"host_calls":37425,"callback_roundtrip":true}` | 0 | 2.16 秒 (load 2.59) |

- コード差分: `git diff 4c531879 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。本 PR の変更は `tools/python/REPORT_PY31.md` の新規追加のみ。
- 測定は main 作業ツリー (`tools/python` は `4c531879` と同一、`git status` で `tools/python` の変更 0) で行った。ビルド物 (`dist/` `work/`) は gitignore 対象。

## 未解決

- 残り mixer 57 関数の意味論と C 実装 — 起票先 #941 (PY-21)。実機 (FL 26.1.7 PE) で確認が要るものは、その issue で未確認と明記すること。
