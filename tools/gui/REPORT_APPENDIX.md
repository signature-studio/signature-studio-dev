# REPORT_APPENDIX — gui-shim 付録 (GUI-6 #182 入力品質)

> **正本**: `tools/gui/REPORT.md`。本書は同 REPORT §12 の全文の付録 (行数上限 250 行のための分割移動。内容は削除していない)。

## 12. GUI-6 (#182): 入力品質 (キー配列 / IME / タッチ・ジェスチャ / Pointer Lock・ClipCursor)
既知類型との関係: lift 欠陥ではなく shim/host の意味論 (`docs/DEFECTS.md` D1a〜D16 に該当なし)。検証起点: 実装コミットは `8dd9457`、本 run の差分 (B2・推奨修正) は後続コミット (下記の数値はコミット済み tree で実測)。

### 結論
- **FL 非依存で CDP 再現できる範囲を実装し e2e 済み。受入条件は未達 → PR は `Refs #182`** (理由は「範囲外・未達」: `bash tools/gui/e2e.sh` 全体の ALL PASS は RetDec 不在で PE lift 層が走らず未確認、WM_POINTER*、実機確認)。
- **キー配列**: 入力 `GUI_IN_KEY_*` の flags に host が set 1 スキャンコード/extended を載せ (`SCAN_BY_CODE`)、shim が現配列で scancode→VK を引く (`kbd_layout_vk`)。`GUI_IN_LAYOUT` で US(0x0409)/DE(0x0407)/FR(0x040C) を切替え、`MapVirtualKeyW` (VK↔VSC/VSC→VK/VK→CHAR)・`ToUnicode`/`ToAscii` (Shift/Caps/AltGr=Ctrl+Alt)・`GetKeyboardLayout`/`GetKeyboardLayoutNameW`/`LoadKeyboardLayoutW` (未対応 KLID は 0 で失敗)/`ActivateKeyboardLayout` が配列に従う。host は Keyboard API の `getLayoutMap` から自動推定 (`layoutFromMap`)。
- **IME**: 隠し textarea の composition イベント → `GUI_IN_IME` (4 UTF-16/レコードで連結) → `WM_IME_STARTCOMPOSITION`/`WM_IME_COMPOSITION` (GCS_COMPSTR|GCS_CURSORPOS / GCS_RESULTSTR)/`WM_IME_ENDCOMPOSITION`。imm32 は `ImmGetContext`/`ReleaseContext`/`GetCompositionStringW`/`SetCompositionWindow`/`SetCandidateWindow` (位置を host へ `GUI_CMD_IME_POS`)/`Get/SetOpenStatus`/`Get/SetConversionStatus`/`NotifyIME`/`IsIME`/`AssociateContextEx` を実装 (計 12 名)。このうち FL の import 表 (IMPORTS.md) で STUB→IMPL になったのは 7 名 (`ImmAssociateContextEx`・`ImmGetContext`・`ImmGetConversionStatus`・`ImmReleaseContext`・`ImmSetConversionStatus`・`ImmSetOpenStatus`・`ImmIsIME`)。残り 5 名 (`ImmGetCompositionStringW`・`ImmSetCompositionWindow`・`ImmSetCandidateWindow`・`ImmNotifyIME`・`ImmGetOpenStatus`) は FL の import 表に無く、IMPORTS.md 上は変化しない。composition 中の入力から WM_CHAR は合成しない。
- **タッチ**: `PointerEvent(pointerType=touch)` → `GUI_IN_TOUCH`。`RegisterTouchWindow` 済み窓へ `WM_TOUCH` (`GetTouchInputInfo` = Win64 TOUCHINPUT 48B)、未登録窓は primary 接触をマウスへ昇格。`SetGestureConfig` (MS 仕様の符号化: `{dwID=GID, dwWant=GC_*, dwBlock}`。`{0, GC_ALLGESTURES, 0}` = 全ジェスチャ有効、`{GID_ZOOM=3, GC_ZOOM=1, 0}` = ZOOM のみ) で許可した GID_ZOOM (2 本指距離) を `WM_GESTURE` (`GetGestureInfo` = Win64 GESTUREINFO 56B) で配送。GID_PAN (1 本指移動) も実装しているが、**selftest / e2e に検査が無く未検証**。
- **Pointer Lock / ClipCursor**: 「カーソル非表示 (`ShowCursor(FALSE)`) かつ capture 中またはボタン押下中」に `GUI_CMD_POINTER_LOCK` で host へ `requestPointerLock` を要求 (要求の発行は selftest で push 数 1/1/0 を検査)。ロック中 host は `movementX/Y` を `cursor_x/y` へ積算 (ClipCursor 矩形へ clamp)。`SetCursorPos` は ClipCursor 矩形へ clamp、`GetClipCursor` は矩形を返す。
- **ブラウザ既定動作の変更**: `src/runtime/gui.ts` は GUI canvas に `touch-action: none` を設定する。タッチによるブラウザ既定のパン/ズームを GUI canvas 上で無効化する (挙動変更。範囲外表を参照)。
- プロトコル追加は enum 値のみ (`GuiShared` のオフセットは不変・`_Static_assert` 更新なし)。`gui_proto.h` ↔ `gui_proto.ts` を同時更新。
- FL の GUI import 面: 実装済み 280 → 292 (`IMPORTS.md` は `gen_api.py` が再生成)。IMPORTS.md の STUB→IMPL は 12 行 (imm32 7 + touch/gesture 5)。

### 検証 (4 vCPU runner、検証起点 `8dd9457`、実測時 load 0.8〜1.1)

- **HEAD `0b71ab1` の実測 (B2 修正後)**: `bash tools/gui/e2e.sh` 全体 **ALL PASS** (exit 0, real 1m36.108s; native selftest 493 passed / 0 failed、reach_test 11 / adapt_test 28 passed、6/6・6b/6・6c/6・6d/6・6e/6・6f/6 PASS、6g/6 入力 ALL PASS)。`tools/gui/input/e2e.sh` ALL PASS (in_pushed=41 in_dropped=0 in_consumed=41, real 3.773 s)。`tools/gui/input/negctl.sh` 12 件すべて検出・検出漏れ 0 (real 2 分 34.430 秒)。以下の表は旧検証起点 `8dd9457` のもの。
| 層 | 結果 |
|---|---|
| native `bash tools/gui/test/selftest.sh` (ASan/UBSan, `8dd9457`) | **492 passed / 0 failed** (既存 426 + GUI-6 の 66 assertion; `test/selftest_gui6.inc`)。DE/FR/US 配列・AltGr・IME 分割再構成・タッチ/ジェスチャ・ClipCursor・Pointer Lock 要求の push 数 (1/1/0)・DE/FR の MAPVK 英字大文字化を含む。所要 real 13.06 s |
| Chrome e2e `bash tools/gui/input/e2e.sh` (CDP `Input.dispatchKeyEvent` / `imeSetComposition` / `insertText` / `dispatchTouchEvent` / `dispatchMouseEvent`, `8dd9457`) | **ALL PASS (21 検査 / 0 FAIL)**。入力リング `in_pushed=41 in_dropped=0 in_consumed=41` (drop 0)。計測: 内部 1.5 s (load 1.12)、real 13.03 s (wasm 再ビルド込み)。ゲストは `input/input_app.c` を emcc で直接 wasm 化 (RetDec 不要) |
| 既存層 (`8dd9457` で再実測, load 0.8〜0.96) | `reach_test` 11 + `adapt_test` 28 passed (15.4 s)、`bpp_golden` EXACT MATCH 16,000 px・ネガコン 2/2 OK (6.4 s)、`simd_e2e` ALL PASS (14.3 s)、`present/e2e.sh` (`PRESENT_SKIP_BENCH=1`) 7 pass / 0 fail (10.0 s)、`check_p1_tests` 51 APIs / 51 実装・テスト付き (0.14 s) |
- ネガティブコントロール (下の「ネガコン実測」): `bash tools/gui/input/negctl.sh` (壊したコピーを `build/negctl` に作りリポジトリのソースは変更しない。変異が効かなければ「broken control」として未検出扱い)。
- 数え方: selftest の passed は `CHK` 成立数 (assertion)。Chrome e2e の検査は `ck()` 行数。

### ネガコン実測 (`bash tools/gui/input/negctl.sh`, 検証起点 `8dd9457`)
| 変異 (ソース 1 箇所を壊す) | 検出した層 | 結果 (passed / failed、または FAIL 件数) |
|---|---|---|
| nc1 物理キー → 現配列 VK 変換 (`kbd_layout_vk`) を無効化 | selftest | 492 passed / **1 failed** → 検出 |
| nc2 DE の Z/Y の配置を入替 | selftest | 488 passed / **5 failed** → 検出 |
| nc3 AltGr (Ctrl+Alt) の文字表を無視 | selftest | 490 passed / **3 failed** → 検出 |
| nc4 WM_IME_COMPOSITION の結果送信フラグを GCS_COMPSTR に変更 | selftest | 490 passed / **3 failed** → 検出 |
| nc5 ZOOM の接触数補正 (離す接触を数えない) を削除 | selftest | 492 passed / **1 failed** → 検出 |
| nc6 ClipCursor の clamp を無効化 | selftest | 492 passed / **1 failed** → 検出 |
| nc7 MAPVK_VK_TO_CHAR の英字大文字化を削除 (本 PR の B4 修正の逆) | selftest | 490 passed / **3 failed** → 検出 |
| nc8 POINTER_LOCK 要求の push を削除 (本 PR の B5 検査の対象) | selftest | 492 passed / **1 failed** → 検出 |
| host-1 KEY の scancode を flags から落とす (gui.ts) | Chrome e2e | exit 1 / **6 FAIL** → 検出 |
| host-2 IME update の送信を落とす (gui.ts) | Chrome e2e | exit 1 / **1 FAIL** → 検出 |
| host-3 touch 分岐を無効化 (touch→mouse 昇格が効かない) (gui.ts) | Chrome e2e | exit 1 / **6 FAIL** → 検出 |
| host-4 Pointer Lock 要求の発行を落とす (gui.ts) | Chrome e2e | exit 1 / **1 FAIL** → 検出 |

- 結果: shim 8 件 + host 4 件 = **12 件すべて検出、検出漏れ 0** (`[negctl] 合計 検出漏れ: 0`, exit 0)。所要 real 2 分 34.66 秒 (user 1 分 18.27 秒)。各変異は壊したコピー (`build/negctl`) で実行し、ソースは変更していない。

### 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
`bash tools/gui/e2e.sh` 全体は `0b71ab1` で ALL PASS (exit 0, real 1m36.108s; PE lift 層 2/6〜6g/6 を含む)。範囲外の残りは下記の行。
| WM_POINTER* / RegisterPointerInputTarget 系 (FL の import に無い) と慣性ジェスチャ (GID_PAN の GF_INERTIA)・GID_ROTATE/TWOFINGERTAP/PRESSANDTAP | issue スコープ「タッチ → WM_POINTER*」の一部が未実装 | #182 (実到達ログ: #174 で FL が呼ぶと確定したら) |
| GID_PAN (1 本指移動の WM_GESTURE) は実装のみで selftest / e2e に検査が無い | パン操作の回帰を検知できない | #182 (テスト追加は次の作業。PM 判断: 今回の PR で足すか) |
| 配列は US/DE/FR のみ・dead key・IME 配列・実 Windows の KBD テーブルとの照合なし (表は公開仕様から手作成)。Caps の数字行 shift-lock 近似 | 他配列では US 相当に落ちる。表の誤りは実機でしか見つからない | #182 (日本語 JIS/実機確認はユーザ依頼候補; 着手時に具体依頼を起票) |
| 実機確認 (OS の日本語 IME・実タッチ端末・実 Pointer Lock 成立) は未実施。headless Chrome では Pointer Lock は要求呼出回数と `movementX` 積算のみ検証 (ロック成立は `locked` を直接設定して代用) | 実環境での成立可否・IME 候補ウィンドウ位置が未確認 | #182 (ユーザ依頼: 実機 Chrome での手動確認) |
| `touch-action: none` を全 GUI canvas に設定 (ブラウザ既定のパン/ズームを無効化) | GUI を表示した画面でのページ操作が変わる。許容範囲の判断が要る | PM 判断 (許容 / 範囲の限定) |
| IME 属性/文節 (GCS_COMPATTR/COMPCLAUSE) と変換候補リスト (ImmGetCandidateList) は未提供 | FL が使えば fail-fast ではなく空を返す | #174 到達ログ後に #182 |
| WM_CHAR 合成は host (gui.ts `key()`) のまま (pump 側 TranslateMessage は未変更) | #103 の補足にある pump 側合成との統合は未決 | #121 (RT-3: 入力 producer 結線) と合わせて決定 |
| 既存: native selftest の ASan UAF flake | `e2e.sh` 1/6 が時々 FAIL | #489 (既存) |

### 再現
```
bash tools/gui/test/selftest.sh        # native 492 assertion
bash tools/gui/input/e2e.sh            # Chrome + CDP 入力 (tsc → emcc → headless Chrome)
bash tools/gui/input/negctl.sh         # ネガコン (shim 8 + host 4; 合計 real 2 分 34 秒)
```
