# PY-62 (#2027): PY-61 で確定した playlist 関数のうち表で実装できる 8 件を C provider と mock に実装

親: #1971 (PY-57)。前段: #2026 (PY-61・`tools/python/REPORT_PY61.md`)。子: #2883 (PY-102・表の引数数の不一致)。既知類型との関係: 該当なし (lift 作業ではない)。起動・GUI に関わらないため製品 KPI は対象外。

## 結論

- PY-61 の未読 26 件のうち、型・範囲 code と戻り値の変換が確定し、表の引数形で実装できる **8 件**を実装した: `getTrackColor`・`isTrackMuteLock`・`getTrackActivityLevelVis`・`getLiveLoopMode`・`getLiveTriggerMode`・`getLivePosSnap`・`getLiveTrigSnap`・`muteTrackLock` (value -1 と省略は反転、それ以外は下位 1 byte の設定・§2・§5-3)。
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
| muteTrackLock (0xd565c0) | value -1 (省略を含む) で +0xd5 byte を反転、それ以外は下位 1 byte を書く (§2・§5-3) | +0xd5 |

- getLive\* の 4 件は書込み側 (`incLive*` 等) が未実装のため、mock と C では既定値 0 のまま読める。muteTrackLock だけは呼出しで反転する (`isTrackMuteLock` に反映される)。
- getLive\* 4 件 (`getLiveLoopMode`・`getLiveTriggerMode`・`getLivePosSnap`・`getLiveTrigSnap`) の戻り値は field の生の int である。enum の意味と既定値 0 は PY-61 から未確定のままで、本 PR では確定していない (既定値は仮置き)。

## 2. 実装しなかった部分と差

- **muteTrackLock の `value` 引数** (binary の書式 `'i|i'`・既定 -1・-1 は反転、他は下位 1 byte を書く (`REPORT_PY61` §3))。main の #2927 で生成表 `provider/gen/fl_table.c` が kwsig 書式 (必須 1・最大 2) に合ったため、C と mock は value を受ける (`tests/playlist_diff.mjs` で確認・§5-3)。表の残りの不一致は §4、子 #2883 (PY-102)。
- **準備判定 (-2)**: binary は vtable 呼出し `[rax+0x98]` で準備を判定するが、その述語は未確定。mock と C は常に準備済みとして扱う。
- **getTrackColor と setTrackColor の byte 順**: `getTrackColor` は PY-61 の確定どおり R/B を入替えて返す。既存の `setTrackColor` (C・mock とも素の値を格納) は格納 byte 順を逆アセンブルしていない。そのため `setTrackColor(3, 0x123456)` の後の `getTrackColor(3)` は `0xff563412` を返す (実測・`tests/playlist_diff.mjs` の末尾)。set と get の round trip は一致しない。この 1 組の期待値は setter の格納順が確定するまで暫定である (既定案: 現状のまま)。

## 3. 未実装の 18 件 (PY-61 で未確定)

- helper の意味が未確定 (`REPORT_PY61` §4-1・§6 の未解決): `isTrackSelected` (helper 0xd56990)・`getDisplayZone` (0xd85210)・`getLiveBlockStatus`・`getLiveStatus`・`getLiveBlockColor` (0x100c030)・`liveTimeToBlockNum` (0x1221b30)・`liveBlockNumToTime` (0x1221aa0) の 7 件。
- 操作コアが未確定: `soloTrack` (0x12e7f80・0xbd68e0)・`selectAll`/`deselectAll` (mode 4/6 の意味)・`lockDisplayZone`・`liveDisplayZone`・`triggerLiveClip`・`refreshLiveClips`・`incLivePosSnap`・`incLiveTrigSnap`・`incLiveLoopMode`・`incLiveTrigMode` の 11 件。
- 起票先: いずれも子 #2809 (PY-91)。

## 4. 表の引数数と binary の書式の不一致 (子 #2883)

### 4-1. 数え方 (定義)

- 母集団: `analysis/flapi/flapi_table.json` の全 435 関数 (`function_total`)。
- 比較できるのは、`sig` (stub 署名。`sig.params` の個数 np) と `kwsig.max` (PE 由来の書式の最大引数数) の**両方がある 273 件**。このうち np ≠ kwsig.max を**不一致 24 件**とする。
- この定義は `analysis/flapi/sig_arity_check.py` (PY-70・#2500) と同じ。再現は次の 1 行 (出力の `after:` 行):

```sh
python3 tools/python/analysis/flapi/sig_arity_check.py tools/python/analysis/flapi/flapi_table.json tools/python/analysis/flapi/flapi_table.json | grep '^after'
# after: 対象 273 件・一致 249・不一致 24
```

- 比較しない件数 (np と max を両方比べられないので数えない): `sig` が無い 30 件 (kwsig.max は 1〜5)、`kwsig.max` が無い 132 件 (うち sig あり 121 件・sig なし 11 件)。`plugins.getPresetCount` だけは sig (np 1) があり kwsig.max が無い。

### 4-2. 差し戻し時の 55 件との関係

差し戻し時の「55 件」は、`sig` 欠落 30 件を np = 0 と見なし、`kwsig.max` 欠落 1 件 (`plugins.getPresetCount`・np = 1) を max = 0 と見なして同じ比較に入れた数である。内訳は **24 + 30 + 1 = 55**。方向も一致する: kwsig.max > np は 22 + 30 = 52 件、np > kwsig.max は 2 + 1 = 3 件。

前版の「`sig` が空の 13 件を含む」は誤り。24 件のうち `sig.params` が空は **10 件** (screen.* の 10 件。`screen.addTextLine` は np 2)。

### 4-3. 不一致 24 件の一覧

`fmt` は `kwsig.fmt` (binary 由来の書式)。方向は kwsig.max と np の大小。

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

- 「`sig` が空」(np 0) の 10 件は `screen.*` の 10 件 (`screen.*` の `sig` 空は `#2554` (PY-70・positional-only の読み取り) と同じ系統の可能性があるが、未確認)。
- `muteTrackLock` (#2) の 2 個目の引数 `value` は、#2927 後の表 (最大 2) で dispatch が受け、C・mock とも §2 の規則で処理する (§5-3)。

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

- コード差分 (測定 commit から HEAD まで、C・mock・テスト): `git diff 1d71dd27 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR の後続コミットは REPORT・`docs/DOC_MAP.md` と PR 本文だけ)。
- `all_tools` の wasm 出力は tracked ファイルを変えない。根拠: `git diff --stat 1d71dd27 HEAD -- tools/python/analysis/mcp/` の出力は 0 行。

### 5-1. 差し戻し対応 (fix round 1) の検証

- 検証は差し戻し時と同じコード (`10617273`) で行った。`provider`・`host`・`tests` は対応で変更していない (`git diff 1d71dd27 HEAD -- tools/python/provider tools/python/host tools/python/tests` = 0 行)。
- emsdk: 上流から `emsdk install 6.0.12` でユーザー領域に導入し (`[EMSDK]` の symlink 先)、`emsdk activate 6.0.12` (`emcc --version` = 6.0.12)。`toolchain-emsdk` の素材は本 run では取得していない (素材置き場は `fl-win64` のみ)。次 run の素材指定は PR 本文の `oc_artifacts` 行。
- `provider/build.sh` (EMSDK_ENV を上記に指定): real 1.301 s・警告 0 (出力は fl_table 行と flprov.js/wasm の 2 行のみ)。
- `node tests/playlist_diff.mjs` (ビルド直後): calls 42・diffs 0・PASS・real 0.090 s。

**ネガティブコントロール (1 件ずつ壊して FAIL を確認し、退避コピーで戻す)**:

| NC | 壊した箇所 | 結果 | 差分数 | rc |
|---|---|---|---|---|
| NC-C: C の muteTrackLock の反転を外す | `provider/fl_engine.c:213` `p->lock = !p->lock` → `p->lock = p->lock` (再ビルド) | `playlist_diff` FAIL | 2 | 1 |
| NC-M: mock の getTrackColor の R/B 入替えを外す | `host/fl_mock.mjs:149` の R/B 入替え式 → `(u \| 0xff000000) >>> 0` (C は再ビルドのまま) | `playlist_diff` FAIL | 7 | 1 |
| 復元後 | 退避コピーを戻して再ビルド | `playlist_diff` PASS | 0 | 0 |

- 復元後の `git status --porcelain=v1 -- tools/python/provider tools/python/host tools/python/tests` は空 (変更なし)。
- 同じ HEAD のコード・復元後の全検査 (`FL_ENGINE=wasm` で wasm 側を使用。所要は `/usr/bin/time` の elapsed、n=1):

| 検証 | 結果 | 所要 |
|---|---|---|
| `node tests/playlist_diff.mjs` | calls 42・diffs 0・PASS | 0.04 s |
| `node tests/provider_check.mjs` | functions 435・implemented 85・unimplemented 350・PASS | 0.36 s |
| `node tests/channels_diff.mjs` | calls 107・diffs 0・PASS | 0.05 s |
| `node tests/mixer_diff.mjs` | calls 48・diffs 0・PASS | 0.05 s |
| `node tests/device_diff.mjs` | calls 7・rejects 4・midi_out 4・diffs 0・PASS | 0.04 s |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・raised 0・host_calls 37425・callback_roundtrip true | 未計時 |

- 検証 HEAD のコード: `10617273` (差し戻し対応では provider・host・tests を変更していない。上記の `git diff 1d71dd27 HEAD -- tools/python/provider tools/python/host tools/python/tests` = 0 行)。
- `provider_check.mjs` は CPython wasm (`dist/flpy.js`) と `work/midi.py` を要する。前段は本文 §5-2 を参照。

### 5-2. provider_check の前段と NC

- 前段 (同じ runner・同じ HEAD のコード): `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (real 5.530 s)、`fetch_inputs.sh` (rc 0・`work/midi.py` 等を配置)、`build_cpython_wasm.sh` (wasm 段 real 2 分 45.8 秒・rc 0。1 回目の試行は native 段が完了し wasm 段で止まった: real 1 分 50.7 秒・rc 1)、`FLPY_SKIP_TABLE=1 build_flpy.sh` (real 5.954 s・rc 0)。
- 1 回目の失敗の原因: `build_cpython_wasm.sh` は `[EMSDK]` の `emsdk_env.sh` を固定で読み、この runner では存在しなかった (`source` が失敗して静かに終了)。`[EMSDK]` の位置を導入先への symlink にして解消した。repo の script は変更していない (runner 上の環境設定)。
- `node tests/provider_check.mjs` (HEAD と同じコード): functions 435・implemented 85・unimplemented 350・mcp_static 60・PASS・real 0.36 s。

**NC-P (provider_check)**: `provider/fl_engine.c:205` の `FL_H(playlist, isTrackMuteLock)` 行を削除して再ビルド。`gen_provider.py --check-handlers` は rc 0 で通過し (ハンドラ 84)、`provider/build.sh` も rc 0。`provider_check.mjs` は `AssertionError [ERR_ASSERTION]: 実装済みのはず: playlist.isTrackMuteLock が未実装` で rc 1 (FAIL)。元に戻して再ビルドした後は PASS (implemented 85)。ビルドの検査 (`--check-handlers`) は削除を検出せず、検出は provider_check の実装数検査だけが行う。

### 5-3. main 取り込み後の再測定 (競合解消 merge)

- 測定 commit (コードを最後に変えた commit): `c0638cf3` (`test(python): playlist_diff covers muteTrackLock set semantics (#2027)`)。
- 取り込み: main `15393741` (merge `ca8895d6`・`38be58be`)、main `a7ea7667` (merge `38be58be`)。main 側の PY-89 (#2805)・PY-87 (#2738) の provider・host・tests 変更と、#2927 (`46f5a007`・表の引数個数を kwsig 書式に合わせる) を取り込んだ。
- 競合: `docs/DOC_MAP.md` (REPORT 行は両方残す)、`tools/python/tests/provider_check.mjs` (2 回。実装集合は pl61・stub89・pe87 を全て含め、件数は 91 / 344)。`fl_engine.c`・`fl_mock.mjs` は自動 merge で、重複実装は無い。
- 表変更への対応 (`decb212c`): #2927 で `playlist.muteTrackLock` の表の引数数が 1 から kwsig `i|i` (必須 1・最大 2) になった。C と mock は REPORT_PY61 §3 の規則 (value -1 (省略を含む) は反転、それ以外は下位 1 byte を書く) を実装した。`tests/playlist_diff.mjs` に設定経路の呼出し 7 件を追加 (42 → 49 呼出し)。
- NC: C の value 分岐を外して (常に反転) 再ビルド → `playlist_diff` FAIL (差分 3 件・rc 1)。元に戻して再ビルド → PASS (49 呼出し)。
- コード差分: `git diff c0638cf3 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本節の後続 commit は REPORT と PR 本文のみ)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf` real 5.525 s)、`fetch_inputs.sh` (rc 0)、`build_cpython_wasm.sh` (real 4 分 13.061 秒・rc 0。取り込み後は再ビルドしていない。`git diff --stat origin/main HEAD -- tools/python/build_cpython_wasm.sh tools/python/build_flpy.sh tools/python/src` は 0 行)、`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0・取り込み後に再ビルド)。
- 測定時の load average (`/proc/loadavg` の 1 分値): 0.27。

| 検証 (`c0638cf3`) | 結果 | 所要 |
|---|---|---|
| `provider/build.sh` | 成功・435 関数・ハンドラ 91 | real 0.916 s |
| `node tests/playlist_diff.mjs` | calls 49・diffs 0・PASS | 0.048 s |
| `node tests/provider_check.mjs` | functions 435・implemented 91・unimplemented 344・mcp_static 60・PASS | 0.367 s |
| `node tests/channels_diff.mjs` | calls 123・diffs 0・PASS | 0.052 s |
| `node tests/mixer_diff.mjs` | calls 49・diffs 0・PASS | 0.049 s |
| `node tests/device_diff.mjs` | calls 8・rejects 4・midi_out 5・diffs 0・PASS | 0.049 s |
| `node tests/general_diff.mjs` | calls 9・diffs 0・PASS (main #2738) | 0.048 s |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・raised 0・host_calls 37425・callback_roundtrip true | real 2.081 s |

§4 の表 (不一致 24 件) は `1d71dd27` 時点の表の測定で、#2927 の後の件数は未測定。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 表の引数数の不一致 24 件 (比較可能な 273 件中・§4)。muteTrackLock の `value` は #2927 で表が合い本 PR で対応済み (§5-3)。残りの件数は #2927 後に未測定 | 不一致の関数で 2 個目以降の引数が code 5 になりうる | #2883 (PY-102) |
| sig 欠落 30 件・kwsig.max 欠落 1 件 (比較対象外・§4-1) | 表の arity を未確認のまま | #2883 本文への追記 (PM 判断) |
| getTrackColor と setTrackColor の格納 byte 順 (set→get の round trip が一致しない) | 色の設定と読出しが食い違う。期待値 `0xff563412` は setter 確定まで暫定 (既定案: 現状のまま) | #2809 (PY-91)。setter の逆アセンブルを対象へ追記する必要あり (PM 判断) |
| getLive\* 4 件の戻り値の enum 意味と既定値 0 | 既定値の正しさ未確定 | #2809 (PY-91) |
| 残り 18 件 (§3)・準備判定 (-2)・既定値の実機値 | 受入条件の残り・初期値の正しさ | #2809 (PY-91) |
