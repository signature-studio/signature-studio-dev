# REPORT — H9 / CAB-98: Plugin database (`.nfo` / `.fst`) 書式解読 + 合成 DB 生成器

> 正本: `tools/hostbridge/nfo/REPORT.md`。書式仕様は `FORMAT.md`。
> **行数**: §10〜§14 は `REPORT_APPENDIX_A.md` (§10〜§12) / `REPORT_APPENDIX_B.md` (§13〜§14) に無変更で分割移動済み
> (250 行上限・`docs/DOC_MAP.md` §1 / #437)。節番号は維持。本文中の `§10`〜`§14` は付録側の節を指す。

最終更新 2026-10-11 / 担当 subagent (hostbridge-nfo) / 再現: `bash tools/hostbridge/nfo/nfo_e2e.sh` (exit 0 = 全 PASS / §13 の h4 結線 e2e を含む) + `bash tools/hostbridge/nfo/h4_e2e.sh` (CAB-216 単独) + `node tools/hostbridge/nfo/analysis/real_ini_check.mjs` (実機照合 21 checks) + `node tools/hostbridge/nfo/h4_recount.mjs` (実装側 独立再計算) + `node tools/hostbridge/nfo/h4_accept_check.mjs` / `node tools/hostbridge/nfo/h4_accept_chrome.mjs` (検収側 独立再計算) / 仕様: `FORMAT.md`

所要 (実測。定義: `bash <script>` の wall time・`/usr/bin/time`・n=3 ・min–max 表記。/tmp/opencode 上、他 subagent 稼働中の load average は並記):

| コマンド | 実測 (n=3) | load average 開始 / 終了 (抜粋) |
|---|---|---|
| `nfo_e2e.sh` (全 step・h4 含む) | **5.90–7.69 s** (5.90 / 6.28 / 7.69 s, exit 0) | 13.98–15.13 / 13.98–15.12 |
| `h4_e2e.sh` (CAB-216 単独) | **3.66–3.75 s** (3.66 / 3.70 / 3.75 s, exit 0) | 7.00–8.09 / 6.43–7.60 |
| `h4_accept_check.mjs` (検収側) | **0.36–0.36 s** (0.36 × 3, exit 0) | 13.32–36.87 / 13.32–36.87 |

## 0. 結論 (先出し)

- **判定: 静的解析のみで書式を確定し、パーサ/ライタ/合成 DB 生成器を実装した。** その後 §10/§11 で実機突合まで完了 (CAB-215/CAB-219)。**実例**: 抽出物 (mac pkg + win installer) に `Installed\` 配下の v2 `.nfo` は **0 件**。`.nfo` は 831 件 (全て ASCII, 25,203 B) あり、`ps_*` を含むのは native の `Plugin.nfo` 141 件 (`ps_vendorname` のみ) だけ (§1)。
- **書式 (FLEngine を逆アセンブルして確定; PluginManager.exe は同一 unit を内包)**: `.nfo` = CRLF の `key=value` 行 (キー大文字小文字非区別、`'` 行はコメント)。`fileversion=2` は `ps_name / ps_presetfilename / ps_files=N` + `ps_file_*_<i>` (i=0 起点)。必須は実質 `ps_files` と `ps_file_plugclass_i` のみ。`.fst` = FLhd(0x30, 2ch, ppq48) + `199 "11.5.5"`, `28`, `201 "Fruity Wrapper"`, `212`, `203 名前`, `213 wrapper chunk`。
- **round-trip 実測**: 同梱 `.nfo` 831/831 byte-exact、FL 11.5.5 書込の `.fst` 26/26 を自作コンテナ writer で byte-exact 再構成 (§3)。v2 `.nfo` は writer→reader の自己整合 (生成 50/50 受理) に加え、**実機 `.Plugins.ini` 406/406 セクションを writer が再現** (§11)。
- **wasm 向け**: OTT / Fresh Air / Kilohearts(45) / Serum 2(2 class) / Massive X の DB エントリを **50 件・102 ファイル** (`.Plugins.ini` 込み) で合成できる (`specs/wasm_plugins.json` + Kilohearts index)。Kilohearts 45 = product_index 展開分の実測 (`formats` に 'vst2' かつ `id` 4 文字 = 44 fx + Phase Plant)。Massive X は **CAB-46 follow-up (§12.5) で spec 追加済** (CID 3 源一致)。
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

実測値 (`work/metrics.json`): 同梱 `.nfo` round-trip **831/831**、`Plugin.nfo` 141/141 読了 (vendor `Image-Line` 141)、FL 11.5.5 `.fst` **26/26 byte-exact 再構成**、生成 50 entry を reader 模型が **50/50 受理** (rejectedFiles 0)、テスト **40/40 PASS**、`nfo_e2e.sh` 実測 5.90–7.69 s (定義は冒頭の所要表)。

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
| `test/` | node:test 40 件 (コーパス往復・FL 準拠規則・生成物の独立パーサ受理・決定性・実機突合) |
| `analysis/` `evidence/` | Ghidra 抽出 (`reproduce.sh`)、定数表、decompile 抜粋 (約 130 KB, FL 実バイナリ由来) |
| `nfo_e2e.sh` | 1 コマンド再現: typecheck → ブラウザ安全性 grep → tests → 実測 → 生成 |

使い方: `node cli/gen.ts specs/wasm_plugins.json <out> [--kilohearts <product_index.json>]`。API は `src/index.ts` (ブラウザ互換: `node:` import なし、tools/flp の `src` と同方針)。

## 5. wasm 版の plugin エントリ設計 (ABI.md / HOSTBRIDGE.md §2.10–2.11 と整合)

方針: PluginManager は移植せず、**ビルド時または初回起動時に `generateDb()` で `Presets/Plugin database/` を仮想 FS に書く**。FL 側コードは無改変 (FL 自身の reader が読む)。仮想 FS は大文字小文字非区別。native Fruity 141 は DB 非経由 (`Plugins\Fruity\…\<name>_x64.dll` + `Plugin.nfo` の存在走査, `fle:0xabf130`) → H4 の PE スタブ側で担保。

| plugin | 形式 | class | 同定子 | `ps_file_filename` (仮想パス) | 備考 |
|---|---|---|---|---|---|
| OTT | VST2 x64 | 0 (fx) | magic `XfTT` = 1483101268 (hostbridge PoC 実測の uniqueID) | `C:\Program Files\Common Files\VST2\Xfer Records\OTT_x64.dll` | chunk: record 51 / 54 (`OTT_x64`) / 55 / 56 |
| Fresh Air | VST2 x64 | 0 | magic `FrAr` (targets/freshair の製品 ID) | `…\VST2\Kilohearts\Fresh Air_x64.dll` | 250 KB shell → `SlateCore.core_64` はモジュール表側で入れ子 LoadLibrary |
| Kilohearts ×45 | VST2 x64 | 0 | magic = 4 文字 product id (`ksgn` 等・実機 45/45 一致) | `…\VST2\Kilohearts\kHs <Name>.dll` | 45 shell → `HeartCore.core_64` 共有。DB 名は `fileName` ("kHs Gain")。plugin 自己申告名は未確認 |
| Serum 2 | VST3 のみ | 8 (gen) | CID `56534558667350736572756D20320000` | `…\VST3\Serum2.vst3\Contents\x86_64-win\Serum2.vst3` | VST3 facade (H5) 前提 |
| Serum 2 FX | VST3 | 7 (fx) | CID `56534558667351736572756D20322066` | 同上 | 同一バイナリ・別 class → 別エントリ (`Effects\VST3\`) |
| Massive X | VST3 | 8 (gen) | CID `5653544e6924486d6173736976652078` (§12.5・3 源一致) | `…\VST3\Massive X.vst3` | 単一ファイルモジュール形 (moduleinfo.json 非同梱)。実機 ini 由来の vendor/category を使用 |

- `ps_file_scanflags_0=1`、`ps_file_bitsize_0=64`、`ps_file_type` は実機準拠の 1 (fx) / 2 (gen) (§11.3)。32bit は載せない (bridge 不使用: HOSTBRIDGE §1.6)。
- Wrapper→VST2 の `hint` (entry export 名) は常に定数 0 で供給元が無い (#218: `tools/hostbridge/h10/REPORT.md` §3-②)。標準名 (`main` / `VSTPluginMain` 系) の export が必須。Kilohearts は stub 消去 (alias) で標準名に揃う。
- 生成量: **50 entry / 102 ファイル / 70,571 B** (決定的, `.Plugins.ini` 込み §11.3・Kilohearts 45 + spec 5)。IDB プリロードに載せても無視できる大きさ。

## 6. 未解決とブロッカー

1. **Installed の実機 v2 サンプルが無く、`.nfo`/`.fst` は「FL コードが受理する形」を静的に再構成したもの**。reader 模型は decompile 準拠だが、FL 本体の実行による検証は未了 (lift 済み FL で `0x910cd0` を動かす検証は H4 以降)。
2. ~~Fruity Wrapper が生成 `.fst` を読めるか~~ → **#218 (H10) で reader 解析済み**: chunk は Wrapper の reader に受理され、record 1/30/31/32 は不要 (Wrapper が既定値で補う)。起動可否の実行検証は #267 (`tools/hostbridge/h10/REPORT.md` §3-①・§4)。
3. ~~Wrapper の VST2 `hint` 供給元 (id 57 候補)~~ → **#218 で解消**: id 57 = `effGetVstVersion`、hint は常に定数 0 で供給元なし (`tools/hostbridge/h10/REPORT.md` §3-②)。
4. ~~`.Plugins.ini` の文字コード、`ps_file_date` の単位、VerifiedIDs の VST2 `id` 表現~~ → **CAB-219 で解決 (§11)**: ini = UTF-8+BOM / date = TDateTime double bits / VST2 id = magic 10 進 (キー順 `<fmt>:<bits>:<id>`)。VST3 `ps_file_filename` の**選択規則は CAB-218 で確定 (§12, FORMAT §9-3)**。
5. VST3 CID → `ps_file_guid` の対応は §11.4 で実機確定 (テキスト = CID 文字列、bytes = Windows 配置)。Wrapper が factory へ渡す順序の実行検証は H5 で。
6. ~~Massive X 素材なし / KH VST2 magic 未確定~~ → **KH magic は CAB-218 で実測確定 (§12.2)**。**Massive X も CAB-46 follow-up (§12.5) で spec 追加・CID 確定** (`~/ダウンロード/Native Instruments Massive X v1.7.1.exe` 解析済。moduleinfo.json は本製品に同梱されない = CID は実機 FL スキャン値を正とした)。

## 7. ユーザ依頼事項 (任意・あれば更に確実化)

Windows 実機から `Installed\` 配下の **実機 v2 `.nfo` / `.fst` 単体ファイル** (VST2 1 組 + VST3 1 組, 特に OTT VST2 側) があると `writeEntry`/`buildWrapperFst` との byte 直比較が即完了する (`.Plugins.ini`/`VerifiedIDs.nfo`/OTT.fst は入手済み §10/§11; `~/ダウンロード` の同名 3 ファイルは evidence と byte 一致を確認済み §12.4)。**Massive X の VST3 CID 依頼は取下げ** — moduleinfo.json は本製品に同梱されないことを実測し (§12.5)、CID は実機 FL スキャン値・Service Center XML・GetPluginFactory 即値の 3 源一致で確定済み。

## 8. 次タスク提案 (下流チケット案)

| # | チケット | 要点 |
|---|---|---|
| H4' (P0) | DB 組込み | ~~`generateDb()` (`.nfo`/`.fst`/`.Plugins.ini`/VerifiedIDs 生成) を仮想 FS 初期化 (起動時/ビルド時) に結線し、lift 済み FL の `0x910cd0` / `0xaba430` に生成 DB を読ませて受理を実行検証~~ — **結線まで完了 (CAB-216 §13)**。残は FL 実物 reader の実行検証のみ (§13.6・§14) |
| H10 (P1) | Wrapper chunk reader の解析 | ~~生成 `.fst` の record 群を Wrapper が受理するか~~ — **完了 (#218, `tools/hostbridge/h10/REPORT.md`)** |
| H11 (P2) | VST3 バンドルのパス規則 | ~~選択規則の突合~~ / ~~H9a / H12~~ — **完了 (CAB-215 §10 / CAB-219 §11 / CAB-218 §12)**。残は §7 の任意提供のみ |

## 9. 規約遵守メモ

- 書込は `tools/hostbridge/nfo/` のみ (`work/` は gitignore: Ghidra project コピー約 280 MB・PluginManager/FLEngine 抽出)。`tools/flp` / `tools/targets` / `tools/m2` / `tools/hostbridge` 既存ファイルは読取のみ。README/docs/ 無改変。`evidence/` は FL 実バイナリの decompile 抜粋 (約 130 KB)・定数表・実機キャッシュファイル 2 件 (`evidence/real_machine/` — ユーザ提供の Plugin database ファイル) を含む (EULA は事実整理のみ: 実バイナリ本体・lift 済み wasm はコミットしない)。外部通信・認証系は不使用。

## 10〜14. 分割移動した節 (付録; 内容は無変更・節番号維持)

250 行上限 (`docs/DOC_MAP.md` §1) のため、§10〜§14 は付録に**無変更で移動**した (#437)。測定値・表・ネガコンは全て付録側に残る。

| 節 | 内容 | 所在 |
|---|---|---|
| §10 (CAB-215) | 実機 `OTT.fst` 照合 (323/323 byte 一致・CID `XTSVTfoTtt`・path 規則の実機証拠) | `REPORT_APPENDIX_A.md` |
| §11 (CAB-219) | 実機 `.Plugins.ini` (406 セクション) + `VerifiedIDs.nfo` (236 キー) 照合と生成対象化 | `REPORT_APPENDIX_A.md` |
| §12 (CAB-218 / CAB-46) | VST3 `ps_file_filename` 規則確定・KH VST2 magic 45/45・Massive X CID 3 源一致 (§12.5) | `REPORT_APPENDIX_A.md` |
| §13 (CAB-216 / HB-H4') | `generateDb()` → pathreg → wvfs 結線 e2e (node + Chrome OPFS)・陰性制御・未解決 | `REPORT_APPENDIX_B.md` |
| §14 | §13 の検収 (独立再計算・照合表・ネガコン・誤記修正・未解決) | `REPORT_APPENDIX_B.md` |

## 15. 追記 (#347 / PR #391, 2026-10-13): nfo_e2e.sh の typecheck 破損 (TS7016) を修正

既知類型との関係: 該当なし (型検査設定のみ・lift 無関係)。

- `/home/ubuntu` 絶対パスの置換 (`_fl.ts`・`metrics.ts`・`h4_e2e.ts`・`real_fst_check.mjs`・`reproduce.sh`・`kh_magic_check.mjs`・`ott_fst_dump.json`) は **#362 / PR #376 (`1c54e11`, merged) で main に入っている**。#347 は #362 の重複起票で、#347 の完了根拠は「#362 で完了済み」。本 PR はこの置換を含まない。
- 本 PR の差分: `tsconfig.json` に `allowJs: true` / `checkJs: false` を追加、`nfo_e2e.sh` の env コメント更新、本節。
- 修正の理由: #376 で `cli/metrics.ts`・`test/_fl.ts` が `tools/shared/paths.mjs` を import するようになり、型宣言が無いため main の `nfo_e2e.sh` typecheck が TS7016 で失敗していた。`allowJs` で `.mjs` を解決する (`checkJs:false` なので `.mjs` 自体は検査しない)。
- 検証 (検証起点: 現 main `fac2c47` vs head `563b11e`、fl-win64 展開済み・`FL_WIN64_DIR` 指定、4 コア / load 1.00、`cd tools/hostbridge/nfo && SKIP_H4=1 bash nfo_e2e.sh`):

| 対象 | exit | 所要 | 結果 |
|---|---|---|---|
| main `fac2c47` | **1** | 0.168 s | typecheck で `cli/metrics.ts(9,27)` / `test/_fl.ts(3,28)` が TS7016 |
| head `563b11e` | **0** | 2.635 s | typecheck 出力なし・browser-safety ok・ini 406/406・CAB-218 failed 0 |

  `node --test test/*.test.ts`: main・head とも tests 40 / pass 36 / fail 0 / skipped 4 (mac コーパス `FL_MAC_DIR` 素材なしで corpus 4 件 SKIP)。Chrome 段 (`h4_e2e.sh`) は本変更と無関係のため `SKIP_H4=1`。
- 行数: 本 REPORT は main 時点で 250 行上限 (DOC_MAP §1) を超過 (374 行) していたが、#437 (DOCS-5) で §10〜§14 を付録 A/B に分割移動して解消した (#378 は p0c 領域で別件)。
