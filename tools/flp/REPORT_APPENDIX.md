# tools/flp/REPORT_APPENDIX.md — REPORT.md の付録 (行数上限 250 のため分割移動)

正本: `tools/flp/REPORT.md`。本書は §12 (L-3 / #104) を移したもの。内容は削除していない (Git 履歴に残る)。

## 12. L-3 (#104): 上位 5 plugin の state (event 213) デコーダ + DSP クラス静的所見

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift 無関係。逆アセンブルの静的読みのみ)。検証起点 commit: `0ce863a` (ブランチ `104-plugin-state-decoders`)。**受入条件 (クラス A/B 判定表) は未達**: デコーダは完了、X/L/W の 3 者比較は未実施 (§12.4)。

**手法**。各 plugin DLL の `CreatePlugInstance` → class ref → vtable[3] = `SaveRestoreState` (`tools/plugins/ABI.md` §3.1) を `scripts/plugin_slot3.py` で逆アセンブルし、Save 分岐の `Stream->Write(buf,len)` 列 (`scripts/save_writes.py`) と Load 分岐の `cmp [version],N` ゲートからレイアウトを転記 (`src/plugstate.ts`)。コード由来の根拠: Delay 3 `0x6e8da0` (u32 ver=1 + 0x68 B)、Reeverb 2 `0x6d4920` (ver 10001 = 0x2711 + 0x3e B、10000 は 0x35 B)、Limiter `0x6d3760` (ver 7, 本体 0xa4 B, v7 のみ flags 1 B)、EQ2 `0x6ec340` (ver 8, 本体 0x120 B + 版ゲート付き 12 フィールド)、Maximus `0x83f8f0` (先頭 u32 の上位 word が版, 本体 126×i32 + 2 B + v≥14 で 33 B + 4 band 副ストリーム)。

**12.1 結果** (数え方: 分母 = win 抽出物 FLhd 9,128 ファイル中、`201` 内部名が各 plugin の `213` イベント。再現 `node cli/plugstate.ts $E2E_FLP_WIN_DIR` / `corpus/plugstate.json`):
| plugin | 213 件数 | 対応版 (件) | layout 適合 | 予測長 = 実長 | 非対応 (旧版・raw 保持) |
|---|--:|--:|--:|--:|--:|
| Fruity Parametric EQ 2 | 1,127 | 1,104 | 1,104 | 1,104/1,104 | 23 (v2) |
| Fruity Limiter | 351 | 338 | 338 | 338/338 | 13 (v5) |
| Fruity Reeverb 2 | 328 | 321 | 321 | 321/321 | 7 (v19–v400) |
| Maximus | 165 | 129 | 129 | 副ストリームのため長さ予測なし | 36 (v2–v6) |
| Fruity Delay 3 | 119 | 119 | 119 | 119/119 | 0 |

- 全 2,090 件で `encode(decode(x)) == x` **byte-exact (2,090/2,090)**。非対応版は tail に全バイト保持するため無損失。4 バイト未満の入力は version 語を持たない `headerless` 表現 (全バイトを tail に保持し、encode はヘッダを書かない) とし、長さ 0〜3 の往復を `test/plugstate.test.ts` で固定 (コーパスには該当なし)。
- Maximus: 本体 510 B (v≤11) / 543 B (v≥14) までを名前付きフィールド化。残り (4 band × 副ストリーム 736–976 B) は各 band オブジェクト自身の `vtable+0x10` が書く可変長で **未デコード** (tail)。
- 所要 (クリーン HEAD, 1 プロセス): `cli/plugstate.ts` 0.692–0.694 s (n=3, load average 0.56) / `test/plugstate.test.ts` 5/5 PASS 0.148–0.152 s (n=3) / 既存 4 ファイル 29/29 PASS / `tsc` rc 0 / `src/` の `node:` import 0 件。出力 JSON は 3 回で同一。
- レビュー指摘対応後の再検証 (headerless 追加): `cli/plugstate.ts` rc 0・0.55–0.58 s (n=3, load average 0.60)・出力 JSON は 3 回同一かつ `corpus/plugstate.json` と一致 / `node --test test/*.test.ts` 37 件中 34 PASS・0 FAIL・3 SKIP / `tsc -p tsconfig.json` rc 0 / 短入力テストは旧 `src/plugstate.ts` で FAIL (長さ 0 で LOSSY)・新で PASS。
- ネガティブコントロール: ① Delay 3 の本体を 26→25 要素にすると layoutOk 119→**0**・予測長 0/119・`plugstate.test.ts` 3 件 FAIL (rc 1)。② Limiter の flags ゲートを v7→v8 にすると layoutOk 338→**157**・予測長 157/338 (rc 1)。いずれも元に戻して rc 0。

**12.2 フィールド意味の範囲**: 名前は DLL の保存対象オフセット (`at`, plugin オブジェクト先頭からの値) まで。EQ2/Limiter/Reeverb 2/Delay 3 の `params` は int32 配列で、各要素のパラメータ名・物理単位への変換は未確定 (実値域のみ観測: 例 EQ2 gain ±1800, Limiter/Maximus は 1000 = 1.0)。

**12.3 DSP クラスの静的所見 (推定。X/L/W 実測ではない)** — `scripts/dsp_class.py` (`corpus/dsp_class.json`): `Eff_Render` (vtable[7]) から `call/jmp rel32` で到達する .pdata 関数を走査。
| plugin | 閉包 (関数 / B) | x87 超越 | libm import | 間接呼出 | 暫定クラス (推定) |
|---|--:|--:|--:|--:|---|
| Parametric EQ 2 | 182 / 38,562 | 0 | 0 | 81 | A 候補 (biquad; 係数計算に `divsd`31・`sqrtsd`1) |
| Limiter | 35 / 5,751 | 0 | 0 | 53 | A 候補 |
| Reeverb 2 | 60 / 11,389 | 0 | 0 | 28 | C 候補 (帰還系; ORACLE §4.2) |
| Maximus | 202 / 50,705 | 0 | 0 | 134 | B–C (マルチバンド圧縮; 閉包外 kernel 表を要確認) |
| Delay 3 | 1 / 123 | 0 | 0 | 3 | **判定不能** (DSP は別 engine DLL。殻のみ走査) |
- 間接呼出 (framework の SIMD kernel 表・仮想呼出) は辿っていないため、閉包外の libm 経由は除外できない。A と書いたものは「閉包内に超越関数が見えない」だけで、**bit-exact の証明ではない**。

**12.4 未解決** (`| 未解決 | 影響 | 起票先 |`)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| X/L/W の 3 者比較 (原本機械語の native 実行 / lift IR / wasm) 未実施。受入「クラス A/B 判定表」は §12.3 の推定止まり | #104 は **Closes にできない** | #104 に継続コメント。次 run で EQ2 (T1) の `Eff_Render` を `tools/plugins/lift/t0_balance` 方式で比較 |
| Maximus の band 副ストリーム (tail 可変長) 未デコード | Maximus の band 設定は raw | 新規子チケット案 (親 #104) |
| `params` 要素のパラメータ名・単位変換が未確定 | 値の意味は使えない (バイト保持のみ) | #104 コメント |
| 旧版 (EQ2 v2 / Limiter v5 / Reeverb 2 v19–400 / Maximus v2–6) の Load 変換未転記 | 計 79 件は raw | #104 コメント |
| Delay 3 の DSP 本体は engine DLL (`PLUGIN_MATRIX.md` #23: shell 3,939K + engine 1,195K) | 判定不能 | #104 コメント |
| `flp_e2e.sh` 全体は mac 素材前提 (§9 既出)。plugstate 段は `E2E_FLP_WIN_DIR` のみで動く | — | §9 既出 |

## 14. #113 S1 (wine64 での FL 26.1.7 起動): 試行結果


素材: `fl-win64` は block 分割 (25,165 block)。`tools/startup/loadpaths/mk_manifest.py` → `tools/assets/inventory/mk_inputs.py` → `tools/assets/win_paths/recover_paths.py` で `$INSTDIR` パスを復元し、インストール木 (25,131 件 / 2.3 GB) を組み立てた。`FL64.exe` = block00038 (597,064 B, STARTUP §0 と一致)、`FLEngine_x64.dll` = block00031 (ImageBase 0x400000、export `CreateFruityInstance`)。再現: `bash tools/flp/s1_wine_probe.sh`。

- wine: apt の `wine64` 9.0 (Ubuntu 9.0~repack-4build3) + `xvfb`。`wineboot -i` でプレフィックス作成まで成功。
- 起動 (`xvfb-run -a wine64 FL64.exe`、90 s 上限): **timeout (rc 124) で終了しない**。`Mfplat.dll` の読込 (G01) は成功、`WinVerifyTrust` が `FLEngine_x64.dll` に対して呼ばれ (G03)、その後 `MSGBOX` を出して停止。**`FLEngine_x64.dll` のロードには到達せず**。
- MessageBox の本文: `WINEDEBUG=+msgbox` の trace で取得 (`MSGBOX_OnInit`)。画面キャプチャ道具は使わず、文言はトレースから確定。
- 判定: S1 は **未達**。止まった箇所は G03 (Authenticode 検査、ホスト側 `0x1400062a0`) と推定。wine の `WinVerifyTrust` を shim する (DLL override) か、oracle 用ローカルパッチが要る。S2 (WAV 書き出し) には未到達。
- 検証 (再測定): 測定 commit `155382c8` (`WORK` を `$RUNNER_TEMP/work` に変更したスクリプトで `bash tools/flp/s1_wine_probe.sh` を実行)。rc 0、実行 5 m 15 s、`blocks with path 25164 / 25165`、multi-dest 1207 blocks。中間成果物は `$RUNNER_TEMP/work` に出力され、`tools/assets/work/` は作られない。`FLEngine_x64.dll` は 22,227,016 B。
- 起動の trace 根拠 (`WINEDEBUG=+loaddll,+msgbox,+wintrust,+crypt`、90 s 上限、rc 124):
  ```
  0024:trace:wintrust:WinVerifyTrust (0000000000000000, {00aac56b-cd44-11d0-8cc2-00c04fc295ee}, 000000000011FBA0)
  0024:trace:loaddll:build_module Loaded L"C:\\windows\\system32\\WINTRUST.dll" at 00006FFFFAA50000: builtin
  0024:trace:msgbox:MSGBOX_OnInit L"The validity of the program could not be verified. Please reinstall it and try again."
  ```
  `FLEngine_x64.dll` のロード行は無い。
- 注: 再測定 (`-all`) の起動ログは 4 行 (`rundll32.exe` 0xc0000135 と `X connection ... broken`) で、rc 124 は出ていない。rc 124 と WinVerifyTrust/MSGBOX は trace 付きの再実行 (上記) でのみ確認した。
- 検証起点: 測定 commit `155382c8` (コード差分の最終 commit)。`git diff 155382c8 HEAD -- tools/flp/s1_wine_probe.sh tools/startup tools/assets` = 空 (差分 0)。`git diff b9de32d0 HEAD -- tools/flp tools/startup tools/assets` は `s1_wine_probe.sh` の 1 行 (`WORK`) と本 REPORT の差分のみ。
- 未解決: G03 回避手段 (oracle 用ローカルパッチ or wine DLL override) / S2・S3 全部 → #113 に残す (Refs #113)。

## 15. #113 S1 達成 / S2 部分 (wine64 + `/R` 書き出し・決定性)

測定 commit: **`d3d0e4f9`** (`tools/flp/s1_g03_patch.py` と `tools/flp/s2_render_probe.sh` を含む最後のコード commit)。実行環境: Ubuntu 24.04、wine64 9.0 (`/usr/lib/wine/wine64`)、xvfb 21.1.12、`nproc`=4。素材 `fl-win64` (`$RUNNER_TEMP/fl-win64/extracted`、block 分割から §14 の手順でインストール木を復元)。

**S1 (達成)**: 前回 (§14) は `WinVerifyTrust` (G03) の失敗で MSGBOX により停止した。`tools/flp/s1_g03_patch.py` が、検査失敗の条件分岐 3 箇所を無条件 `jmp` に書き換える (期待バイトを照合してから書換え、oracle 用ローカルコピーのみ・commit しない・配布しない)。
- FL64.exe VA `0x140006eaf` (`je`→`jmp`、G03 ホスト検査の失敗 → -2 分岐)
- FLEngine_x64.dll VA `0x1375ee9` (`jne`→`jmp`、エンジン自身の検査、フラグ 0x3d1)
- FLEngine_x64.dll VA `0x137633e` (`jne`→`jmp`、ホスト EXE の検査、フラグ 0x23f)

結果 (`xvfb-run -a wine64 FL64.exe`、120 s、`WINEDEBUG=+loaddll,+msgbox,+wintrust`): rc 124 (終了せず GUI 継続)。`FLEngine_x64.dll` が `native` でロードされ、MSGBOX は 0 件。G01 (Mfplat) 通過。その後 `Shared\*.dll` (Blend2D・freetype・ILTools 等) のロード、`WTSRegisterSessionNotification`・`DwmFlush`・WebView 周辺 (wininet cookie) の呼出しまで到達。G03 は**検証を通すのではなく検証結果を無視する**パッチなので、CN="Image Line NV" の一致は確認していない (GATES G03 の「通す」方針の oracle 版)。

**S2 (部分)**: `tools/flp/s2_render_probe.sh Autogun.flp 3` (`Data/System/Render tests/Autogun.flp`、render 2.0 s の 1 本) を commit 済み HEAD で 3 回実行した。
| run | rc | 所要 | 形式 | data バイト | data SHA-256 |
|--:|--:|--:|---|--:|---|
| 1 | 0 | 16 s | PCM (fmt 1), 2 ch, 48000 Hz, **16 bit** | 385,000 | `fe7a0614…e561a` |
| 2 | 0 | 16 s | 同上 | 385,000 | 同上 |
| 3 | 0 | 16 s | 同上 | 385,000 | 同上 |

- 3 回の data SHA-256 は全て一致 (T2 の決定性は、16-bit 出力では成立)。
- 出力 sample rate は、wine レジストリ `HKCU\Software\Image-Line\FL Studio 26\Devices\Audio output` の `Sample rate` (既定 44100) を 48000 に書き換えると 48000 Hz になる (確認済み)。
- 未達: 目標の **32-bit float** が出ない。`/R` の trace (`WINEDEBUG=+reg`) では、書き出し設定の鍵 `General\WAVRenderForm` は開かれるが、その中の値 (`WAV bit depth`・`Export WAV`・`Dither`) は読まれていない。値を変えても形式は変わらなかった (`WAV bit depth`=2・3、`Export WAV`=2 で 16-bit のまま)。`/E`・`/O` を付けても WAV は出るが 16-bit、`/F` を付けると WAV は出ない。ビット深度を決める経路は未特定。 追加試行 (各 rc 0): `DS_32BitBufBox`=1、`LastExportedFormats`=4 / 16 でも 16-bit のまま。
- 再現の注意: `wine64 reg add` の直後に FL64.exe を起動すると rc 231 で即終了する。`wineserver -k` で止めると正常に戻る (`s2_render_probe.sh` に反映済み)。

**未解決** (`| 未解決 | 影響 | 起票先 |`)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 書き出しのビット深度を 32-bit float にする経路 (`/R` が読む設定) の特定 | S2 の受入「48 kHz / 32-bit float / dither off」が未達 | #2546 (子、親 #113) |
| Render tests 82 本 + Demo 3 本の全数書き出しと、sha256・メトリクス JSON の commit (S3) | 未着手 | #2546 (子、親 #113) |
| 書き出し WAV の内容 (音色・レベル) の妥当性は未確認。T5 の C/D 閾値の校正には使えない | #106 の閾値確定が未着手 | #106 |
