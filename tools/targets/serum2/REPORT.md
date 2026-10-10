# Xfer Serum 2 v2.1.5 インストーラ解析 + lift 可否評価 (J serum2)

- 解析日: 2026-10-10 / 形式: `analysis/plugins/ott/REPORT.md` に準拠 / 再現: `bash tools/targets/serum2/scripts/run_all.sh` (展開済みなら約1.5分, 全出力は `out/`)
- 素材 (`~/ダウンロード`): `Install_Xfer_Serum2_2.1.5.exe` 1,313,084,056 B / `Xfer Serum2 v2.1.5.pkg` 1,325,553,209 B
- 大物 (展開物 2.8GB・Ghidra proj) は `work/` (`tools/targets/serum2/.gitignore` で除外)。実測以外は「推定」と明記。

## 0. 結論 (先出し)

| 項目 | 判定 |
|---|---|
| 構成 | **VST3 のみが実体** (Win x64 / mac universal)。VST2・32bit・WinARM64・CLAP なし。AU/AAX は VST3 を dlopen する薄いラッパ |
| フレームワーク | VST3 SDK 3.7.12 + **VSTGUI4 (Direct2D/DirectComposition)**。JUCE ではない。DSP は Xfer 独自 (osc 7種/フィルタ18クラス/FX 十数系) |
| コード規模 | Win .text **10.59 MB / 関数 33,791 (Ghidra 33,792)**。OTT (.text 1.97MB, DSP 20KB) の約5倍・DSP は推定 **1.5〜2.5 MB** (OTT の 75〜125 倍) |
| SIMD | **SSE2 スカラ主体**。packed 演算 9,483 命令/1,072 関数、AVX/FMA は 19+37 関数のみ (配置が CRT/libm 域, 推定)。AVX-512 無し |
| パッカー/難読化 | **無し** (標準セクション, 逆アセンブル網羅 100.00%, EP は標準 CRT, アンチデバッグ無し)。.rdata 4.4MB の高エントロピーは zlib 圧縮の事前計算 float テーブルと実証 |
| **認証** | **有り (blocker 候補)**: Xfer アカウントのブラウザ認可 + Machine ID + オフライン license ファイル。未認可は demo 版 (UI overlay)。ネット通信 (WININET/ソケット) を含む |
| lift 可否 | **DSP 部: 可 (難度 高)** / **GUI まで含む全体: 条件付き (難度 極高)** |
| 推定工数 | DSP ヘッドレス (ノート/MIDI→音声) で 8〜14 人月、GUI 込みで +6〜12 人月 (推定, §6) |
| 主 blocker | (B1) 認証/demo の強制点が DSP 内に有るか未特定 + 認証方針の判断 (B2) シンボル皆無 (B3) 規模 |

## 1. インストーラ構成

### 1.1 Windows (`Install_Xfer_Serum2_2.1.5.exe`)
- PE32 / **NSIS 3.10 Unicode / Deflate・非ソリッド** (manifest `Nullsoft Install System v3.10`, requireAdministrator, Authenticode 署名付き)。標準 `7z x` で全展開 (7,370 files / 1,413,375,641 B, `Everything is Ok`)。Image-Line 拡張なし。
- 展開物: `$COMMONFILES64/VST3/Serum2.vst3/` (本体 19.2MB + `Resources/moduleinfo.json` + `patch.zip` 49KB) と `.../Avid/Audio/Plug-Ins/Serum2.aaxplugin`、残りはユーザ領域に置かれるコンテンツ:

| ディレクトリ | files | bytes | 内容 |
|---|---:|---:|---|
| Multisamples | 4,118 | 939,260,634 | FLAC 3,977 + SFZ 140 |
| Tables | 289 | 173,372,140 | wavetable WAV (float32 mono 44.1k, 2048smp/frame, `clm ` chunk) |
| Samples | 856 | 203,826,813 | FLAC 661 / WAV 167 / AIF 20 |
| Impulses | 110 | 54,516,381 | IR FLAC |
| Skins | 691 | 17,356,117 | PNG 1x/2x 686 + TTF 3 (+`theme.json` 方式) |
| Presets | 627 | 3,909,388 | `.SerumPreset` 626 (`XferJson\0` ヘッダ + JSON) |
| Effect Chains/Clips/LFO/Arp/PZ Filter/Styles/System/Curves | 666 | 583,944 | `.serumfx(rack)`/`.xferclip`/`.xfershape`/`.xferarp`/`.xferfilterpz*` 等 |

- `patch.zip` は **データ差分のみ** (mac postinstall が content dir に unzip) (`DX.sfz` + panel PNG 2枚)。OTT の `rebyter.exe` 型のバイナリ後パッチは **無い**。

### 1.2 macOS (`Xfer Serum2 v2.1.5.pkg`)
- xar → 5 component pkg (gzip cpio): `VST3` (2.1.5) / `AU` (2.1.5) / `AAX` (**2.0.24**) / `Default-Skin` (1,383 files, 17.5MB) / `Presets` (payload 1.29GB)。`hostArchitectures=x86_64,arm64`, macOS ≥10.13, Developer ID: Steve Duda (42K3SNWUP7) 署名。
- postinstall は shell (VST3: 権限調整 + 既存コンテンツがあれば `patch.zip` を `/Library/Audio/Presets/Xfer Records/Serum 2 Presets` に展開 / Presets: chmod) と AU 用の署名付き Mach-O。**mac AAX のみ PACE Eden** (`__Pace_Eden.bundle`, 100,896 B)。VST3/AU に PACE なし。EULA (`Resources/License.txt`) §(c) は逆コンパイル・解読等を禁止、§(e) は無断共有・配布を禁止 (事実の転記のみ)。

## 2. プラグインバイナリ一覧

| ファイル | 形式 | arch | サイズ | コード部 | 備考 |
|---|---|---|---:|---|---|
| Win `Serum2.vst3` | VST3 | x64 PE32+ | 19,236,864 | .text 10,593,334 / .rdata 7,356,876 / .pdata 405,492 | export `GetPluginFactory/InitDll/ExitDll`, import 332/13DLL, lld-link, build 2026-07-07 |
| Win `Serum2.aaxplugin` | AAX ラッパ | x64 | 794,632 | .text 556,782 | `\VST3\Serum2.vst3` をロード, ACF export, 署名付 |
| mac `Serum2.vst3/.../Serum2` | VST3 | universal | 34,174,416 | x86_64 slice 17,603,536 (`__text` 10,029,520) / arm64 slice 16,545,232 | **strip 済** (export 3: `GetPluginFactory/bundleEntry/bundleExit`), 要 llvm-lipo |
| mac `Serum2.component` | AU ラッパ | universal | 462,064 | - | `aumu Xf2X` / `aumf Xf2Y`, manufacturer `XFER`, VST3 を動的ロード |
| mac `Serum2.aaxplugin` | AAX ラッパ | universal | 642,640 (+Eden 100,896) | - | AAX 2.0.24 |

- VST3 クラス (moduleinfo.json): `Serum 2` (Instrument|Synth) と `Serum 2 FX` (Fx) の各 Component + Controller の計 4 CID (processor/controller 分離型)。SDK 表記 `VST 3.7.12`。
- **推奨 lift 対象 = Win x64 `Serum2.vst3`**: MS x64 ABI・`.pdata` で関数境界が確定 (OTT と同条件)・RTTI/vtable 残存。mac は strip 済で情報量で劣る (arm64 slice は lifter 前提外)。
- Win .rsrc 126KB の entropy 7.99 は **zstd 圧縮の UI 記述 `DATA/SERUM2.UIDESC`** (125,234B → 2,093,822B の VSTGUI uidesc JSON, 123 template)。パッカーではない。

## 3. フレームワーク判定

**結論: VST3 SDK + VSTGUI4 + Xfer 独自エンジン + 多数の OSS 静的リンク (JUCE ではない — `juce` 文字列は HTTP UA の 1 箇所のみ)**。RTTI 型名 1,475 個 (非テンプレ 920, vtable 2,311 / クラス 1,099) による。

| 層 | 実体 | lift 方針 |
|---|---|---|
| ホスト IF | `Steinberg::Vst::{AudioEffect,EditController,Component,...}` (VST3 SDK 3.7.12), AAX wrapper | shim 側で最小 VST3 host を新規実装 (OSS ヘッダ) |
| GUI 基盤 | `VSTGUI::*` 〜 3,360 関数/692KB + Win32/D2D/DirectComposition platform 層 | upstream VSTGUI を wasm 再ビルド + canvas platform (lift しない) |
| Xfer GUI | `Serum*Controller / *Display / *TemplateParams / XferKnob...` 〜 13.8k 関数/3.8MB (address-locality 推定) | lift か置換 (§6) |
| DSP | `SerumDSP, Voice, Oscillator, WarpOscillator, {WT,MultiSample,Sample,Granular,Spectral,Noise,Sub}Osc(+State)`, `XferFilter*` 18 クラス, `Xfer{Bode,Chorus,Comp,Conv,Delay,DimE,Dist,EQ,Flanger,Hyper,Phaser,Reverb,FXSplit/3/MS}`, `LFO/SkEnv/Macro/ModMatrix/ChaosGraph`, `Arp/AlgoArp/PatternArp/ClipPlayer/MidiClip/MidiProcessor/PitchQuantizer` | **lift 対象の本体** |
| OSS (再ビルド候補) | nlohmann::json 3.12, SQLite (プリセット DB / `S1.SerumPresetTable` attach), zlib, zstd, libsndfile (メッセージ文字列) + libFLAC/Vorbis, muParser (`mu::Parser`=wavetable 数式), PFFFT + ZL(zita 系) convolver, libsfz, MTS-ESP client (`\MTS-ESP\LIBMTS.dll` 動的), VST3/AAX SDK | upstream から wasm 再ビルドし境界で接続 |

- DSP の構成要素 (文字列 enum より): osc 型 7 (`kOsc_WT..Sub`), WT warp 55 種 + Spectral warp 約 90 種 (FM/PD/AM/RM/Distortion/Filter 含む), distortion 18 種, unison stack/detune モード, reverb 5 種 (Plate/Hall/Vintage/Abyss/Space), mod: LFO×10 / Env×4 / Macro×8。
- 実装構造: processor/controller 分離のため **DSP は `SerumDSP` (AudioEffect 派生) に閉じ、GUI は IEditController 経由でパラメータ/メッセージのみ**。headless 駆動 (GUI 不生成) が可能な設計。
- FL Studio 固有挙動あり (`com.image-line.flstudio`, 設定 `Hide FX Plug-In from FL Studio`)。

## 4. DSP コアの規模見積

### 4.1 実測 (`out/census_summary.json`, `out/fp_bands.txt`, `out/layout_map.txt`)

| 指標 | 値 |
|---|---|
| .text / 関数 (pdata) / Ghidra 関数 | 10,593,334 B / 33,791 / 33,792 (`-noanalysis`+pdata 生成で 1 分) |
| 関数サイズ | 中央値 82B, p90 577B, p99 3,473B, 最大 115,265B (SQLite parser 系と推定), >4KB 235 本, >16KB 24 本 |
| 命令 / call | 2,515,362 / 159,199 (call_mem 29,999 = 仮想呼び出し/IAT) |
| SSE スカラ FP 演算 (ss/sd) | 51,535 命令 |
| SSE packed 演算 | 9,483 命令 / 1,072 関数。SSE4.1 47, SSSE3 4, SSE4.2 23, x87 4 |
| AVX/AVX2/FMA | ymm 564 命令/**19 関数**, FMA 331 命令/**37 関数**, VEX 2,630, zmm **0**。位置は .text 末尾 (0x1809a9c20..0x180a18f80, CRT/libm 域, **推定**) |
| cpuid | 12 命令 (関数 0x1801beb70 は leaf 7 の BMI2 検出で zstd 由来と推定 + CRT `__isa_available` 等。HWID 用ではない) |
| FP 演算 ≥30 の関数 | 508 本 / 1.26MB (関数バイトの 12.5%), ≥100: 123 本 / 579KB (5.7%) |

- FP 密度 (fp 演算/KB) の山 (256KB 窓): `0x180340000` 30.0, `0x1803c0000` 29.2, `0x1802c0000/0x180300000` 18.3〜18.4, `0x1808c0000` 18.9, `0x180880000` 17.0, `0x180080000` 11.6。それ以外は GUI/ライブラリで 0〜9。
- 領域の同定 (RTTI vtable 位置): フィルタ `XferFilter*` の仮想関数は 0x18008b270〜0x1805ef20c に分散 (Wild 13.1KB 0x180302020 付近, CombFlangePhase 13.0KB 0x1802fd890 付近。最大 FP 関数 0x1802f7510 = 22,386B/スカラ FP 2,141 命令は直接呼出元無し=間接呼出), osc 0x1803c83b0〜0x1803e9d00, voice core 0x18007e700〜0x1800861f3, conv/fft 0x1805ea750〜0x1805ecb22。
- **DSP 規模推定 = FP 山の合計 約 1.5〜2.5 MB (.text の 15〜25%)**。OTT (DSP 20KB 未満, 関数 166 本) の **75〜125 倍**。vtable 起点の静的 closure は間接呼び出しで切れ下限 (89 root → 886 関数/449KB) しか出ず、真の closure は lift 時の動的トレースで確定する必要あり。
- 静的 `.rdata` 4.4MB (0x180afc000〜) = **zlib 圧縮の事前計算 float32 テーブル** (+0x1c56d0 の `78 DA` を inflate → float32 ≥3.19MB を確認。唯一の参照元 0x18087da10 が実行時に inflate (展開長 0x317b30 = 3,242,800 B = **6,700×484B** と厳密一致) し per-entry に double→float 変換)。データなので lift 不要・zlib は upstream 再ビルド。
- 浮動小数点: UCRT libm (FMA3 dispatch 版を含む) を静的リンク → wasm では emscripten libm に置換 = **ulp 差は不可避** (OTT M10 の exp/log chain と同型)。bit-exact は目標にせず許容誤差判定 (dB 単位) が現実的。

## 5. コピープロテクション / 認証の判定 (blocker 候補)

### 5.1 バイナリ保護 (パッカー・難読化・アンチデバッグ): **無し** (`out/protect_indicators.txt`, `out/pe_survey.txt`)

| 観点 | 結果 |
|---|---|
| セクション | `.text .rdata .data .pdata .fptable .retplne .tls _RDATA .rsrc .reloc` (標準, VMProtect/Themida/UPX/Enigma 等の名前・文字列なし) |
| エントロピー | .text 6.43 (通常), .rdata 7.45 (zlib テーブル), .rsrc 7.99 (zstd uidesc), .data 5.27 |
| EP / TLS | EP 0x9ca5f0 は .text 内の標準 `_DllMainCRTStartup`。TLS callback 1 本 (0x1809a50f8, CRT) |
| 逆アセンブル網羅 | pdata 関数 10,129,995/10,130,044 B = **100.00%**、オーバレイ無し |
| アンチデバッグ | `IsDebuggerPresent` は CRT/UEF の 2 箇所のみ。`rdtsc` 命令 0、`int 2d` 無し (`int` 7 = fastfail)、NtQuery 系 import 無し。`wine_get_version` 検出あり (ネット モジュール内 0x1801bc2b0) |
| 難読化 | `jmp reg` 1,137 (jump table), `call reg` 1,058, cmov 10,595 = 通常コンパイラ出力水準。制御フロー平坦化の兆候なし |
| 署名 | Win VST3 本体は Authenticode 無し (AAX/インストーラは有り)。mac は Developer ID 署名 (`_CodeSignature` 有) |
| ビルド | lld-link (`LLD PDB`), PDB パス `C:\actions-runner\_work\Serum2\Serum2\win\x64\Release\...Serum2.pdb`, **シンボル/PDB 不在** |

### 5.2 ライセンス認証: **有り (機能的な blocker 候補)**
外部事実 (Xfer サポート記事 *Machine Authorization Problems*): Serum 2 は **DAW 内エディタで xferrecords.com アカウントにログインして認可** (Serum 1 のシリアルは無効)、台数制限あり、オフラインは **Machine ID を表示 → my_account でライセンスファイルを生成 → 本体に読み込ませる**。Splice Rent-to-Own は Splice デスクトップアプリ経由で検証。

バイナリ側の実測 (`out/xref_scan.txt`, `work/ghidra_light/decomp_targets.c`):

| 証拠 | 内容 |
|---|---|
| uidesc テンプレート | `SpliceRTO` (`Click "Authorize" to log into your Xfer account.` / `Authorize` ボタン), `SpliceExpired` (`Refresh your License with Splice`), `SpliceMaxLimit` (`contact Xfer support`), `overlay_demo_version(_fx)(_mini)` bitmap。文字列 `Locate License` (0x18089ea80 が使用) = **オフライン license ファイル選択** |
| ネット | WININET: `InternetOpenA` ラッパ 0x1801bb8d0 (非同期 GET: 0x1801bc630/0x1801bca00, 呼出元 0x1801bb2b0 が UA 文字列 `"juce"` を渡す)。`ShellExecuteExA` 0x1801bc300 (ブラウザ起動, 直接の呼出元 10 関数: Download Update / Update Available / ヘルプ/サポートリンク等)。WS2_32: ローカル ソケットサーバ 0x180429290 (socket/bind/listen) + 0x18042dc20 (WSAPoll/accept/recv/send) — 呼出元 0x18042a950 は `ShellExecuteExA` も呼ぶ → **「ブラウザ認可 + ローカル callback サーバ」型の認可フローと推定** |
| 暗号 | RFC 8032 の `SigEd25519 no Ed25519 collisions` 文字列 + Ed25519 位数 L (0x180aa1ee0) + SHA-512 (K 表 0x180a711d0, 圧縮関数 0x180432700) → **署名検証用 Ed25519 が静的内蔵** (license ファイル検証と推定)。CryptoAPI MD5 は汎用 hex ヘルパ 0x1801bee30 |
| Machine ID | HWID 系 API の import は**皆無** (GetVolumeInformation/IP Helper/WMI/SetupAPI/MachineGuid 参照なし)。`RegOpenKeyExA` は `Software\XferRecords\Serum2InstallerPrefs` のみ, `DeviceIoControl 0x900A4` はジャンクション作成 (FSCTL_SET_REPARSE_POINT), `CoCreateGuid`+`GetTickCount64` (0x18001e2c0) は乱数 seed 風。**Machine ID の生成元は静的には未特定** (prefs 保存 GUID か mac の IOKit `IOPlatformUUID` 相当の可能性。要追跡) |
| demo | `demoVersion` は state JSON の key (0x18004fad0 / 0x1800c2b50 が読み書き) — 保存物に demo フラグを載せるだけで、**音声経路での強制 (無音化・ノイズ挿入等) の有無は未確認** |
| 平文文字列 | 認可処理の文字列 (エンドポイント path, license 形式, エラー文) は Win/mac とも平文で見当たらない (URL は `https://xferrecords.com/` 接頭辞のみ)。文字列分割か短文字列の組立と推定 |

**lift 可否への影響**: (1) 認可は GUI/コントローラ側の機能 (ネット・ブラウザ・ファイルダイアログ) で、方針「外部通信を要する機能は対象外」により wasm 版では実行不能 → 認可状態を**外部から注入**するか demo 動作で走らせるかの判断が必須。(2) **認可状態が DSP (`SerumDSP::process`) 内で参照されるか未特定** — 参照するなら demo では音が制限され得て、参照値の供給点が lift の必須論点。(3) 保護機構が無いため静的解析・lift 自体の障壁にはならない。(4) EULA §(c)/(e) と製品ライセンスの扱いは**ユーザ判断事項** (助言ではなく事実の提示)。

## 6. lift 可否・推定工数・必要 shim 面

### 6.1 判定

| 範囲 | 可否 | 難度 | 推定工数 (人月, **推定**) | 根拠 |
|---|---|---|---:|---|
| 最小 host (VST3 GetPluginFactory→processor 生成→setupProcessing→process) の駆動 PoC | 可 | 中 | 1〜2 | VST3 は COM 風 vtable で境界明確・パッカー無し・OTT で ctor 駆動実績 |
| OSS ライブラリ境界の同定と置換 (sqlite/zlib/zstd/sndfile/json/muparser/pffft) | 可 | 中〜高 | 1.5〜3 | シンボル皆無 → RTTI/文字列/定数 (SHA-512 K, CRC32 表等) による署名照合が必要 |
| **DSP closure lift** (voice+osc+filter+FX+mod, ヘッドレス音声出力) | 可 | **高** | **6〜10** | DSP 1.5〜2.5MB は OTT の 75〜125 倍。OTT は 166 関数でも M6〜M10 の 5 段を要し bit-exact 未達 → 規模増に対しパイプライン既存分で圧縮しても桁違い |
| 数値検証 (ネイティブ参照との dB 誤差判定) | 要 参照音源 | 中 | 1〜2 | 実機参照が必要 (§8 ユーザ依頼)。libm 差で ulp 不一致 |
| データ層 (wavetable/sample/IR 1.4GB の fetch+FS, FLAC 復号) | 可 | 中 | 1〜2 | 全て外部ファイル (バイナリ非埋め込み)。要オンデマンド配信 |
| **GUI** (VSTGUI+D2D → canvas) | 条件付き | **極高** | +6〜12 | Xfer ビュー群 3.8MB/約 1.4 万関数。(a) 全 lift (b) upstream VSTGUI + uidesc(2MB JSON)+PNG で再構築し Xfer 固有ビューのみ lift/置換 |
| 認可 (account/Machine ID/license) | **対象外 (方針)** | - | - | 外部通信・認証のため。注入/回避方針はユーザ判断 |
| **合計 (DSP ヘッドレス)** | 可 | 高 | **8〜14** | GUI 込みは +6〜12 |

- 想定 wasm サイズ (推定): DSP closure のみで 4〜10MB、全 lift で 25〜35MB。
- ビルド系: clang-cl 産 (lld-link) のため MSVC 固有イディオムは少ないが、C++ EH は x64 SEH (`.pdata`/unwind) 経由。OTT 同様に unwind 無視/例外経路の置換が必要。

### 6.2 必要 shim 面 (Win import 332 本の分類)

| 領域 | import (本数) | 使途 | DSP のみ | 全体 |
|---|---|---|---|---|
| メモリ | Heap* 8, Global* 5, VirtualProtect(CRT), Local/Free | CRT/malloc | 要 (M4 heap shim 流用) | 要 |
| スレッド/同期 | CreateThread/ExitThread, Tls* 4, Fls* 4, SRW lock/CondVar 8, CriticalSection 7, CreateMutexW, Sleep, WaitFor*, **ThreadpoolWork 3**, **IOCP 2**, SList 3 | PPL/std::async (preset DB 走査・pack build), UI/param 同期 | 一部 (SRW/TLS/FLS) | 要 (pthread/MT) |
| ファイル IO | CreateFileA/W, Read/Write, SetFilePointer*, GetFileSizeEx, FindFirst/Next*, Move/Delete/Remove, SHCreateDirectoryExW, SHFileOperationW, **CreateFileMapping/MapViewOfFile**, **LockFile(Ex)**, **ReadDirectoryChangesW**, GetTempPath, GetFullPathName 他 約 40 | SQLite (mmap/lock), サンプル/テーブル ストリーミング, prefs JSON, プリセットフォルダ監視 | 要 (FS shim + HTTP range fetch) | 要 |
| 時刻 | QueryPerformanceCounter/Frequency, GetTickCount(64), GetSystemTime*, TimeZone, locale 系 (CRT) | CPU メータ, 乱数 seed | 要 | 要 |
| レジストリ | RegOpenKeyExA/RegQueryValueExW/RegCloseKey (InstallerPrefs のみ) | データフォルダ位置 | 固定値で代替 | 同左 |
| 暗号 | CryptAcquireContextA/CreateHash/HashData/GetHashParam (MD5) | hex ハッシュ | 小 (自前 MD5) | 小 |
| ネット | WININET 6, WS2_32 13 | 更新確認・認可フロー | **不要 (fail-fast)** | 対象外 |
| GUI | USER32 77, GDI32 12, ole32 12, SHELL32 10, SHLWAPI 3, d3d11/dwmapi/d2d1/DWrite(+dcomp 動的) | VSTGUI Win32 platform | 不要 | **canvas platform 新規実装** |
| SIMD | SSE2 (xmm) 全般, packed 9.5k 命令, AVX/FMA は CRT/libm のみ | DSP 演算 | **要 SIMD helper** (OTT: 156 種) | 同左 |
| VST3 host | IPluginFactory/IComponent/IAudioProcessor/IEditController/IConnectionPoint/IMessage | プラグイン境界 | 最小 host 新規 | 同左 + IPlugView |

## 7. blocker と保留事項

| ID | 内容 | 深刻度 | 次の一手 |
|---|---|---|---|
| B1 | 認可状態が DSP 内で参照されるか未特定 / Machine ID 生成元未特定 / 認可は外部通信必須 | **高** | Ghidra 全解析 (`GHIDRA=1`) + `SerumDSP::process` 到達グラフで auth/demo フラグの読み出し点を列挙 → 下流 T2 |
| B2 | Win/mac ともシンボル皆無 (PDB パスのみ)。OSS 境界/クラス名は RTTI・定数照合頼み | 中 | ライブラリ署名 DB 作成 (T3) |
| B3 | DSP closure 規模 (推定 1.5〜2.5MB) が既存 lift 実績 (OTT 166 関数/FLEngine mm 677 関数) を桁超え | 高 | 段階 lift: osc 1 種 → filter 1 種 → voice → FX (T4〜) |
| B4 | libm 差 (FMA3 dispatch 版 UCRT) による ulp 不一致 | 低〜中 | dB 許容誤差判定 |
| B5 | 1.4GB コンテンツのブラウザ配信 | 中 | 遅延 fetch + IndexedDB |
| 非 blocker | パッカー/VMProtect/アンチデバッグ: 無し、PACE は mac AAX のみ | - | - |

## 8. ユーザ依頼事項
1. **認可方針の決定**: wasm 版で (a) demo のまま動作させる (b) 認可済み状態を外部注入する (c) Serum 2 を対象から外す のいずれにするか。EULA §(c)(e) (§1.2) の扱いも含めユーザ判断。
2. (可能なら) **ネイティブ参照音源**: 認可済みの Windows/mac 環境で、固定プリセット・固定 MIDI をオフライン書き出しした WAV (Linux 側に wine 無し)。数値検証 (T5) に必須。
3. 認可済みライセンスが有る場合のみ: Machine ID 生成元の特定には当該環境での挙動観測 (ファイル/レジストリアクセス) が有効。

## 9. 下流チケット案

| # | チケット | 概要 | 目安 |
|---|---|---|---|
| T1 | serum2-host-poc | 最小 VST3 host 新規 + `GetPluginFactory`→`SerumDSP` 生成→`process` 空回し (GUI/認可なし, OSS ヘッダ利用) | 1〜2 人月 |
| T2 | serum2-auth-trace | Ghidra 全解析で認可/demo フラグの定義・参照点・DSP 側の強制有無・Machine ID 生成元を特定し報告 (外部通信コードは触れない) | 2〜3 週 |
| T3 | serum2-oss-boundary | sqlite/zlib/zstd/sndfile/FLAC/json/muparser/pffft/libsfz の関数署名 DB と境界 cut 表 | 1.5〜3 人月 |
| T4 | serum2-lift-osc-filter | DSP closure 段階 lift: WT osc → `XferFilterSVF/Ladder` → voice (SIMD helper 追加) | 3〜5 人月 |
| T5 | serum2-numeric-ref | 参照音源 (§8-2) + dB 誤差判定ハーネス | 1〜2 人月 |
| T6 | serum2-content-stream | wavetable/sample/IR の HTTP range + FS shim + FLAC 復号 | 1〜2 人月 |
| T7 | serum2-gui-strategy | VSTGUI upstream + canvas platform の PoC と Xfer ビュー lift/置換の方針決定 | 2〜3 週 (調査) |

## 10. 再現・成果物

```
bash tools/targets/serum2/scripts/run_all.sh        # 展開(7z/xar/cpio/lipo) → 構造・保護・census → Ghidra light(1分)
GHIDRA=1 bash tools/targets/serum2/scripts/run_all.sh   # +Ghidra 全自動解析 (CPU 重い・未実施)
```
- `scripts/`: `pe_survey.py` `protect_indicators.py` `crypto_scan.py` `rtti_classes.py` `text_census.py` `dsp_closure.py` `layout_map.py` `fp_bands.py` `xref_scan.py` `disasm_fn.py` `callers.py` `blob_refs.py` `ghidra_light.sh` `ghidra_win64.sh` / `ghidra/SerumLight.java` `SerumSurvey.java` `targets_auth.txt`
- `out/` (80KB): 上記出力。`work/` (gitignore): 展開物・Ghidra proj・`ghidra_light/decomp_targets.c` (20 関数の decompile)。
- 限界: ① Ghidra 全自動解析 (`ghidra_win64.sh`) は環境再起動で 3 回中断し未完 (light pass のみ実測)。② 静的 closure/FP 山は粗い推定。③ mac 版の個別解析は構造確認止まり。
