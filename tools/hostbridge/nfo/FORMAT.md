# FORMAT — FL Studio 26.1.7 Plugin database (`.nfo` / `.fst`) 書式仕様

対象: FL Studio 26.1.7.5653 (win64 `FLEngine_x64.dll`、アドレスは ImageBase 0x400000 の `fle:0x…`)。`PluginManager.exe` は同一 unit を内包 (同じ `ps_*` 文字列と同形の関数 3 本を実測)。
根拠は `evidence/` (Ghidra decompile 抜粋 + 定数表) と `analysis/reproduce.sh` で再生成可能。実装は `src/` (パーサ/ライタ/生成器)、検証は `test/` と `nfo_e2e.sh`。

確度: **[確]** = decompile/定数表で直接確認 + 実装テストあり / **[推]** = コード上の挙動から推定 (直接の実例なし) / **[未]** = 未確認。
実例: `Installed\` 配下の v2 `.nfo` は **抽出物に 0 件** (REPORT §1)。よって v2 の書式は **FL の読み書きコードの解読**に基づく。
**実機照合 (CAB-219, 2026-10-10)**: ユーザ実機の `.Plugins.ini` (406 セクション = 実機 v2 `.nfo` 本文の全量) と `VerifiedIDs.nfo` (236 キー) を取得 — 本書の [確/実機] 印の項目を実ファイルで裏取りし、writer が 406/406 セクションを再現 (REPORT §11, `evidence/real_machine/`)。

## 1. 物理配置 [確]

FL は browser root `0x3fe` に `Presets\Plugin database\` (ユーザ) と `Data\Patches\Plugin database` (システム) を登録する (`fle:0x9db5b0`)。ユーザ側の下に PluginManager が書く:

```
Presets\Plugin database\
  Installed\
    VerifiedIDs.nfo                      ← ID → nfo 相対パス表 (任意キャッシュ, §6)
    .Plugins.ini                         ← 全 nfo をまとめた INI キャッシュ (任意, §6)
    Effects\  | Generators\              ← fx / gen で分岐 (fle:0x8f05d0, 0xab9200)
      VST\  VST3\  AudioUnit\  CLAP\     ← plugclass → フォルダ (fle:0x8f0300)。Fruity\ は natives 用 (走査はディレクトリ, §7)
        <name>.fst  <name>.nfo           ← 1 プラグイン = 1 組 (小文字拡張子, fle:0xab8e60 / 0xabba70)
      New\                               ← 新規検出分のコピー (fle:0xabba70 末尾, 0xab9b10)
    <fmt>\<id>[ [64bit]].NFO             ← ID 名の nfo (任意, §6)
```

- `<name>` = プラグイン名の無害化: `\ / | ? * " < > :` → `-`、先頭 `.` → `-` (`fle:0x8f0740`) [確]。拡張子は `LCMapStringW(LOWERCASE)` で小文字化 (`fle:0x450560`) → `.nfo`/`.fst` [確]。読込側の探索は `.NFO`/`.FST` (大文字) 定数も使う (`fle:0x8f05d0`, 0xab8e60) → **仮想 FS は大文字小文字非区別が必要** [確]。
- 同梱 (システム) の `Data\System\Plugin databases\…` は別物: ブラウザ並び替え用の木で、`.nfo` は `Bitmap=`/`Tip=`/`IconIndex=` 等の汎用 info (`ps_*` は 0 件)、`.fst` は FL 同梱 native の既定状態。

## 2. `.nfo` の文法 (value file) [確]

プレーンテキストの `key=value` 行 (Delphi `TStringList.Values` 風)。実装: `src/valuefile.ts`。

| 項目 | 規則 | 根拠 |
|---|---|---|
| 行区切り | CRLF で書く / 読みは CR・LF・CRLF 混在可。末尾 EOL は任意 (同梱 831 件中 765 件は EOL なし 1 行) | `fle:0x913720` LoadFromFile / 同梱実測 |
| キー検索 | 行頭から最初の `=` までがキー、**大文字小文字非区別**、最初に一致した行が勝つ。値は `=` 直後〜行末 (trim なし) | `fle:0x65de10` (両辺 upper 化して比較)。同梱に `ps_Vendorname` 5 件 |
| コメント | 行頭が `'` の行は無視 | 同上 (`*line != 0x27`) |
| 整数 | Delphi `StrToIntDef` (10 進 / `$hex` / `0x`、不正 → 既定値)。int64 は `StrToInt64Def` | `fle:0x43aae0`, `0x43abf0` |
| 文字コード | ASCII のみ実測 (同梱 831 件すべて ASCII)。BOM は TStringList が判別 (UTF-8/16)、BOM 無しは ANSI [推]。生成器は非 ASCII 時に UTF-8+BOM | [推] |
| 書込 | `key=value` を追記 (`%s=%s`)。既定値の項目は書かない | `fle:0x913360`, `0x914780`, `0x914880` |

## 3. `fileversion=2` (indexed 形式) のキー [確]

ファイル単位キーは `<base>_<i>` (`i` = 0 起点の file index; 接尾辞は `"_"+IntToStr(i)`, `fle:0x9138a0`)。リーダ `fle:0x910cd0`/`0x911e10`、ライタ `fle:0x911940`+`0x913f40` (出力順どおりに表記)。

| key | 型 | 既定 (書込省略条件) | FL が必須か (読込時) |
|---|---|---|---|
| `fileversion` | int | 読込既定 1。書込は常に `2` | 2 でなければ v1 経路 (§4)。2 以外の未知値は無視されエントリ空 |
| `iconindex` / `color` / `tip` | 48 / `$40B6F6` / `"<fmt> / <bits> bit"` | runtime flag 8 (= "new") の時のみ書く | 不要 (browser 装飾) |
| `ps_name` | str | 空なら省略 | 任意 (表示名) |
| `ps_presetfilename` | path | 空なら省略。DB 内は `%FLPluginDBPath%\…` | **新規インスタンス生成に必要** [推]。空で `fallbackFst` なら `<nfo>.fst` を採用 (`fle:0x910cd0` param_4) |
| `ps_files` | int | 0 なら省略 | **必須**: 0 / 欠落 → ファイル 0 件 → エントリ破棄 |
| `ps_file_name_i` | str | 空なら省略 | 任意 |
| `ps_file_filename_i` | path | 空なら省略。`%FLPath%` 圧縮あり | ロードに必要。FL 配下パスは `%FLPath%\…` |
| `ps_file_plugclass_i` | int | −1 なら省略 | **必須**: 欠落 → −1 → そのファイルは破棄 |
| `ps_file_type_i` | int | 0 なら省略 | **1 or 2 のみ有効**、他は 0 に丸める (mask 0x06)。1=effect 強制、2=generator 強制、0=class で判定。実機スキャナは検証済 (scanflags=1) エントリに **常に 1 (fx) / 2 (gen)** を書く (406 セクション中 363、未検証 stub のみ 0) [確/実機] |
| `ps_file_bitsize_i` | 32/64 | 常に書く | 任意。`64` 以外は 32bit (内部値 2=32bit, 3=64bit) |
| `ps_file_arch_i` | str | 空なら省略 | 任意。`Intel`/`Apple`/`Apple + Intel` (0=空)。**実機 Windows でも常に `Intel`** (407/407) [確/実機] |
| `ps_file_magic_i` | int32 | 0 なら省略 | VST2 の uniqueID。**符号付き int32 の 10 進** (`'XfTT'`=1483101268)。範囲外は 0。≥2³¹ は負値表記 (writer `IntToStr(Integer)`, §9-2 [推]) |
| `ps_file_guid_i` | `{GUID}` | null GUID なら省略 | VST3 class id。不正文字列は null 扱い (FL は例外)。**VST2 エントリにも書かれる**: 実機は疑似 GUID `ASCII("VST"+magic4文字(BE)+小文字名)` を 16B に NUL 詰め (実機 64/64, `vst2PseudoGuid`) [確/実機] |
| `ps_file_date_i` | int64 | 0 なら省略 | スキャナの変更検出。**実体 = 最終書込時刻の Delphi TDateTime (double, 元期 1899-12-30) の IEEE754 ビット再解釈を 10 進表記** (実機 407/407 が 2015-10-22〜2026-09-29 の TDateTime に整合; 例 `4676583981019826458` = 2026-07-07 19:48:06) [確/実機] |
| `ps_file_size_i` | int64 | 0 なら省略 | 任意 (同上) |
| `ps_file_scanflags_i` | int | 0 なら省略 | 任意。disk 1,2,0x10,0x20 ↔ 内部 1,2,4,0x10 (`fle:0x910590/0x910530`)。内部 8 は runtime のみ (new) |
| `ps_file_vendorname_i` | str | 空なら省略 | 任意 |
| `ps_file_category_i` | str | 空なら省略 | 任意 |
| `ps_file_idstring_i` | str | 空なら省略 | CLAP の plugin id (record 58 の元) |
| `ps_compatibility_i` | list | 空なら省略 | 任意。`TStrings.DelimitedText` (区切り `,` 引用 `"`, 非 strict)。実機では **別版 CID の別名リスト** (Splice INSTRUMENT: 自 CID + 4 個の旧 CID) — VerifiedIDs は compat の GUID にも 1 キーずつ作る (→ §6) [確/実機] |

**エントリの採否** [確]: 読込後、`slot = f(plugclass, bits)` が −1 のファイルは捨てられ (`fle:0x8f6990`)、ファイル 0 件のエントリは破棄 (`fle:0x910cd0` 末尾)。slot: Fruity(2,3) 32/64 → 0/1、VST(0,4) → 2/3、VST3(7,8) → 4/5、**AU(9,10) と CLAP(11,12) は 64bit のみ** → 6 / 7、DX(1,5)・class 6・13+ は常に −1。
同じ slot に 2 ファイルは入らない (後勝ち: `fle:0x8f49e0` が既存を `Remove`)。

### 3.1 plugclass [確] (`fle:0x8ef860` 名称、`0x8f0ab0` fx/gen 変換)

| 値 | 0 | 1 | 2 | 3 | 4 | 5 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 意味 | VST fx | DX fx | FL fx | FL gen | VST gen | DX gen | VST3 fx | VST3 gen | AU fx | AU gen | CLAP fx | CLAP gen |

fx/gen の組は (0,4)(1,5)(2,3)(7,8)(9,10)(11,12)。`Effects\`/`Generators\` の振り分けと `.fst` の `212` の gen フラグはこの値で決まる。6 は未使用。

## 4. `fileversion=1` (legacy, 単一レコード) [確: 読込のみ]

`fle:0x910810`: `ps_vendorname, ps_magic, ps_guid, ps_plugclass, ps_category, ps_scanflags` + `ps_pluginfilename_{fl, vst_32, vst_64, vst3_32, vst3_64}` から最大 5 ファイルへ展開する。`ps_plugclass` が {0,1,2,7,9,11} なら fx、他は gen 側の class へ (`fle:0x8f0ab0`)。FL 26.1.7 のライタは v2 のみ書く。

## 5. native の `Plugin.nfo` [確]

`Plugins\Fruity\{Effects|Generators}\<dir>\Plugin.nfo` は `ps_vendorname` (+ 任意 `ps_dummy64bit=1`) だけを読む (`fle:0xabe970`)。同梱 141 件は全て `ps_vendorname=Image-Line` (5 件は `ps_Vendorname`、2 件に `ps_dummy64bit=1`)。**native は DB を経由せず** `fle:0xabf130` が `Plugins\Fruity\{Effects,Generators}\*\` を走査し、`<dir>.dll` / `<dir>_x64.dll` (無ければ `FruityPlug*.dll`) の存在で 32/64bit のファイルを作る (class 2/3、`Plugin.nfo` から vendor)。

## 6. 補助ファイル (キャッシュ) と ID 参照

| ファイル | 内容 | 確度 |
|---|---|---|
| `Installed\VerifiedIDs.nfo` | value file。キー `"<fmt>:<32\|64>:<id>"` (**bits が id の前**, 実機 236/236) → 値 = `Installed\` からの相対 nfo パス (`ChangeFileExt(<fst>, ".NFO")`, `fle:0xabb500`+`0x8f15a0`)。`fmt` ∈ {VST, VST3, AU, CLAP, FL, DX} (`fle:0x8ef860`)。読込は 9155c0 (TValueFile, 一定間隔で再読込)。**id の文字列表現 [確/実機]**: VST = `ps_file_magic` の 10 進 (64/64), VST3 = `ps_file_guid` の `{GUID}` テキスト (171/171), CLAP = plugin id 文字列。**対象 = scanflags=1 かつ native 以外のエントリすべて** (実機: 236 キー → 223 nfo; compat GUID は 1 GUID = 1 キー)。実機ファイルは ASCII/CRLF/末尾 CRLF/236 行 | キー形・値形・id 表現・対象集合 [確/実機] |
| `Installed\.Plugins.ini` | `TMemIniFile`。**セクション名 = `Installed` 相対の `<sub>\<name>` (拡張子なし)**、中身は同じ `ps_*` 行 — **`.nfo` 本文と同一** (書込 `fle:0x912d10` が `.nfo` 用 `0x913f40`/ヘッダ部 `0x911940` と同じ関数を呼ぶ)。**文字コード = UTF-8 + BOM (中身が全 ASCII でも BOM 付き)、CRLF、各セクション (最終を含む) の後ろに空行 1 行** [確/実機]。セクション順 = 内部リスト順 (実機では最近スキャンした Serum 2 が先頭、以後 Fruity が alphabetical 等) [推]。無い時 FL は `Installed\**\*.NFO` を全読みして作り直す (`fle:0xaba430` → `0xab9f40` → `0xabaf70`)。実機 406 セクション / 407 ファイル / 214,350 B — **native Fruity 139 (Installed 外の `.nfo` を持たない) も含む**。検証済 (scanflags=1) エントリは `type=1/2`・`arch=Intel`・`date`/`size` 実値入り、未検証 (scanflags=2/0x22) は `type`/`guid`/`vendor`/`category` を欠く stub | 構造・文字コード・本文同値・空行規則 [確/実機] / セクション順 [推] |
| `Installed\VST\<magic 10進>[ [64bit]].NFO`, `Installed\VST3\{GUID}[ [64bit]].NFO` | ID 名の nfo の存在検査 (`fle:0x914a20`, `0x916710`) | パス規則 [確] / 実運用での作成者 [未] |
| 参照文字列 (FLP 内の plugin 参照) | `<path>\|class=N\|magic=N\|guid={…}` (`fle:0x915220` 書, `0x914ca0` 読: キー `class,name,guid,vstid,id`) | [確] |

プロジェクト読込時の探索順 (`fle:0x915750`, `0x916280`, `0x916710`) [確]: ① VerifiedIDs (キー=class 名+ID) → ② ID 名 nfo / `.Plugins.ini` セクション → ③ `<ファイル名>.NFO` を `Installed\` 下で名前検索して `0x910cd0` で直読み。①②が空でも ③ で救われる。

## 7. FL がいつ何を読むか [確: 呼出元の実測]

| 契機 | 関数 | 読むもの |
|---|---|---|
| 起動時/再走査後のプラグイン一覧構築 | `fle:0xaba430` | `.Plugins.ini` → 無ければ `Installed\**\*.NFO` 全部 (`0x910cd0`) → `.Plugins.ini` を再生成 |
| Fruity (native) 列挙 | `fle:0xabf130` | `Plugins\Fruity\…\Plugin.nfo` (`0xabe970`) |
| プロジェクト/FST から plugin 参照を解決 | `fle:0x915750` | VerifiedIDs.nfo / ID nfo / 名前検索 → `0x910cd0` |
| ブラウザ項目 (`.fst`) の情報表示 [推: 用途は呼出元の形から推定] | `fle:0x108aad0` | 兄弟の `<name>.NFO` (`0x910cd0`): vendor, category, `"<fmt> / <bits> bit"` |
| 新規インスタンス作成 | (`ps_presetfilename` の `.fst`) | `.fst` を通常の plugin-state として投入 → Fruity Wrapper が chunk を読む |
| スキャン (外部 `PluginManager.exe`) | `fle:0xabba70` 相当 | 書込側: `.fst` 生成 (`0xaba880`) → `.nfo` (`0x911940`) → `.Plugins.ini` セクション (`0x912d10`) → `New\` へコピー |

## 8. `.fst` (plugin-state, Fruity Wrapper 配下の VST/CLAP/AU) [確: 構造 / 推: 個別フラグ意味]

FL 自身の書込 (`fle:0xaac300` → `0xaac1e0` → `0xab8ae0` → `0xa9eff0`)。同梱 `Data\System\Plugin databases` の FL 11.5.5 書込 26 ファイルで構造一致 (コンテナ層は **26/26 byte-exact 再構成**):

```
"FLhd" u32=6  { u16 format=0x30, u16 nChannels=2, u16 ppq=48 }  "FLdt" u32 len
 199 TEXT "11.5.5\0"                    FlVersion (ASCII)
  28 BYTE 1                             (DB 生成経路は常に 1: aba880 が param_4=0 を渡す)
 201 TEXT UTF-16LE "Fruity Wrapper\0"
 212 DATA 52 B: 0 …, u32@8 = 2, u16@16 = 0x10 (generator) | 0   (残り 0)
 203 TEXT UTF-16LE <表示名>\0           (内部名と異なる時のみ = 常に出力)
 213 DATA wrapper chunk
```
wrapper chunk (`0xa9eff0`, `tools/flp` の `parseWrapperData` で再パース可): `u32 8` (**format version**: Wrapper が受理するのは 5–12、Wrapper 自身の writer は 12、FL 11.5.5 の DB writer は 8。kind ではない — H10 `tools/hostbridge/h10/REPORT.md` §2) に続き `{u32 id, u64 size, payload}`:

| id | size | 内容 | 出現条件 |
|---|---|---|---|
| 2 | 25 | `u8 0; i32 −1; i32 −1; u32 flags; u32 0; u8 1; 0…` flags = `0x407908` \| `0x400` (64bit のみ) \| `0x100000` (32+64 の両方は無い) | 常に |
| 50 | 16 | `u32 plugclass`, 残り 0 | 常に |
| 51 | 4 | VST2 uniqueID (u32 LE) | class 0,4 / AU 等の既定分岐 |
| 52 | 16 | VST3 class id (`ps_file_guid` と同じ 16 B) | class 7,8 / 既定分岐 |
| 58 | n | CLAP id (ANSI) | class 11,12 |
| 54 | n | 名前 = **ファイル名の拡張子なし basename** (CLAP は plugin 名) | 非空の時 |
| 55 | n | プラグインのパス (複数ファイル entry では出さない) | 非空の時 |
| 56 | n | vendor | 非空の時 |
| 53 | n | プラグイン state (`effGetChunk`) | 持つ時のみ。DB 生成では出さない |

文字列は ANSI コードページ (version ≤ 8; version ≥ 9 は UTF-8。ASCII なら同一) で NUL なし。**生成器は version 8 (既定) では ASCII 限定 (非 ASCII は例外)、非 ASCII は version 9–12 を opt-in (`chunkVersion`)** — 根拠・shimx `CP_ACP` 実測は `tools/hostbridge/h10/REPORT.md` §9 (#549)。レコード意味 (2 の各 flag の意味、212 の u32@8) は構造は確定、**意味付けは推定**。実プロジェクトに入るレコード (1, 30, 31, 32, 53, 57 等) は Wrapper 側が自分の保存時に足す (FL 書込の DB `.fst` には無い)。**Wrapper の reader (`fw:0x875af0`) は 1, 2, 30, 31, 32, 50–58 の 14 id だけを読み、未知 id は読まずに skip、欠落は既定値**(1 = MIDI port −1/−1、30 = 未使用、31/32 = 0 件で plugin 既定 routing、50 = **0 (VST2 fx)**、57 = 1、53 無し = 既定 state)。**id 57 は VST2 hint ではなく `effGetVstVersion` (opcode 58) の戻り値** で、bitness 不一致時のみ使われる。hint (`TVSTPlugin` 第 6 引数) の供給元は存在しない (呼出元 1 件・定数 0)。212 の `u16@16`: **0x10 = generator** (`fle:0xf54900` が 0x31/0x32 の種別判定に使用)、**0x80 は DB 生成経路では立たない** (`fle:0xaac300` 第 4 引数 = 0)。根拠・検証は `tools/hostbridge/h10/REPORT.md`。

## 9. 未確認 [未]

1. `Installed\` の **実機 `.nfo` / `.fst` 単体ファイル** (本文は `.Plugins.ini` セクションと同一と強く推定 — CAB-219 で 406 セクションの writer 再現まで確認済; ファイル自体は REPORT §7 の依頼継続)。
2. `ps_file_date` の**単位は解決** (TDateTime double bits, §3)。残: VST2 `magic` の負値 (≥2^31) の VerifiedIDs 10 進表記 — **符号付き 10 進と推定 [推]**: writer `fle:0x914780` は int32 値を `IntToStr(Integer)` (`fle:0x43a7e0`) で整形するため ≥2^31 は負値表記になり、reader 側 `StrToIntDef` は 2^31 以上の無符号リテラルを Integer に丸められない (既定値 0) — 符号付き以外では自己往復しない。実機 64 magic は全て <2^31 (max 1802729331) で負値の実例は無し (CAB-218)。
3. ~~VST3 バンドルの `ps_file_filename`~~ → **CAB-218 で規則確定 [確/実機+静的]**: `ps_file_filename` = **FL が LoadLibraryW で直接消費する「ロード可能モジュールファイル」のパス**。根拠: (a) QuickFontCache `CreateVST3Instance` (qfc:0x58a200) → `TVST3Instance` は与えられたパスをそのまま `LoadLibraryW` し (qfc:0x58a3d0→0x41d910)、qfc 内に `Contents`/`x86_64-win` の文字列は**皆無** (バンドル解決は最終 hop に存在しない); (b) Wrapper `TVST3Plugin.LoadPlugin` (fw:0x84ad90) も plugin record の filename バッファ (+0x20e, 261 wchar) を**無変換で** `CreateVST3Instance` へ渡す; (c) 実機 179 VST3 entry は全てモジュールファイルを指す — 単一ファイルモジュール形 164 (`…\OTT.vst3` — OTT 1.37 インストーラは `…\VST3\OTT.vst3` を**単一ファイル**として同梱, 実測 3,244,032 B = ini `ps_file_size` 一致; kHs 45 種 247,296 B = winpkg 単一ファイル `.vst3_64` 一致) とバンドル内部バイナリ形 15 (`…\Serum2.vst3\Contents\x86_64-win\Serum2.vst3` — Serum 2.1.5 インストーラの実配置, 内部バイナリ 19,236,864 B = ini 一致)。**writer 規則**: 仮想 FS に単一ファイルで置くなら `<dir>\<Name>.vst3`、バンドル配置なら `<dir>\<Name>.vst3\Contents\x86_64-win\<Name>.vst3` を書く (generateDb の Serum 2 は実機一致の内部バイナリ形に修正済み)。`.fst` record 55 は `ps_file_filename` と同値 (OTT 実機 `.fst` = ini と同じ単一ファイル形)。旧「バンドルフォルダ形」呼称は誤解を招くため本書では「モジュールファイル形」に改称。
4. `tip` 文字列の厳密な生成 (`fle:0x8f58b0`) と `New\` の運用 (本生成器は不使用)。実機 `tip=VST3 / 64 bit`・`color=$40B6F6`・`iconindex=48` は §3 既定値どおり [確/実機]。
5. ~~Kilohearts VST2 uniqueID~~ → **CAB-218 で実測確定 [確/実機]**: KH 46 種 (kHs snapin 38 + Carve EQ/Disperser/Faturator/Multipass/Slice EQ/Snap Heap + Phase Plant + Fresh Air) の実機 magic は **product_index.json の 4 文字 id と 45/45 完全一致** (`ksbc`/`kdsp`/`ksge`/`kphp`…、BE で magic 値に読む)。旧「id とは別物」は誤り (訂正)。VST2 category は実機準拠で Effect (44 fx) / Synth (Phase Plant, 唯一の KH generator) — `cli/gen.ts` と spec `_note` に反映、機械検証は `analysis/kh_magic_check.mjs`。Fresh Air は vendor=**Slate Digital** / category=Effect (実機)。
