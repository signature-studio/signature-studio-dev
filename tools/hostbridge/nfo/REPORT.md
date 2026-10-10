# REPORT — H9 / CAB-98: Plugin database (`.nfo` / `.fst`) 書式解読 + 合成 DB 生成器

最終更新 2026-10-10 / 担当 subagent (hostbridge-nfo) / 再現: `bash tools/hostbridge/nfo/nfo_e2e.sh` (exit 0 = 全 PASS, 約 2 s) / 仕様: `FORMAT.md`

## 0. 結論 (先出し)

- **判定: 静的解析のみで書式を確定し、パーサ/ライタ/合成 DB 生成器を実装した。** 実機サンプルは不要だった (ただし v2 `.nfo` の実例照合だけは未了 → §7 で実機ファイルを依頼、任意)。
- **実例**: 抽出物 (mac pkg + win installer) に `Installed\` 配下の v2 `.nfo` (`ps_file_plugclass` / `fileversion=2` を含むもの) は **0 件**。`.nfo` は 831 件 (全て ASCII, 25,203 B) あり、`ps_*` を含むのは native の `Plugin.nfo` 141 件 (`ps_vendorname` のみ) だけ (§1)。
- **書式 (FLEngine を逆アセンブルして確定; PluginManager.exe は同一 unit を内包)**: `.nfo` = CRLF の `key=value` 行 (キー大文字小文字非区別、`'` 行はコメント)。`fileversion=2` は `ps_name / ps_presetfilename / ps_files=N` + `ps_file_*_<i>` (i=0 起点)。必須は実質 `ps_files` と `ps_file_plugclass_i` のみ。`.fst` = FLhd(0x30, 2ch, ppq48) + `199 "11.5.5"`, `28`, `201 "Fruity Wrapper"`, `212`, `203 名前`, `213 wrapper chunk`。
- **round-trip 実測**: 同梱 `.nfo` 831/831 byte-exact、FL 11.5.5 書込の `.fst` 26/26 を自作コンテナ writer で byte-exact 再構成 (§3)。v2 `.nfo` は writer→reader の自己整合 (生成 49/49 受理) と decompile 準拠テスト (29 件 PASS)。
- **wasm 向け**: OTT / Fresh Air / Kilohearts(46) / Serum 2(2 class) の DB エントリを 49 件・99 ファイル・40,661 B で合成できる (`specs/wasm_plugins.json` + Kilohearts index)。Massive X は素材なしでエントリ未生成 (§5)。
- **コミット**: `feat(hostbridge): plugin database nfo/fst format and synthetic generator` (tools/hostbridge/nfo のみ)。

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
- 定数表 (class mask、GUID 位置表、arch 名、212 テーブル) は `analysis/dump_tables.py` が PE から機械抽出 (`evidence/fle_tables.txt`)。再生成 `analysis/reproduce.sh` (約 1 分)。
- 突合: ① 同梱 `.fst` 26 件で `199/28/201/212/213` 構造と FLhd(0x30,2,48) を byte 単位で再現。② `tools/flp` の独立パーサ (`parseFlp` / `parseWrapperData`) が生成 `.fst` と wrapper chunk を受理 (kind 8, 記録 id 2/50/51|52/54/55/56)。③ native `Plugin.nfo` 141 件を `ps_vendorname` (大小混在) / `ps_dummy64bit` で読了。

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

- `ps_file_scanflags_0=1`、`ps_file_type` は 0 (class で fx/gen 判定)、`ps_file_bitsize_0=64`。32bit は載せない (bridge 不使用: HOSTBRIDGE §1.6)。
- Wrapper→VST2 の `hint` (entry export 名) は標準名 (`VSTPluginMain`) なら不要。Kilohearts は stub 消去 (alias) で標準名に揃う。hint を DB に持たせる必要が出た場合の記録先は未特定 (§6-3)。
- 生成量: 49 entry / 99 ファイル / 40,661 B (決定的)。IDB プリロードに載せても無視できる大きさ。

## 6. 未解決とブロッカー

1. **Installed の実機 v2 サンプルが無く、`.nfo`/`.fst` は「FL コードが受理する形」を静的に再構成したもの**。reader 模型は decompile 準拠だが、FL 本体の実行による検証は未了 (lift 済み FL で `0x910cd0` を動かす検証は H4 以降)。
2. Fruity Wrapper が生成 `.fst` (record 2/50/51/54/55/56 のみ) を読んで VST2/VST3 を起動できるかは未検証 (Wrapper の chunk reader は未解析; record 1/30/31/32 は Wrapper が補うと推定)。`tools/flp` の独立パーサ受理までは確認。
3. Wrapper の VST2 `hint` (`TVSTPlugin` 第 6 引数) の供給元レコード (id 57 候補) は未特定。標準名エクスポートでは不要。
4. `.Plugins.ini` の文字コード、`ps_file_date` の単位、VerifiedIDs の VST2 `id` 表現、VST3 バンドルの `ps_file_filename` (フォルダ or 内部バイナリ) は未確認。FL の自己修復/名前検索経路 (FORMAT §6) で致命にならない見込みだが推定。
5. VST3 CID (TUID raw 16 B) → `ps_file_guid` は「バイト列 = Windows GUID メモリ配置」と推定 (text↔bytes は可逆で record 52 に同じ 16 B を入れる設計のため内部一貫、ただし Wrapper が factory へ渡す順序は未検証)。
6. Massive X 素材なし。Kilohearts の VST2 uniqueID = product id は仮定。

## 7. ユーザ依頼事項 (任意・あれば即確定)

Windows 実機 (FL Studio 26.x、対象プラグインをインストールし Plugin Manager でスキャン済み) から次を提供 (パス: `%USERPROFILE%\Documents\Image-Line\FL Studio\Presets\Plugin database\`):
1. `Installed\Effects\VST\<任意の VST2 エフェクト>.nfo` と同名 `.fst` (できれば OTT)。
2. `Installed\Generators\VST3\<任意の VST3 シンセ>.nfo` と同名 `.fst` (できれば Serum 2)。
3. `Installed\VerifiedIDs.nfo` と `Installed\.Plugins.ini` (先頭 50 行程度で可)、`Installed\VST\*.NFO` があればその 1 つ。
4. 可能なら Massive X (NI) の VST3 CID (`moduleinfo.json`) またはその `.nfo`。
→ `writeEntry` / `buildWrapperFst` の出力と byte 比較でき、§6-1,4,5 が解消する。

## 8. 次タスク提案 (下流チケット案)

| # | チケット | 要点 |
|---|---|---|
| H9a (P1) | 実機サンプル照合 | §7 のファイルで `writeEntry` と byte 比較し、差分を FORMAT.md / 生成器へ反映 |
| H4' (P0) | DB 組込み | `generateDb()` を仮想 FS 初期化 (起動時/ビルド時) に結線し、lift 済み FL の `0x910cd0` / `0xaba430` に生成 DB を読ませて受理を実行検証 |
| H10 (P1) | Wrapper chunk reader の解析 | 生成 `.fst` の record 群を Wrapper が受理するか (hint レコード・record 1/30–32 の要否) を `fw:` 側で確定 |
| H11 (P2) | VST3 バンドルのパス規則 | Serum 2 の `ps_file_filename` 形と QuickFontCache `CreateVST3Instance` の入力を突合 |
| H12 (P2) | `.Plugins.ini` / VerifiedIDs の実機照合 | ini 文字コード・VST2 id 表現を確定し、生成対象化 |

## 9. 規約遵守メモ

- 書込は `tools/hostbridge/nfo/` のみ (`work/` は gitignore: Ghidra project コピー約 280 MB・PluginManager/FLEngine 抽出)。`tools/flp` / `tools/targets` / `tools/m2` / `tools/hostbridge` 既存ファイルは読取のみ。README/MILESTONES/HANDOFF 無改変。
- `evidence/` は FL 実バイナリの Ghidra decompile 抜粋 (約 130 KB) と定数表を含む (EULA は事実整理のみ: 実バイナリ本体・lift 済み wasm はコミットしない)。外部通信・認証系は不使用。

## 10. 追記 (CAB-215 部分実施, 2026-10-10): 実機 OTT.fst 照合

**結論**: ユーザ実機の `Installed\Effects\VST3\OTT.fst` (323 B) を取得し、CAB-98 の全模型 (コンテナ writer / wrapper chunk 解析 / 生成器) が **byte 級で一致**することを確認した (下表, 全 PASS)。`.fst` 書式の実機裏取りとしては完了。ただし **実機 v2 `.nfo` / `VerifiedIDs.nfo` / `.Plugins.ini` は実機に存在せず未入手** → 本チケット本来の主眼である `writeEntry` との `.nfo` byte 比較は未了で、**部分実施**として扱う (§7 の依頼は継続)。

再現: `node tools/hostbridge/nfo/analysis/real_fst_check.mjs` (exit 0 = 全 PASS, 約 0.2 s)。サンプル本体・全ダンプは `evidence/real_machine/`。

### 10.1 検証結果 (実測)

| 検証 | 結果 |
|---|---|
| ① CAB-98 コンテナ writer `assembleFst` 再構成 | **byte 一致 323/323** (イベント列から元ファイルを完全再現) |
| ② tools/flp 独立パーサ | `parseFlp`→`writeFlp` lossless (firstDiff −1)、`parseWrapperData` が 213 を受理 (kind 8, path/vendor/name/guid 復元) |
| ③ イベント列完全ダンプ | FLhd(0x30, 2ch, ppq48) / 199 "11.5.5" / 28=1 / 201 "Fruity Wrapper" / 212 (u32@8=2, u16@16=0 = fx) / 203 "OTT" / 213 (191 B) — **既存モデル (FORMAT §8) と差分 0** |
| ④ 213 wrapper chunk 解析 | u32 8 + 記録 6 本 `[2, 50, 52, 54, 55, 56]`、鎖は 191/191 B を厳密消費 (詳細 §10.2) |
| ⑤ 生成器との照合 | `buildWrapperFst` (サンプル逆抽出 spec) が **byte 一致**。さらに generateDb (OTT VST3 仮想 spec) の `.fst` は実機ファイルと **sha256 まで一致** (`f6942876…`)、その生成 `.nfo` を 49 エントリ検証器と同一の reader 模型 (`entryFromBytes`) が受理 (dropped 無し / rejectedFiles 0 / slot 5) |

→ **FL 実機が DB に置いた `.fst` を自前生成器が byte 一致で再現した初の実証** (CAB-98 では同梱 26 ファイルのコンテナ層まで)。

### 10.2 wrapper chunk 213 の内容 (実測) — VST3 CID を確認

| 記録 | 値 (実測) | 既存モデルとの照合 |
|---|---|---|
| 2 | flags = **0x507D08** = 0x407908 \| 0x400 (64bit のみ) \| 0x100000 | `src/fst.ts` の「64bit 単一ファイル」予測と完全一致。record 2 flags の **実機初観測** (同梱 corpus に wrapper chunk 形式の `.fst` は 0 件 = REPORT §1 の再確認) |
| 50 | plugclass = **7 (VST3 fx)** | `Effects\VST3` 配置と整合 |
| 51 | **無し** | class 7 では 51 を出さない分岐 (FORMAT §8) を実機で初裏取り |
| **52** | **VST3 CID = `5854535654666F547474000000000000`** (raw 16 B) = ASCII **`XTSVTfoTtt`** + NUL×6。GUID text 形 `{56535458-6654-546F-7474-000000000000}` (Windows GUID メモリ配置)、FUID 文字列形 `565354586654546F7474000000000000` [導出] | record 52 が raw TUID 16 B を持つ設計を実機で確認。**CAB-46 (Massive X CID) の突合基準および VST3 hosting の TUID としてそのまま使用可** |
| 54 | `OTT` (拡張子なし basename、`.vst3` を除去) | 既定規則どおり |
| 55 | `C:\Program Files\Common Files\VST3\OTT.vst3` (**バンドルフォルダ**) | §10.3 |
| 56 | `Xfer Records` | — |

CID 取扱いの注意: 公開インデックスではこの CID 値を独立突合できなかった (実機 `.fst` が第一級情報源)。Xfer 公表によると OTT VST3 は v1.33 で導入され **1.33/1.34 には ID 不整合バグがあり 1.35 で修正** — CID は版依存しうるため、本値は「ユーザ環境に導入された版の実測」として扱う。

### 10.3 VST3 path 規則の実機証拠 (H11 / CAB-218 へ)

- 実機配置 `Installed\Effects\VST3\<name>.fst` = class 7 → `Effects\VST3` (FAMILY_DIR 規則) と一致。
- Wrapper が保持する path (record 55) は **バンドルフォルダ形** (`…\VST3\OTT.vst3`、`Contents\x86_64-win\…` を含まない) → generateDb が Serum 2 で既に使っている形と同一。**generateDb の配置規則・path 規則に変更不要**。
- 留意: record 55 は `.fst` 内の値。`.nfo` 側の `ps_file_filename` の実機値は未入手 (同形と推定するが FORMAT §9-3 は未確認のまま)。
- 参考: 実機の DB root は `%USERPROFILE%\Documents\Image-Line\FL Studio\…` (generate.ts の `DEFAULT_DB_PATH` = Public Documents は `%FLPluginDBPath%` 圧縮用の option 値であり、書式への影響なし)。

### 10.4 「.nfo 無し .fst」の意味 (CAB-216 generateDb の優先順位へ)

- **事実**: 実機に `OTT.fst` のみ存在し `OTT.nfo` / `VerifiedIDs.nfo` / `.Plugins.ini` は無かった → `Installed\` 配下に `.fst` 単体が実在しうる、の実例。
- **解釈 [推]**: plugin picker の一覧構築 (`fle:0xaba430`) は `.Plugins.ini` / `Installed\**\*.NFO` 全読みが源泉ゆえ、`.nfo` 無しの OTT は picker には載らないはず。`.fst` 単体で効くのは (a) ブラウザ木のアイテム表示、(b) ダブルクリックでの新規インスタンス生成 (213 の record 55 path から Wrapper が起動可能) まで。プロジェクト読込時の ID 解決 (VerifiedIDs / ID 名 nfo / 名前検索) も `.nfo` 前提。
- **→ 示唆**: generateDb は `.nfo` + `.fst` を両方書く現行方針を維持するのが正 (picker 掲載とプロジェクト解決に `.nfo` が必須)。このサンプルは「.fst 単体でも browser プリセットとしては成立する」ことの実例で、優先順位を変える根拠にはならない。なお実機の FL が実際に OTT を picker 表示していたかは確認不能 (未検証点)。

### 10.5 `specs/wasm_plugins.json` OTT エントリとの差分

実機の登録は **VST3**、spec は **VST2** — 書式の誤りではなく**登録形式の違い**。wasm 版 OTT は VST2 lift (m6〜m10) ゆえ spec を VST2 のまま維持する。OTT.vst3 を hosting する段になったら spec に 1 行追加 (`format: vst3`, `guid: 5854535654666F547474000000000000`, `path: …\VST3\OTT.vst3`) すれば **実機と byte 一致の `.fst` が得られることを本検証で実証済み** (spec 変更は未実施 — CAB-46 の領域と REPORT §0/§5 の実測値保全のため)。

| 項目 | 実機 (VST3) | spec 現行 (VST2) |
|---|---|---|
| 配置 | `Effects\VST3\OTT.fst` | `Effects\VST\OTT.fst` |
| plugclass | 7 | 0 |
| ID 記録 | 52: CID `5854…0000` (`XTSVTfoTtt`) | 51: magic 1483101268 (`XfTT`) |
| 54 名前 | `OTT` | `OTT_x64` |
| 55 path | `…\Common Files\VST3\OTT.vst3` | `…\Common Files\VST2\Xfer Records\OTT_x64.dll` |
| 56 vendor / 203 "OTT" / 212 / FLhd / 199 / 28 | 同一 | 同一 |

### 10.6 成果物と未入手

- 追加: `evidence/real_machine/OTT.fst` (実機サンプル本体, 323 B, sha256 `f694287667fe486d5b9849f162a6712e198c610ebb61b0746af241b93044b3ff`)、`evidence/real_machine/ott_fst_dump.json` (全イベント + 記録列 + CID + 検証結果 + 実機由来 spec からの仮想 `.nfo` 全文)、`analysis/real_fst_check.mjs` (1 コマンド再現)。既存成果物 (src/test/FORMAT.md/specs/evidence 既存分) は無改変。
- **未入手 (§7 継続)**: 実機 v2 `.nfo` (`writeEntry` byte 比較 = 本チケット主眼の残部)、`VerifiedIDs.nfo`、`.Plugins.ini`、VST2 側の実機 `.fst`/`.nfo`。いずれか入手後に本節へ追記する。
