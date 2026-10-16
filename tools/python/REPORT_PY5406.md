# PY-5406 (#5838 の子): wine64 上の FLEngine_x64.dll 署名検証の失敗原因を WINEDEBUG で切り分ける

親: #5838。前提: PY-5392 (REPORT_PY5392.md)。署名検証の迂回・DLL の差し替えは扱わない (製品の署名確認を外す操作のため)。

## 結論 (先出し)

1. **本 run ではインストーラの展開を完了できなかった**。`wineboot --init` の後に `/S` を 900 秒待ったが、`FLEngine_x64.dll` は作られず、インストーラは終了しなかった (`timeout 900` で打ち切り)。前測定の「272 秒で終了・DLL は展開済み」は本 run で再現していない。
2. **判定 (受入 2)**: 未確認。理由: 展開が完了せず、本 run では probe の `WinVerifyTrust` ログを採取できなかった。
3. **前測定の `WinVerifyTrust` の戻り値** (1 回目 `0x80096004`、2 回目 `0x00000000`): 本 run では再現していない。前測定 (commit `e18d02f22`) の値として扱う。
4. **decoder 未対応の fixme**: 前測定では 1 回目の失敗中に 2 回出ている。直後の decode は `returning 1` (成功) なので、失敗の直接原因かは未確定。

## 測定

| 項目 | 本 run (commit `76cc4daa1` 上で実行) | 前測定 (commit `e18d02f22`) |
|---|---|---|
| wine | `wine-9.0 (Ubuntu 9.0~repack-4build3)` (`/usr/lib/wine/wine64`) | 同じ |
| 素材 | `fl-win64` を `tar --zstd -xf` で展開 14 秒 (rc 0) | `fl-win64` (展開 9 秒) |
| `wineboot --init` | 6 秒 (rc 0) | 12.7 秒 (rc 0) |
| インストーラ `/S` | 900 秒で打ち切り (rc 124)。`FL Studio 2026/` は未作成 | 272 秒 (rc 199)。DLL は展開済み |
| DLL 同一性 (sha256 先頭 16) | 比較不能 (DLL 無し) | 一致 (`b2c64da40921cf26`) |
| probe 所要 | 未実行 (DLL 無しのため install 後の probe に進めない) | 1 分 30 秒 (`FL_SECS=90`) |
| load average | install 実行中の `uptime`: 1 分平均 0.00 (18:45 時点) | 採取コマンドが記録されていないため表に載せない |

## 再現 (本 run の手順)

素材: `oc_artifacts: fl-win64`。`$RUNNER_TEMP` は runner の一時領域 (`fl-win64.tar.zst` を展開した dir 内で実行)。

```
export WINE=/usr/lib/wine/wine64 WINEPREFIX=$RUNNER_TEMP/wineprefix WINEDEBUG=-all
timeout 120 $WINE wineboot --init
timeout 900 xvfb-run -a $WINE flstudio_win64_26.1.7.5653.exe /S
```

- `xvfb-run` は使用 (`-a`)。`/S` の起動は `wineboot --init` の後。
- 完了判定: `$WINEPREFIX/drive_c/Program Files/Image-Line/FL Studio 2026/FLEngine_x64.dll` が存在し、`extracted/block00031_PE.bin` と sha256 が一致すること。待ち上限は 900 秒。
- 本 run: 上限 900 秒で判定を満たさず (DLL 無し)、完了は確認できなかった。
- `wine_fl_probe.sh` の install 分岐 (`timeout 150`・`timeout 120`) は本測定の経路ではない。本 run の 900 秒でも展開が完了しなかったため、150 秒で完了する根拠は無い。probe の install 値は変更していない。

probe 本体の再現コマンド (前測定の経路。DLL が展開済みの環境が前提):

```
WINE=/usr/lib/wine/wine64 WINEDEBUG=+relay,+crypt,+wintrust,+err FL_SECS=90 bash tools/python/wine_fl_probe.sh
```

## 前測定の probe 出力 (commit `e18d02f22`・本 run では未再現)

```
flengine_sha256_16 installed=b2c64da40921cf26 block00031=b2c64da40921cf26
fl64_rc=124
createfile_flengine=1
sip_guid_flengine=1
loadlibrary_flengine=0
winverifytrust_ret=80096004 00000000 
msgbox_unverified=1
unsupported_spc_decoder=2
first_wvt_ret_line=367532:0024:trace:wintrust:WinVerifyTrust returning 80096004
last_crypt_wintrust_line=0024:trace:wintrust:WinVerifyTrust returning 00000000
```

- `loadlibrary_flengine=0`: `LoadLibrary` 経由の読込みは無く、`CreateFileW` と `CryptSIPRetrieveSubjectGuid` で署名検査の段階に入った。
- `0x15e4280` の watch は張っていない (受入 2 の watch は #5838 の範囲)。DllMain 到達は未観測。

## 因果の読み方

- 前測定の 1 回目の `WinVerifyTrust` の中で、`CreateFileW` → `CryptSIPRetrieveSubjectGuid` → `CryptMsgGetParam` → `CryptDecodeObjectEx` (decoder 未対応 fixme ×2) が順に出て、最後に `0x80096004` を返した。
- fixme の直後の decode は成功 (`returning 1`) を返しており、未対応 decoder が出力を作れなかったかは未確認。別原因 (証明書チェーン・署名の別部分) の可能性を残す。
- 2 回目の呼び出しは `0x00000000` で成功。MessageBox は 2 回目の成功の後に出た。呼び出し元がどちらを見るかは、ログからは確定できない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 本 run で `/S` が 900 秒で完了せず、前測定の展開・probe 出力を再現できていない | 受入 2 の判定の根拠が本 run に無い。前測定の値は再現未確認 | #5838 |
| 1 回目 `0x80096004` の直接原因 (decoder 未対応 fixme との因果) が未確定 | wine 側の対応 (decoder 追加・wine 版変更) が要るかを判定できない | #5838 |
| `FLEngine_x64.dll` の `LoadLibrary` 完了・DllMain 到達が未観測 | watch 0x15e4280 を張れない (受入 2 は未達) | #5838 |
| 2 回目の成功と MessageBox の関係 (呼び出し元がどちらの戻り値を見るか) | 同上 | #5838 |

## 製品 KPI

動かしていない。FLEngine の起動 (dispatch 数・通過 unit 数) は未測定。`tools/flelift/boot/REPORT.md` の値は変えていない。
