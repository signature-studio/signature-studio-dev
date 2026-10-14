# legal REPORT — LGL-6 一次文書の補完取得 (#89)

自動生成ではない。LEGAL.md (`docs/LEGAL.md`) の「見つからなかった/確認できなかった文書」節
(§7) と台帳 (`[NI-EULA]`・`[SLATE-ToS]` 行) が参照する実測値の正本。

## 0. 結論

| 対象 | 結論 | 検証状態 |
|---|---|---|
| Native Instruments Massive X の同梱 EULA | 未検出 (`.exe` は展開不能、`.dmg` に文書無し) | **前回記録の転記。今回の run では素材未取得のため再測定していない** |
| Slate Digital Fresh Air の同梱 EULA | 未検出 (`7z l` で文書 0 件) | **前回記録の転記。今回の run では素材未取得のため再測定していない** |
| Xfer 公式利用規約ページ | 未発見 (`/eula`・`/terms`・`/terms_of_service` は 404) | 2026-10-14 取得 (レビュー時にも再確認) |
| Image-Line 承諾版 | 依頼者の記録事項。確認不可 | — |

## 1. Massive X (`plugins-massivex`)

前回 (2026-10-14、PR #2375 の検証記録) の内容。素材 `plugins-massivex` を展開して得た値。

- (a) `Native Instruments Massive X v1.7.1.exe`: 1,870,391,792 B。PE / Inno Setup 系。
  - `7z` は開けなかった。
  - `innoextract` 1.9 は「Setup loader checksum mismatch / Unexpected setup data version 6.4.2 / block header CRC32 mismatch」で失敗し、内部ファイル一覧は取得できなかった。
  - 文字列検索 (`EULA` / `license agreement`) では該当の文書名は検出されなかった。
- (b) `NI_Massive_X_1.7.1.dmg`: HFS 内の `Massive X 1.7.1/` 配下は InstallBuilder 製の `*.expansions.app` / `massive-X-1.7.1-osx-installer.app`。
  - `*licen*` / `*eula*` / `*.rtf` / `*.pdf` / `*.txt` は無し (`VR.nfo` のみ)。
- Web 版 EULA (§4.4 of LEGAL.md) との同一性は未確認。

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

- Massive X・Fresh Air の再測定は、`plugins-massivex` / `plugins-freshair` を依頼コメントの `oc_artifacts:` 行で取得した run で行う。
- 再測定の結果が前回と異なる場合は、本ファイルを更新して LEGAL.md 側に影響があるか確認する。
