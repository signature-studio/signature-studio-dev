# PY-5406 (#5838 の子): wine64 上の FLEngine_x64.dll 署名検証の失敗原因を WINEDEBUG で切り分ける

親: #5838。前提: PY-5392 (REPORT_PY5392.md)。署名検証の迂回・DLL の差し替えは扱わない (製品の署名確認を外す操作のため)。

## 結論 (先出し)

1. **インストーラの展開は完了した**。前回 (run 38937326252) は 900 秒で未完だったが、今回は `wineboot --init` の後に `/S` を実行し 272 秒で終わった (終了コードは 199 だが、`FLEngine_x64.dll` は展開されていた)。展開の完了確認は `drive_c/Program Files/Image-Line/FL Studio 2026/FLEngine_x64.dll` の存在と sha256 の一致。
2. **`WinVerifyTrust` の戻り値**: 1 回目 `0x80096004` (`TRUST_E_CERT_SIGNATURE`)、2 回目 `0x00000000`。対象は `C:\Program Files\Image-Line\FL Studio 2026\FLEngine_x64.dll`。MessageBox「The validity of the program could not be verified」は 2 回目の成功の後に出た。
3. **decoder 未対応の fixme は、1 回目の失敗中の呼び出しで出ている**。`CryptDecodeObjectEx` の `1.3.6.1.4.1.311.2.1.4` (SPC_INDIRECT_DATA 系) が 2 回出るが、その直後に decode は `returning 1` (成功) を返している。decoder が無くても成功扱いで返る経路のため、**失敗の直接原因かは未確定**。
4. **判定 (受入 2)**: 「wine 側の decoder 追加が要るか」は **未確認**。理由: 1 回目の失敗の直接原因を、ログだけでは特定できない。decoder を実装して 1 回目が 0 になるかを見る実験 (wine のソースを変える) が要る。これは本 issue の範囲外。

## 測定

| 項目 | 値 |
|---|---|
| 測定 commit | `e18d02f22` (`tools/python/wine_fl_probe.sh` のコード変更を含む最後の commit) |
| wine | `wine-9.0 (Ubuntu 9.0~repack-4build3)` (`/usr/lib/wine/wine64`) |
| 素材 | `fl-win64` (`oc_artifacts: fl-win64` の `.tar.zst`、展開 9 秒) |
| インストーラ | `wineboot --init` 12.7 秒 (rc 0)。`flstudio_win64_26.1.7.5653.exe /S` 272 秒 (rc 199。DLL は展開済み) |
| DLL 同一性 | `flengine_sha256_16 installed=b2c64da40921cf26 block00031=b2c64da40921cf26` (一致) |
| probe 所要 | 1 分 30 秒 (`FL_SECS=90`) |
| load average | 実行中 0.07〜0.3 (負荷は無し) |

probe 出力 (コミット済み HEAD `e18d02f22`):

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

- `fl64_rc=124` は 90 秒で打ち切ったため (想定どおり)。`loadlibrary_flengine=0`: `LoadLibrary` 経由の読込みは無く、`CreateFileW` + `CryptSIPRetrieveSubjectGuid` で署名検査の段階に入った。
- `0x15e4280` の watch は張っていない (受入 2 の watch は #5838 の範囲)。DllMain 到達は未観測。

## 因果の読み方

- 1 回目の `WinVerifyTrust` (呼び出し) の中で、`FLEngine_x64.dll` の `CreateFileW` → `CryptSIPRetrieveSubjectGuid` → `CryptMsgGetParam` → `CryptDecodeObjectEx` (decoder 未対応 fixme ×2) が順に出て、最後に `0x80096004` を返した。fixme はこの呼び出しの内側にある。
- ただし fixme の直後の decode は成功 (`returning 1`) を返しており、未対応 decoder が出力を作れなかったかは未確認。失敗の直接原因が別 (例: 証明書チェーン・署名の別部分) の可能性を残す。
- 2 回目の呼び出しは `0x00000000` で成功している。MessageBox は 2 回目の成功の後に出た。どちらの戻り値を呼び出し元が見るかは、ログからは確定できない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1 回目の `0x80096004` の直接原因 (decoder 未対応 fixme との因果) が未確定 | wine 側の対応 (decoder 追加・wine 版変更) が要るかを判定できない (判定は「未確認」) | #5838 |
| `FLEngine_x64.dll` の `LoadLibrary` 完了・DllMain 到達が未観測 | watch 0x15e4280 を張れない (受入 2 は未達) | #5838 |
| 2 回目の成功と MessageBox の関係 (呼び出し元がどちらの戻り値を見るか) | 同上 | #5838 |

## 製品 KPI

動かしていない。FLEngine の起動 (dispatch 数・通過 unit 数) は未測定。`tools/flelift/boot/REPORT.md` の値は変えていない。

## 再現

```
WINE=/usr/lib/wine/wine64 WINEDEBUG=+relay,+crypt,+wintrust,+err FL_SECS=90 bash tools/python/wine_fl_probe.sh
```

前提: `apt-get install wine64 wine32:i386 xvfb xauth` (wine64 は PATH 外の `/usr/lib/wine/wine64`)、素材 `fl-win64`。
