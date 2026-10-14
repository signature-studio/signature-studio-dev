# legal REPORT — LGL-6 一次文書の補完取得 (#89)

自動生成ではない。LEGAL.md (`docs/LEGAL.md`) の「見つからなかった/確認できなかった文書」節
(§7) と台帳 (`[NI-EULA]`・`[SLATE-ToS]` 行) が参照する実測値の正本。

測定 commit: `54bacdc0` (main)。コード変更なし (docs のみ・e2e 対象外)。

## 0. 結論

| 対象 | 結論 | 検証状態 |
|---|---|---|
| Native Instruments Massive X の同梱 EULA | **未確認** (`.exe` は展開不能、`.dmg` に文書名の付いたファイル無し。InstallBuilder の `.dat` は未解読) | 2026-10-14 再測定 (素材 `plugins-massivex`) |
| Slate Digital Fresh Air の同梱 EULA | **なし** (win zip 30 件・pkg 427 件に文書無し。同梱は User Guide PDF のみ) | 2026-10-14 再測定 (素材 `plugins-freshair`) |
| Xfer 公式利用規約ページ | **公式ページなし** (候補 URL 7 件 404、トップ・freeware・Serum 2 ページに規約リンク無し) | 2026-10-14 再取得 |
| Image-Line 承諾版 | 依頼者の記録事項。確認不可 | — |

## 1. Massive X (`plugins-massivex`)

### 1-1. `Native Instruments Massive X v1.7.1.exe` (1,870,391,792 B)

- Inno Setup 系。ローダの magic `rDlPtS` + 5.1.5 形式の識別子が PE 内 `0x117ef0` にあり、版文字列は `Inno Setup Setup Data (6.4.2)`。
- 7-Zip 23.01 (`7z l`): `Cannot open the file as archive`。
- innoextract (`dscharrer/innoextract` master `6e9e34ed`、2025-02-06): 版表に 6.4.2 が無いため、版表に `Inno Setup Setup Data (6.4.2)` (Unicode) を 1 行追加した**調査用ローカルビルド**で試行。
  - 結果 1: `block header CRC32 mismatch` (`Setup loader checksum mismatch!` の警告付き)。
  - 結果 2: ヘッダ CRC 検査を警告に変えた調査用ビルドでも、次の data block で `block CRC32 mismatch` により一覧取得不可。
  - 形式差 (6.4.x のローダ/block 仕様) の可能性が高いが、断定はしない。調査用ビルドはリポジトリに含めない。
- 平文検索 (`EULA` / `license agreement`): 文書名は検出されず。ただし圧縮データ内は平文検索の対象外のため、これだけでは「無い」とは言えない。

### 1-2. `NI_Massive_X_1.7.1.dmg` (1,584,690,730 B)

- HFS 内 26 ファイル。`massive-X-1.7.1-osx-installer.app` と `Massive.X.1.7.1.expansions.app` (InstallBuilder 製)。
- `*licen*` / `*eula*` / `*agree*` / `*.rtf` / `*.pdf` / `*.html` に該当するファイルは無し (`VR.nfo` のみ、テキスト)。
- `Contents/Resources/osx-{x86_64,arm64}.dat` (約 3 MB) は InstallBuilder の独自形式で、平文検索では文書が見えない。解読手段を用意していないため未確認。

### 1-3. Web 版との同一性

未確認。Web 版 EULA (`[NI-EULA]`、台帳 `ni-eula`) の全文は LEGAL.md §4.4 のとおり検収時に確認済み。

## 2. Fresh Air (`plugins-freshair`)

- `Fresh Air.Win.zip` (33,932,552 B): 30 エントリ。文書は `Slate Digital Fresh Air - User Guide.pdf` のみ。他は `unins000.dat` / `unins000.exe` と plugin 本体・プリセット。
- `Fresh Air.pkg` (36,871,956 B, mac): `Distribution` に `<license>` なし。4 つの子 pkg (1_-_AU / 2_-_VST3 / 3_-_APP,_Uninstaller / 4_-_Content) の Payload を展開して 427 ファイル。`licen|eula|agree|terms` の名前のファイルは 0 件。文書は User Guide PDF のみ。
- 結論: 同梱 EULA は無い。適用される規約は `[SLATE-ToS]` (オンライン版) のみで、版・適用範囲は未確認 (§7 の「入手元と保有ライセンス」は依頼者の記録事項として残す)。

## 3. Xfer 公式規約ページ

2026-10-14 取得:

| URL | 結果 |
|---|---|
| `https://xferrecords.com/eula` | 404 |
| `https://xferrecords.com/terms` | 404 |
| `https://xferrecords.com/terms_of_service` | 404 |
| `https://xferrecords.com/legal` | 404 |
| `https://xferrecords.com/end-user-license-agreement` | 404 |
| `https://xferrecords.com/eula-terms` | 404 |
| `https://xferrecords.com/serum2` | 404 |
| `https://xferrecords.com/privacy_policy` | 200 (プライバシーポリシー。利用規約の文面ではない) |
| `https://xferrecords.com/` (トップ) | 200。規約系リンクは `/privacy_policy` のみ |
| `https://xferrecords.com/freeware` | 200。本文とリンクに EULA / license agreement / terms の文言なし |
| `https://xferrecords.com/products/serum-2` | 200。EULA / licen / terms / legal を含むリンクなし |

結論: 公式の規約ページは確認できなかった (確認日 2026-10-14)。インストーラ版の文面は台帳 `xfer-eula` で保持済み。

## 4. 台帳

本回の run で新たに全文を取得できた規約は無い。台帳 (`docs/LEGAL_TERMS_LEDGER.json`) は変更なし。

## 5. 再測定の条件

- 再測定は `plugins-massivex` / `plugins-freshair` を依頼コメントの `oc_artifacts:` 行で取得した run で行う。
- Massive X の `.exe` を読むには、Inno Setup 6.4.2 の形式に対応した展開手段が要る (§1-1 の試行は未達)。
