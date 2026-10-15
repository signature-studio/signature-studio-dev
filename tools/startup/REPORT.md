# REPORT — H startup-process: FL 起動シーケンス / 子プロセス / ゲート / レジストリ / スタブ計画

日付: 2026-10-10 / 担当: H startup-process / 書込範囲: `tools/startup/` のみ / 再現: `bash tools/startup/startup.sh` (約 3 分, exit 0, `verify.py` 92/92 OK)

## 0. 結論 (数値は全て実測。推定は「推定」と明記)

1. **起動はホスト 11 ステップ + エンジン 13 ステップ = win 24 ステップ、mac 10 ステップ**。ホスト (FL64.exe 597,064 B / OsxFL 5.0 MB) は
   `THostInstance` (0x38 B, host version=1) を作り、エンジン唯一のエントリ **`CreateFruityInstance`** を 1 回呼ぶだけ。win は
   `CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)` (定数ハンドシェイク)、mac は `(host, &iface)`。**メッセージループは win ではこの関数の内部** (`TApplication.Run` 0x86a660) にあり、mac では戻ってからホストが `iface->vtbl+200` (vtable オフセット 200 = slot25) を呼ぶ。→ STARTUP.md
2. **ブラウザ版で置換するのはホスト側のみ** (glue 約 20 行 + 仮想レジストリ + Win32 スタブ約 60 API + 専用 Worker 上のメッセージポンプ)。エンジンの 13 ステップは lift してそのまま動かす。**FL コードは無改変**。→ stub_plan.md
3. **外部起動点は PROCESSES.csv 30 行 (win 23 / mac 7)**。FL が自分で起動する外部実行体は win **11 種** (CreateProcessW 2 関数 / ShellExecuteA 1 / ShellExecuteExW 3 / ShellExecuteW 17 関数)。
   判定: 必要 0 / 不要 8 / 代替 15 / 対象外 4 / 後回し 3。**ブラウザ版で「プロセスとして必要」なものは無い**。FL64.exe 自身は CreateProcess を一切呼ばない (IAT で確認)。
4. **ゲートは 16 件 (GATES.md)**。起動をブロックし得るのは 8 件 (G01–G08) で、全て shim の戻り値か仮想レジストリ既定で通る。ネットワーク/認証/更新/WebView 系 (G09–G13) は **起動時には発火しない** (遅延タイマー or ユーザ操作起点)。
5. **レジストリ**: REGISTRY.csv 457 行。win のキー 46 本 (HKCU/HKLM; 内訳: コード上でリテラル確認 31 / ベース名からの推定 5 / インストーラ(NSIS)報告ベース 10)、エンジンが参照する値名 222 種 (FL の `TRegistry` 経由・全て REG_SZ 文字列; 例外は OS の `CurrentMajor/MinorVersionNumber` DWORD 2 値のみ)、`default` 列に ReadInt/ReadBool の既定値を抽出。
   mac は `~/Library/Preferences/Image-Line/reg.xml` (libwinbridge `TXmlRegistry`) + CFPreferences `com.image-line.shared`。seed は最小 18 値 (`data/vreg_seed.json`)。

## 1. 成果物

| ファイル | 内容 |
|---|---|
| `STARTUP.md` | 起動シーケンス (図+24 ステップ表+mac 10 ステップ)、host 構造体、引数/環境変数、設定ロード、初回アイドル、FS 参照 |
| `GATES.md` | G01–G16 (条件/VA/失敗時/ブラウザ方針) |
| `stub_plan.md` | ブート順、host glue 仕様、メッセージポンプ、VFS、スタブ表 (戻り値付き)、vreg、受入テスト、下流チケット T1–T11 |
| `PROCESSES.csv` | 30 行: 起動点/API/VA/トリガ/引数/判定/代替/確度 |
| `REGISTRY.csv` | 457 行: platform/hive/key/value/type/default/access/category/source/confidence |
| `data/vreg_seed.json` | 仮想レジストリ初期値 (18 値) |
| `startup.sh`, `scripts/*.py`, `ghidra_scripts/*.java` | 1 コマンド再現 (Ghidra decompile / 全関数 index / TRegistry 呼出点抽出 / CSV 生成 / 実バイナリ検証) |

## 2. 方法 (再現可能)

- **FL64.exe**: Ghidra 12.1.4 headless で WinMain と 8 関数を decompile (`fl64_decomp.c`)、`scripts/pedis.py` (capstone+pefile, RIP 相対の文字列/IAT 注釈) で逆アセンブル確認。
- **FLEngine_x64.dll**: `tools/m2` の Ghidra プロジェクト (59,009 関数) を**複製**して読取専用で処理 (元は無改変)。`CallTree.java` で全関数の callee/文字列/import を索引化 (`func_index.tsv`, 59,009 行)、
  `CallSiteStrings.java` で `TRegistry` メソッド (`0x5ae000–0x5b4000`) への全 call site 1,395 箇所から直前の `lea/mov/xor` で積まれた文字列・即値引数を抽出 → 在庫化 (呼出元 147 関数)。
- **mac**: OsxFL / libwinbridge / FLEngine の x86_64 slice を Ghidra で decompile (`fat_slice.py`)。
- **検証**: `scripts/verify.py` が Ghidra 無しで実バイナリから 92 項目を独立照合 (IAT・文字列・vtable・ハンドシェイク定数の機械語・ツール表 `0x15342a0`・CSV 整合)。`FORCE=1 startup.sh` で全工程再計算 → 92/92。

## 3. 主要な実測事実 (抜粋; 詳細は各 md)

| 項目 | 値 |
|---|---|
| FL64.exe | MSVC C++、`main`=`0x140007560` (WinMain)、Media Foundation 検査 → `THostInstance`(vtbl `0x140069d00`, 3 slot) → `0x1400062a0` (パス解決/署名検証/LoadLibrary) |
| エンジン export | win: `CreateFruityInstance`(VA 0x1375990)/`__dbk_fcall_wrapper`/`dbkFCallWrapperAddr` の **3 本のみ**。mac: 1 本のみ |
| 署名ゲート | 3 箇所 (host→engine `0x1400062a0`、engine 自己検査 ×2 `0x1375990`)。署名者名 == "Image Line NV" → 不一致 -2 |
| エンジン所在 | `<exeDir>\FLEngine_x64.dll` → 無ければ `HKCU/HKLM(WOW64_32)\Software\Image-Line\Shared\Paths\FL Studio engine` (値=ファイルパス)。`Builds\` があれば `ShowEngineChoice` |
| 登録情報 | `…\Registrations\FL Studio 26.1\ILRegKey` (HKCU→HKLM)。マシン識別コード (`MachineGuid`+`GetComputerNameExW`+Reg 系、および `SHFolder.dll` を `LoadLibraryW` で読み名前で解決した `SHGetFolderPathW` (CSIDL 0x1a)) が **24 関数にインライン展開** (`license_obs/REPORT.md` §9) |
| フラグ | `byte[0x14f84a8]` は `0x10c7cd0` だけが書込。読み側: bit0=0→"Registered to: <name>"、1→"Please remember to register"。bit1→Fire edition |
| ユーザデータ | `Shared data`(HKCU Paths) → 無ければ `SHGetFolderPath(CSIDL_PERSONAL)\Image-Line\`。書込テスト `testpermissions.tmp`。env `FLStudio<k>Data` 等を設定 |
| 単一インスタンス | `FindWindowW("TFruityLoopsMainForm")` + WM_COPYDATA |
| ツール表 (engine `0x15342a0`) | id0 ControlCreator / id1 fldiagnostic / 1000 CopyLicenseToAllUsers / 1001 CloudBounceConsole / 1002 RemoveLicenses |
| WebView2 | engine が `LoadLibraryW("WebView2Loader.dll")` を**動的**に行う (`0xbe3520`)。`flHelper` JS コールバック 23 種。画面= FL CLOUD Sounds / Gopher+MCP / Help(index_offline.html)。FL64.exe は WebView2 を使わない |
| Edge 201 MB | `MicrosoftEdgeUpdateSetup.exe` = WebView2 Runtime を入れるインストーラ同梱物。実行時には使われず、ブラウザ版では不要 |
| MCP | `MCPTools.pyc` を組込 Python が実行する**プロセス内ツール** (`tools/call` JSON)。待受ポート無し。外部 AI (Gopher) とセットで対象外 |
| クラッシュレポータ | プロセス内 (`0x11f0540`)。ログ `<UserData>\Crash\`、Send=HTTP upload、再起動=`fldiagnostic /restartfl`。Breakpad/Crashpad/MiniDumpWriteDump の文字列・import は無し |

## 4. 未解決・ブロッカー (正直に)

1. **ライセンス: Trial 制限の機能的な全容は未確定** (#107 の結果 → `tools/startup/license_obs/REPORT.md`: Trial 判定の本体は gradeChar ≤ 0x40 で bit0=Trial は**反証**、ILRegKey 無し/空は実機械語で観測済み、非空は未観測 = #525)。
   さらに、ILRegKey の検証は MachineGuid 等を含むマシン識別コードに依存すると**推定** (インライン24 関数。未解読)。
2. **起動必須アセットの最小集合は未計測** (win 全展開 2.3 GB)。`open()` トレース待ち (T5, FLEngine が動いてから)。
3. 表のうち `[+0x20/+0x28] = 0x140069820` (host の 2 ポインタ) と host vtbl の呼ばれ方は、静的には用途を確定できず lift 後 trace が必要 (T1)。
4. 「section via wrapper」型の設定値 (REGISTRY.csv で `key` が `(section via wrapper…)`) は親キー名を静的に確定できず**候補表示**に留めた (値名 113 種)。実キーは lift 後に vreg の open ログで確定できる。
5. `PluginManager` の win 版引数・`ilbridge` のコマンドライン、`CloudBounceConsole` を呼ぶ側のパス導出は mac 文字列/静的推論による (W03/W09 の `evidence` は `v/s`)。
6. 他担当の `tools/m11` (DllMain closure lift) は進行中で、本タスクの S09/S12–S22 はその完了待ち。M11 の成果物には触れていない。

## 5. ユーザ依頼事項

1. **(任意) 正規ライセンス所持なら、Image-Line アカウントからエクスポートした登録ファイル (`.reg`) を `~/ダウンロード` に配置** — T9/T11 で Trial 以外の挙動を観測するための入力。無ければ Trial 前提で進める (偽造・生成はしない)。
2. 外部通信が必要な機能 (FL Cloud / Gopher AI / 認証 / 更新) を「完全に無効のまま」で良いか確認 (現計画は WinInet 常時オフライン)。
3. ブラウザ版の Help (`Help/index_offline.html`) を優先度どこに置くか (T8 は任意扱い)。

## 6. 次タスク提案 (下流チケット)

T1 startup-glue (THostInstance+CreateFruityInstance+終了処理) / T2 vreg (仮想レジストリ shim, seed, IndexedDB) / T3 win-stubs-startup (約 60 API の fail-soft) /
T4 wininet-offline / T5 vfs-layout+asset-trace / T6 message-pump (SAB ring, Worker ブロック) / T7 cpython-wasm (任意) / T8 help-viewer (任意) /
T9 license-import (任意・ユーザ起点) / T10 crash-restart / T11 license-observation。内容と依存は `stub_plan.md` §8。
推奨順: **T2 → T3 → T1 (m11 の DllMain closure 後) → T6 → T5 → T11**。
T5 の trace → 最小 asset 集合の変換器は `tools/startup/assettrace/REPORT.md` (実 FL trace は T1 待ち・#105)。

## 7. 参照した既存資産 (読取のみ)

`docs/REFERENCES.md` `[WIN64]` / `[MAC]` の REPORT (記述のうち「FL64.exe が WebView2 を使う」は**誤り**で、WebView2 はエンジン側に動的束縛される。「Electron/CEF 無し」は正しい),
`tools/m2/{REPORT.md,SHIM_INVENTORY.md,work/ghidra_dll}`, `tools/m11/` (存在確認のみ)。既存 REPORT の「registry/ファイル関連付けは Web では memory/cookie」は、本調査で
**エンジンの全設定が REG_SZ の TRegistry 経由**と判明したため、cookie ではなく **vreg (IndexedDB)** を推奨に修正。

## 8. #2713 [WIN-2]: 起動指標の統一 — `boot_metric.json` (単一スキーマ)

既知類型との関係: 該当なし (lift・逆アセンブル・IR pass は触らない。既存 REPORT と results からの算出のみ)。

**結論 (測定 commit 時点の値)**: 「起動」の数え方は 5 通り (17 / 52 / 53・56 / 209 / 928) あり、いずれも別の量を指す。`tools/startup/boot_metric.json` (`boot_metric/v1`) に、路線 (m11 / x64c / native-ref) とモード別のレコードとして載せた。m11 / x64c の DllMain 連鎖の record では、最終到達ステップは S09 (DllMain 内の unit 初期化まで)、CreateFruityInstance (S11) 未到達。この 2 点は harness の構造による (§8-3)。flengine 路線の record (`flengine-cfi-probe`) では CreateFruityInstance の入口 (S12) まで到達する (測定 commit `ae963e28` 時点。現 HEAD は未再測定。§8-6)。`docs/STATUS.md` 先頭の 1 行がこの結論を指す。

### 8-1. 5 通りの数え方 → スキーマのフィールド対応

| 値 | 何を数えているか | 出典 | boot_metric の対応 (`id`.フィールド) | 扱い |
|---|---|---|---|---|
| 17 | m11 通常起動の完了 unit | `tools/m11/REPORT.md` §1 表 (#132 以前の旧値が表に残存) | 対応なし | 旧値。現行は 53 |
| 52 | m11 + GUI shim 結合版の units_run | `tools/gui/flengine/results/boot.json` | `m11-gui-tolerant`.units.ok | 現行 |
| 53 / 56 | m11 通常起動の units_run (実行 53) / 完了 (実行 53 + skip 3) | `tools/m11/REPORT.md` §14 の `de50ffa` 行と skip 内訳 | `m11-tolerant-sequential`.units.ok (53)、units.ok + units.skipped (56 = 完了。派生) | 現行 |
| 209 | x64c boot の dispatch (完走 208) | `tools/flelift/boot/results/boot_summary_plain.json` | `x64c-strict-sequential`.units.dispatched (209)、units.ok (208 = dispatched − failed) | 現行 |
| 928 | native 実機械語の hybrid の units_run (wasm ではない) | `tools/liftdiff/REPORT_LD26.md` §1 (測定 commit `2ca85816`) | `native-ref-hybrid`.units.ok (928)、units.total (942) | 参照値 |
| 872 | m11 隔離 survey の ok | `tools/m11/REPORT_APPENDIX_1430.md` (測定 commit `7e149974`) | `m11-isolated-survey`.units.ok | 現行 (`de50ffa` の §14 の 866 より新しい commit) |
| 892 | x64c 隔離 survey の ok (FLE-5 末) | `tools/flelift/boot/results/survey.json` | `x64c-isolated-survey`.units.ok | 現行 (#253 の 888 は FLE-3 の表値) |

### 8-2. 測定 commit 時点の値 (`boot_metric.json` の算出結果)

| id | 測定 commit (出典の記載) | 完走 (ok) | 失敗 (failed) | dispatch | 停止 (unit / VA / kind) |
|---|---|---|---|---|---|
| m11-tolerant-sequential | `de50ffa` (§14 表行。停止位置は表行 `6654322`) | 53 (完了 56) | 1 (停止 unit 1 本) | 57 | 57 / 0x16fde0 / halt0 |
| m11-isolated-survey | `7e149974` (付録の節) | 872 | 23 (trap) | — | — (miss 46・noproc 1) |
| m11-gui-tolerant | `703b4857` (gui REPORT の見出し「本節を正とする」。boot.json の値はこの commit と一致を `git show` で確認) | 52 | 1 (boot_threw) | — | — |
| m11-gui-survey | `719f1c43` (gui REPORT §6i。S1 値と survey_soft.json が一致) | 870 | 24 (trap) | — | — (miss 47・noproc 1) |
| x64c-strict-sequential | 記載なし (最終更新 commit `ac5d6d46`) | 208 | 1 | 209 | 209 / 0x816e80 / oob |
| x64c-isolated-survey | 記載なし (最終更新 commit `12958453`) | 892 | 3 (unlifted) | — | — (uncovered 47) |
| native-ref-hybrid | `2ca85816` (liftdiff の測定 commit 行) | 928 (total 942) | — (first_fail 830) | — | — |

`gui_natural` (RegisterClassW / CreateWindowExW の自然到達回数): boot (`m11-gui-tolerant`) は 0 / 0、隔離 survey (`m11-gui-survey`) は 2 / 2。`probes`: x64c boot は GetMem 1886・FreeMem 776 (JSON 値)。`first_wm_paint`・`pixels` は全レコード null (未測定。理由は null_reasons)。

### 8-3. 算出の仕組み

- 生成: `python3 tools/startup/boot_metric.py` (`--check` は既存 JSON との一致検査、`--route x64c` は路線の現在値だけを表示)。
- 出典: REPORT の表行・節・見出し (節の中で一意に一致させる) か results の JSON キー。手で値を書かない。
- commit は 2 種類を分けて持つ。`source[].measured_commit` は表行・節・見出しに測定 commit として書かれたもので、無ければ null。`source[].file_last_commit` は `git log -1 -- <file>` (測定 commit ではない)。レコードの `commit` は measured_commit から取り、書かれていなければ null (理由は null_reasons)。
- 派生値 (`derived`): リテラルではなく出典の値から導く項目と規則を書く。m11 の failed 1 は「停止 unit 1 本」、dispatched は units_run + units_skipped + 停止 unit 1 本 (停止 unit 番号と一致を検査)、total は survey 列の合計 (942 と一致を検査)。gui survey の trap は kinds の合計と一致を検査し、REPORT の S1 値とも照合する。
- CreateFruityInstance 未到達 (`reached: false`, `last_step: S09`) は harness の構造による。算出時に m11・gui/flengine・flelift/boot の非 work ファイルを走査し、`CreateFruityInstance` の呼出し構文が 0 件であることを検査する (コメント行・行末コメント・.md を除く。gui/flengine は測定 probe `cfi_probe.mjs` だけを allow で除く。1 件でも MetricError)。呼出しは `tools/startup/glue` 側にある。STARTUP.md の DllMain の段 (S09) が harness の到達する最後の段で、S11 (`GetProcAddress(…"CreateFruityInstance")`) は harness が呼ばない。
- gui survey の JSON は REPORT の測定 commit 時点の内容 (`git show <commit>:<path>`) から読む。作業ツリーの後続 commit の値は読まない。
- 出典が無い・一意でない・照合が合わない場合は `MetricError` で止まる (exit 1)。値は捏造しない。

### 8-4. 検証

- 単体 (固定 fixture): `python3 tools/startup/test_boot_metric.py` → `Ran 21 tests ... OK`。期待値 (m11 53 / 57 / 0x16fde0、survey 872 / 23 / 46 / 1、gui 52 / 870 / 24、x64c 208 / 209 / 0x816e80、x64c survey 892 / uncovered 47、native 928 / 942 / 830 など) を固定入力で検査する。null の全項目に理由があることも検査する。
- ネガティブコントロール (いずれも期待どおり `MetricError`): (a) 表行 `de50ffa` を壊す、(b) JSON の `boot.units_run` キーを消す、(c) 出典ファイル `tools/liftdiff/REPORT_LD26.md` を消す、(d) m11 survey の ok を 900 にして合計 942 と食い違わせる、(e) gui REPORT の S1 値 (870 → 871) を JSON と食い違わせる、(f) m11 の非 work ファイルに `CreateFruityInstance` を置く。
- 実データ: `python3 tools/startup/boot_metric.py --check` → `boot_metric: OK`。
- 測定 commit → HEAD のファイル差分 (範囲 `tools/m11 tools/gui tools/flelift tools/liftdiff tools/shimx tools/startup/STARTUP.md`、`git diff --shortstat <起点> HEAD -- <範囲>`。範囲は本 PR の変更対象を含まない):

| record | 起点 (測定 commit または最終更新 commit) | 差分 |
|---|---|---|
| m11-tolerant-sequential (表行 de50ffa) | `de50ffa` | 811 files (+99,361 / −1,395) |
| m11-tolerant-sequential (停止の表行 6654322) | `6654322` | 811 files (+99,371 / −1,395) |
| m11-isolated-survey | `7e149974` | 465 files (+64,020 / −282) |
| m11-gui-tolerant | `703b4857` | 569 files (+68,480 / −355) |
| m11-gui-survey | `719f1c43` | 390 files (+42,827 / −169) |
| x64c-strict-sequential (測定 commit 不明) | `ac5d6d46` | 991 files (+136,528 / −2,213) |
| x64c-isolated-survey (測定 commit 不明) | `12958453` | 983 files (+136,291 / −2,152) |
| native-ref-hybrid | `2ca85816` | 382 files (+42,129 / −145) |
| flengine-cfi-probe (範囲は `tools/shim`・`cfi_probe.mjs`) | `adad27ad` (再測定の commit) | 0 (`adad27ad` 以後に差分なし。内訳は `REPORT_APPENDIX_2880.md` §9-8) |

  flengine-cfi-probe 以外の路線は差分が 0 ではない。文書と results は測定 commit 時点の値であり、現 HEAD の実測ではない。flengine-cfi-probe は `adad27ad` で再測定した (§8-6)。他の路線の再測定の要否は本 issue の範囲外で、§8-5 で PM 判断とする。
- 文書・results の変更有無 (出典 6 ファイル): `git diff --stat 580dd294 4e8bdd8c -- tools/m11/REPORT.md tools/m11/REPORT_APPENDIX_1430.md tools/gui/flengine/results tools/flelift/boot/results tools/flelift/boot/REPORT.md tools/liftdiff/REPORT_LD26.md tools/startup/STARTUP.md` の出力は空 (base 4e8bdd8c までの範囲)。

### 8-5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| x64c の GetMem: `boot_summary_plain.json` は 1886、`tools/flelift/boot/REPORT.md` §9 (CI 再測) は 1,890 | 同じ unit 209 停止で数値が 4 食い違う。JSON 値 (1886) を採用 | PM 判断 (#253 は CLOSED のため紐づけ先を決められない) |
| x64c の隔離 survey は closure 外 46 / noproc 1 を分けていない | miss・noproc は null (合計 uncovered 47 のみ) | PM 判断 (#253 は CLOSED のため survey 分類の起票先を決められない) |
| gui `boot.json` の `boot_threw` は `unreachable`、`tools/gui/flengine/REPORT.md` §6d (B1) は `memory access out of bounds` | 停止理由の表記が食い違う。`m11-gui-tolerant` は failed 1 のみ記録 | #174 (OPEN, GUI-3) へ。範囲に含めるかは PM 判断 |
| gui REPORT §5 の「GUI soft は OOB 21 / halt0 8」と `survey_soft.json` の kinds (OOB 16 / halt0→longjmp 7 / unreachable 1、計 24) が食い違う | 本 record は JSON 値 (trap 24) を採用。REPORT 側は未更新 | #174 (OPEN, GUI-3) へ。PM 判断 |
| m11 の survey は `REPORT.md` §14 (866, `de50ffa`) と `REPORT_APPENDIX_1430.md` (872, `7e149974`) が並存 | JSON は commit が新しい 872 を採用。本体 REPORT は未更新 | PM 判断 (m11 REPORT 更新の依頼) |
| x64c の測定 commit が出典に無い (boot・survey 両方) | 測定 commit は null。最終更新 commit を測定 commit と読まない | PM 判断 (REPORT に測定 commit を書く依頼) |
| 再測定の要否: §8-4 の差分 (flengine-cfi-probe 以外) は 0 でない | 「現在値」と読むと HEAD の実態とずれる | PM 判断 (本 issue の範囲外) |
| `first_wm_paint`・`pixels` (最初の WM_PAINT・画素) は全路線で未測定 | 最初のウィンドウの数値は null | PM 判断 (後続 WIN の issue は未起票) |
| native hybrid の `first_fail 830` の意味 (失敗か停止か) が REPORT に無い | `units.failed` は null | PM 判断 (liftdiff 担当の issue は未特定) |
| gui `results/survey_soft.json` は `5f9d7cbd` で 870/24 → 872/22 に更新されたが、gui REPORT §6d・§6i は測定 commit `719f1c43` の 870/24 のまま | `m11-gui-survey` は `719f1c43` 時点の JSON を読む (本 PR で変更)。HEAD の JSON とは食い違う | #174 (OPEN, GUI-3) へ。PM 判断 |
| 規則 (f) (pr-lint) の対象は #3191 の 4 パス (`tools/m11/REPORT.md`・`tools/flelift/boot/REPORT.md`・`tools/gui/flengine/`・`tools/startup/`)。`boot_metric.json` の出典には `tools/m11/REPORT_N2714.md`・`tools/m11/REPORT_APPENDIX_1430.md`・`tools/liftdiff/REPORT_LD26.md`・`tools/flelift/boot/results/boot_summary_plain.json` もあるが、これらの変更では警告されない | 出典を変えた PR の boot_metric.json 更新漏れを検出しない | PM 判断 (対象の拡張。issue 未起票) |

### 8-6. flengine 路線の record (`flengine-cfi-probe`)

測定 commit `adad27ad` (出典: `tools/gui/flengine/REPORT_APPENDIX_2880.md` §9-3・§9-8。`ae963e28` の測定も同じ値・`REPORT_APPENDIX.md` §7-4)。`cfi_probe.mjs` が DllMain attach の後に CreateFruityInstance を 1 回呼ぶと、入口 (STARTUP S12) に届き、本体内で EnterCriticalSection の fail-fast (CS `0x12bd390`、登録されていない CS) により `Aborted` する。`last_step: S12` は**下限**で、S13 以降の到達と fail-fast の位置・呼出元 VA は未測定 (#3077 [WIN-16])。fail-fast の API は §7-4 と §9-3 の一致を検査する。`tools/shim`・`cfi_probe.mjs` は `adad27ad` 以後に変わっていない (`REPORT_APPENDIX_2880.md` §9-8)。
