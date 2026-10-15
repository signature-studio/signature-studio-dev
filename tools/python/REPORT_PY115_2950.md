# PY-115 (#2950): flapi 表の追加引数 (soloChannel.value・getTrackName.maxLen) を C と mock に実装する

親: #2927 (PR #2956 merge 済み。引数個数表を FLEngine の書式に合わせ、追加引数が code 5 で拒否されなくなった)。前段: `tools/python/REPORT_PY115.md` (#2951 の mixer 格納式)。既知類型: 該当なし (lift 作業ではない。引数の意味論の欠落)。

## 結論

- `channels.soloChannel(index, value=-1, useGlobalIndex=0)`: `value` は -1 で反転、他は現在値の下位 1 B と比較し、不一致なら反転する。C と mock に実装した。`useGlobalIndex` は型検査のみで、container 切替は未モデル (子 #3654)。
- `mixer.getTrackName(index, maxLen=-1)`: `maxLen > 0` のときだけ切り詰める。長さが maxLen を超えるとき末尾から mask 外の文字を削り、先頭 maxLen 文字へ切る。C と mock に実装した。非 ASCII (PE は UTF-16) は未確認 (子 #3654)。
- `device.midiOutMsg` の 5 個目 (子 #3655)・`plugins.getParamValueString` の 3 個 (子 #3656) は未実装。1 run で PE 解析と実装の両方を終えられないと判断し、子に分けた。

## 1. 測定

- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` real 7.248 s。`toolchain-emsdk` を `$RUNNER_TEMP/opt` へ展開 real 10.991 s。
- 入力: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/python/fetch_inputs.sh` real 1.509 s、rc 0。
- build: `EMSDK_ENV=$RUNNER_TEMP/opt/emsdk/emsdk_env.sh bash tools/python/provider/build.sh` real 13.057 s、rc 0 (sysroot の初回生成を含む)。実行前 load average `0.52 0.64 0.34`。
- 差分検査 (測定 commit `6d095b9f6` の provider・mock・tests):
  - `node tests/channels_diff.mjs` → `{"calls":231,"diffs":0,"PASS":true}`
  - `node tests/mixer_diff.mjs` → `{"calls":69,"diffs":0,"PASS":true}`
  - `node tests/device_diff.mjs` → `{"calls":8,"rejects":4,"midi_out":5,"diffs":0,"PASS":true}`
  - `node tests/sig_arity_probe.mjs` → `{"kwsig_targets":24,"fails":0,"PASS":true}`
- 比較 (前 run の WIP `3e754b8b`、#2927 未 merge の表): `channels_diff`・`mixer_diff` は追加引数が code 5 で FAIL していた。#2956 merge 後の main の表では PASS。
- 未実行: `node tests/provider_check.mjs` と `FL_ENGINE=wasm node tests/all_tools.mjs` (48/48)。`dist/flpy.js` (CPython wasm) が無いため (§5)。

## 2. 逆アセンブルの事実 (PE `block00031_PE.bin`。前 run の解析)

| 対象 | VA | 根拠 |
|---|---|---|
| soloChannel ハンドラ | `0xd59bf0` | fmt `i\|ii`、kwlist `index/value/useGlobalIndex`。既定 `value=-1`・`useGlobalIndex=0` |
| soloChannel callback | `0xd59b40` → `0xd843d0` | `0x1005730(index, dl = useGlobalIndex>0)` で channel を解決。dl≠0 と dl=0 で別 container。範囲外 -4 |
| 反転 | `0xffaa60` | `value == -1` のとき。名前は呼出し形からの推定 |
| 一致判定 | (callback 内) | `cmp bl (value の下位 1 B), al (現在の solo)`。一致なら不変、不一致なら反転 |
| getTrackName ハンドラ | `0xd5e970` | fmt `i\|i`、kwlist `index/maxLen`。`maxLen > 0` のときだけ `0x12be470` |
| 切詰め | `0x12be470` | 長さ > maxLen のとき、末尾 (1-based 位置 len から 1 つずつ) を見る。大文字化 (a-z のみ) した文字が mask に無ければ `0x414f20(s, i, 1)` で 1 字削除し、長さ ≤ maxLen で終了。最後に `0x414ec0` で先頭 maxLen 字へ切る |
| 全文 | `0x12be2f0` | `maxLen ≤ 0` |
| mask | `0x12be684` (32 B bitmap) | `0-9` と大文字子音 `BCDFGHJKLMNPQRSTVWXYZ`。母音 `AEIOU`・空白・記号は削除対象 |

## 3. 変更

- `provider/fl_engine.c`: `soloChannel` を上記の規則にし、`track_name_fit` を追加して `getTrackName` に `maxLen` を入れた。`getTrackCount` (`NMIX - 2`) と `getEqBandCount` (3) は main の行を残した。
- `host/fl_mock.mjs`: 同じ規則 (`fitName`・`soloChannel`)。`mixer.getTrackName` は `(...a)` で `argI(a, 1, -1)` を読む。
- `tests/channels_diff.mjs` (+18 行)・`tests/mixer_diff.mjs` (+8 行): value -1/0/1/2/256・型不正、maxLen 0/1/3/4/100/既定/型不正。solo 状態は `isChannelSolo` で比較。
- 取り込み: 前 run の WIP は #2927 前の main 基点だったため、現 `origin/main` (`6e7d1e59b`) 上に cherry-pick した (衝突 2 箇所は上記 `getTrackName` を新規側に、`getTrackCount`・`getEqBandCount` は main 側を残して解消)。

## 4. 差分の確認

- 測定 commit `6d095b9f6` (コードを最後に変えた commit) から HEAD までの範囲差分: `git diff 6d095b9f6 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis` (本 REPORT の commit 後も 0 行)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `channels.soloChannel` の `useGlobalIndex` (`0x1005730` の dl 経路) | 値を変えても結果が変わらない (未モデル) | #3654 (PY-226) |
| `mixer.getTrackName` の非 ASCII (PE は UTF-16) | 非 ASCII 名の切詰めが未確認 | #3654 (PY-226) |
| `device.midiOutMsg` の 5 個目 `arg4` (word の bit 24–31) | 未実装。C・mock が送った word を記録しない | #3655 (PY-227) |
| `plugins.getParamValueString` の `index`・`slotIndex`・`useGlobalIndex` (`slotIndex≠-1` の経路 `0xd7fb34` 未読) | 未実装 | #3656 (PY-228) |
| `provider_check.mjs` §3 以降・`all_tools.mjs` 48/48 (`dist/flpy.js` 要) | 未検証 (§1) | 下記 §5.1 |

### 5.1 flpy の検証

(本節は検証後に更新する)
