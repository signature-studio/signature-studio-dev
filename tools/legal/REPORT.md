# legal REPORT — LGL-6 一次文書の補完取得 (#89)

自動生成ではない。LEGAL.md (`docs/LEGAL.md`) の「見つからなかった/確認できなかった文書」節
(§7) と台帳 (`[NI-EULA]`・`[SLATE-ToS]` 行) が参照する実測値の正本。

## 0. 結論

| 対象 | 結論 | 検証状態 |
|---|---|---|
| Native Instruments Massive X の同梱 EULA | **同梱なし** (復号した setup-0 ヘッダに文書名・本文なし) | LGL-10 (#2498) で実測 (§1-1〜§1-2)。インストーラの CRC 3 種は不一致で原因未確定 (§1-3) |
| Slate Digital Fresh Air の同梱 EULA | 未検出 (`7z l` で文書 0 件) | **前回記録の転記。今回の run では素材未取得のため再測定していない** |
| Xfer 公式利用規約ページ | 未発見 (`/eula`・`/terms`・`/terms_of_service` は 404) | 2026-10-14 取得 (レビュー時にも再確認) |
| Image-Line 承諾版 | 依頼者の記録事項。確認不可 | — |

## 1. Massive X (`plugins-massivex`) — LGL-10 (#2498)

- 測定 commit: `89e2dad6` (読み取りスクリプト `tools/legal/inno_probe/inno_probe.py` を追加した commit。以後コード変更なし)。
- 素材: `plugins-massivex.tar.zst` から `Native Instruments Massive X v1.7.1.exe` (1,870,391,792 B) のみ展開 (`tar --zstd -xf` 2.3 s)。`.dmg` は今回未展開 (前回記録の転記。InstallBuilder 製の `.app` のみで文書なし)。
- 実行: `python3 tools/legal/inno_probe/inno_probe.py <exe> <header.bin>`。所要 1.07 s (real)、実行前 load average 0.13 / 0.29 / 0.21。

### 1-1 形式 (Inno Setup 6.4.2 の公開ソース `jrsoftware/issrc` tag `is-6_4_2` に基づく)

- オフセット表 `TSetupLdrOffsetTable` (44 B・ID `rDlPtS` + 6 B、`TableCRC` は先頭 40 B の CRC-32)。`Shared.Struct.pas`・`Compiler.SetupCompiler.pas`。
- setup-0 = `SetupID` (64 B、`Inno Setup Setup Data (6.4.2)`) + 圧縮ブロック。ブロック = `CRC32(Hdr)` 4 B + `Hdr {StoredSize: 4 B, Compressed: 1 B}` + 格納データ。格納データは「CRC32 4 B + 最大 4096 B」のチャンクの繰り返し (`Compression.Base.pas`)。
- 圧縮は LZMA1。最初の 5 B が props (`lc/lp/pb` の 1 B + 辞書サイズ 4 B、`TLZMA1Decompressor`)。
- 文書の実データ (setup-1) のチャンクは `zlb\x1a` で始まり、`foChunkEncrypted` 時は XChaCha20 (`Setup.FileExtractor.pas`)。setup-0 のヘッダ部は暗号化されない (読み取り側が復号前に読むため)。

### 1-2 実測 (`Native Instruments Massive X v1.7.1.exe`)

| 項目 | 格納値 | 6.4.2 定義での計算値 | 判定 |
|---|---|---|---|
| オフセット表の位置 | 0x117EF0 (ID 1 件) | — | 一意 |
| `TotalSize` | 1,870,391,792 | ファイルサイズ 1,870,391,792 | 一致 |
| `Offset0` (setup-0) | 0x6F61F3BC → `Inno Setup Setup Data (6.4.2)` | — | 一致 |
| `Offset1` (setup-1) | 0x118E00 → `zlb\x1a` | — | 一致 |
| `TableCRC` | 0x0E18DD9B | 0x4659C120 | **不一致** |
| ブロックヘッダ CRC | 0x8DB97B3D (`StoredSize`=287,235、`Compressed`=1) | 0x60A32A0F | **不一致** |
| チャンク CRC | 71 チャンク中 **71 件不一致** (枠は 70×4096 + 231 = 286,951 B で整合) | — | **不一致** |
| LZMA1 復号 | props lc=4 lp=0 pb=2 dict=64 MiB、出力 3,424,540 B、`eof=True` | — | 整合 |

### 1-3 同梱文書の判定 (復号したヘッダブロックの全文字列を検索)

- 文書系の名前 (`eula`・`licen[cs]e`・`agreement`・`readme`・`terms`、または `.rtf`・`.pdf`・`.htm(l)`・`.doc(x)`・`.md`・`.nfo`・`.chm`) を含む文字列は 24 件。すべて Inno Setup 標準の UI メッセージ (多言語の `License Agreement`・`README file` 等) か、パターン文字列 `*.exe,*.dll,*.chm`。配置される文書ファイルは無い。
- `.txt` の配置名は 93 件。すべて Massive X のコンテンツ (`Chordtables\…`・`Harmonizetables\…` 等) で、文書名は無し。
- 40 文字以上の長い本文ブロックは最長 389 文字 (Inno 標準メッセージ)。`[Setup] LicenseFile` 相当の本文は無し。
- 結論: **同梱なし** (EULA 文書も使用許諾本文も含まれない)。Web 版 EULA (§4.4 of LEGAL.md) との同一性比較の対象が無いため、台帳 `ni-eula` への追加はしない。

### 1-4 未確定 (LGL-10 受入 1 の残り)

- 3 種類の CRC (`TableCRC`・ブロックヘッダ CRC・全チャンク CRC) は 6.4.2 の定義 (標準 CRC-32) と一致しない。CRC-32C・BZIP2 系・MPEG-2 系・初期値 0 で反転なし のいずれとも一致しない。**不一致の原因 (素材の改変・別ビルド・未知の CRC 方式) は未確定**。
- 長さ (ブロック長と 71 チャンクの枠) と LZMA の終端 (`eof=True`) は整合するため、不一致は CRC の値のみと見られる。
- 6.4.2 の標準ローダ (`TCompressedBlockReader`) は CRC 不一致で例外を出す。7-Zip・innoextract が開けないのと整合する。本節の内容読みは CRC を検査せずに行ったもので、インストーラの完全性は確認していない。

## 2. Fresh Air (`plugins-freshair`)

前回 (2026-10-14) の内容。素材 `plugins-freshair` を展開して得た値。

- `Fresh Air.Win.zip`: 導入後ツリーを平坦化した形。`unins000.dat` のみ (文書無し)。
- `Fresh Air.pkg` (mac): `Distribution` に `<license>` なし。
- `7z l` の結果で `licen|eula|agreement` に該当するエントリ 0 件。
- 同梱文書は User Guide PDF `Slate Digital Fresh Air - User Guide.pdf` のみ。

## 3. Xfer 公式規約ページ

- `https://xferrecords.com/eula` → 404
- `https://xferrecords.com/terms` → 404
- `https://xferrecords.com/terms_of_service` → 404
- `https://xferrecords.com/privacy_policy` → 取得可 (プライバシーポリシーで利用規約の文面ではない)
- 2026-10-14 のレビュー時にも同じ結果を確認。

## 4. 再測定の条件

- Massive X・Fresh Air の再測定は、`plugins-massivex` / `plugins-freshair` を依頼コメントの `oc_artifacts:` 行で取得した run で行う。Massive X は `python3 tools/legal/inno_probe/inno_probe.py <展開した exe> [header.bin]` (展開先は repo 外)。
- 再測定の結果が前回と異なる場合は、本ファイルを更新して LEGAL.md 側に影響があるか確認する。
