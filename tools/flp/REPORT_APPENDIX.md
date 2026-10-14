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

測定 commit: **`8be0756f`** (`tools/flp/s1_wine_probe.sh`・`s2_render_probe.sh` を変えた最後のコード commit)。`tools/flp/s1_g03_patch.py` は `f6bce8c1` から変更なし。`f6bce8c1` からの変更は SC2010 対応 (`cp "$EXT"/block00038_*` の glob 化) のみ。実行環境: Ubuntu 24.04、wine64 9.0 (`/usr/lib/wine/wine64`)、xvfb-run、`nproc`=4。素材 `fl-win64` (`tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開、`extracted` 25,165 block)。wineprefix は本 run で新規作成。

**再現 (1 コマンド)**: `WINEDEBUG=+loaddll,+msgbox,+wintrust bash tools/flp/s1_wine_probe.sh`。前提: `sudo apt-get install -y wine64 xvfb`、`pip install pefile`、素材 `fl-win64` の展開 (`$RUNNER_TEMP/fl-win64/extracted`)。前提が欠けると `S1 rc=127` などになり、下の `124` の読み方は当たらない。インストール木の組立 → G03 パッチ (`s1_g03_patch.py`、3 箇所) → `timeout 120` で起動。末尾の 2 行が結果: `S1 rc=…` (124 = 120 s で終了せず) と `S1 MSGBOX_OnInit=… FLEngine_x64.dll native-load=…` (件数は `$RUNNER_TEMP/s1_probe.log` を `grep -c` で数えた値。`WINEDEBUG` を省くと trace が出ず件数は 0 になる)。G03 の件数は `grep -c 'WinVerifyTrust returning 80096010'` と `grep -c 'WinVerifyTrust returning 00000000'` で数える。

**S1 (達成)**: §14 では G03 (Authenticode 検査、`tools/startup/GATES.md`) の失敗で MSGBOX により停止した。`tools/flp/s1_g03_patch.py` は検査分岐 3 箇所を書き換える。`objdump -d` で確認した構造は次のとおり。各分岐の飛び先は検査成功側、フォールスルーは戻り値 -2 の失敗側。書換えは飛び先を変えない無条件 `jmp` なので、検査結果を無視して成功側へ継続させる。
- FL64.exe VA `0x140006eaf`: `je 0x140006ebc` → `jmp` (`test %bl,%bl` の直後。フォールスルーは `mov $-2,%r15d`。G03 ホスト検査)
- FLEngine_x64.dll VA `0x1375ee9`: `jne 0x1375efa` → `jmp` (`cmpb $0,0x3d1(%rbp)` の直後。フォールスルーは `movl $-2`。エンジン自身の検査)
- FLEngine_x64.dll VA `0x137633e`: `jne 0x137634f` → `jmp` (`cmpb $0,0x23f(%rbp)` の直後。フォールスルーは `movl $-2`。ホスト EXE の検査)

結果 (commit `8be0756f`、n=1、`timeout 120`): **rc 124** (120 s で終了せず GUI 継続)、**MSGBOX 0 件**、**`FLEngine_x64.dll` native 1 件**。止まる箇所の記録 (GATES の順):
- G01 (Mfplat): `Mfplat.dll` の読込は成功 (`Loaded … Mfplat.dll`、builtin)。`MFStartup` の戻り値は trace 対象外のため未確認。失敗の MessageBox は出ていない (MSGBOX 0 件)。
- G02 (エンジン所在): `Loaded L"Z:\…\fl-install\FLEngine_x64.dll" … native`。exe 直下のエンジンを読めており、通過。
- G03 (Authenticode): `WinVerifyTrust` は 6 回呼ばれ、戻り値は `0x80096010` が 3 回・`0` が 3 回。1 回目の `0x80096010` (署名なし) を含め、パッチにより結果を無視して継続。CN="Image Line NV" の一致は確認していない (検証を通すのではなく結果を無視する oracle 版)。
- その後は `Shared\dsp_ippv2_x64.dll` などの Shared 配下 DLL の読込 (native) と `DwmFlush` の stub 呼出しまで到達。ログ末尾の `X connection … broken` は timeout による xvfb の終了。

所要 (`time`、n=1、並列数 1、wineprefix 新規作成を含む): S1 probe 全体 (インストール木の組立 + 起動 120 s) real 7 m 42 s (user 1 m 21 s / sys 4 m 20 s)。load average (1 / 5 / 15 分): 開始 0.36 / 0.25 / 0.11、終了 1.02 / 0.90 / 0.50。

**S2 (部分)**: `bash tools/flp/s2_render_probe.sh Autogun.flp 3` (`Data/System/Render tests/Autogun.flp`、render 2.0 s の 1 本) を commit `8be0756f` で、S1 と同じ wineprefix 上で連続 3 回実行。各 run の前に block から FL64.exe / FLEngine_x64.dll を取り直し、G03 パッチを当てる。

| run | rc | 所要 | 形式 | data バイト | data SHA-256 (64 桁) |
|--:|--:|--:|---|--:|---|
| 1 | 0 | 15 s | PCM (fmt 1), 2 ch, 48000 Hz, **16 bit** | 385,000 | `13d61a057ac2f6a6920b409e8b5693293ec7f3a43b5688eae139e64b0c3c6299` |
| 2 | 0 | 15 s | 同上 | 385,000 | 同上 |
| 3 | 0 | 17 s | 同上 | 385,000 | 同上 |

- 3 回の data SHA-256 は全て一致 (同一 run 内の T2 決定性)。3 run の合計 real 49.2 s (準備を含む)。load average 開始 0.86 / 0.87 / 0.49、終了 1.52 / 1.06 / 0.58。
- **前回記録の SHA は今回再現しなかった**: `f6bce8c1` の run の `363fb7aa68bea2d5614c97b84b68803432f77b87041802cdde97134e16dbcf2b` (64 桁で記録あり)。`d3d0e4f9` の run の SHA は 64 桁で記録されておらず照合できない (`fe7a0614…e561a` は省略記録のみ)。SHA は run 間・環境間で変わる (原因は未特定。wineprefix の残存状態、ホスト差が候補)。決定性は「同一 run 内の 3 回一致」まで。
- 実行ごとの環境 (未記録の欄は記録が無いことを示す。レビュワーの再実行は round 3 の review 記載の値):

| run | 測定 commit | CPU | wine | wineprefix | S2 の data SHA-256 (3 回) |
|---|---|---|---|---|---|
| A (前回 fix) | `f6bce8c1` | AMD EPYC 9V45 | 9.0 | 未記録 | `363fb7aa68bea2d5614c97b84b68803432f77b87041802cdde97134e16dbcf2b` |
| B (本節の表) | `8be0756f` | 未記録 | 9.0 | 新規 (本 run) | `13d61a057ac2f6a6920b409e8b5693293ec7f3a43b5688eae139e64b0c3c6299` |
| レビュワー再実行 (計 6 本) | `6a5a4092`・`8be0756f` | 不明 | 不明 | 不明 | `363fb7aa68bea2d5614c97b84b68803432f77b87041802cdde97134e16dbcf2b` |
- 出力 sample rate: `HKCU\Software\Image-Line\FL Studio 26\Devices\Audio output` の `Sample rate` (既定 44100) を 48000 にすると 48000 Hz (本測定の全 run で確認)。
- **追加試行** (`S2_REG` で、いずれも commit `8be0756f`、各 1 run):

| 試行 | `S2_REG` の内容 | rc | 形式 | SHA-256 |
|---|---|--:|---|---|
| T1 | `Software\Image-Line\FL Studio 26\Devices\Audio output` / `DS_32BitBufBox`=1 | 0 | 16 bit | `13d61a057ac2f6a6920b409e8b5693293ec7f3a43b5688eae139e64b0c3c6299` (同一) |
| T2 | T1 の値を 0 に戻す + `Software\Image-Line\FL Studio 26\General` / `LastExportedFormats`=4 | 0 | 16 bit | 同一 |
| T3 | `Software\Image-Line\FL Studio 26\General` / `LastExportedFormats`=16 | 0 | 16 bit | 同一 |

- 再現例: `S2_REG=$'Software\\Image-Line\\FL Studio 26\\General|LastExportedFormats|16' bash tools/flp/s2_render_probe.sh Autogun.flp 1`。
- キーの位置: `LastExportedFormats` は `tools/startup/REGISTRY.csv` の `Software\Image-Line\FL Studio 26\General` (既定 8)。`DS_32BitBufBox` は FLEngine_x64.dll 内の UI 部品名 (`DSPanel` 付近) を確認しただけで、登録先の `Devices\Audio output` は推定 (`Sample rate` と同じ音声出力の鍵)。
- 注: 前回 run では T3 の後の `user.reg` で `LastExportedFormats` が `"8"` に戻っていた。FL が終了時に書き戻すため、起動時に 4 / 16 を読んでいない可能性がある (未確定。本 run では未確認)。
- **未達**: 目標の **32-bit float** が出ない。`WAV bit depth`=2・3、`Export WAV`=2 でも 16-bit のまま。`/E`・`/O` を付けても WAV は出るが 16-bit、`/F` を付けると WAV は出ない。ビット深度を決める経路は未特定。
- 再現の注意: `wine64 reg add` の直後に FL64.exe を起動すると rc 231 で即終了する。`wineserver -k` で止めると正常に戻る (`s2_render_probe.sh` に反映済み)。

**差分 0 の証跡** (`docs/WORKFLOW.md` §6): `git diff 8be0756f HEAD -- tools/flp/s1_g03_patch.py tools/flp/s2_render_probe.sh tools/flp/s1_wine_probe.sh tools/startup tools/assets` の出力は空 (0 行)。本節を含む REPORT_APPENDIX.md の commit だけが HEAD の差分。

**未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 書き出しのビット深度を 32-bit float にする経路の特定 (`LastExportedFormats` 4 / 16・`DS_32BitBufBox`=1 は効かなかった) | S2 の受入「48 kHz / 32-bit float / dither off」を満たせない | #2546 (子、親 #113) |
| SHA が run 間で変わる (`363fb7aa68bea2d5614c97b84b68803432f77b87041802cdde97134e16dbcf2b` (f6bce8c1)・`13d61a057ac2f6a6920b409e8b5693293ec7f3a43b5688eae139e64b0c3c6299` (8be0756f)。`d3d0e4f9` の SHA は 64 桁の記録なし)。原因未特定 | 決定性は同一 run 内の 3 回一致まで。別 run・別環境での一致は未確認 | #113 に継続コメント |
| Render tests 82 本 + Demo 3 本の全数書き出しと、sha256・メトリクス JSON の commit (S3) | S3 は未着手 | #2546 (子、親 #113) |
| 書き出し WAV の内容 (音色・レベル) の妥当性は未確認。T5 の C/D 閾値の校正には使えない | #106 の閾値確定が未着手 | #106 |

## 16. #2546 (L-13): `/R` の書き出し形式 (32-bit float) の経路調査

測定 commit: **`aafd1c76`** (`tools/flp/s2_render_probe.sh` と `tools/flp/s2_imm_patch.py` を変えた最後のコード commit)。環境: Ubuntu 24.04、wine64 9.0 (`/usr/lib/wine/wine64`)、xvfb-run、`nproc`=4。素材 `fl-win64` は `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (25,165 block)、インストール木は 25,131 件 (`recover_paths` 経由、組立 3 m 02 s)。

**結論: 受入 1 (48 kHz / 32-bit float) は未達。** 試したすべての `/R` 書き出しが 48 kHz / **16-bit** (fmt 1・2 ch) のままだった。経路は未特定で、子 #3052・#3053 に切り出した。

**16.1 実測** (`bash tools/flp/s2_render_probe.sh Autogun.flp 1`、各 run は同一 HEAD。SHA-256 は data チャンク)

| 試行 | 変えたもの | rc | 所要 | 形式 | data SHA-256 (先頭 8 桁) |
|---|---|--:|--:|---|---|
| B | 無変更 (n=3) | 0 | 15 / 14 / 15 s | 16-bit | `2e067272` ×3 (同一) |
| T | `S2_TRACE_REG=1` (`WINEDEBUG=+reg`) | 0 | 15 s | 16-bit | `2e067272` |
| P1 | `FLEngine_x64.dll` VA `0xef6d4b` の `movzbq 0xe18(%rax),%rcx` を `mov $1,%ecx` に置換 | 0 | 14 s | 16-bit | `2e067272` |
| P2 | VA `0xa64b66` の書式即値 0 → 1 | 0 | 14 s | 16-bit | `2e067272` |
| P3 | VA `0x6725e1` の書式即値 0 → 1 | 0 | 15 s | 16-bit | `2e067272` |
| P4 | VA `0x6725e1` の書式即値 0 → 2 | 0 | 13 s | 16-bit | `2e067272` |
| P5 | VA `0x67240d` の書式即値 0 → 1 | 0 | 14 s | 16-bit | `2e067272` |
| P6 | VA `0x67240d` の書式即値 0 → 2 | 0 | 14 s | 16-bit | `2e067272` |

- 同一入力 3 回 (B) の SHA-256 は一致 (`2e067272…`)。本 run の値は §15 の `13d61a05…` と異なる (run・環境差。§15 の表と同じ扱い)。
- P1〜P6 の入力行 (`S2_PATCH`): 実行時の行は記録が残っていない (リポジトリと #2546 のコメントに無い)。下記は表の VA と書換え内容から組み直した行で、**再実行は未実施**。`s2_imm_patch.py` を素材 `block00031_PE.bin` (FLEngine_x64.dll) のコピーに当てると期待バイトが一致し (exit 0)、逆アセンブルは `movzbq 0xe18(%rax),%rcx` → `mov $0x1,%ecx`、`movb $0x0,0x28(%rsp)` → `movb $0x1,…` / `$0x2` になる。

```
P1: S2_PATCH=$'ef6d4b|480fb688180e0000|b9010000000f1f00' bash tools/flp/s2_render_probe.sh Autogun.flp 1
P2: S2_PATCH=$'a64b66|c644242800|c644242801' bash tools/flp/s2_render_probe.sh Autogun.flp 1
P3: S2_PATCH=$'6725e1|c644242800|c644242801' bash tools/flp/s2_render_probe.sh Autogun.flp 1
P4: S2_PATCH=$'6725e1|c644242800|c644242802' bash tools/flp/s2_render_probe.sh Autogun.flp 1
P5: S2_PATCH=$'67240d|c644242800|c644242801' bash tools/flp/s2_render_probe.sh Autogun.flp 1
P6: S2_PATCH=$'67240d|c644242800|c644242802' bash tools/flp/s2_render_probe.sh Autogun.flp 1
```
- 前段 (変更前の probe、`S2_REG` で `Software\Image-Line\FL Studio 26\General\Render` に `WAV bit depth`=0/1/2/3・`Export WAV`=1・`Dither`=0 を書いた 4 試行): すべて 16-bit。`user.reg` には値が残る (`"WAV bit depth"="3"`)。`/R` がこの値を読んだかは未測定 (16.2)。

**16.2 トレース** (T、開かれたレジストリキー 759 種。抽出するのは `NtOpenKeyEx` の鍵名だけ): `General\Render` を単一の相対名で開く記録は **0 件**。開かれたのは `General\WAVRenderForm` (30 回) と `General\WAVRenderForm (mixer)` (1 回) など。`Render` 単独・`General` 直下からの open は未確認。`General` を開いてから `Render` を相対名で開く経路は、`General\Render` の文字列検索では見えない。`WAV bit depth`・`Export WAV` の値の読出しは未測定 (probe は値名を抽出しない)。鍵名は末尾の `"` を含む (`sed` が行末の `"` を除かない。件数には影響しない。次の再測定で直す)。このため `RenderOptions.load` (VA `0xeec630`) を `/R` が通るかは、本測定からは判定できない。

**16.3 静的所見** (`FLEngine_x64.dll`、ImageBase `0x400000` 込みの VA。`objdump -d` と目視、未確定の推定を含む)
- `RenderOptions.load` の `WAV bit depth` (VA `0xeec933`): 読込ヘルパ `0xeec5d0` が `[0,2]` に丸めて `obj+0xe18` (1 byte) に格納。構築側 `0xedff36` の `movb $0x2,0xe18(%rcx)` が既定値 2。
- `RenderOptions.load` の呼出し元 wrapper は `0xee6a20` (VA `0xee6a2c` で load)。`/R` からの直接の呼出しは見つからなかった。
- `0xef6d4b` は `obj+0xe18` を読み、フラグ `0x45`・`0x46` に変換して `0xef6e2d` (`0x672580`) 等へ渡す (P1 で変えても出力は不変)。
- `RIFF` / `fmt ` を書くのは VA `0x670fd0` だけ (`0x671082`・`0x67111c`)。書式引数 `0x178` が 1 のとき fmt を `0x674e10` で書き (`bits=0x18`)、それ以外は汎用 sample writer。
- `0x670fd0` の直接の呼出し元: `0x672130` (書式は 6 番目の引数)、`0x672390` (書式 0 の即値は VA `0x67240d` = P5・P6)、`0xa64b6b` (書式 0 の即値は VA `0xa64b66` = P2)。`0x672130` の呼出し元は `0x672580` (書式 = `r8b`。`0xef6e2d` から `0x45` を渡す)、`0x6725c0` (書式 0 の即値は VA `0x6725e1` = P3・P4)、ほか 8 箇所。`0x672390` の呼出し元は wrapper `0x696a60` と `0x11e9704`。
- 32-bit float (fmt タグ 3) を書くコードは、上記の範囲では確認できなかった。

**16.4 解釈と次の一手**: 本測定から言えるのは次まで。(1) `General\Render` を単一の相対名で開く記録は無い (16.2)。(2) P1〜P6 と S2_REG の 4 試行 (16.1 前段) では出力は変わらなかった (すべて 16-bit)。(3) 出力が変わることを確かめる正の対照は無い。よって「保存された書式は使われない」「即値は通らない」とは結論しない。次は `/R` のコマンドライン処理から書出し関数までを追う (#3052)。

**差分 0 の証跡** (`docs/WORKFLOW.md` §6): `git diff aafd1c76 HEAD -- tools/flp/s2_render_probe.sh tools/flp/s2_imm_patch.py tools/startup tools/assets` の出力は空 (0 行)。本節を含む REPORT の commit (`tools/flp/REPORT.md`・`tools/flp/REPORT_APPENDIX.md`) だけが HEAD の差分。

**未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `/R` の 32-bit float 経路 (書式を決める値・関数) が未特定 | 受入 1 未達 | #3052 ([L-14]) |
| Render tests 82 本 + Demo 3 本の全数書き出しと sha256・メトリクス JSON の commit | 未着手。16-bit では受入 2 を満たさない | #3053 ([L-15]、依存は #3052) |
| `/R` が `RenderOptions` の保存値を読むかは未確定 (`General\Render` の単一相対名は 0 件。`Render` 単独・`General` 直下は未確認) | 設定経由で形式を切り替えられるかを判定できない | #3052 |
| `Render` 単独・`General` 直下からの open と、`WAV bit depth`・`Export WAV` の値の読出しが未測定 (probe は `NtOpenKeyEx` の鍵名だけ抽出) | `RenderOptions.load` を `/R` が通るかを判定できない | #3052 |
| P1〜P6 の入力行は未記録。§16.1 の行は組み直しで、未再実行 | §16.1 の P1〜P6 の結果は組み直した行では確認していない | #3052 |
| data SHA-256 が run・環境で変わる (`2e067272` 本 run / `13d61a05` §15) | 決定性は同一 run 内 3 回一致まで | #2546 にコメント済み (issuecomment-6178890982) |
