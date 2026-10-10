# 外部参照の解決状況 (gen_link.py 分類; shimx は nm 実測)

| 区分 | boot_final2.ll (shimx REPORT の 557) | 現行リンク対象 boot_final3.ll |
|---|---|---|
| 外部参照 総数 | 557 | 570 |
| shimx 解決 | 182 | 184 |
|   うち機能実装 | 169 | 171 |
|   うちスタブ (常時エラー/0 台) | 13 | 13 |
| GUI/audio 対象外 (fail-fast or 0 返却スタブを生成) | 171 | 171 |
|   user32/gdi32/他 GUI | 170 | 170 |
|   dsound (audio) | 1 | 1 |
| lift 由来 (shimx の対象外) | 203 | 214 |
|   m11 側 C が提供 (SIMD helper / fnstub / rt) | 188 | 211 |
|   どこも未提供 (lift_unresolved) | 12 | 0 |
|   LLVM intrinsic | 3 | 3 |
| 未分類 (shimx 署名ずれ declare 等) | 1 | 1 |

GUI/audio の DLL 内訳: boot_final2.ll (shimx REPORT の 557): user32.dll 114, gdi32.dll 53, uxtheme.dll 1, shcore.dll 2, dsound.dll 1; 現行リンク対象 boot_final3.ll: user32.dll 114, gdi32.dll 53, uxtheme.dll 1, shcore.dll 2, dsound.dll 1

shimx 解決のうちスタブ (inventory status=S): CoCreateInstance, InternetGetConnectedState, OutputDebugStringW, SHAppBarMessage, SetErrorMode, SetThreadErrorMode, ShellExecuteW, WTSRegisterSessionNotification, acmMetrics, midiOutShortMsg, timeBeginPeriod, timeEndPeriod, timeGetDevCaps
未分類: boot_final2.ll (shimx REPORT の 557)=['SHGetFolderPathW.1'], 現行リンク対象 boot_final3.ll=['SHGetFolderPathW_D1']
