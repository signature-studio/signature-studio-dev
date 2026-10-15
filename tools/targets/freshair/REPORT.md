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
| ネットワーク | `ws2_32/wininet/winhttp/urlmon/crypt32/bcrypt/ncrypt` import **0** (core の import DLL は kernel32/user32/gdi32/comdlg32/advapi32(GetUserNameW のみ)/shell32/ole32 の 7 本)。文字列中の DLL 名にも無し。ローカル IPC 系 (`CreateMutexW`/`PeekNamedPipe`/`WaitNamedPipeA`) はあるがネットワーク API ではない。URL は slatedigital.com / slatedigital.zendesk.com (UTF-16) の ShellExecute 用リンクのみ (kilohearts.com の URL 文字列は未検出) |
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
| B6 | UI (Skia 17MB, .rsrc PNG 177) は lift 対象外。素材は非再配布運用 (EULA は別途確認) | 低 (DSP のみ wasm 化、UI は別実装/shim)。**方針決定済み: `docs/DECISIONS.md` D7 (2026-10-13, #53)** |

## 7. 下流チケット案

1. **FA-1 動的確認 (ユーザ/環境)**: Windows または Windows Sandbox で VST3 を FL/他ホストにロードし、iLok 無しで音が通るか・ライセンスダイアログの有無を観測 (§4.1 不一致の確定)。
2. **FA-2 Compressor/Gain/Filter snapin の DSP クロージャ lift**: `lift/gain_e2e.sh` を雛形に Compressor `process` (0x180775220, 1,664 B, 間接 call 1) → Filter → FreshAirDsp 制御層へ拡大。native 参照ハーネス (`native_gain.c`) をクラス単位に一般化。
3. **FA-3 共通 pass 昇格**: ①comis `no_branch` 分岐再構成 (CFG は機械語から) ②脱落 load/branch の機械検出器 ③xmm 引数 signature 復元 ④`gen_msimd` を base 名+型キー化。OTT (M6-M11) と共有。
4. **FA-4 FreshAirDsp 駆動ハーネス**: `FRAR/DUMP` のチェーン (Filter×2/Compressor×3/Gain×3) と param id (0x157..) 対応表を復元し、マクロ → 子パラメタの写像を確認、factory `.epf` 8 本 (1,244 B) で試験。
5. **FA-5 Kilohearts target との統合** (#52): 機械語比較を実施済み → **§11**。snapin の process 実装は同一ビルドではなく、共有できるのは共通基盤 (数学 lib / CRT / allocator) のみ。
6. **FA-6 UI** (#53): `.rsrc` 内 `FRAR/*` PNG 95・vec を使う WebGL/Canvas UI は非同梱運用 (素材はユーザ手元で抽出) — M7 HUD 方針に合流。**方針は `docs/DECISIONS.md` D7 で決定済み**。素材抽出・描画の実装は HUD 側 (#10) で行い、Fresh Air 固有の UI 実装チケットは起票しない。

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

## 11. FA-5: SlateCore ⇄ HeartCore の snapin 実装同一性 (#52, 機械語比較)

- 再現: `bash tools/targets/freshair/ks_identity.sh [outdir]` (素材 = `work-liftlib-targets` の SlateCore / HeartCore。下の 3 スクリプトを直列実行)。比較は **正規化後の完全一致** のみ (類似度は参考)。
- 最大値の基準 (11-1 の「最大 Compressor 0.436・Gain 0.475」の除外理由と全 37 件の最大): 付録 [REPORT_APPENDIX_FA5.md](REPORT_APPENDIX_FA5.md) §A1。
- 正規化 (`ks_identity.py` の `Pe.norm`): **E** = call/jmp 先・`[rip+disp]`・イメージ内絶対アドレス即値だけを抽象化 (構造体 offset・即値・レジスタは残す) / **R** = E から数値をすべて落とす (レジスタ名は残す) / **M** = mnemonic 列のみ。類似度 = difflib ratio。関数境界は .pdata (CHAININFO 連続チャンク併合)。

### 11-1. 結果 (実測)

| 比較 | 結果 |
|---|---|
| 共通 `*Dsp` クラス (RTTI) | **37** (SlateCore 38 = 37 + `FreshAirDsp`)。vtable は 35 クラスが KH 20 slot / SC 17 slot、2 クラスが 21/18・21/17 |
| process 相当 slot (KH slot 14 を SC 全 slot と総当たり) の完全一致 | E **0/37**・R **0/37**・M **1/37** (TapeStop = 9 B の stub で自明)。M 類似度の中央値 0.243、最大は Compressor 0.436・Gain 0.475 (実体のある関数のみ) |
| Gain process (KH 0x1804b0380 609 B/137 命令 ⇄ SC 0x180afe090 446 B/86 命令) | E 類似度 0.036 / M 類似度 0.475。this の state offset が別 (KH `+0x64..0x78`、SC `+0x9c..0xd0`)、param 取得経路も別 (`ctx+0x3188` ⇄ `this+0x90`→`+0x9dc4`)。構造体配置が違う (同一ソースかどうかは機械語からは判定できない) |
| 全 .pdata 関数 (≥12 命令) の E ハッシュ照合 | KH 87,227 関数 / SC 18,027 関数 → 共通ハッシュ **829**・SC 側 **1,679 関数 / 218,520 B** (SC の ≥12 命令関数合計 17,203,480 B の 1.3%) |
| Fresh Air DSP closure (FreshAirDsp + Gain + Filter + Compressor 全 slot からの direct call 到達, 177 関数 / 68,389 B) のうち KH と E 一致 | **63 関数 / 21,740 B (31.8%)**。一致する側は powf `0x18103fd60`⇄KH `0x180fc3640` (3,782 B)・pow `0x181046890`⇄`0x180fc4590` (5,777 B)・FMA 数学 lib・allocator/CRT 等の **共通基盤**。process 本体は 0 本 |
| 上記 63 関数のうち KH 側 VA が `snapins.json` の lift VA に出現 | 49 本 (VA の 9 桁 hex 文字列一致の粗い判定。複数 KH 関数が同一ハッシュになる SC 関数が 7 本ある) |
| 上記 63 関数の `.rdata` 定数 (rip 参照先先頭 16 B) | 参照なし 35 / 一致 8 / **不一致 20**。コードが一致しても参照先定数が違う関数がある (内訳は下の 11-3) |

実測: 検証起点 HEAD `47c07803` (`git worktree` clean 展開、`work-liftlib-targets` 展開後) で `ks_identity.sh` を 2 回実行: 42.2 s / 40.8 s (EXIT=0、nproc=4、load 1 分値 0.63 → 1.29 / 1.10 → 1.29)。2 回の `ident.json` / `census.json` / `share.json` / `rdata_class.json` は byte 一致 (決定的)。`ks_rdata_class.py` 0.22 s (EXIT=0、value 17 / ptr 3)。

### 11-2. 結論と制約

- **1 回の lift で両対象に効く範囲 = 共通基盤のみ** (SC DSP closure の 31.8% / 21,740 B)。snapin ごとの process は SlateCore と HeartCore で別ビルドの機械語で、既存 KH lift (`tools/targets/kilohearts/snapins/`) の IR/wasm を SlateCore に流用することはできない (Gain は SC 側も別途 lift 済み = §5)。
- ID の一致 (§1) は **製品 ID・クラス名・17/20 slot の vtable 形が同系統** であることまで。実装同一性は本節で「機械語レベルでは同一でない」と確定。
- **Gain の差分実行 (①)**: 同一入力 200 case で L/R/state が bit 一致 **127/200** (不一致は全て ramp 継続経路 `first=0`、差は 1 ulp 級)。bit 一致しないことを確定したが、原因 (丸め順か入力差か) は未特定。詳細は付録 §A3。
- **未検証**: ① 残り (Gain 以外の snapin は [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) で判定基準と振り分けまで。差分が実行できるのは Gain だけで、Compressor・Filter は #3506・#3507 へ、残りは #52 の残件。ramp 式の丸め順の切り分けは付録 §A3-4・§A3-5)。② `.rdata` 不一致 20 本の分類は 11-3 (一部は未確定)。③ 直接 call のみ追跡 (間接 call は辿らない = closure は下限)。

### 11-3. `.rdata` 不一致 20 関数の分類 (`ks_rdata_class.py`)

分類結果: `value` 17 / `ptr` 3 / `count`・`order` 0。`value` 17 件は語単位の切り分け (`ks_rdata_value.py`、[REPORT_APPENDIX_FA5_VALUE.md](REPORT_APPENDIX_FA5_VALUE.md) §A5) で **配置差では説明できない** (`.rdata` 内を指す RVA 候補の指す 16 B が KH の `.rdata` に存在しない語がある)。RVA 候補 (32 bit 値) が RVA か定数かは未判定のため、この結論は参照先の内容差の下限であり、「意味が違う」の根拠ではない。詳細・未確定事項は付録 [REPORT_APPENDIX_FA5.md](REPORT_APPENDIX_FA5.md) §A2、[REPORT_APPENDIX_FA5_VALUE.md](REPORT_APPENDIX_FA5_VALUE.md) §A5。

## 12. FA-9: 制御層 setter 経路 (0x180c9d700 → 0x180ca1480 → 0x180da6c00) の実経路測定 (#665, Refs #648 #452)

既知類型との関係: **該当なし** (DEFECTS D1〜D17 の lift 欠陥は本測定で未観測。近縁の D12 は「出力のみ比較で register 不可視」だが、本件は **harness の map 空による 0x157 経路の未到達** で別件)。

### 12-0. 結論 (先出し)

- **受入 1 (C+0x2d0/C+0x328 と C+0x318 木の実測): 未達。** harness 構築値のみ実測。C+0x2d0 == C+0x328 (72/72 呼出)、C+0x318 木は空 (map 検索 found=0 が 72/72)、静的分岐 (map 非経由) は 0 回。**実 snapin 構築 (FLE boot 連鎖) からの実値は未取得。**
- **受入 2 (実経路の実行・ID 解決先・Filter 出力変化): 部分。** 解決先は子リスト index 0 (Filter#1) のみ (120/120 呼出で k=0)。値は **1 周目 (各 scenario の先頭 3 呼出) のみ** 0x157/0x158 = pow(x,0.62)、0x15a = 0.0 が epf 8/8 と一致 (FA-4 再現)。**2・3 周目は未検証** (観測のみ・判定外): 予測 (1 周目と同じ式) との一致は 0x157 12/16、0x158 14/16、0x15a=0.0 は 8/16。0x15a は 2・3 周目 (16 呼出) のうち 8 件が非零。予測式は未確定。**0x180da6c00 の呼出は 0 回** のため Filter 出力への到達は未測定。摂動 (初期 Mid Air を 0.9 に強制) でも L/R 出力は 40/40 呼出で不変 = 本 harness は 0x157 の効果を観測できない。native/wasm bit-exact は空 map 経路 (setter を含む) で 15/15。
- **受入 3 (DUMP 接続表経由で Filter ID 1〜4 に届くか): 未達。** DUMP の Filter は chain idx 0 と 2 の 2 個。宛先は常に idx 0 のため、idx 2 (Filter#2) へはこの経路で届かない。ID 1〜4 との対応は未解決。
- **受入 4 (Compressor/Gain の同 ID 意味): 未達。** 即値 0x157/0x158/0x15a を持つ pdata 関数は 53 件 (imul と rsp 操作を除外後、偽陽性を含む)。Compressor/Filter/Gain の process 閉包 (78/109/62 関数) との交差は 0、wrapper ctor 閉包 (39/40/39 関数) との交差も 0。同 ID の意味は未解決。
- 注: 既存の `REPORT_FA7.md` / `REPORT_FA8.md` は repo に存在しない (Issue 本文の参照先)。FA-7/8 の値は再取得せず、本節は FA-4 (`lift2/REPORT.md` §12) の再現から始めた。

### 12-1. 静的読み (逆アセンブル, 未実機確認)

- `0x180ca1480(C, out, key)`: key 無し/keycnt=0 → `{C+0x2b0, C+0x360}`。`C+0x2d0 == C+0x328` → map 検索 (`C+0x318` の木, `+0xa8`)。不一致かつ keycnt=1 かつ key0=0 → 静的返却 `{C+0x308, C+0x470}` (map を引かない)。不一致で keycnt≠1 → ゼロ。不一致で key0≠0 → map 検索。
- `0x180c9d700(child, id, value, key)`: `out[0]` から `[·+0x10]` の object に対し vtable slot +0x50(id) → +0x18 → +8(value)、続いて `0x180da6c00(out[1], id, idx, 2)`。`0x180da6c00` は r9=2 のとき `0x180f9e540` の結果と `this+0xe8` を比べ、不一致の分岐で id×16 の表 (`this+0x30`) へ (連番, idx) を書き `this+0x48` を増やす (静的読み。一致時は vtable 経路 `[this]+0x50` へ)。

### 12-2. 実測 (clean checkout で run_fa9 5 回・run_chainmap 3 回。数値は全実行で同一, 全て `lift2/` の再現スクリプト)

| 項目 | 分母 | 結果 | 再現 |
|---|---|---|---|
| FA-4 再現: child 呼出と .epf 突合 (判定は 1 周目の 3 呼出) | epf 8 本 | 一致 (結果の正本は `lift2/REPORT.md` §11。本節は同じ再実行で周回別の観測を取る) | `run_chainmap.sh` |
| 2・3 周目の値 (観測のみ・判定外): 0x157=pow(mid,.62) / 0x158=pow(high,.62) / 0x15a=0.0 に一致 | 各 16 呼出 | 12 / 14 / 8。周回間で値が変わるのは 0x157 が 8 本中 3 本 (S900・S901・S904)、0x158 が 1 本 (S904)。S903 は 3 周とも不変 (maptrace の数え上げ) | `run_chainmap.sh` (`fa4_chain_map.py` の観測行) |
| 0x180ca1480 呼出 (setter 内) | 8 シナリオ (S900–S907) | 72 (9/シナリオ) | `run_fa9.sh` |
| 分岐: C+0x2d0 == C+0x328 (map 経路) | 72 | 72 (静的分岐 0) | 同 |
| map 検索 found (C+0x318 木, head が自身 = 空) | 72 | 0 | 同 |
| 0x180da6c00 呼出 | 8 | 0 | 同 |
| ERR (base, native) | 8 | 0 | 同 |
| 宛先 child index (MAPTRACE 全件, S900–S907 + structured) | 120 | 全て 0 | `run_chainmap.sh` |
| 即値 0x157/0x158/0x15a を持つ pdata 関数 | pdata 25,063 | 53 (≥100KB 38 / <100KB 15) | `fa9_imm_scan.py` |
| 閉包交差 (process 閉包 78/109/62、ctor 閉包 39/40/39。root は下記注) | 53 | 6 閉包すべて 0 | `fa9_closure_cross.py` |
| native vs wasm bit-exact (epf 8 + structured 2 + random 5, fma0/1) | 15 | 判定ゲートとして 15/15 (結果の正本は `lift2/REPORT.md` §11) | `run_ctrl.sh 2 5` |

閉包の再現条件: `closure.py <core> <root>` を **`--stop` 無し**で実行 (`fa9_closure_cross.py` が同条件で計算)。process root = Compressor 0x180775220 (78 関数) / Filter 0x180b6f050 (109) / Gain 0x180afe090 (62)。ctor root = 各 wrapper ctor を単独で指定 (Compressor 0x180774cd0 → 39 / Filter 0x180b6ed50 → 40 / Gain 0x180afde00 → 39)。§3.2 の「Gain process 単体 = 4 関数」は `--stop 0x1803ded20` 付き (同 option で Compressor 51 / Filter 109 / Gain 4)。

### 12-3. ネガティブコントロール (native のみ, wasm 側は未実施)

| 摂動 | 期待 | 結果 |
|---|---|---|
| (b) `FA_ALT9=1`: C+0x328 を C+0x2d0 と不一致にし静的分岐を強制 | 後段が ERR になり、プローブが分岐を検出できる | 8/8 ERR、8/8 path=static。SIGSEGV (`sig=11 rip=0x180c9d74c addr=0x50`): setter が `[C+0x318]` (controller) の vtable を読み、0 のまま `call [0+0x50]`。詳細は `run_fa9.sh` が `FA_DBG=1` で `work/ctrl/fa9_alt.err` に保存し、ゲート出力に 1 行表示 (FA_DBG 無しでは出ない) |
| (c) 各シナリオ初回呼出の M+0x9dc4 (初期 Mid Air) を 0.9 に強制 (元値はシナリオごとに異なる。`fa9_check.py mkpert` が先頭 W ブロックの 1 件だけを書換え、他の L/R サンプル等は不変) | 状態ダンプに届く (盲点検査の有効性) | 状態ダンプ差分 395 トークン (子 8 体の P+0x9dc4〜0x9f60 窓、M 窓、ほか 1 窓)。**L/R 出力差分 0/40 呼出** → 0x157 の変化は L/R に届かない (map 空で setter が no-op) |

### 12-4. 検証範囲 / 範囲外

- 範囲内: 制御層 slot[12] → 0x180c9d700 → 0x180ca1480 (空 map 経路) の native 実機機械語と wasm mlift の bit-exact (15/15)、epf 8 本の ID 写像 (FA-4)、静的分岐の強制 (ネガコン)。
- 範囲外: 実 snapin 構築 (FLE boot 連鎖) からの C+0x2d0/C+0x328/C+0x318 の値、非空 map による 0x180da6c00 到達、Filter#2 (DUMP idx 2)、DUMP ID 1〜4 との対応、Compressor/Gain 側の ID の意味。wasm 側のネガコンは未実施。
- 判定ゲート: `run_fa9.sh` は (a) base の 72/0/0 と (b) ERR 8/8 と (c) 摂動が状態に届くこと、さらに `run_ctrl.sh` の 15/15 を全て満たすときのみ PASS (不合格時は非 0)。L/R 差分は観測のみで判定に使わない。

### 12-5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 snapin 構築 (FLE boot 連鎖) からの C+0x2d0/C+0x328/C+0x318 の実値 (受入 1) | 空 map が実機と同じかが不明 | #253 / #672 (boot 連鎖・open) と #702 (FA-9b で追跡)。#227 は closed のため参照しない |
| 非空 map の構築 (controller 木 + {ptr, ctrl} 値 + 子 object の vtable slot +0x50/+0x18/+8) で 0x180da6c00 を到達させ、Filter 出力の native/wasm 比較 (受入 2 後半)。静的読み (map 探索・ノード配置・入口条件) は `REPORT_APPENDIX_FA16.md` §1〜3。FA_NODE1=1 時の setter addr=0x50 系の失敗形の読みは `REPORT_APPENDIX_FA22.md` (部分達成、#1578) | 0x157/0x158 の効果が未測定 | #702 (FA-9b) / #1182 (FA-16) / #1791・#1789 (FA-25・FA-24) |
| Filter#2 (DUMP idx 2) に macro ID が届く経路と、ID 1〜4 との対応 (受入 3) | Filter#2 のパラメタ連動が不明 | #702 |
| 0x157/0x158/0x15a の Compressor/Gain 側の意味 (受入 4)。候補 53 件のうち ≥100KB の 38 件は pdata 境界かテーブルの疑いで未検証 | 子 ID 写像の全体像 | #648 (PM コメント済み) |
| 2・3 周目の 0x157/0x158/0x15a の値の式 (12-2 の観測行) | 1 周目以外の ID 写像が未確定 | #665 (親へ注記。子は PM 起票待ち) |
| `run_chainmap.sh` の native_ctrl_trace は S2004 の後で trace が途切れる (終了コード 0・stderr に診断なし・原因未確認。MAPTRACE は S2004 で終端)。スクリプトは native の終了コードを見ず、判定は epf S900–S907 のみ | 検証範囲の明示 (判定自体は影響なし) | #665 (本 PR で注記) |
| REPORT_FA7.md / REPORT_FA8.md が repo に無い | 参照先不在 | #648 |

### 12-6. 再現・環境・実測時間

- 検証起点 commit: 本 commit (`fix(freshair)` の直後の HEAD。本節の数値はこの版で実測)。
- 手順 (clean checkout): `git worktree add --detach <dir> d572059` → `work/` が無い状態から、`plugins-freshair` の zip と `work-liftlib-targets` のみ展開 (epf と SlateCore はここから得る) → `pip install --user capstone==5.0.7 pefile==2024.8.26` → `bash lift2/run_fa9.sh` (初回は内部で `build_ctrl.sh` を実行) → `bash lift2/run_chainmap.sh` → `python3 lift2/fa9_closure_cross.py <core>`。
- 実測 (逐次実行, 所要は `date` 差, load は `/proc/loadavg` の 1 分値を各 run 直前に採取):
  - `run_fa9.sh`: 初回 (build_ctrl 込み) 36.93 s (n=1)、build 後 **3.79–4.41 s (n=3)**。全 3 回 GATE PASS。
  - `run_chainmap.sh`: **2.28–2.97 s (n=3)**。全 3 回 OK 8/8。
  - load は各 run の直後に `/proc/loadavg` の 1 分値を採取 (2.41〜2.65)。runner の負荷が高い状態での値。
  - `fa9_closure_cross.py`: 59.1 s (n=1, 参考)。閉包 6 本 + 候補列挙。
- 変更点 (コード, `f5483d5` → `d572059`): `lift2/env.sh` が `TMPDIR` を作成。`build_ctrl.sh` は clang 失敗で非 0 終了し成果物を確認。`run_fa9.sh`・`run_chainmap.sh` は `native_ctrl`・`ctrl_full.cjs`・`iat_slots.txt` が揃わなければ再 build (従来は `iat_slots.txt` だけで skip)。`run_ctrl.sh` は成果物が無ければ exit 2 (従来は 0 行の MISMATCH)。`run_fa9.sh` の (b) は `FA_DBG=1`。`fa4_chain_map.py` は 2・3 周目の観測行を追加。`fa9_closure_cross.py` を新規追加。`native/native_ctrl.c` の `FA_PROBE9`/`FA_ALT9` は `f5483d5` から変更なし。摂動 (c) は初回呼出の M+0x9dc4 だけを書き換える (全行の `1 9dc4` 置換をやめた。差分は 1 トークン/シナリオ、差分トークン数 395)。
