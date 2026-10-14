# legal REPORT — LGL-6 一次文書の補完取得 (#89)

自動生成ではない。LEGAL.md (`docs/LEGAL.md`) の「見つからなかった/確認できなかった文書」節
(§7) と台帳 (`[NI-EULA]`・`[SLATE-ToS]` 行) が参照する実測値の正本。

測定 commit: `54bacdc0` (main)。コード変更なし (docs のみ・e2e 対象外)。
差分 0 の証跡 (測定 commit から HEAD まで、docs と本 REPORT を除く範囲。出力は 0 行):
`git diff 54bacdc0 HEAD --stat -- . ':(exclude)docs' ':(exclude)tools/legal/REPORT.md'`

## 0. 結論

| 対象 | 結論 | 検証状態 |
|---|---|---|
| Native Instruments Massive X の同梱 EULA | **未確認** (`.exe` は展開不能、`.dmg` に文書名の付いたファイル無し。InstallBuilder の `.dat` は未解読) | 2026-10-14 再測定 (素材 `plugins-massivex`)。7-Zip 26.00 と offset table を追加解析 (§1-1、展開手段は #2498)。fix round 1 では件数の再実行なし (§5) |
| Slate Digital Fresh Air の同梱 EULA | **ファイル名判定では無し** (win zip 30 件・pkg 427 件のファイル名に `licen\|eula\|agree\|terms` 無し。同梱は User Guide PDF のみ。PDF 本文は未検索) | 2026-10-14 再測定 (素材 `plugins-freshair`)。pkg の展開件数は別 run の記録と不一致 (§2・未解決) |
| Xfer 公式利用規約ページ | **公式ページなし** (候補 URL 7 件 404、トップ・freeware・Serum 2 ページに規約リンク無し) | 2026-10-14 再取得 |
| Image-Line 承諾版 | 依頼者の記録事項。確認不可 | — |

## 1. Massive X (`plugins-massivex`)

### 1-1. `Native Instruments Massive X v1.7.1.exe` (1,870,391,792 B)

- Inno Setup 系。ローダの magic `rDlPtS` + 5.1.5 形式の識別子が PE 内 `0x117ef0` にあり、版文字列は `Inno Setup Setup Data (6.4.2)`。
- 7-Zip 23.01 (`7z l`): `Cannot open the file as archive`。7-Zip 26.00 (Linux x64、別 run `ff2cf6ac` で追加) も同じ結果。
- innoextract (`dscharrer/innoextract` master `6e9e34ed`、2025-02-06): 版表に 6.4.2 が無いため、版表に `Inno Setup Setup Data (6.4.2)` (Unicode) を 1 行追加した**調査用ローカルビルド**で試行。
  - 結果 1: `block header CRC32 mismatch` (`Setup loader checksum mismatch!` の警告付き)。
  - 結果 2: ヘッダ CRC 検査を警告に変えた調査用ビルドでも、次の data block で `block CRC32 mismatch` により一覧取得不可。
  - 形式差 (6.4.x のローダ/block 仕様) の可能性が高いが、断定はしない。調査用ビルドはリポジトリに含めない。
  - 別 run (`ff2cf6ac`) の追加解析: ローダの offset table (`rDlPtS`、ファイル内 `0x117EF0`) を innoextract の読み順で解釈すると、`revision=1`・`TotalSize=0x6f7be9f0` (= ファイルサイズ)・`header_offset=0x6f61f3bc` (版文字列 `Inno Setup Setup Data (6.4.2)` の位置)・`data_offset=0x118e00` (先頭 `zlb\x1a`) となる。位置は妥当だが、ローダ CRC は一致しない (innoextract の警告と同じ)。
  - ヘッダ block の先頭 `CRC32=0x8db97b3d` は、続く size・compression の 5 バイトの CRC32 (`0x60a32a0f`) とも、その次の 4096 バイトのチャンク CRC32 (格納値 `0xfd71ceb1`、計算値 `0xaa80f78f`) とも一致しない。6.4.x で block 形式または CRC の範囲が変わった可能性が高いが、確定していない。CRC 範囲の総当たりは時間切れで一致を得られなかった。解明は子 issue #2498 (`[LGL-10]`) に移す。
- 平文検索 (`EULA` / `license agreement`): 文書名は検出されず。ただし圧縮データ内は平文検索の対象外のため、これだけでは「無い」とは言えない。

### 1-2. `NI_Massive_X_1.7.1.dmg` (1,584,690,730 B)

- HFS 内 26 ファイル。`massive-X-1.7.1-osx-installer.app` と `Massive.X.1.7.1.expansions.app` (InstallBuilder 製)。
- `*licen*` / `*eula*` / `*agree*` / `*.rtf` / `*.pdf` / `*.html` に該当するファイルは無し (`VR.nfo` のみ、テキスト)。
- `Contents/Resources/osx-{x86_64,arm64}.dat` (バイト数は未記録。下のコマンドで取る) は InstallBuilder の独自形式で、平文検索では文書が見えない。解読手段を用意していないため未確認。

再現 (`plugins-massivex` を `$RUNNER_TEMP/plugins-massivex/` に展開した run で実行する。本 fix run では素材が無く**未実行**。7-Zip 23.01 が Dmg を開けることは `7z i` で確認のみ):

```sh
D="$RUNNER_TEMP/plugins-massivex/NI_Massive_X_1.7.1.dmg"
stat -c %s "$D"                                                  # dmg のバイト数
7z l -slt "$D" | grep -c '^Path = '                              # HFS 内件数 (先頭の Path はアーカイブ自身。期待 26 + 1)
7z l -slt "$D" | grep '^Path = ' | grep -icE 'licen|eula|agree|\.rtf$|\.pdf$|\.html$'   # 文書候補の件数 (期待 0)
7z l -slt "$D" | grep -E -A4 '^Path = .*osx-(x86_64|arm64)\.dat$' | grep -E '^(Path|Size) = '   # .dat のバイト数
```

### 1-3. Web 版との同一性

未確認。Web 版 EULA (`[NI-EULA]`、台帳 `ni-eula`) の全文は LEGAL.md §4.4 のとおり検収時に確認済み。

## 2. Fresh Air (`plugins-freshair`)

- `Fresh Air.Win.zip` (33,932,552 B): 30 エントリ。文書は `Slate Digital Fresh Air - User Guide.pdf` のみ。他は `unins000.dat` / `unins000.exe` と plugin 本体・プリセット。
- `Fresh Air.pkg` (36,871,956 B, mac): `Distribution` に `<license>` なし。4 つの子 pkg (1_-_AU / 2_-_VST3 / 3_-_APP,_Uninstaller / 4_-_Content) の Payload を展開して 427 ファイル。`licen|eula|agree|terms` の名前のファイルは 0 件。文書は User Guide PDF のみ。
- 別 run の記録 (commit `ff2cf6ac`、2026-10-14 14:46): `7z l` で win zip 30 エントリ・pkg 最上位 25 エントリ。展開物は **446 ファイル** と記録されている。本節の 427 (前回記録) と**不一致**で、計数条件 (どの Payload を数えたか) が未確認。名前検索 (`licen|eula|agreement|terms`) は 0 件。どちらの件数が正しいかは再計数で確定する (未解決)。
- 結論: ファイル名判定では同梱 EULA は無い (PDF 本文は未検索)。適用される規約は `[SLATE-ToS]` (オンライン版) のみで、版・適用範囲は未確認 (§7 の「入手元と保有ライセンス」は依頼者の記録事項として残す)。

再現 (`plugins-freshair` を `$RUNNER_TEMP/plugins-freshair/` に展開した run で実行する。本 fix run では素材が無く**未実行**。下の 2 行 (zip) と Payload 展開ループは合成データで動作確認のみ):

```sh
P="$RUNNER_TEMP/plugins-freshair"
python3 -c 'import sys,zipfile; print(len(zipfile.ZipFile(sys.argv[1]).namelist()))' "$P/Fresh Air.Win.zip"   # win zip の件数 (期待 30)
unzip -Z1 "$P/Fresh Air.Win.zip" | grep -ciE 'licen|eula|agree|terms'                                      # 文書候補の件数 (期待 0)
W="$RUNNER_TEMP/fa-pkg-check"; rm -rf "$W"; mkdir -p "$W" && 7z x -y -o"$W" "$P/Fresh Air.pkg" >/dev/null   # Xar を展開 (子 pkg の Payload が出る)
find "$W" -name Payload -type f | while read -r p; do d="$p.d"; mkdir -p "$d"; gunzip -c "$p" | (cd "$d" && cpio -idm --quiet); done
find "$W" -path '*Payload.d/*' -type f | wc -l                                                              # pkg の件数 (期待 427)
find "$W" -path '*Payload.d/*' -type f | grep -ciE 'licen|eula|agree|terms'                                  # 文書候補の件数 (期待 0)
```

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
| `https://xferrecords.com/license` | 200。店舗ページ (ナビ・カート・サインイン・Privacy Policy のみ)。規約本文・規約リンク無し (別 run `ff2cf6ac` で取得) |
| `/terms-of-use`・`/ott`・`/products/ott`・`/faq`・`/support` | 404 (別 run `ff2cf6ac`) |

fix run (2026-10-14) で同じ 11 URL を再取得し、結果は同一 (404 が 7 件、200 が 4 件)。再現コマンド (1 本):

```sh
for u in https://xferrecords.com/{eula,terms,terms_of_service,legal,end-user-license-agreement,eula-terms,serum2,privacy_policy,,freeware,products/serum-2}; do printf '%s %s\n' "$(curl -s -o /dev/null -m 20 -w '%{http_code}' "$u")" "$u"; done
```

結論: 公式の規約ページは確認できなかった (確認日 2026-10-14)。インストーラ版の文面は台帳 `xfer-eula` で保持済み。

## 4. 台帳

本回の run で新たに全文を取得できた規約は無い。台帳 (`docs/LEGAL_TERMS_LEDGER.json`) は変更なし。

## 5. 再測定の条件

- 再測定は `plugins-massivex` / `plugins-freshair` を `oc_artifacts:` 行 (PR 本文) で取得した run で行い、§1-2・§2 の再現コマンドを実行する。
- 2026-10-14 の fix round 1 では `$ARTIFACTS_DIR` に `fl-win64` のみ実在し (`plugins-massivex` `plugins-freshair` `plugins-ott` は無い)、§1-2・§2 の件数は**再実行していない** (§0 の検証状態は前回・別 run の記録)。
- `plugins-ott` の実測は本 PR に含めない (OTT の mac pkg・win の記述は既存の記録のまま)。
- Massive X の `.exe` を読むには、Inno Setup 6.4.2 の形式に対応した展開手段が要る (§1-1 の試行は未達。解明は #2498)。
