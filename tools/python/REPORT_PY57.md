# PY-57 (#1971): playlist 残り 36 関数の逆アセンブル (部分: 根拠を読めた 8 件)

親: #1934 (PY-56)。前段の所属確定は `tools/python/REPORT_PY44.md`、確定 2 件は `tools/python/REPORT_PY56.md`。

## 結論

- 残り 36 件のうち、戻り値・範囲 code を**確定できた関数は 0 件**。
- 逆アセンブルで骨格を読めたのは 8 件 (下表)。目視のみが 2 件 (`getVisTimeTick`・`getVisTimeStep`)。未読は 26 件。
- `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/provider_check.mjs` は変更していない。推測で実装しない (規範)。
- 残りは子 issue に分割した (本文末尾の「未解決」)。

## 測定

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C` で展開。実測 real 5.68 s (user 4.90 s / sys 5.70 s)。展開後 3.3 GB。load 測定なし。
- 逆アセンブル 1 回 (`pe_disasm.py <VA> <命令数>`): real 0.084 s (user 0.063 s / sys 0.022 s)。
- 解析対象は `extracted/block00031_PE.bin` (`flstudio_win64_26.1.7.5653.exe` 同梱)。

## 読めた関数 (VA は `pe_disasm.py` の出力)

| 関数 | VA | 読めた事実 (根拠 VA) | 未確定 |
|---|---|---|---|
| `isTrackMuted` | 0xd56160 | index を `[rbp+0x2c]` に受ける (`0xd56172`)。範囲 `1 <= index <= 0x1f4 (500)` (`0xd5618b`〜`0xd56197`)。範囲外は `-4` (`0xd561bd`)。範囲内は `0x12e1a20` の戻り値から `[rax+rcx*4+0x3c]` (要素 `0x45*4` bytes) を読み、`!= 0` を bool 化 (`0xd561a6`〜`0xd561ab`) して `0xd561b9` の関数へ渡す | `0xd561b9` の呼び出し先の意味・`-4` の Python 側の表現 |
| `isTrackSolo` | 0xd566f0 | `isTrackMuted` と同形: 範囲 `1..500`・範囲外 `-4`・`0x12e68a0` を経由して bool | `0x12e68a0` の意味 (未読) |
| `getTrackActivityLevel` | 0xd56ea0 | `isTrackMuted` と同じ範囲判定。範囲内は `[rax+rcx*4+0x5c]` を `float` として読み `cvtss2sd` で double 化して返す | 呼び出し先の意味 |
| `muteTrack` | 0xd56330 | 引数 2 個 (index・value) を保存。`0xd58d80` で track の先頭ポインタを取得。既定値 `-1` / `0` を `[rbp+0xa8]`・`[rbp+0xa4]` に置き、PyArg 書式 (`lea r9,[rip+...]`) で受ける。その後 `0xd843d0` を 9 引数で呼ぶ | 書式文字列の中身 (未読)・`value=-1` の意味 (toggle か)・`0xd843d0` の引数の意味 |
| `selectTrack` | 0xd56b60 | 引数 index を受ける (`0xd56b9e`〜`0xd56bb7`)。既定値 `-1` (`[rbp+0x98]`)。`0xd843d0` を呼ぶ形は `muteTrack` と同じ | 書式文字列・`0xd843d0` の引数の意味 |
| `getVisTimeBar` | 0xd580f0 | 引数なし。グローバル `int*` の値を `ecx` に入れ、グローバル関数ポインタを呼ぶだけ | 呼び出し先の意味 |
| `getSongStartTickPos` | 0xd581f0 | `getVisTimeBar` と同形 (グローバル `int` を渡して転送) | 呼び出し先の意味 |
| `getPerformanceModeState` | 0xd585d0 | グローバルの 1 byte (`movzx rcx, byte ptr [rax]`) を渡して転送 | 呼び出し先の意味。戻り型は表で bool |

- 目視のみ: `getVisTimeTick` (0xd58110)・`getVisTimeStep` (0xd58130) は `getVisTimeBar` と同形に見えるが、本 run では完全には読んでいない。
- 範囲 code: 範囲外で `-4` (`0xfffffffffffffffc`) を返す経路が `isTrackMuted`・`isTrackSolo`・`getTrackActivityLevel` で同じ。ただし `-4` が repo の `RANGE` にどう対応するかは未確認。
- `0xd82c20` は `-4` や `0` などの状態 int を受ける共通の後処理に見える (`ecx` を `[rbp+0x24]` に保存し、0 のとき `0xc38bc0` を呼ぶ分岐を持つ)。役割は未確定。

## 未読 26 件

REPORT_PY44 の未実装 38 件から、確定 2 件 (`selectTool`・`scrollTo`・PY-56)、読めた 8 件、目視 2 件を除いた残り 26 件:

`soloTrack`・`isTrackMuteLock`・`muteTrackLock`・`isTrackSelected`・`selectAll`・`deselectAll`・`getTrackColor`・`getTrackActivityLevelVis`・`getDisplayZone`・`lockDisplayZone`・`liveDisplayZone`・`getLiveLoopMode`・`getLiveTriggerMode`・`getLivePosSnap`・`getLiveTrigSnap`・`getLiveBlockStatus`・`getLiveStatus`・`getLiveBlockColor`・`triggerLiveClip`・`refreshLiveClips`・`incLivePosSnap`・`incLiveTrigSnap`・`incLiveLoopMode`・`incLiveTrigMode`・`liveTimeToBlockNum`・`liveBlockNumToTime`

- 件数の内訳: 42 件 (playlist 配列) − 実装済み 4 件 (`trackCount`・`getTrackName`・`setTrackName`・`setTrackColor`) = 未実装 38 件。このうち確定 2・読めた 8・目視 2 を除いて 26 件。
- `getTrackColor` は REPORT_PY44 の表 (37 行) に行が無い。playlist 配列には存在する (`tools/python/provider/gen/fl_table.c:454`)。PY44 の表の欠落は本 PR では直さず、ここで補う。

## 検証

- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_disasm.py 0xd56160 60` (foreground・0.1 s 以下)。
- コード差分: 本 PR は `tools/python/REPORT_PY57.md` と `docs/DOC_MAP.md` の REPORT 索引行のみ。C provider・mock・テストは無変更のため、`all_tools.mjs` 48/48 は再測定しない (`docs/WORKFLOW.md` §6)。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未読 26 件の戻り値・範囲 code・引数の意味 | C 実装が決まらない | #2026 (PY-61) |
| 読めた 8 件の呼び出し先 (`0xd843d0`・`0x12e68a0`・`0xd82c20` ほか) の意味と `-4` ↔ `RANGE` の対応 | 8 件の実装が決まらない | #2026 (PY-61) |
| 決めた関数の `fl_engine.c` 実装・`provider_check.mjs` 件数更新・mock 差分 0・`all_tools` 48/48 | 受入条件の残り | #2027 (PY-62) |
