# Slate Digital Fresh Air 1.0.9 — インストーラ解析 + lift 可否 (事前解析 K)

- 日付: 2026-10-10 / 素材: `~/ダウンロード/Fresh Air.Win.zip` (33,932,552 B), `Fresh Air.pkg` (36,871,956 B)
- 再現: `bash tools/targets/freshair/analyze.sh` (展開→PE/保護判定→RTTI/closure→Gain lift→wasm bit-exact を直列実行。生成物は `work/`、`tools/targets/freshair/.gitignore` で除外)
- 法的判断は含まない (技術的事実のみ)。EULA 上の可否は別途確認が必要。

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| 実体 | 配布 DLL/AU/VST3/AAX は **250KB の薄いシェル**。DSP+UI は全て `SlateCore.core_64` (Win x64, 36.3MB) / `SlateCore` (mac **arm64 のみ**, 19.1MB) に在る |
| フレームワーク | JUCE ではない。**Kilohearts "HeartCore" snapin エンジン** (PDB: `...\Slate Fresh Air\bin_freshair\HeartCoreFreshAir.pdb`)。UI=Skia、boost、AAX/VST SDK。コアは 37 製品 ID (`FrAr`+`ks*`/`k*` 36 種) を内包 |
| Fresh Air の DSP | **新規 DSP ではなく既存 snapin の合成**: プリセット `FRAR/DUMP` ("FRESH AIR v8") = **Filter ×2 + Compressor ×3 + Gain ×3** + マクロ (UI ノブ: Mid Air / High Air / Trim)。FreshAirDsp 自体は vtable 全 17 slot で 2.3KB 級の制御層 |
| DSP 規模 (実測, 直接 call のみ=下限) | 237 関数 / 67,689 B / 15,988 命令 / SSE 3,281 命令 (20.5%) (capstone mnemonic 判定。Ghidra は 15,463 命令 / XMM・YMM 操作 3,925=§3.3。うち pdata 外 call 先 62 関数は 16 B 仮定 = 992 B、pdata 実在は 175 関数 / 66,697 B)。コア .text 17.58MB の **0.39%**。OTT (166 関数 / 58,891 B) の ~1.15 倍 |
| **認証/保護 (Win)** | **PE イメージ内 (shell/core/unins) の PACE/iLok/Eden マーカー 0、ネット系 import 0、パッカー無し** (§4)。PACE 文字列は AAX の署名ブロック (PE イメージ外) にのみ有り。公式 User Guide は「iLok 必須」と記載 → **バイナリ内実装と不一致 (未解明)**。静的には lift を阻む要因は検出されず |
| 認証/保護 (mac) | コアが **PACE Eden ラッパ** (`__pbootstrap`/`__POVERTEXT` + 4.1MB エントロピー 8.00 の `__data`) かつ arm64 のみ → **lift 対象外** |
| **lift→wasm 試行** | `gain::GainDsp::process` (SlateCore 0x180afe090, 446 B +meter 2 本) を RetDec→修復 pass→emcc で wasm 化し **実機 x86 機械語と 400/400 シナリオ bit-exact** (§5)。修復は 3 類型のみ (全て OTT 既知クラス) |
| 判定 | **lift 可 / 難度: 中** (DSP 規模は OTT 同等、認証 blocker 無し。難所は C++ 実行時層と SSE helper 署名・分岐脱落の機械修復)。**blocker 無し (Win x64 を正本とする限り)** |

## 1. 展開物とバイナリ表

zip は **インストール後ツリー** (Inno Setup 5.5.7 の `unins000.exe` 同梱、`C__ProgramData_...` へ平坦化) ゆえ、インストーラ側の `[Run]`
動作 (例: 認証関連コンポーネントの導入) は観測不能。pkg は xar → 4 payload (AU/VST3/App+Uninstaller/Content)、`Distribution` は
`hostArchitectures="arm64"`、**VST2 も AAX も mac には無い**。Win/mac とも ProductVersion 1.0.9。

| ファイル | 形式 | arch | サイズ (B) | .text / 備考 |
|---|---|---|---|---|
| `Fresh Air.dll` (VST2 fn: `VSTPluginMain`/`main`) | PE32+ DLL | x64 | 250,368 | .text 154,928, pdata 751 関数, import: kernel32 96/user32 1/shell32 1/ole32 1 |
| `Fresh Air.vst3` | 同上 | x64 | 250,368 | **VST2 DLL とバイト同一** (md5 a5f0ddef…)。`GetPluginFactory`/`InitDll`/`ExitDll` を同 DLL に同居 |
| `Fresh Air.aaxplugin` | 同上 | x64 | 266,960 | 上と同一コード + 署名テーブル 16,592 B = WIN_CERTIFICATE 2 本 (①Kilohearts AB EV/Sectigo Authenticode 10,048 B、②**PACE 署名ブロック** 6,544 B @file+260,416 = "ILokCC"/PACE Anti-Piracy 証明書鎖 + `WrapInstaller`/`Eden wrapper shared library`/`PACE Anti-Piracy 2023`/`5.8.1` 属性。PE イメージ本体は VST2/VST3 とバイト単位で同一コード) |
| **`SlateCore.core_64`** | PE32+ DLL | x64 | **36,285,952** | .text 17,575,936 / .rdata 1.67MB / .data 0.71MB / **.rsrc 16.3MB** / pdata **25,063 エントリ** (CHAININFO 2,557 含む → 論理関数 22,506) / export 120 |
| `Fresh Air.component` (AU) | Mach-O universal | x86_64 76,720 + arm64 92,384 | 190,688 | シェル。`KHSAudioUnitFactory` |
| `Fresh Air.vst3` (mac) | 同上 | 同上 | 190,688 | シェル (AU とサイズ同) |
| **`SlateCore`** (mac) | Mach-O thin-in-fat | **arm64 のみ** | 19,142,496 | `__text` 11,898,564, **Eden ラッパ** (§4) |
| データ | — | — | — | 工場プリセット `.epf` 8 本 (各 1,244 B)、User Guide.pdf (12.3MB, 11 頁)、mac Resources (PNG 174 / vec 154 / fxp)、Win は同等物を core の `.rsrc` に埋込 (375 DATA: PNG 177 / TTF 5 / fxp 32 / vec・dump 171) |

- シェル 3 形式は Win で同一コード。シェルは `SlateCore` を `LoadLibrary` するだけ (失敗時文言: "Could not load SlateCore, which is required by Fresh Air")。
- core export 120 = 製品 37 ID × {`ACFRegisterPlugin_`/`GetPluginFactory_`/`VSTPluginMain_`} + 共通 9。製品 ID: `FrAr`(Fresh Air) ほか `ksgn`(Gain)・`ksfi`(Filter)・`kscp`(Compressor)・`kpeq`・`kdsp`(Disperser)・`kfat`(Faturator) 等 = **Kilohearts snapin の ID と一致**。
- `SnapinDsp<XxxDspModel>` テンプレートが 38 個 (全 snapin 同一 vtable 形 17 slot)。

## 2. フレームワーク判定

- JUCE RTTI なし。`freshair::{FreshAirDsp, FreshAirDspModel, FreshAirController, FreshAirEditor, UIFreshAirLarge, Meter, SlateKnob, ...}` が RTTI で列挙可 (`rtti_vtables.py`)。
- 共通基盤: Kilohearts SDK (`SnapinDsp<T>`, `Parameter<T>`, `SnapinRegistry`, `UI*`), Skia (SkSL/SkVM/Gr* を静的リンク), boost (shared_ptr/property_tree/multiprecision), Roboto/Rajdhani フォント, AAX SDK, VST SDK。
- **コアの 98%+ は UI/Skia/CRT/他 snapin**。Fresh Air に必要な DSP は一部 (§3)。

## 3. DSP コア規模 (実測)

方法: `.pdata` 関数境界 (CHAININFO チャンク併合) + capstone の direct-call closure (`closure.py`)。**間接 call は追わない → 下限**。Ghidra(範囲限定) 突合は §3.3。

### 3.1 FreshAirDsp (vtable 0x1810cab70, ctor 0x1803dee20 267 B)
- slot[12] 0x1803dfc10 (1,237 B) = 処理本体: `[this+0x90]+0xa080` の子 snapin リストを走査し、マクロ値から子へパラメタ設定 (`0x180c9d700(child, id=0x157/0x158/0x15a, value)`) → 各子で `0x180ca0d50(child, ctx)` を呼ぶ (逆アセンブルからの推定)。slot[4] 0x1803e0380 (516 B, SSE 32 命令), slot[13] 0x1803e01d0 (422 B)。
- チェーン構成は `FRAR/DUMP` resource (2,614 B) の snapin 名: `Filter, Compressor, Filter, Compressor, Gain, Compressor, Gain, Gain` (出現順) + 文字列 `Main`/`Trim`/`Both`/`Macro 6-8` (マクロ名)。

### 3.2 子 snapin の closure (direct call, `--stop 0x1803ded20`=vector 再配置)
| snapin | 関数数 | バイト | SSE 率 | 備考 |
|---|---|---|---|---|
| GainDsp (process 0x180afe090) | **process 単体 closure=4 関数/925 B**、vtable 全体 66 関数/17,318 B | | 19% | 平滑ランプ + 2ch ゲイン + 2 乗平均メータ |
| FilterDsp (0x180b6f050 他) | 119 | 39,329 | 32% | SSE 最多 |
| CompressorDsp (process 0x180775220 1,664 B) | 88 | 27,132 | 15% | |
| **和集合 (FreshAir+3 snapin)** | **237** | **67,689** | 20.5% | SSE-heavy (>=20 命令) 32 関数 = 33,038 B。最大: 0x181046890 (5,777 B)、0x18103fd60 (3,782 B, SSE 315 命令, 用途未同定) |

DSP closure に `LicenseManager` 取得関数 (0x180ca86e0) / `LicenseNotification*` は **含まれない** (§4)。IAT 呼出は CRT/例外/ヒープ/TLS 系のみ。

### 3.3 Ghidra 突合
- シェル DLL 全体 (full analysis): 関数 861 (pdata 751; 差は thunk/IAT), .text 155KB, 命令 40,033, XMM/YMM 操作命令 1,669 (4.2%)。DSP は無く CRT/SDK のみ。
- core DSP closure (範囲限定, `-noanalysis` import → 237 関数のみ disassemble): 237 関数 / 67,689 B (capstone と一致) / **命令 15,463** (capstone 15,988: padding・テーブル差 3%) / **XMM・YMM 操作命令 3,925 (25.4%)** / call 790。SSE 率は mnemonic 判定 (20.5%) より operand 判定 (25.4%) が高い。DSP 命令の約 1/4 が SIMD レジスタ関与。

## 4. コピープロテクション / 認証 (blocker 候補) — 事実整理

### 4.1 Windows x64 (正本候補)
| 検査 | 結果 |
|---|---|
| iLok/PACE/Eden/wraptool/dongle 文字列 (ASCII+UTF-16, shell×2/AAX/core/unins000.exe; 語境界一致) | **PE イメージ内 0 件** (shell・core・unins000.exe は全域 0)。AAX のみ署名テーブル第 2 エントリ (PACE 署名ブロック, file+260,416 以降) に 36 件: PACE Anti-Piracy CA/Master/Root・"ILokCC" 証明書鎖、`pace-ccjf1`、`WrapInstaller`/`Eden wrapper shared library`/`Copyright 2023, PACE Anti-Piracy`/`5.8.1`。= AAX が PACE 署名ツールを通した痕跡で、コードは未ラップ (VST2/VST3 と同一)。Pro Tools 側の署名検証強制は未検証 |
| セクション/エントロピー | 通常の MSVC 7 セクション。64KB 窓で >7.5 は `.rsrc` (PNG/TTF 圧縮データ) のみ。.text エントロピー 5.98 (shell 6.48) |
| コードの平文性 | pdata 先頭バイトが標準 MSVC prologue (先頭 3B: `48 89 5c`=5,977 / `40 55 48`=4,141 / `41 57 41`=2,657 …)。entry 0x100be34 は .text 内の CRT |
| ネットワーク | `ws2_32/wininet/winhttp/urlmon/crypt32/bcrypt/ncrypt` import **0** (core の import DLL は kernel32/user32/gdi32/comdlg32/advapi32(GetUserNameW のみ)/shell32/ole32 の 7 本)。文字列中の DLL 名にも無し。ローカル IPC 系 (`CreateMutexW`/`PeekNamedPipe`/`WaitNamedPipeA`) はあるがネットワーク API ではない。URL は slatedigital.com / kilohearts.com / zendesk の ShellExecute 用リンクのみ |
| HW 指紋 | `DeviceIoControl` 2 箇所は ioctl=0x900A8 (`FSCTL_GET_REPARSE_POINT`, シンボリックリンク解決)。`GetUserNameW` 1 (用途未確認)。`CoCreateGuid` 1。ボリューム S/N・MAC 取得 API 無し |
| Kilohearts ライセンス層 | `LicenseManager`/`LicenseNotification{Popup,Snapin,Trigger}`/`LicenseInfo<disperser,faturator>` が **コアに存在** (getter 0x180ca86e0 の直接呼出元 38 関数。確認した 1 例は 0x888 B スタックの構築系関数で、UI/エディタ側と推定)。文言: "You do not have a license for this plugin. **It will still work as part of this preset, but can not be edited.**" → 挙動は **編集不可の soft gate**。Disperser/Faturator は serial 画面あり。**Fresh Air の DSP closure 237 関数は license getter を呼ばない** (直接 call のみ確認) |
| 公式記述 | User Guide: "An iLok license is required... Fresh Air will not function without a valid license" (iLok Cloud は Internet 接続要) |
| **不一致** | 公式は iLok 必須だが、供給された Win バイナリに iLok 実装が見当たらない。可能性 (未検証): ①ライセンス確認は別コンポーネント/インストーラ側 ②この配布物では未ラップ ③AAX のみ PACE 署名で強制。**動的実行 (Windows/Wine) は未実施**のため、実行時挙動は未確認 |

### 4.2 macOS
- `SlateCore` (arm64): `__pbootstrap`(544 B)/`__POVERTEXT`/`__POVERDDATA` セクション、`__data` 4,096,961 B (エントロピー **8.000**)、文字列 `com.paceap.eden.wrapper/`・`handleWrapEvent`・`CantTutThis`・`NSCreateObjectFileImageFromMemory` (メモリロード bootstrap) = **PACE Eden ラッパ**。`__text` 自体は平文 (6.49) だが、暗号化された 4.1MB 領域が別に在る (中身・用途は Eden 実装依存で未解析)。
- シェル (AU/VST3) は Eden 無し (Apple 署名のみ)。pkg は arm64 ホスト限定。→ mac は lift 対象外 (RetDec x86_64 路線とも不整合)。

### 4.3 lift 可否への影響と迂回案 (技術的事実)
1. **Win x64 の DSP は認証モジュールと呼出経路上で分離**している: DSP は `SnapinDsp<T>` 派生クラスの仮想関数 (`process`) で、UI/Editor/Controller/LicenseManager とは別 vtable。ライセンス getter の呼出元は 38 関数で、DSP closure 内に無い。
2. したがって **lift 後に認証が DSP 実行を阻む箇所は静的には見つからない**。仮に存在した場合の整理: (a) `LoadLibrary` 経路 (シェル→core) は wasm では不要 (core を直接リンク)、(b) `FreshAirDsp`/子 snapin を C++ オブジェクトとして直接構築し process を呼ぶ駆動 (本試行 §5 と同方式) なら UI・ライセンス層を経由しない、(c) `LicenseManager` が必要になった場合は getter (0x180ca86e0) の stub 化で足りる構造 (soft gate、編集可否のみ)。
3. 要確認 (ユーザ依頼): Windows 実機/Windows Sandbox での動作観測 (iLok 無しで起動・音が通るか)。結果次第で §4.1 の不一致を確定できる。

## 5. lift→wasm 試行: `gain::GainDsp::process` (0x180afe090)

対象: Fresh Air の Gain snapin の process (446 B, SSE スカラ。2ch 乗算・係数ランプ・2 乗平均メータ)。closure 4 関数 (process + meter 更新 2 本 118 B ×2 + `std::vector` 再配置 243 B=stub)。

パイプライン (`lift/gain_e2e.sh`, 1 コマンド): RetDec `--select-ranges` (8 s) → `ref/ir_normalize.py`+`ref/ir5_patch.py` (m2/m5 の参照コピー) → **`lift/fa_fix_gain.py`** → `lift/fa_simd.c` (`ref/msimd6_core.h` 流用の `__asm_*` helper 12 種) → emcc 6.0.12 (`-O1 -ffp-contract=off -frounding-math`) → node。
参照は **実機 x86-64 機械語**: `lift/native_gain.c` が `SlateCore.core_64` を ImageBase 0x180000000 に MAP_FIXED 敷設し MS x64 ABI で直接実行 (m5 `native_fx` 方式。lift IR/wasm と非循環)。

結果: **`RESULT: BIT-EXACT 400/400 scenarios`** (mode 0/1・初回フラグ・Δ=0/微小/大・n=0..128・非正規数・負値・meter/vector push 有無。比較対象=L/R 出力+obj 状態+param ブロック+push された vector。NaN/Inf は意図的に除外 — x86 と wasm の NaN payload 差を切り分けるため)。

RetDec 出力の欠陥と修復 (対照実験 `lift/gain_ablate.sh` で各々が必須と実測):
| 類型 | 症状 | OTT 既知クラス | 無効化時 |
|---|---|---|---|
| **P1'** comisd 後の `jbe/jae` が **脱落** (0x180afe0fb-115: \|Δ\|<1e-15 で ramp 無効) | `__asm_comisd` 呼出のみ残り分岐無し | m6 [P1] の `no_branch` 型 (m6: comis 94 サイト中 66 が未対応) | **87/400 不一致** |
| **F7'** `mov rax,[rdx]` (L ch ポインタ) の load 脱落 | ctx 構造体を音声バッファとして書換 | m9 [F7] deref 落ち | 1 本目で wasm OOB trap |
| **F2'** callee への xmm1 (meter) 引数落ち | 2 callee が未初期 xmm1 を読む | m6/m8 [F2] SVF xmm1 dropped | **400/400 不一致** |

所見: ①1 関数 446 B で 3 類型が全て顕在 → **OTT 同様「脱落分岐」「脱落 load」「脱落 xmm 引数」が主要欠陥**。機械検出器 (機械語と IR の load/branch 数差分チェッカ) が汎用化の要。②`gen_msimd6.py` は RetDec の **per-binary サフィックス名 (`mulss__18` 等) をキー**にしており別バイナリへ流用不可 → base 名+宣言型キーへの改修が必要 (本試行は手書き 12 種)。③本関数はグローバル/vtable/例外を一切触らないため、OTT で難所だった data 敷設・VA remap は未検証。

## 6. blocker / リスク

| # | 内容 | 評価 |
|---|---|---|
| B1 | 認証: Win に実装検出なし。公式は iLok 必須と記載 (§4.1 不一致) | 静的には blocker 無し。**動的確認が必要** (ユーザ環境依頼 U1) |
| B2 | mac コアは Eden + arm64 のみ | 対象外 (Win x64 を正本) |
| B3 | C++ 実行時層: `shared_ptr`/boost/`std::vector`/TLS/SEH/ヒープ。DSP 直接駆動で多くは回避可だが `FreshAirDsp` ctor→子 snapin 構築→Parameter 登録は経由 | 中 (shim 4 本 + 例外無効化) |
| B4 | 間接 call 172 (未解決)・vtable 経由の子 snapin 呼出 → closure は下限。RTTI で vtable は確定可 | 中 (m6 `ott_vtables*.py` 手法) |
| B5 | lift 欠陥 3 類型が OTT と同率 → bit-exact 化は修復 pass 量産が前提 (OTT は M6→M10 で未完) | 中〜高。Gain/Compressor 先行で見積り更新 |
| B6 | UI (Skia 17MB, .rsrc PNG 177) は lift 対象外。素材は非再配布運用 (EULA は別途確認) | 低 (DSP のみ wasm 化、UI は別実装/shim) |

## 7. 下流チケット案

1. **FA-1 動的確認 (ユーザ/環境)**: Windows または Windows Sandbox で VST3 を FL/他ホストにロードし、iLok 無しで音が通るか・ライセンスダイアログの有無を観測 (§4.1 不一致の確定)。
2. **FA-2 Compressor/Gain/Filter snapin の DSP クロージャ lift**: `lift/gain_e2e.sh` を雛形に Compressor `process` (0x180775220, 1,664 B, 間接 call 1) → Filter → FreshAirDsp 制御層へ拡大。native 参照ハーネス (`native_gain.c`) をクラス単位に一般化。
3. **FA-3 共通 pass 昇格**: ①comis `no_branch` 分岐再構成 (CFG は機械語から) ②脱落 load/branch の機械検出器 ③xmm 引数 signature 復元 ④`gen_msimd` を base 名+型キー化。OTT (M6-M11) と共有。
4. **FA-4 FreshAirDsp 駆動ハーネス**: `FRAR/DUMP` のチェーン (Filter×2/Compressor×3/Gain×3) と param id (0x157..) 対応表を復元し、マクロ → 子パラメタの写像を確認、factory `.epf` 8 本 (1,244 B) で試験。
5. **FA-5 Kilohearts target との統合**: SlateCore 内の `ks*` 37 ID は Kilohearts snapin と同系統の可能性が高い (推定)。Kilohearts 解析担当と DSP closure/pass を共有 (同一実装なら 1 回の lift で両対象)。
6. **FA-6 UI**: `.rsrc` 内 `FRAR/*` PNG 95・vec を使う WebGL/Canvas UI は非同梱運用 (素材はユーザ手元で抽出) — M7 HUD 方針に合流。

## 8. 成果物

- `analyze.sh` / `fetch.sh` — 展開と全解析の 1 コマンド化
- `pe_inspect.py` (PE 構造・import・保護指標), `entropy_map.py`, `rtti_vtables.py` (MSVC x64 RTTI→vtable), `closure.py` (pdata+capstone closure、`--find-vref`), `disasm.py`
- `ghidra_scripts/{FaStats,FaScoped}.java`
- `lift/` — `gain_e2e.sh`, `gain_ablate.sh`, `fa_fix_gain.py`, `fa_simd.c`, `fa_stub.c`, `abl_extra.c`, `native_gain.c`, `gain_harness.mjs`, `gen_scen.py`
- `ref/` — m2/m5/m6 からの参照コピー (`ir_normalize.py`, `ir5_patch.py`, `gen_msimd6.py`, `msimd6_core.h`, `m6_simd_check.py`)。tools/m* は無改変。
- `work/` (ignore): 展開物・IR・wasm・各 JSON (RTTI/closure/callers)。

## 9. ユーザ依頼事項
- **U1**: 上記 FA-1 (Windows 実機/Sandbox での動作観測)。可能なら iLok 無し環境での挙動と、公式 Slate Digital インストーラ自体 (`Fresh Air.exe` 等) の提供 (本 zip は post-install ツリーで `[Run]` 動作が観測不能)。

## 10. 検収記録 (2026-10-10, 独立再計算)
- `analyze.sh` / `gain_e2e.sh` / `gain_ablate.sh`: work/ キャッシュ再利用・別 dir へ clean 再生成 (zip/pkg から, 29 s) のいずれも 400/400 bit-exact、ablation は P1 87/400・F7 trap(1/400 実行)・F2 400/400 不一致で一致。
- 独立再計算で一致: 2 ファイル sha256 同一 / 全サイズ / core pdata 25,063 エントリ / .text 17,575,936 / Gain process 0x180afe090 = 446 B / Compressor process 0x180775220 = 1,664 B / license getter 呼出元 38 (DSP closure 内 0) / 独立 BFS closure は 237 を包含 (--stop 0x1803ded20 配下 2 関数/246 B 差のみ)。
- 本節で §0・§1・§4.1 の PACE 記述 (AAX 署名ブロックの `Eden wrapper` 属性)・pdata 数の表記・closure の 16 B 仮定を訂正。
