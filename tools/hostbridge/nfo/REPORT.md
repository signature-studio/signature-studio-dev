# REPORT — H9 / CAB-98: Plugin database (`.nfo` / `.fst`) 書式解読 + 合成 DB 生成器

最終更新 2026-10-10 / 担当 subagent (hostbridge-nfo) / 再現: `bash tools/hostbridge/nfo/nfo_e2e.sh` (exit 0 = 全 PASS, 約 2 s) + `node tools/hostbridge/nfo/analysis/real_ini_check.mjs` (実機照合 21 checks) / 仕様: `FORMAT.md`

## 0. 結論 (先出し)

- **判定: 静的解析のみで書式を確定し、パーサ/ライタ/合成 DB 生成器を実装した。** その後 §10/§11 で実機突合まで完了 (CAB-215/CAB-219)。**実例**: 抽出物 (mac pkg + win installer) に `Installed\` 配下の v2 `.nfo` は **0 件**。`.nfo` は 831 件 (全て ASCII, 25,203 B) あり、`ps_*` を含むのは native の `Plugin.nfo` 141 件 (`ps_vendorname` のみ) だけ (§1)。
- **書式 (FLEngine を逆アセンブルして確定; PluginManager.exe は同一 unit を内包)**: `.nfo` = CRLF の `key=value` 行 (キー大文字小文字非区別、`'` 行はコメント)。`fileversion=2` は `ps_name / ps_presetfilename / ps_files=N` + `ps_file_*_<i>` (i=0 起点)。必須は実質 `ps_files` と `ps_file_plugclass_i` のみ。`.fst` = FLhd(0x30, 2ch, ppq48) + `199 "11.5.5"`, `28`, `201 "Fruity Wrapper"`, `212`, `203 名前`, `213 wrapper chunk`。
- **round-trip 実測**: 同梱 `.nfo` 831/831 byte-exact、FL 11.5.5 書込の `.fst` 26/26 を自作コンテナ writer で byte-exact 再構成 (§3)。v2 `.nfo` は writer→reader の自己整合 (生成 49/49 受理) に加え、**実機 `.Plugins.ini` 406/406 セクションを writer が再現** (§11)。
- **wasm 向け**: OTT / Fresh Air / Kilohearts(46) / Serum 2(2 class) の DB エントリを 49 件・100 ファイル (`.Plugins.ini` 込み) で合成できる (`specs/wasm_plugins.json` + Kilohearts index)。Massive X は素材なしでエントリ未生成 (§5)。
- **CAB-218 (§12)**: VST3 `ps_file_filename` = **LoadLibraryW で消費するモジュールファイルパス** (規則確定, Serum 2 を内部バイナリ形に修正) / KH VST2 magic は product_index id と**実機 45/45 一致** / VerifiedIDs VST2 id = 符号付き 10 進 (64/64, ≥2³¹ は推定)。
- **コミット**: `feat(hostbridge): plugin database nfo/fst format and synthetic generator` → 以後 §10〜§12 分は git log 参照 (tools/hostbridge/nfo のみ)。

## 1. 実例の探索結果 (実測)

| 探索対象 | 件数 | 備考 |
|---|---|---|
| `**/*.nfo` (mac `…/Resources/FL`) | **831** (25,203 B) | `Bitmap=` 558 / `ps_vendorname` 141 (うち `ps_Vendorname` 5, `ps_dummy64bit` 2) / `Tip=` 95 / `Description` 35 / `MenuIconIndex` 35 / `IconIndex` 23 / `ColIndex` 13 / `HeightOfs`・`SortGroup` 各 5 / `Visible` 2 / `SortBy` 1 |
| うち `Plugins\Fruity\{Effects,Generators}\*\Plugin.nfo` | 141 (Effects 90 + Generators 51) | 全て `ps_vendorname=Image-Line` (native 用、DB 外ファイル。FORMAT §5) |
| `Data\System\Plugin databases` | `.nfo` 433 / `.fst` 429 / `.png` 424 | ブラウザ木用。`.nfo` は汎用 info (`ps_*` 0)。`.fst` は FL 同梱 native の既定状態 |
| うち FL 11.5.5 が書いた plugin-state `.fst` | 26 | 構造 `199 28 201 212 213` = FL の DB 書込と同一 (§3) |
| `Fruity Wrapper` を内部名とする DB `.fst` | **0** | Wrapper 配下 (VST/CLAP) の `.fst` 実例は無い → chunk は decompile + `tools/flp` の `parseWrapperData` 突合 |
| win installer (25,166 ブロック) の ASCII 平文 `ps_file_plugclass` | 0 | `ps_*` の UTF-16 文字列は PE 内 (FLEngine / PluginManager) のみ |

→ **`Installed\` の v2 `.nfo/.fst` は出荷されない** (PluginManager が実機で生成)。必要な実機ファイルは §7。

## 2. 解読の方法と根拠

- FLEngine (`block00031_PE.bin`, 既存 Ghidra project をコピー) の `ps_*` 文字列 xref から **読込 `fle:0x910cd0` / INI 版 `0x911e10` / 書込 `0x911940`+`0x913f40` / INI 書込 `0x912d10` / native `0xabe970`** を特定。値の getter/setter (`0x913be0` 等 20 関数)、キー接尾辞 (`"_"+i`)、plugclass の表 (名称 `0x8ef860`、フォルダ `0x8f0300`、slot `0x8f6990`)、探索 (`0x915750`/`0x916710`)、書込 (`0xabba70`/`0xaba880`/`0xab8ae0`/`0xaac300`/`0xa9eff0`) を読んだ。PluginManager.exe も `ps_*` を使う同形関数 (`FUN_0077ac80` 等) を内包。
- 定数表 (class mask、GUID 位置表、arch 名、212 テーブル) は `analysis/dump_tables.py` が PE から機械抽出 (`evidence/fle_tables.txt`)。再生成 `analysis/reproduce.sh` (約 1 分)。突合: ① 同梱 `.fst` 26 件で `199/28/201/212/213` 構造と FLhd(0x30,2,48) を byte 単位で再現。② `tools/flp` の独立パーサ (`parseFlp` / `parseWrapperData`) が生成 `.fst` と wrapper chunk を受理 (kind 8, 記録 id 2/50/51|52/54/55/56)。③ native `Plugin.nfo` 141 件を `ps_vendorname` (大小混在) / `ps_dummy64bit` で読了。

## 3. 確定した書式の要点 (確度付き; 詳細は FORMAT.md)

| 項目 | 内容 | 確度 |
|---|---|---|
| 文法 | `key=value`、CRLF 書込・混在読込可、キー大文字小文字非区別・先勝ち、`'` コメント、値 trim なし、整数は `StrToIntDef` | 確 |
| キー | `fileversion=2`, `ps_name`, `ps_presetfilename` (`%FLPluginDBPath%`), `ps_files`, `ps_file_{name,filename(%FLPath%),plugclass,type,bitsize,arch,magic,guid,date,size,scanflags,vendorname,category,idstring}_<i>`, `ps_compatibility_<i>` | 確 |
| 書込規則 | 既定値は省略 (plugclass −1 / type 0 / magic 0 / null GUID / date,size 0 / scanflags 0 / 空文字)。`bitsize` は常に出力。順序は FORMAT §3 の表どおり | 確 |
| 必須 | `ps_files≥1` と各ファイルの `ps_file_plugclass`。plugclass 欠落 or slot 無し (DX / class 6 / 32bit の AU・CLAP) は黙って捨てられ、0 件ならエントリ破棄 | 確 (reader 模型で再現) |
| plugclass | 0 VST fx / 1 DX fx / 2 FL fx / 3 FL gen / 4 VST gen / 5 DX gen / 7 VST3 fx / 8 VST3 gen / 9,10 AU / 11,12 CLAP。フォルダ `VST\ VST3\ AudioUnit\ CLAP\` | 確 |
| magic / guid | magic = 符号付き int32 の 10 進。guid = `{XXXXXXXX-…}` 38 文字大文字、バイト↔文字は Windows GUID メモリ配置 | 確 (文字写像) / VST3 の CID → bytes は raw 順と推定 |
| 配置 | `Presets\Plugin database\Installed\{Effects\|Generators}\{VST\|VST3\|AudioUnit\|CLAP}\<無害化名>.{nfo,fst}`。拡張子は小文字、無害化は `\/\|?*"<>:` → `-` | 確 (仮想 FS は case-insensitive 必須) |
| `.fst` | FLhd(0x30, 2ch, ppq48)・events `199 "11.5.5"`, `28=1`, `201 Fruity Wrapper`, `212` (52B: u32@8=2, u16@16=0x10 if gen), `203 name`, `213`=u32(8)+記録列 | 確 (構造) / 推 (flag 意味) |
| 補助 | `VerifiedIDs.nfo` (`<VST\|VST3\|CLAP>:<GUID>:<64>=<rel .NFO>`)、`.Plugins.ini` (INI キャッシュ; 無ければ FL が NFO を全走査して再生成) | 確 (形) / 推 (VST2 の id 表現) / 未 (ini の文字コード) |
| 読む時点 | 起動時の一覧構築 (`.Plugins.ini` → NFO 全読み)、プロジェクト読込の plugin 解決 (VerifiedIDs → ID nfo → 名前検索)、新規インスタンス (`ps_presetfilename` の fst) | 確 (呼出元の実測) |

実測値 (`work/metrics.json`): 同梱 `.nfo` round-trip **831/831**、`Plugin.nfo` 141/141 読了 (vendor `Image-Line` 141)、FL 11.5.5 `.fst` **26/26 byte-exact 再構成**、生成 49 entry を reader 模型が **49/49 受理** (rejectedFiles 0)、テスト **29/29 PASS**、e2e 全体 1.7 s。

## 4. 成果物 (tools/hostbridge/nfo/)

| パス | 内容 |
|---|---|
| `FORMAT.md` | 書式仕様 (確度付き)。REPORT は本書 |
| `src/valuefile.ts` | 無損失 value file パーサ/ライタ (EOL/BOM 保存)、`StrToIntDef` 互換、文字コード補助 |
| `src/format.ts` | plugclass / slot / scanflags / GUID↔text / VST2 疑似 GUID / 名前無害化 / パストークン / DelimitedText |
| `src/entry.ts` | `PluginEntry` モデル、**reader (fle:0x910cd0/0x911e10 準拠: v1 と v2)**、**writer (0x911940/0x913f40 準拠)**、native `Plugin.nfo` |
| `src/fst.ts` | wrapper chunk (`0xa9eff0`) と `.fst` (`0xaac300`/`0xaac1e0`) の生成、`assembleFst` コンテナ writer |
| `src/generate.ts` | plugin 一覧 → `Installed/**` の `.nfo/.fst/VerifiedIDs.nfo` (決定的出力) |
| `cli/gen.ts` `cli/metrics.ts` | 生成 CLI / 実測値出力。`specs/wasm_plugins.json` が wasm 用 plugin 表 |
| `test/` | node:test 29 件 (コーパス往復・FL 準拠規則・生成物の独立パーサ受理・決定性) |
| `analysis/` `evidence/` | Ghidra 抽出 (`reproduce.sh`)、定数表、decompile 抜粋 (約 130 KB, FL 実バイナリ由来) |
| `nfo_e2e.sh` | 1 コマンド再現: typecheck → ブラウザ安全性 grep → tests → 実測 → 生成 |

使い方: `node cli/gen.ts specs/wasm_plugins.json <out> [--kilohearts <product_index.json>]`。API は `src/index.ts` (ブラウザ互換: `node:` import なし、tools/flp の `src` と同方針)。

## 5. wasm 版の plugin エントリ設計 (ABI.md / HOSTBRIDGE.md §2.10–2.11 と整合)

方針: PluginManager は移植せず、**ビルド時または初回起動時に `generateDb()` で `Presets/Plugin database/` を仮想 FS に書く**。FL 側コードは無改変 (FL 自身の reader が読む)。仮想 FS は大文字小文字非区別。native Fruity 141 は DB 非経由 (`Plugins\Fruity\…\<name>_x64.dll` + `Plugin.nfo` の存在走査, `fle:0xabf130`) → H4 の PE スタブ側で担保。

| plugin | 形式 | class | 同定子 | `ps_file_filename` (仮想パス) | 備考 |
|---|---|---|---|---|---|
| OTT | VST2 x64 | 0 (fx) | magic `XfTT` = 1483101268 (hostbridge PoC 実測の uniqueID) | `C:\Program Files\Common Files\VST2\Xfer Records\OTT_x64.dll` | chunk: record 51 / 54 (`OTT_x64`) / 55 / 56 |
| Fresh Air | VST2 x64 | 0 | magic `FrAr` (targets/freshair の製品 ID) | `…\VST2\Kilohearts\Fresh Air_x64.dll` | 250 KB shell → `SlateCore.core_64` はモジュール表側で入れ子 LoadLibrary |
| Kilohearts ×46 | VST2 x64 | 0 | magic = 4 文字 product id (`ksgn` 等) **仮定** | `…\VST2\Kilohearts\kHs <Name>.dll` | 46 shell → `HeartCore.core_64` 共有。DB 名は `fileName` ("kHs Gain")。plugin 自己申告名は未確認 |
| Serum 2 | VST3 のみ | 8 (gen) | CID `56534558667350736572756D20320000` | `…\VST3\Serum2.vst3` | VST3 facade (H5) 前提 |
| Serum 2 FX | VST3 | 7 (fx) | CID `56534558667351736572756D20322066` | 同上 | 同一バイナリ・別 class → 別エントリ (`Effects\VST3\`) |
| Massive X | VST3 (想定) | 8 | **未取得** | — | `~/ダウンロード` に素材なし。moduleinfo.json の CID が得られ次第 `specs` に 1 行追加 (class 8, vst3) |

- `ps_file_scanflags_0=1`、`ps_file_bitsize_0=64`、`ps_file_type` は実機準拠の 1 (fx) / 2 (gen) (§11.3)。32bit は載せない (bridge 不使用: HOSTBRIDGE §1.6)。
- Wrapper→VST2 の `hint` (entry export 名) は標準名 (`VSTPluginMain`) なら不要。Kilohearts は stub 消去 (alias) で標準名に揃う。hint を DB に持たせる必要が出た場合の記録先は未特定 (§6-3)。
- 生成量: 49 entry / **100 ファイル** / 69,342 B (決定的, `.Plugins.ini` 込み §11.3)。IDB プリロードに載せても無視できる大きさ。

## 6. 未解決とブロッカー

1. **Installed の実機 v2 サンプルが無く、`.nfo`/`.fst` は「FL コードが受理する形」を静的に再構成したもの**。reader 模型は decompile 準拠だが、FL 本体の実行による検証は未了 (lift 済み FL で `0x910cd0` を動かす検証は H4 以降)。
2. Fruity Wrapper が生成 `.fst` (record 2/50/51/54/55/56 のみ) を読んで VST2/VST3 を起動できるかは未検証 (Wrapper の chunk reader は未解析; record 1/30/31/32 は Wrapper が補うと推定)。`tools/flp` の独立パーサ受理までは確認。
3. Wrapper の VST2 `hint` (`TVSTPlugin` 第 6 引数) の供給元レコード (id 57 候補) は未特定。標準名エクスポートでは不要。
4. ~~`.Plugins.ini` の文字コード、`ps_file_date` の単位、VerifiedIDs の VST2 `id` 表現~~ → **CAB-219 で解決 (§11)**: ini = UTF-8+BOM / date = TDateTime double bits / VST2 id = magic 10 進 (キー順 `<fmt>:<bits>:<id>`)。VST3 `ps_file_filename` の**選択規則は CAB-218 で確定 (§12, FORMAT §9-3)**。
5. VST3 CID → `ps_file_guid` の対応は §11.4 で実機確定 (テキスト = CID 文字列、bytes = Windows 配置)。Wrapper が factory へ渡す順序の実行検証は H5 で。
6. ~~Massive X 素材なし / KH VST2 magic 未確定~~ → **KH magic は CAB-218 で実測確定 (§12.2)**。Massive X は `~/ダウンロード/Native Instruments Massive X v1.7.1.exe` を確認済み — 未解析 (§12.4)。

## 7. ユーザ依頼事項 (任意・あれば更に確実化)

Windows 実機から `Installed\` 配下の **実機 v2 `.nfo` / `.fst` 単体ファイル** (VST2 1 組 + VST3 1 組, 特に OTT VST2 側) と Massive X (NI) の VST3 CID (`moduleinfo.json`) があると `writeEntry`/`buildWrapperFst` との byte 直比較と spec 追加が即完了する (`.Plugins.ini`/`VerifiedIDs.nfo`/OTT.fst は入手済み §10/§11; `~/ダウンロード` の同名 3 ファイルは evidence と byte 一致を確認済み §12.4)。

## 8. 次タスク提案 (下流チケット案)

| # | チケット | 要点 |
|---|---|---|
| H4' (P0) | DB 組込み | `generateDb()` (`.nfo`/`.fst`/`.Plugins.ini`/VerifiedIDs 生成) を仮想 FS 初期化 (起動時/ビルド時) に結線し、lift 済み FL の `0x910cd0` / `0xaba430` に生成 DB を読ませて受理を実行検証 |
| H10 (P1) | Wrapper chunk reader の解析 | 生成 `.fst` の record 群を Wrapper が受理するか (hint レコード・record 1/30–32 の要否) を `fw:` 側で確定 |
| H11 (P2) | VST3 バンドルのパス規則 | ~~選択規則の突合~~ / ~~H9a / H12~~ — **完了 (CAB-215 §10 / CAB-219 §11 / CAB-218 §12)**。残は §7 の任意提供のみ |

## 9. 規約遵守メモ

- 書込は `tools/hostbridge/nfo/` のみ (`work/` は gitignore: Ghidra project コピー約 280 MB・PluginManager/FLEngine 抽出)。`tools/flp` / `tools/targets` / `tools/m2` / `tools/hostbridge` 既存ファイルは読取のみ。README/MILESTONES/HANDOFF 無改変。`evidence/` は FL 実バイナリの decompile 抜粋 (約 130 KB)・定数表・実機キャッシュファイル 2 件 (`evidence/real_machine/` — ユーザ提供の Plugin database ファイル) を含む (EULA は事実整理のみ: 実バイナリ本体・lift 済み wasm はコミットしない)。外部通信・認証系は不使用。

## 10. 追記 (CAB-215 部分実施, 2026-10-10): 実機 OTT.fst 照合

**結論**: ユーザ実機の `Installed\Effects\VST3\OTT.fst` (323 B) を取得し、CAB-98 の全模型 (コンテナ writer / wrapper chunk 解析 / 生成器) が **byte 級で一致**することを確認した (下表, 全 PASS)。`.fst` 書式の実機裏取りとしては完了。ただし **実機 v2 `.nfo` / `VerifiedIDs.nfo` / `.Plugins.ini` は実機に存在せず未入手** → 本チケット本来の主眼である `writeEntry` との `.nfo` byte 比較は未了で、**部分実施**として扱う (§7 の依頼は継続)。再現: `node tools/hostbridge/nfo/analysis/real_fst_check.mjs` (exit 0 = 全 PASS, 約 0.2 s)。サンプル本体・全ダンプは `evidence/real_machine/`。

### 10.1 検証結果 (実測, 全 PASS)

① `assembleFst` が実機 `.fst` を **byte 一致 323/323** で再現。② tools/flp `parseFlp`→`writeFlp` lossless、`parseWrapperData` が 213 を受理。③ イベント列 = FLhd(0x30,2ch,ppq48) / 199 "11.5.5" / 28=1 / 201 "Fruity Wrapper" / 212 (u32@8=2, u16@16=0=fx) / 203 "OTT" / 213 (191 B) — 既存モデル (FORMAT §8) と差分 0。④ 213 = u32 8 + 記録 6 本 `[2,50,52,54,55,56]`、191/191 B 厳密消費。⑤ `buildWrapperFst` (逆抽出 spec) が byte 一致、generateDb (OTT VST3 仮想 spec) の `.fst` は実機ファイルと **sha256 まで一致** (`f6942876…`)、生成 `.nfo` も reader 模型が受理 (dropped 無し / rejectedFiles 0 / slot 5)。→ **FL 実機が DB に置いた `.fst` を自前生成器が byte 一致で再現した初の実証**。

### 10.2 wrapper chunk 213 の内容 (実測) — VST3 CID を確認

| 記録 | 値 (実測) |
|---|---|
| 2 | flags = **0x507D08** = 0x407908 \| 0x400 (64bit のみ) \| 0x100000 — record 2 flags の**実機初観測** (src/fst.ts の「64bit 単一ファイル」予測と完全一致) |
| 50 / 51 | plugclass = **7 (VST3 fx)** / **無し** (class 7 では 51 を出さない分岐を実機で初裏取り) |
| **52** | **VST3 CID = `5854535654666F547474000000000000`** (raw 16 B = ASCII `XTSVTfoTtt`+NUL×6)。GUID text 形 `{56535458-6654-546F-7474-000000000000}` (Windows GUID メモリ配置) — record 52 が raw TUID 16 B を持つ設計を実機確認。**CAB-46 (Massive X CID) の突合基準および VST3 hosting の TUID としてそのまま使用可** |
| 54 / 55 / 56 | `OTT` (拡張子なし basename) / `C:\Program Files\Common Files\VST3\OTT.vst3` (**モジュールファイル形** — §10.3, §12.1) / `Xfer Records` |

CID 取扱の注意: 公開インデックスではこの CID 値を独立突合できなかった (実機 `.fst` が第一級情報源)。Xfer 公表によると OTT VST3 は v1.33 で導入され 1.33/1.34 には ID 不整合バグがあり 1.35 で修正 — CID は版依存しうるため本値は「ユーザ環境に導入された版の実測」として扱う。

### 10.3 VST3 path 規則の実機証拠 (H11 / CAB-218 へ) → **§12 で確定**

- 実機配置 `Installed\Effects\VST3\<name>.fst` = class 7 → `Effects\VST3` (FAMILY_DIR 規則) と一致。record 55 は `ps_file_filename` と同値。実機の DB root は `%USERPROFILE%\Documents\Image-Line\FL Studio\…` (generate.ts の `DEFAULT_DB_PATH` = Public Documents は `%FLPluginDBPath%` 圧縮用の option 値であり書式への影響なし)。

### 10.4 「.nfo 無し .fst」の意味 (CAB-216 generateDb の優先順位へ)

- **事実**: 実機に `OTT.fst` のみ存在し `OTT.nfo` / `VerifiedIDs.nfo` / `.Plugins.ini` は無かった → `Installed\` 配下に `.fst` 単体が実在しうる実例。**解釈 [推]**: picker 一覧構築 (`fle:0xaba430`) は `.Plugins.ini`/`Installed\**\*.NFO` 全読みが源泉ゆえ `.nfo` 無しの OTT は picker に載らず、`.fst` 単体で効くのはブラウザ木表示とダブルクリック新規インスタンス生成まで。→ generateDb は `.nfo` + `.fst` 両方書く現行方針を維持が正 (実機 FL での picker 表示は未検証)。

### 10.5 `specs/wasm_plugins.json` OTT エントリとの差分

実機の登録は **VST3**、spec は **VST2** — 書式の誤りではなく**登録形式の違い** (plugclass 7 vs 0、record 52 CID vs 51 magic、path `…\VST3\OTT.vst3` vs `…\VST2\Xfer Records\OTT_x64.dll`、54 `OTT` vs `OTT_x64`)。wasm 版 OTT は VST2 lift (m6〜m10) ゆえ spec を VST2 のまま維持。OTT.vst3 を hosting する段になったら spec に 1 行追加 (`format: vst3`, `guid: 5854535654666F547474000000000000`, path は §12.1 規則) すれば**実機と byte 一致の `.fst` が得られることを本検証で実証済み**。

### 10.6 成果物と未入手

- 追加: `evidence/real_machine/OTT.fst` (323 B, sha256 `f694287667fe486d5b9849f162a6712e198c610ebb61b0746af241b93044b3ff`)、`evidence/real_machine/ott_fst_dump.json` (全イベント + 記録列 + CID + 検証結果 + 仮想 `.nfo` 全文)、`analysis/real_fst_check.mjs`。既存成果物は無改変。**未入手 (§7 継続)**: 実機 v2 `.nfo`/`.fst` 単体 (本文は `.Plugins.ini` セクションと同一と判明 — CAB-219 §11 で writer 406/406 再現済)、VST2 側実機 `.fst`/`.nfo`。→ `VerifiedIDs.nfo` と `.Plugins.ini` は 2026-10-10 に入手・照合済み (§11)。

## 11. 追記 (CAB-219 / CAB-215 残部, 2026-10-10): 実機 `.Plugins.ini` + `VerifiedIDs.nfo` 照合と生成対象化

**結論**: ユーザ実機の 2 ファイルを `evidence/real_machine/` に取り込み、(1) `.Plugins.ini` 書式を確定してパーサ+ライタ実装 (`src/ini.ts`) — **round-trip byte 一致**かつ**自前 writer が実機 406/406 セクションを再現**。decompile 実測 (ini 書込 `0x912d10` が `.nfo` 用 `0x913f40`/`0x911940` を共用) どおり**セクション本文 ≡ `.nfo` 本文**なので、CAB-215 の主眼「`writeEntry` ↔ 実機 v2 `.nfo` 比較」は 406 実機エントリで成立。(2) `VerifiedIDs.nfo` の VST2 id 表現を確定 (**`ps_file_magic` の 10 進**)、キー順序の誤り (`<fmt>:<id>:<bits>` → 実機は **`<fmt>:<bits>:<id>`**) を修正し 236/236 受理。(3) 生成器 `.Plugins.ini` 対応 + 実機準拠の既定値化。**e2e は 39/39 テスト + 実機照合 21 checks + 831/831 round-trip で exit 0 維持** (`node analysis/real_ini_check.mjs` = 21 checks 全 PASS)。

### 11.1 実測値

| ファイル | 実測 |
|---|---|
| `.Plugins.ini` | **214,350 B** / sha256 `52532ffd…b710c6` / **UTF-8 + BOM** (内容は全 ASCII でも BOM 付き) / CRLF のみ / 6,942 行 / **406 セクション** (重複なし) / 407 ファイル行 / native Fruity 139 / 装飾付き (iconindex/color/tip) 6 / 2 ファイル entry 1 (Vital: VST3+VST2) |
| `VerifiedIDs.nfo` | **16,942 B** / sha256 `35f8688f…d2a6` / ASCII / CRLF / **236 キー = VST 64 + VST3 171 + CLAP 1** → **223 nfo** を参照 (13 キーは compat 由来の重複参照) |

### 11.2 確定した規則 (FORMAT.md §3/§6 に反映済み)

- `.Plugins.ini` = **UTF-8+BOM、CRLF、各セクション (最終含む) の後ろに空行 1 行**。セクション名 = `Installed` 相対 `<sub>\<name>`。セクション順 = 内部リスト順 [推]。**native Fruity 139 (`.nfo` を持たない) もセクション化** — ini は `Installed\*.NFO` の上位集合。キー順序・省略規則は既存 writer 模型どおり (406/406 再現 = 実機検証)。`iconindex=48` / `color=$40B6F6` / `tip="VST3 / 64 bit"` を実機初観測。
- **`ps_file_date` = TDateTime (double, 元期 1899-12-30) の IEEE754 ビット再解釈 10 進** — 407/407 が 2015-10-22..2026-09-29 に整合 (例 `4676583981019826458` = 2026-07-07 19:48:06)。「単位未判定」解消。**`ps_file_arch` は Windows 実機でも常に `Intel`** (407/407)。検証済 (scanflags=1, 363 ファイル) は `type` 必ず 1 (fx) / 2 (gen)。未検証 stub (scanflags=2/0x22, 44) は `type`/`guid`/`vendor`/`category` を欠く (スキャナがロード失敗した kHs / iZ 系の実例)。
- **VerifiedIDs**: VST2 id = **magic 10 進** (64/64 突合、pseudo-GUID ではない)、VST3 id = `ps_file_guid` テキスト (171/171)、CLAP = id 文字列。**対象 = non-native かつ scanflags=1 の全エントリ** (223/223 集合一致)。**`ps_compatibility` の GUID は 1 GUID = 1 キー** (Splice INSTRUMENT: 自 CID + 旧 CID 4 個 = 5 キー) — compat = 別版 ID の別名、を実機で確定。
- **VST2 疑似 GUID** (`ps_file_guid` on VST2 files): `ASCII("VST" + magic4文字(BE) + 小文字名)` を 16B — 実機 64/64 (Fresh Air = `{56535446-7241-7266-7265-736820616972}` = "VSTFrArfresh air")。`vst2PseudoGuid` を実機則に修正 (旧: 非小文字化 + fx で "VSE" 接頭; `fle:0x8f0d30` param_4≠0 分岐は実観測なし)。符号付き 10 進の ≥2³¹ 補足は §12.3 / FORMAT §9-2。

### 11.3 生成器への反映 (実機準拠) と CAB-218 (VST3 path / CID) への新知見

- `generateDb` が **`Installed/.Plugins.ini` を出力** (既定 on, `pluginsIni: false` で停止)。VerifiedIDs キー修正により**生成 Serum 2 / Serum 2 FX の 2 キーは実機 VerifiedIDs と byte 一致**。`.nfo` 既定値を実機準拠に: `type=1/2`、`arch=Intel`、VST2 疑似 GUID、Serum 2 (gen) category 省略。生成量 49 entry / **100 ファイル** / 40,661 → **69,342 B**。検証: 生成 Serum 2 セクション ≡ 実機セクション (**date/size/filename 除く全行一致**)。
- **`ps_file_filename` の実機分布**: 内部バイナリ形 (`…\Serum2.vst3\Contents\x86_64-win\Serum2.vst3` — Serum 2 / Scaler 3 / Splice) と単一ファイルモジュール形 (`…\Vital.vst3`, kHs 群) の**両方が実在**。`.fst` record 55 (OTT) は単一ファイル形 → 選択規則は **CAB-218 で確定 (§12)** — 本節時点では未確定ゆえ Serum 2 path をバンドル形のままとしていたが、§12 で内部バイナリ形に修正済み。
- **VST3 CID ↔ GUID テキスト**: 実機 `ps_file_guid` テキスト = moduleinfo CID 文字列そのもの = **Windows GUID メモリ配置で raw TUID と相互変換** (OTT record 52 実機 raw `XTSVTfoTtt` と整合) → `tuidFromHex` を「CID テキスト hex → Windows 配置 bytes」に修正 (旧: raw 順と誤解釈)。H5 hosting の TUID 変換もこの規則。

### 11.4 CAB-215 残部の処理と成果物

CAB-215 の主眼 (writeEntry ↔ 実機比較) は **ini セクション経由で達成** (§11.1/11.2, 406/406)。未入手: `.nfo`/`.fst` 単体ファイルと VST2 側実機 `.fst` — §7 依頼は任意で継続。**検収コメントは投稿せず REPORT 追記のみ** (CAB-215 は In Review 維持、メインが検収を統括)。成果物: 追加 = `evidence/real_machine/{.Plugins.ini, VerifiedIDs.nfo}` / `src/ini.ts` / `test/real_machine.test.ts` (10 test) / `analysis/real_ini_check.mjs`。変更 = `src/{format,entry,generate}.ts`、`specs/wasm_plugins.json` (_note + Serum 2 category)、`nfo_e2e.sh` (実機 step)、FORMAT.md (§3/§6/§9)、テスト 29 → **39**。Kilohearts VST2 magic は本節時点「id と別物」と誤記 — **CAB-218 §12.2 で 45/45 一致と訂正済み**。

## 12. 追記 (CAB-218 / CAB-46 小口, 2026-10-10): VST3 `ps_file_filename` 規則確定 + KH VST2 magic 実測確定

**結論**: (1) **H11 選択規則を確定** — `ps_file_filename` (VST3) = **FL が `LoadLibraryW` で直接消費する「ロード可能モジュールファイル」のパス**。CAB-219 の「バンドルフォルダ形」呼称は実態が**単一ファイルモジュール** (`<Name>.vst3` という名前の PE DLL) だったための誤認で、両形の差はプラグイン側の実配置 (単一ファイル vs バンドル) 由来。FL 側に directory→`Contents` 解決は存在しない。generateDb は Serum 2 を実機一致の**内部バイナリ形**に修正し filename 込み実機突合を成立。(2) **KH VST2 magic は実測確定** — product_index.json の 4 文字 id が実機 **45/45 一致** (spec の magic 値変更は不要、§11.4 の「別物」誤記を訂正)。Fresh Air (`FrAr`) も実機一致。併せて KH の category/vendor/kind を実機準拠に修正。(3) VerifiedIDs VST2 id は **64/64 = magic の符号付き 10 進**。≥2³¹ の負値例は実機に無し → FORMAT §9-2 に writer 根拠 (`IntToStr(Integer)`) 付きの**推定**として記録。

### 12.1 H11 根拠 (静的解析は読取のみ + 実機突合)

| 根拠 | 実測 |
|---|---|
| QuickFontCache_x64.dll `CreateVST3Instance` (qfc:0x58a200 — block24350 を Ghidra 新規解析) | `TVST3Instance` 生成 → **`LoadLibraryW(与えられたパス)`** (qfc:0x58a3d0 → 0x41d910) → `GetProcAddress("InitDll")` 呼出 → `"GetPluginFactory"`。**qfc 内に `Contents`/`x86_64-win`/`moduleinfo` の文字列は皆無** = 最終 hop にバンドル解決は存在しない |
| Wrapper `TVST3Plugin.LoadPlugin` (fw:0x84ad90) | plugin record の filename バッファ (+0x20e, 261 wchar) を**無変換**で `CreateVST3Instance` へ渡す。CID (`ps_file_guid`/record 52) は factory クラス列との `IsEqualGUID` 選択に使用 (§11.3 と整合)。fw の `moduleinfo.json` 探索 (`0x83b730`) は列挙/走査側の補助で、instance 化の入力変換ではない |
| 実機 179 VST3 entry の filename 分布 | 内部バイナリ形 15 / モジュールファイル形 164 — **全てが「モジュールファイル」を指す** (`evidence/real_machine/.Plugins.ini`) |
| 単一ファイル形の実証 (OTT + kHs) | OTT 1.37 インストーラ (NSIS) は `…\VST3\OTT.vst3` を**単一ファイル**で同梱 — 展開実測 **3,244,032 B** = 実機 ini `ps_file_size_0` 完全一致。Kilohearts winpkg も `kHs *.vst3_64` 単一 PE DLL (例 kHs Gain **247,296 B** = 実機 ini 一致, VST3 45 種) |
| 内部バイナリ形の実証 (Serum 2) | Serum 2.1.5 win インストーラ実配置 `Serum2.vst3\Contents\x86_64-win\Serum2.vst3` (**19,236,864 B** = 実機 ini (FX) 一致) |

→ **writer (generateDb) 規則**: 仮想 FS への配置形に合わせる。単一ファイルで置くなら `<dir>\<Name>.vst3`、バンドル配置なら `<dir>\<Name>.vst3\Contents\x86_64-win\<Name>.vst3`。`.fst` record 55 は `ps_file_filename` と同値になるため OTT 実機 `.fst` と自動的に同一形。

### 12.2 KH magic 差し替え表 (全量は `node analysis/kh_magic_check.mjs` 出力)

- **判定: product_index.json の 4 文字 id (= spec 現行値) が正しかった** — 実機 45/45 一致。代表: `kHs Bitcrush`=`ksbc` (1802723939) / `kHs Dynamics`=`ksot` (1802727284) / `kHs 3-Band EQ`=`ksqe` (1802727781) / Disperser=`kdsp` (1801745264) / Carve EQ=`ksge` (1802725221) / Phase Plant=`kphp` (1802528880) / Snap Heap=`kmic` / Multipass=`kmup` / Slice EQ=`kpeq`。実機 VST2 magic 64/64 が 4 文字印刷可能 ASCII (BE)。
- 生成器更新 (cli/gen.ts): KH 拡張の category `Kilohearts`→**`Effect`** (実機 44 fx)、**Phase Plant を generator (class 4) + category `Synth`** へ (実機 `Generators\VST\Phase Plant`)。spec: Fresh Air を vendor **`Slate Digital`** / category `Effect` へ (旧 Kilohearts/Exciter は実測不一致)。→ 生成 KH 46 entry が実機セクションと **name/magic/guid/class/type/bits/arch/vendor/category 全項目一致 (46/46)**。
- KH 以外の実測判明分 (spec 対象外, 記録のみ): iZotope 系 `INS0`/`ZMR1`/`ZOI2`/`ZRL1`/`ZBM2`/`iZVn`/`IZVD`/`VxS2`、GClip=`gyAd`、Scaler 3=`Scl3`/`Sc3F`、UJAM `SE-*` 3 種、FL Studio VSTi 2 種、Beatmaker、Youlean、Vital=`Vita` 等 18 種 (スクリプト出力参照)。

### 12.3 検証と回帰

- `analysis/kh_magic_check.mjs` 新設 (**16 checks, exit 0**): ini 抽出 VST2 magic 64 (Effects\VST 55 種) / KH index 突合 45+FrAr / VerifiedIDs 64/64 符号付き 10 進・負値 0 件 (max magic 1802729331 < 2³¹) / VST3 filename 15+164 / OTT・kHs・Serum の installer↔ini size 突合 / 生成 KH 46/46・Serum 2 2 セクション filename 込み一致。`nfo_e2e.sh` に step 追加 — **e2e exit 0 維持** (テスト 39 / 実機照合 21 checks / round-trip 831/831 / 生成 49 entry 受理)。
- ≥2³¹ magic (要件 3): 実機 64 magic は全て <2³¹ で負値例無し → **REPORT 上は推定**。根拠: writer `fle:0x914780` は int32 を `IntToStr(Integer)` (`fle:0x43a7e0`) で整形 (≥2³¹ は負値出力)、reader `StrToIntDef` は 2³¹ 以上の無符号リテラルを Integer に丸められず既定値 0 — 符号付き以外に自己往復する表記が無い。

### 12.4 CAB-46 (Massive X 稼働中) への引き継ぎ

- **KH magic 差し替え作業は CAB-46 側で不要** (実測確定・生成器反映済み)。CAB-98 領域の残は §7 の実機単体ファイル提供のみ。Massive X は `~/ダウンロード/Native Instruments Massive X v1.7.1.exe` を確認済み (win) — 解析後 `moduleinfo.json` の CID を得れば spec 1 行で追加可 (class 8, `path` は §12.1 規則で実配置に応じて選択)。VST2 側は VerifiedIDs 形 (magic 10 進) と KH パターン (id=4 文字) を踏襲。参考: `~/ダウンロード` の `FL_STUDIO_.Plugins.ini` / `FL_STUDIO_VerifiedIDs.nfo` / `OTT.fst` は `evidence/real_machine/` 同名 3 ファイルと **byte 一致** (cmp 実測) — 引き継ぎ側の再入手は不要。

### 12.5 追記 (CAB-46 follow-up, 2026-10-10): Massive X spec 追加 — CID 三重突合で一致

**結論**: `specs/wasm_plugins.json` に Massive X (class 8 = VST3 gen) を追加し、生成エントリが**実機 `[Generators\VST3\Massive X]` セクション (実機 ini に実在 — FL が実moduleをスキャン済み) と filename/guid/vendor/category 込みで一致** (date/size 除く全行一致, mx_check 実測)。Class CID は **`5653544e6924486d6173736976652078`** で、(1) 実機 ini `ps_file_guid_0`、(2) Service Center XML `VST3ID` (`tools/targets/massivex/work/extracted/…/Massive X.xml`)、(3) GetPluginFactory (`0x18000a870`) 即値 `mov edx,0x4e692448` (CAB-46 §4, 今回 disassembly 再実測) からの NI 規則導出 — の **3 源が一致 (= 不一致、CID 候補の列挙不要)**。**moduleinfo.json は本製品は同梱されない** (installer 11,602 ファイルの payload に 0 件、95 MB 単一ファイル PE 内にも `moduleinfo.json` 文字列は無く `Steinberg::ModuleInfoLib` RTTI 名のみ) — ゆえに moduleinfo 由来の抽出は不可で、**実機 FL 自身のスキャン値 (ps_file_guid = FL が GetPluginFactory から取得した CID) を正**として採用した。

| 項目 | 実測 |
|---|---|
| CID 16B | text 順 ASCII **`VSTNi$Hmassive x`** / Windows GUID メモリ配置 **`4e54535624696d486173736976652078`** (CAB-46 §4 生値と一致, `.fst` record 52 / `tuidFromHex` はこの配置) |
| NI FUID 規則 (Massive X で実証) | ASCII `"VST"` + PluginID **BE32** (`0x4e692448`→`Ni$H`) + lower(name) を 16 B に刈り — 同族例: Massive v1 `{5653544E-694D-616D-6173-736976650000}` / FM8 FX `{5653544E-6986-3866-6D38-206678000000}` (実機 VerifiedIDs, "VSTN" 起始) [med] |
| `ps_file_filename` | **`C:\Program Files\Common Files\VST3\Massive X.vst3`** — **単一ファイルモジュール形** (§12.1 規則の実配置適用: installer dst `{cf}\VST3\Massive X.vst3` が単一 PE 95,356,824 B = 実機 ini `ps_file_size_0` **完全一致**, `\Contents\` 経由なし — task 前提の「内部バイナリ形」ではなく実配置が単一ファイル形) |
| 実機準拠の他値 | plugclass 8 / type 2 / bits 64 / arch Intel / scanflags 1 / vendor **`Native Instruments`** (Service Center の Company 表記 `…GmbH` ではなくスキャン記録値) / category **`Instrument|Synth`** (= PClassInfo2 subCategories, PE 内 lea 先 `0x184fe7ff7` 実測 / cardinality `0x7fffffff`・version `1.7.1 (R0)`・sdk `VST 3.7.14` も lea 実測) |
| UPID / SNPID / VST2 | UPID `41ce4ac2-34f7-469b-beb8-59a8ad7a8a67` は**ライセンス用製品 ID で CID ではない**、実機セクションに `ps_compatibility` 無し → **Serum 2 踏襲で spec も compat 無し**。SNPID `MXE`。VST2 `Massive X.dll` (95,249,816 B) は実在するが spec 未収録 (VST3 のみ — Serum 2 踏襲, 将来は magic `1315513416`=0x4e692448) |

検証: `analysis/mx_check.mjs` 新設 (**10 checks, exit 0**; massivex work/ 資産は existsSync ガードのオプション参照) — 実機セクション突合 / CID 3 源突合 / FUID 規則 / installer 単一ファイル形・moduleinfo 不在 / 生成セクション + VerifiedIDs 行 verbatim 突合。`nfo_e2e.sh` に step 追加 — **e2e exit 0 維持** (tests 39→**40** / 実機 21 checks / CAB-218 16 checks / round-trip 831/831 / 生成 **50 entry・102 ファイル** reader+tools/flp 全受理)。既存節 (§0〜§12.4) は無改変。
