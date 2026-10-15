# PY-115 (#2950): flapi 表の追加引数 (soloChannel.value・getTrackName.maxLen) を C と mock に実装する

親: #2927 (PR #2956 merge 済み。引数個数表を FLEngine の書式に合わせ、追加引数が code 5 で拒否されなくなった)。前段: `tools/python/REPORT_PY115.md` (#2951 の mixer 格納式)。既知類型: 該当なし (lift 作業ではない。引数の意味論の欠落)。

## 結論

- `mixer.getTrackName(index, maxLen=-1)`: `maxLen > 0` のときだけ切り詰める。長さが maxLen を超えるとき末尾から mask 外の文字を削り、先頭 maxLen 文字へ切る。PE (`0x12be470`) で確定し、C と mock に実装した。非 ASCII (PE は UTF-16) は未確認 (子 #3654)。
- `channels.soloChannel(index, value=-1, useGlobalIndex=0)`: `value == -1` で反転する (`0xffaa60` の呼出しを PE で確認)。`value ≠ -1` の比較は PE の比較対象 `0xffa940(k,0)` が現在の solo と同定できていない (§2)。C と mock の「現在の solo との比較」は推定で、受入条件から外して子 #3654 に移した。`useGlobalIndex` は型検査のみ (子 #3654)。
- 差分検査 (`channels_diff`・`mixer_diff`) が確かめるのは C≡mock であり、PE≡C ではない。
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
- flpy (CPython wasm): `bash build_cpython_wasm.sh` real 3 分 21 秒 rc 0 → `FLPY_SKIP_TABLE=1 EMSDK_DIR=<emsdk 展開先> bash build_flpy.sh` real 4.789 s rc 0 (`FLPY_SKIP_TABLE=1` で追跡済みの `flapi_table.json` を再生成しない)。
- `node tests/provider_check.mjs` → `{"functions":435,"implemented":155,"unimplemented":280,"mcp_static":60,"PASS":true}`、real 0.275 s。
- `FL_ENGINE=wasm node tests/all_tools.mjs` → `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}`、real 1.303 s。
- 修正 run (差し戻し対応。C・mock のソースは変えていない。変えたのは本 REPORT・DOC_MAP・PR 本文):
  - 素材: `$ARTIFACTS_DIR` (`/home/runner/artifacts`) に `toolchain-emsdk` が無かったため、上流 emsdk を `git clone --depth 1` して `./emsdk install 6.0.12`・`./emsdk activate 6.0.12` で取得した (版は `tools/m1/flags.sh` の pin と同じ。取得の所要は未計測)。PE は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <tmp> extracted/block00031_PE.bin` real 2.178 s。
  - build: `EMSDK_ENV=<上流 emsdk>/emsdk_env.sh bash tools/python/provider/build.sh` real 1.192 s、rc 0 (sysroot キャッシュ済み)。
  - 差分検査 (コード差分 0 の HEAD 上): `channels_diff` `{"calls":231,"diffs":0,"PASS":true}`、`mixer_diff` `{"calls":69,"diffs":0,"PASS":true}`、`device_diff` `{"calls":8,"rejects":4,"midi_out":5,"diffs":0,"PASS":true}`。
  - ネガティブコントロール (C を 1 件ずつ壊して実行し、元に戻して再ビルド):
    - A: `provider/fl_engine.c` の `soloChannel` の比較 `(uint8_t)v != k->solo` を `==` に反転 → `channels_diff` が FAIL (`channels/playlist 差分 7 件`)。`mixer_diff` は PASS (`{"calls":69,"diffs":0,"PASS":true}`)。
    - B: `track_name_fit` の mask 文字列に `A` を 1 字追加 → `mixer_diff` が FAIL (`差分 2 件`)。`channels_diff` は PASS (`{"calls":231,"diffs":0,"PASS":true}`)。
    - 元に戻して再ビルド後、`channels_diff` 231/0 PASS・`mixer_diff` 69/0 PASS。`git diff --stat HEAD -- tools/python/provider` は空。

## 2. 逆アセンブルの事実 (PE `block00031_PE.bin`。前 run の解析 + 修正 run の追加読み)

| 対象 | VA | 根拠 |
|---|---|---|
| soloChannel ハンドラ | `0xd59bf0` | fmt `i\|ii`、kwlist `index/value/useGlobalIndex`。既定 `value=-1`・`useGlobalIndex=0` |
| soloChannel callback | `0xd59b40` → `0xd843d0` | `0x1005730(index, dl = useGlobalIndex>0)` で channel `k` を解決。dl≠0 と dl=0 で別 container。範囲外 -4。先頭の `call [vtable+0x98]` (未同定) の戻り値が 0 なら何もせず返る |
| `value == -1` の分岐 | `0xd59b40` 内 `cmp rbx, -1` | `0xffaa60(k, dl)` を呼ぶ。`dl` は `.text` の 1 B (`0xd59bd0` = 0) |
| `value ≠ -1` の比較 | `0xd59b40` 内 `cmp bl, al` | `bl` = value の下位 1 B、`al` = `0xffa940(k, 0)`。一致なら不変、不一致なら `0xffaa60(k, 0)` で反転。**`al` は現在の solo と同定していない** (下記) |
| solo getter | `0xd59a80` (`isChannelSolo`) | `[k+0x32e]≠0` かつ `[k+0x892]==0` かつ `0xffa940(k,0)≠0` のとき 1 (`0xd59ac4`〜`0xd59b0c` の分岐) |
| `0xffa940(k, dl)` | (`0xffa940`) | j を 0..count−1 で走査し、j == `[k+0x794]` を飛ばす。dl≠0 のときは `[j+0x798]==[k+0x798]` を要求。`[j+0x32e]≠0` の j に `[j+0x892]==0` が 1 つでもあれば 0、無ければ 1。dl=0 のとき k の `+0x32e`・`+0x892` は読まない |
| `0xffaa60(k, flag)` | (`0xffaa60`) | `esi = 0xffa940(k, flag&1)`・`edi = 0xffaa00(k)` (`0xffaa00` 未読)。esi==0 なら loop `0xffab33`: edi==0 のとき各 j の `[j+0x891]` を 0 にする。flag&1 のときは `[j+0x798]==[k+0x798]` の j だけを対象にし、`[j+0x892]≠0` かつ j≠k の j は飛ばす。残った j には (edi==0 のとき先に `[j+0x891]` を 2 (`[j+0x32e]≠0`) か 1 に設定して) `0x737640` を呼ぶ。esi≠0 なら loop `0xffaa9a` (`[j+0x891]≠0` の j に `0x737640`)。どちらも `[j+0x892]` を書かない |
| getTrackName ハンドラ | `0xd5e970` | fmt `i\|i`、kwlist `index/maxLen`。`maxLen > 0` のときだけ `0x12be470` |
| 切詰め | `0x12be470` | 長さ > maxLen のとき、末尾 (1-based 位置 len から 1 つずつ) を見る。大文字化 (a-z のみ) した文字が mask に無ければ `0x414f20(s, i, 1)` で 1 字削除し、長さ ≤ maxLen で終了。最後に `0x414ec0` で先頭 maxLen 字へ切る |
| 全文 | `0x12be2f0` | `maxLen ≤ 0` |
| mask | `0x12be684` (32 B bitmap) | `0-9` と大文字子音 `BCDFGHJKLMNPQRSTVWXYZ`。母音 `AEIOU`・空白・記号は削除対象 |

### soloChannel の比較対象 (`value ≠ -1`) は未同定

- getter `0xd59a80` は `[k+0x32e]≠0 ∧ [k+0x892]==0` のとき `0xffa940(k,0)≠0` を返す。両条件が偽のとき getter は 0 だが、比較対象の `0xffa940(k,0)` は 1 になりうる (`0xffa940` は k の `+0x32e`・`+0x892` を読まない)。よって `cmp bl, al` を「現在の solo との比較」と読む根拠は、2 条件が成り立つ範囲に限られる。
- C・mock の `k.solo` (bool) が PE のどの状態に対応するかは未同定。`0xffaa60` が書くのは `[j+0x891]` で、getter が読む `[j+0x892]` は書かない (`0xffaa00`・`0x737640` 未読)。反転が getter の出力を変えることは PE で未確認。
- 次の run で決めること (子 #3654): `0xffa940` の戻り値と getter の値を比べる実測、`0xffaa00`・`0x737640` の役割、`[j+0x892]` を書く箇所の特定。

## 3. 変更

- `provider/fl_engine.c`: `soloChannel` の比較を上記の推定 (`(uint8_t)v != k->solo` で反転) にし、`track_name_fit` を追加して `getTrackName` に `maxLen` を入れた。`getTrackCount` (`NMIX - 2`) と `getEqBandCount` (3) は main の行を残した。
- `host/fl_mock.mjs`: 同じ規則 (`fitName`・`soloChannel`)。`mixer.getTrackName` は `(...a)` で `argI(a, 1, -1)` を読む。
- `tests/channels_diff.mjs` (+18 行)・`tests/mixer_diff.mjs` (+8 行): value -1/0/1/2/256・型不正、maxLen 0/1/3/4/100/既定/型不正。solo 状態は `isChannelSolo` で比較。
- 取り込み: 前 run の WIP は #2927 前の main 基点だったため、現 `origin/main` (`6e7d1e59b`) 上に cherry-pick した (衝突は C と mock の `getTrackName` の 2 箇所。maxLen 対応版を採り、`getTrackCount`・`getEqBandCount` は main 側の行を残した)。

## 4. 差分の確認

- 測定 commit `6d095b9f6` (コードを最後に変えた commit) から HEAD までの範囲差分: `git diff 6d095b9f6 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis` (本 REPORT の commit 後も 0 行)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `channels.soloChannel` の `value ≠ -1` の比較対象 (`0xffa940(k,0)`) と getter (`0xd59a80`) の同定。C・mock の `k.solo` が PE のどの状態か | 比較・反転の結果が PE と一致するか未確認 (検査は C≡mock のみ) | #3654 (PY-226) |
| `channels.soloChannel` の `-1` 反転の効果 (`0xffaa60` は `[j+0x891]` を書く。`0xffaa00`・`0x737640` 未読) | getter の出力が反転するか未確認 | #3654 (PY-226) |
| `channels.soloChannel` の `useGlobalIndex` (`0x1005730` の dl 経路) | 値を変えても結果が変わらない (未モデル) | #3654 (PY-226) |
| `mixer.getTrackName` の非 ASCII (PE は UTF-16) | 非 ASCII 名の切詰めが未確認 | #3654 (PY-226) |
| `device.midiOutMsg` の 5 個目 `arg4` (word の bit 24–31) | 未実装。C・mock が送った word を記録しない | #3655 (PY-227) |
| `plugins.getParamValueString` の `index`・`slotIndex`・`useGlobalIndex` (`slotIndex≠-1` の経路 `0xd7fb34` 未読) | 未実装 | #3656 (PY-228) |

- flpy 経由の検査 (`provider_check.mjs`・`all_tools.mjs` 48/48) は §1 の前 run の測定のとおり PASS (コード差分 0 行)。修正 run では再実行していない。
