# REPORT 付録 A — nfo §10〜§12 (CAB-215 / CAB-219 / CAB-218 / CAB-46 follow-up)

> 本体: `tools/hostbridge/nfo/REPORT.md`。本書は REPORT.md の §10〜§12.5 (元 391 行版の 120〜226 行) を
> **無変更で分割移動**したもの (250 行上限のため・#437)。節番号は元のまま (他文書の `REPORT §11` 等の参照が有効)。

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

- `analysis/kh_magic_check.mjs` 新設 (**20 checks, exit 0**): ini 抽出 VST2 magic 64 (Effects\VST 55 種) / KH index 突合 45+FrAr / VerifiedIDs 64/64 符号付き 10 進・負値 0 件 (max magic 1802729331 < 2³¹) / VST3 filename 15+164 / OTT・kHs・Serum の installer↔ini size 突合 / 生成 KH 46/46・Serum 2 2 セクション filename 込み一致。`nfo_e2e.sh` に step 追加 — **e2e exit 0 維持** (テスト 39 / 実機照合 21 checks / round-trip 831/831 / 生成 49 entry 受理)。**検収修正**: 初版は相対パス誤り (`../../../../targets/` → 実在しない `<repo>/targets/`) で KH index 突合・kHs/Serum size 突合の 4 check が静的 skip (16 checks 表記は実測 20 から 4 を欠落) — 3 レベル (`../../../targets/`) に修正し全 20 check が実行される。khIndexMatch 出力も hardcode 文字列から実測値 (90/90) に変更。
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

検証: `analysis/mx_check.mjs` 新設 (**19 checks, exit 0**; massivex work/ 資産は existsSync ガードのオプション参照) — 実機セクション突合 / CID 3 源突合 / FUID 規則 / installer 単一ファイル形・moduleinfo 不在 / 生成セクション + VerifiedIDs 行 verbatim 突合。`nfo_e2e.sh` に step 追加 — **e2e exit 0 維持** (tests 39→**40** / 実機 21 checks / CAB-218 20 checks / round-trip 831/831 / 生成 **50 entry・102 ファイル** reader+tools/flp 全受理)。既存節 (§0〜§12.4) は無改変。**検収修正**: 初版は相対パス誤り (`../../../../targets/massivex/work/` → 実在せず) で work/ 依存 9 check (XML 3源突合 / installer 11,602・単一 .vst3 / PE 95,356,824・moduleinfo 不在 / UPID / compat / VST2 dll) が全て静的 skip (10 checks = 19−9) だった — 3 レベルに修正 + XML VST3ID 比較の波括弧不備 (XML 実値は `{}` 無し) + Buffer に matchAll 無しの 3 点を修正し、本機で全 19 check が実行・PASS。
