# PY-5392 (#5838): wine64 9.0 の導入可否と FLEngine_x64.dll の watchpoint 採取前提

親: #5771 (lane (b))。対象: FL64.exe を wine64 で起動し、`FLEngine_x64.dll` への到達を確認する。
素材: `oc_artifacts: fl-win64` (fl-win64 素材の展開物。場所は runner の環境変数で指定)。再現: `WINEDEBUG=+relay,+crypt,+wintrust,+err FL_SECS=90 bash tools/python/wine_fl_probe.sh` (`WINE=/usr/lib/wine/wine64`)。

## 結論 (先出し)

1. **wine64 は導入できた**: `wine-9.0 (Ubuntu 9.0~repack-4build3)`。wine64 本体は PATH 外 (Ubuntu 既定の配置。スクリプトは `WINE` 環境変数で上書き可)。32bit 側 `wine32:i386` も必要 (無いと FL のインストーラが `syswow64/ntdll.dll` で c0000135)。
2. **現 head (`5f82093a0`) では FLEngine_x64.dll の展開を再現できていない**: CI 実装 run `38937326252` (job `117096076218`) で、インストーラ `flstudio_win64_26.1.7.5653.exe /S` を `timeout 900` で実行したが rc 124 で終わり、`drive_c/Program Files/Image-Line/FL Studio 2026/` は作られなかった。probe は `NO_FLENGINE_EXTRACTED` (rc 3) で止まり、6 項目は出ていない。
3. **前 run の観測 (リポジトリ外ログ・再現未確認)**: FL64.exe が FLEngine_x64.dll を `CreateFileW` で開き、署名検査 (`CryptSIPRetrieveSubjectGuid`) まで進んだこと、その後の署名検証の段階で modal の MessageBox が出て止まったこと。いずれも現 head の probe では再現していない。前 run のログはリポジトリに保存していない。
4. **watch 未 hit (受入 2 は未達)**: `0x15e4280` は張っていない。`LoadLibrary` の完了 (DllMain) は未観測。ImageBase 0x400000 のため、展開できた場合に同じ RVA として扱える前提は、展開の再現まで未確定。
5. 前回 (run 38905762260) の「msimg32 の後で停止」は、loaddll のみのトレースで見えた位置にすぎない。

## 測定 (現 head `5f82093a0` の実測・run 38937326252)

| 項目 | 値 |
|---|---|
| OS | Ubuntu 24.04.5 (runner) |
| wine | 9.0 (apt: wine64・wine32:i386 の導入は成功) |
| インストーラ | `flstudio_win64_26.1.7.5653.exe /S` を `timeout 900` で実行 → rc 124。`FL Studio 2026/` は未作成 |
| probe | `WINEDEBUG=+relay,+crypt,+wintrust,+err FL_SECS=90 bash tools/python/wine_fl_probe.sh` → `NO_FLENGINE_EXTRACTED` (rc 3)。所要 164 秒 |
| 6 項目 (`fl64_rc` 他) | 未出力 (probe が FL64 起動前に終了) |
| `flengine_sha256_16` | 未出力 (FLEngine_x64.dll が無いため比較できない) |
| dispatch 数・通過 unit 数 | 未測定 (FLEngine の初期化関数に到達せず) |

- load average: 実行中 0.1〜0.9 (負荷は無し)。
- 展開の実時間 (900 秒以内に完了するか) は未確定。

## 前 run の観測 (リポジトリ外ログ・再現未確認)

以下は前の run の観測で、現 head の run では再現していない。数値は本文・REPORT のどこにも採用しない。

- FLEngine_x64.dll の読込み開始 (`CreateFileW`・署名検査) まで進んだ。
- 署名検証の段階で MessageBox (validity could not be verified) が出て、modal で止まった。
- `CryptDecodeObjectEx` の `1.3.6.1.4.1.311.2.1.4` 未対応 fixme が出ていた。これと署名検証の失敗との因果は未確認。
- 署名検証の結果を書き換えて読み込ませる迂回は、製品の署名確認を外す操作のため本 issue では行わない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 現 head でインストーラが FLEngine_x64.dll を展開できない (900 秒で未完)。probe の 6 項目は現 head で未再現 | watch 0x15e4280 の前提 (展開・ロード完了) が未確定 | #5838 (受入 2 は未達のまま継続) |
| 署名検証の段階で止まる原因 (wine 側の decoder の有無か、別 wine 版か) が未確定 | watch を張れない | #5838 |
| FL64.exe の GUI 初期化の完了 (FLEngine 初期化の起点) は未確認 | dispatch 数・通過 unit 数 (KPI) を測れない | #5838 |

## 次の run への引継ぎ

- 第一に、インストーラの完了を確認する: `drive_c/Program Files/Image-Line/FL Studio 2026/FLEngine_x64.dll` の存在。無ければインストーラの待ち時間か展開方法を変えて再測定する (900 秒で未完だった事実を基準にする)。
- FLEngine_x64.dll が存在したら、`bash tools/python/wine_fl_probe.sh` を foreground で 1 回実行し、出力 6 項目と `flengine_sha256_16` をそのまま本文と本 REPORT に転記する。測定 commit は実行した head の完全 SHA にする。
- 署名検証の段階で止まる原因の確定は、迂回ではなく wine 側の decoder の有無 (wine 9.0 の対象外か、別版で通るかの比較) で行う。判断が出るまで受入 2 は未達。

## 製品 KPI

動かしていない: FLEngine の起動 (dispatch 数・通過 unit 数) は未測定。`tools/flelift/boot/REPORT.md` の値は変えていない。
