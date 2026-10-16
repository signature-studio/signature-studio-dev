# PY-5392 (#5838): wine64 9.0 の導入可否と FLEngine_x64.dll の watchpoint 採取前提

親: #5771 (lane (b))。対象: FL64.exe を wine64 で起動し、`FLEngine_x64.dll` への到達を確認する。
素材: `oc_artifacts: fl-win64` (fl-win64 素材の展開物。場所は runner の環境変数で指定)。再現: `bash tools/python/wine_fl_probe.sh`。

## 結論 (先出し)

1. **wine64 は導入できた**: `wine-9.0 (Ubuntu 9.0~repack-4build3)`。wine64 本体は PATH 外 (Ubuntu 既定の配置。スクリプトは `WINE` 環境変数で上書き可)。32bit 側 `wine32:i386` も必要 (無いと FL のインストーラが `syswow64/ntdll.dll` で c0000135)。
2. **FLEngine_x64.dll は展開できた**: インストール先の `FL Studio 2026/FLEngine_x64.dll` の SHA-256 先頭 16 桁 `b2c64da40921cf26` が `block00031_PE.bin` と一致。ImageBase 0x400000 のため `0x15e4280` は同じ RVA として扱える。
3. **FL64.exe は FLEngine_x64.dll を読みに行く**: 主スレッドが `CreateFileW` で開き、`CryptSIPRetrieveSubjectGuid` (署名検査) まで進んだ (relay ログ)。その後 GUI のメッセージループに入り、WM_MOUSEMOVE を処理している。
4. **watchpoint 1 回 hit は未確認 (watch 未 hit)**: `0x15e4280` は張っていない。ロード完了 (LoadLibrary の `Ret`) は relay ログで確認できず、FLEngine の DllMain 呼出しも記録されていない。
5. 前回 (run 38905762260) の「msimg32 の後で停止」は、loaddll のみのトレースで見えた位置にすぎなかった。relay ログでは FLEngine_x64.dll の読込み開始 (CreateFileW・署名検査) まで進んでいる。LoadLibrary の完了は未確認。

## 測定 (runner 実測)

| 項目 | 値 |
|---|---|
| OS | Ubuntu 24.04.5 (runner) |
| wine | 9.0 (apt: wine64・wine32:i386) |
| インストーラ | `flstudio_win64_26.1.7.5653.exe /S` を `xvfb-run` 下で 150 秒。PowerShell 段階で timeout (exit 124) するが、展開は完了 |
| FLEngine 同一性 | 展開物 b2c64da40921cf26 = block00031_PE.bin b2c64da40921cf26 |
| FL64.exe 起動 (loaddll トレース) | 90 秒 timeout (exit 124)。msimg32.dll 読込後にログが止まる (トレースの取り方に依存) |
| FL64.exe 起動 (relay トレース) | 60 秒 timeout (exit 124)。ログ 1,988,127 行。主スレッド 0024 が FLEngine_x64.dll を CreateFileW・CryptSIPRetrieveSubjectGuid まで処理 |
| relay での FLEngine 参照 | 9 行 (GetFileAttributesW 3・RtlDosPathNameToNtPathName_U 4・CreateFileW 1・CryptSIPRetrieveSubjectGuid 1) |
| dispatch 数・通過 unit 数 | 未測定 (FLEngine の初期化関数に到達せず) |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FLEngine_x64.dll` のロード完了 (LoadLibrary の Ret・DllMain) を relay で確認できていない。watch を張る位置 (ロード後の RVA 0x15e4280) が未確定 | lane (b) の watchpoint 採取が進まない | 本 issue #5838 (受入 2 は未達のまま。部分達成) |
| FL64.exe の GUI 初期化の完了 (FLEngine 初期化の起点) は未確認 | dispatch 数・通過 unit 数 (KPI) を測れない | 本 issue #5838 |

## 製品 KPI

動かしていない: FLEngine の起動 (dispatch 数・通過 unit 数) は未測定。`tools/flelift/boot/REPORT.md` の値は変えていない。
