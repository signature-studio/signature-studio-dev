# PY-226 (#4674): mixer.getTrackName の非 ASCII 切詰めを PE (UTF-16) で確定し、C・mock に反映する

親: #3654 (PY-226 の受入 3 を子 #4674 へ移した)。前段: `tools/python/REPORT_PY115_2950.md` (`maxLen` の ASCII 版)。既知類型: 該当なし (lift 作業ではない。文字列の符号化の不一致)。

## 結論

- PE `0x12be470` の切詰めは **UTF-16 code unit** 単位。長さの比較・後ろから 1 unit ずつ見る判定・削除 (`0x414f20`) はすべて unit 数で行う。
- 判定は a-z を大文字化してから mask (`0x12be684`: `0-9` と大文字子音 `BCDFGHJKLMNPQRSTVWXYZ`) に当てる。判定 `cmp cx,0xff; ja` により、0x100 以上の unit (非 ASCII) は mask 外として削除される。
- C (`provider/fl_engine.c` の `track_name_fit`) は UTF-8 バイト列で数えていたため、非 ASCII 名で PE と食い違っていた。C は UTF-8 ⇄ UTF-16 の変換を挟んで unit 単位に直した。mock は JS 文字列 (UTF-16) で元から同じ数え方なので、切れた境界の孤立サロゲートを U+FFFD にする処理を足した。
- 差分検査 `tests/mixer_diff.mjs` に非 ASCII の 7 呼出しを追加し、C≡mock で PASS。変異 (mask に `A` を追加) で FAIL することを確認した。

## 1. 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` から `block00031_PE.bin`・`block25159/24429/24430/24618_DATA.bin` を展開 (`tar --zstd -xf ... --wildcards` real 2.848 s)。`toolchain-emsdk.tar.zst` を `$RUNNER_TEMP/opt` へ展開 real 3.705 s。
- 入力: `FL_WIN64_DIR=$RUNNER_TEMP/fl bash tools/python/fetch_inputs.sh` rc 0 (mac pkg 無し → win64 の DATA block から取得)。
- provider build: `EMSDK_ENV=$RUNNER_TEMP/opt/emsdk/emsdk_env.sh bash tools/python/provider/build.sh` real 15.260 s、rc 0 (sysroot の初回生成を含む)。
- 逆アセンブル: `objdump -D -b binary -m i386:x86-64` で `0x12be470` (切詰め)・`0x414f20` (1 unit 削除)・`0x414ec0` (先頭 n unit へ切る) を読んだ。mask 32 B `0x12be684` は `0-9BCDFGHJKLMNPQRSTVWXYZ` の bit のみ (0x80 以上は 0)。

| 検査 (コード commit `0a49395f4` 上) | 結果 |
|---|---|
| `node tests/mixer_diff.mjs` | `{"calls":76,"diffs":0,"PASS":true}` |
| `node tests/channels_diff.mjs` | `{"calls":238,...,"diffs":0,"grid_diffs":0,"PASS":true}` |
| `node tests/device_diff.mjs` | `"diffs":0,"PASS":true` |
| 変異 (C の mask に `A` を追加、再ビルド) | `mixer_diff` FAIL (`mixer 差分 3 件`) |
| 変異を戻して再ビルド | `mixer_diff` 76/0 PASS |
| `node tests/sig_arity_probe.mjs` (本 PR) | FAIL: `screen.drawText` の max=6 が code 5 |
| 同 probe を `origin/main` (`14aae5450`) で実行 | 同じく FAIL: `screen.drawText` 1 件。本 PR の影響ではない |
| `node tests/mixer_diff.mjs` を `origin/main` で実行 | `{"calls":69,"diffs":0,"PASS":true}` (本 PR で追加した 7 件を除く) |

## 2. 未実施 (実行環境の制約)

- `provider_check.mjs`・`all_tools.mjs` (flpy 経由): `build_cpython_wasm.sh` は 4 分 0 秒で成功 (rc 0) したが、`build_flpy.sh` が `set -u` の下で `EMSDK_DIR` を参照して落ちた。`source emsdk_env.sh` が `EMSDK_DIR` を unset するためで、`build_flpy.sh` 側の既知の問題 (本 PR の変更とは無関係)。`build_flpy.sh` の修正は本 PR の範囲外。
- 結果として flpy 経由の 48 呼出しは未確認。C の変更が影響するのは `mixer.getTrackName` の非 ASCII 入力だけなので、既存の 48 呼出しの名前は ASCII 前提の値と思われるが、未確認。

## 3. 変更

- `provider/fl_engine.c`: `u8_to_u16`・`u16_to_u8` を追加し、`track_name_fit` を unit 単位にした。mask 判定は `ch > 0xff` (非 ASCII) を mask 外にする。
- `host/fl_mock.mjs`: `fitName` を unit 単位のループに直し、切詰め結果の孤立サロゲートを U+FFFD にする。
- `tests/mixer_diff.mjs` (+8 行): `"aé🎵B"` (UTF-16 で 5 unit、`🎵` は 2 unit) を maxLen 3/2/1 で切る。`"🎵BCD"` を maxLen 1/3 で切る。

## 4. 差分の確認

- 測定 commit `0a49395f4` (コードを最後に変えた commit)。REPORT の commit 後の差分は `git diff 0a49395f4 HEAD -- tools/python/provider tools/python/host tools/python/tests` で確認する (REPORT のみの commit であればコード差分は 0 行)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `build_flpy.sh` が `source emsdk_env.sh` の後に `EMSDK_DIR` を参照して `set -u` で落ちる | flpy 経由の `provider_check`・`all_tools` が再実行できない | 起票先 未定 (PM 判断) |
| `screen.drawText` の個数検査 (`sig_arity_probe` が max=6 を code 5 で拒否) | main でも同じ 1 件。本 PR の対象外 | 起票先 未定 (PM 判断) |
| `channels.soloChannel` の `value`・`useGlobalIndex` | 従来どおり | #4460 |
