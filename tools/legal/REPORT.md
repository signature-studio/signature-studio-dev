# legal REPORT — LGL-6 一次文書の補完取得 (#89)

自動生成ではない。LEGAL.md (`docs/LEGAL.md`) の「見つからなかった/確認できなかった文書」節
(§7) と台帳 (`[NI-EULA]`・`[SLATE-ToS]` 行) が参照する実測値の正本。

測定 commit: `89e2dad6` (Massive X の読み取りツール `tools/legal/inno_probe/` を追加した commit)。以後 `tools/legal/inno_probe` は変更なし (`git diff 89e2dad6 HEAD -- tools/legal/inno_probe` は 0 行)。Fresh Air と Xfer は素材と外部 URL の実測で、コードに依存しない。
差分 0 の証跡 (本 PR が導入するコード差分。docs と本 REPORT を除く範囲。出力は 0 行):
`git diff origin/main...HEAD --stat -- . ':(exclude)docs' ':(exclude)tools/legal/REPORT.md'`

## 0. 結論

| 対象 | 結論 | 検証状態 |
|---|---|---|
| Native Instruments Massive X の同梱 EULA | **同梱なし** (復号した setup-0 ヘッダに文書名・本文なし。`.dmg` の HFS 内にも文書候補 0 件)。インストーラの CRC 3 種は 6.4.2 の定義と一致せず、完全性は未確認 | LGL-10 (#2498) で実測 (§1-2・§1-3)。fix round 3 の run で再確認 (§1-5・§1-6)。CRC 不一致の原因は未確定 (§1-4) |
| Slate Digital Fresh Air の同梱 EULA | **ファイル名判定では無し** (win zip・pkg のファイル名に `licen\|eula\|agree\|terms` 無し。文書拡張子の通常ファイルは User Guide PDF を含め数件で、PDF 本文は未検索) | 2026-10-14 再測定 (fix round 3 の run、素材 `plugins-freshair`)。§2 の全コマンドを実行。件数: zip 30 エントリ・pkg の Payload 427 ファイル (作業ディレクトリ全体 446 ファイル。定義は §2) |
| Xfer 公式利用規約ページ | **公式ページなし** (候補 URL 12 件 404、トップ・freeware・Serum 2 ページに規約リンク無し) | 2026-10-14 再取得 (fix round 3 の run。§3 の 16 URL と `/license`) |
| Image-Line 承諾版 | 依頼者の記録事項。確認不可 | — |

## 1. Massive X (`plugins-massivex`) — LGL-10 (#2498)

- 素材 (LGL-10 の run): `plugins-massivex.tar.zst` から `Native Instruments Massive X v1.7.1.exe` (1,870,391,792 B) のみ展開 (`tar --zstd -xf` 2.3 s)。fix round 3 の run では exe と `.dmg` の両方を展開し、§1-5・§1-6 を実測 (展開の手順は §1-5)。
- 実行: `python3 tools/legal/inno_probe/inno_probe.py <exe> <header.bin>`。所要 1.07 s (real)、実行前 load average 0.13 / 0.29 / 0.21。fix round 3 の run でも同じ exe に実行し、§1-2 の表と一致した。

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

### 1-5 再確認 (fix round 3 の run、素材 `plugins-massivex`)

- sha256 (exe): `81077730b61fe0c503ffd466dd1350be7bd4f14f48fa8366b23298baadb087ca`。`inno_probe.py` を本 run で実行し、§1-2 の表と一致 (exit 0)。
- 7-Zip 23.01 (`7z l`) と 7-Zip 26.00 (Linux x64。`[7ZIP]` の公式 tar.xz を取得して `7zz` を実行): どちらも `Cannot open the file as archive`。
- stock innoextract 1.9 (`[INNOEXTRACT]`、`-t`): exit 2。ローダの checksum 不一致と版 6.4.2 の未知は警告として出た後、`block header CRC32 mismatch` でヘッダ解析が止まる (1.9 は Inno Setup 6.0.5 まで対応)。
- 調査用ビルド (master `6e9e34ed` に版表の 6.4.2 行を足したもの) は前回 run の記録 (commit `31068167`。本 run では未再実行)。ヘッダ CRC 検査を警告に変えても、次の data block で `block CRC32 mismatch`。調査用ビルドはリポジトリに含めない。
- 平文検索 (`eula|license agreement|end user license`、大小文字無視): exe 全体で 7 件。いずれも 4〜5 文字の断片で、前後はバイナリ (例: `R>sEuLAoT`)。文書名・文面ではない。圧縮データ内は平文検索の対象外のため、これだけでは「無い」とは言えない。
- 別実装の検算: offset table とブロックヘッダの CRC を、`inno_probe.py` とは別に `zlib.crc32` で再計算し、§1-2 と一致 (下のブロック)。

再現 (fix round 3 の run で実行):

```sh
mkdir -p "$RUNNER_TEMP/plugins-massivex" && cd "$RUNNER_TEMP/plugins-massivex" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-massivex.tar.zst"
E="$RUNNER_TEMP/plugins-massivex/Native Instruments Massive X v1.7.1.exe"
sha256sum "$E"
python3 tools/legal/inno_probe/inno_probe.py "$E" > "$RUNNER_TEMP/inno_probe.json"; echo "exit=$?"   # §1-2 の値 (exit 0。JSON は $RUNNER_TEMP に出る)
7z l "$E" 2>&1 | grep -c 'Cannot open the file as archive'        # 期待 1 (7-Zip 23.01)
mkdir -p "$RUNNER_TEMP/sz26" && cd "$RUNNER_TEMP/sz26" && curl -sSL -o 7z2600-linux-x64.tar.xz https://www.7-zip.org/a/7z2600-linux-x64.tar.xz && sha256sum 7z2600-linux-x64.tar.xz && tar -xJf 7z2600-linux-x64.tar.xz   # 期待 c74dc4a4…edc6
"$RUNNER_TEMP/sz26/7zz" l "$E" 2>&1 | grep -c 'Cannot open the file as archive'   # 期待 1 (7-Zip 26.00)
python3 - "$E" <<'PY'
import sys, mmap, zlib, struct
f = open(sys.argv[1], 'rb')
m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
i = m.find(b'rDlPtS')
rev, total, exe_off, exe_usize, exe_crc, hdr, data = struct.unpack_from('<7I', m, i + 12)
print(hex(i), rev, hex(total), total == len(m), hex(hdr), m[hdr:hdr+29], hex(data), m[data:data+4])
p = hdr + 0x40
crc, size, comp = struct.unpack_from('<IIB', m, p)
print(hex(p), hex(crc), size, comp, hex(zlib.crc32(m[p+4:p+9])))
print(hex(struct.unpack_from('<I', m, p+9)[0]), hex(zlib.crc32(m[p+13:p+13+4096])))
print(hex(zlib.crc32(m[p+4:p+9+size])), hex(zlib.crc32(m[p+9:p+9+size])))
PY
timeout 200 grep -a -o -i -E 'eula|license agreement|end user license' "$E" | wc -l   # 平文一致 (fix round 3 の run は 7)
mkdir -p "$RUNNER_TEMP/innox" && cd "$RUNNER_TEMP/innox" && apt-get download innoextract libboost-iostreams1.83.0 libboost-filesystem1.83.0 libboost-program-options1.83.0 libboost-system1.83.0 && for d in *.deb; do dpkg -x "$d" root; done
LD_LIBRARY_PATH="$PWD/root/usr/lib/x86_64-linux-gnu" timeout 300 ./root/usr/bin/innoextract -t "$E"; echo "exit=$?"   # 期待 exit=2・block header CRC32 mismatch
```

### 1-6 `.dmg` (`NI_Massive_X_1.7.1.dmg`、fix round 3 の run で実測)

- sha256: `a5ee2e34def4416c0a9d7554c680c0eb48c14ef43b20e8aa2dfbf0bc81aa4fb0` (1,584,690,730 B)
- HFS (`2.hfs`) 内に `Massive X 1.7.1/` 配下のファイル 26 件 (`7z l -slt` の `Folder = -` の行。ディレクトリ・`2.hfs` の入れ子は数えない)。`massive-X-1.7.1-osx-installer.app` と `Massive.X.1.7.1.expansions.app` (InstallBuilder 製)。文書候補 (`licen|eula|agree|.rtf|.pdf|.html`) は 0 件。
- `Contents/Resources/osx-arm64.dat` 3,077,355 B・`osx-x86_64.dat` 3,169,667 B (各 `.app` に同サイズの 1 組、計 4 件)。InstallBuilder の独自形式で、平文検索では文書が見えない。解読は未実施 (PR 本文の未解決表)。

再現 (fix round 3 の run で実行):

```sh
D="$RUNNER_TEMP/plugins-massivex/NI_Massive_X_1.7.1.dmg"
sha256sum "$D"
stat -c %s "$D"                                                                  # dmg のバイト数 (期待 1584690730)
7z l -slt "$D" | awk '/^Path = /{p=substr($0,8)} /^Folder = -/{ if (p ~ /^Massive X 1\.7\.1\//) print p }' > "$RUNNER_TEMP/dmg_files.txt"
wc -l < "$RUNNER_TEMP/dmg_files.txt"                                             # HFS 内ファイル数 (期待 26)
grep -icE 'licen|eula|agree|\.rtf$|\.pdf$|\.html$' "$RUNNER_TEMP/dmg_files.txt"  # 文書候補の件数 (期待 0)
7z l -slt "$D" | awk '/^Path = /{p=substr($0,8)} /^Size = /{ if (p ~ /osx-(arm64|x86_64)\.dat$/) print $3, p }'   # .dat のバイト数
```

### 1-7 Web 版との同一性

未確認 (同梱版が無いため比較対象が無い)。Web 版 EULA (`[NI-EULA]`、台帳 `ni-eula`) の全文は LEGAL.md §4.4 のとおり検収時に確認済み。

## 2. Fresh Air (`plugins-freshair`)

素材: fix round 3 (2026-10-14) の run で `plugins-freshair.tar.zst` が実在し、`$RUNNER_TEMP/plugins-freshair/` に展開して実測した。

```sh
mkdir -p "$RUNNER_TEMP/plugins-freshair" && cd "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst"
```

- `Fresh Air.Win.zip` (33,932,552 B、sha256 `5a370f02bc84512b896fb38ee38146f1cca0d30319c35ac18430ddda08fb34c8`): 30 エントリ (ディレクトリ 13 + 通常ファイル 17)。文書拡張子 (`pdf|txt|rtf|html`) の通常ファイルは 2 件 (User Guide PDF と `USER Presets/dummy.txt`)。名前判定 (`licen|eula|agree|terms`) は 0 件。
- `Fresh Air.pkg` (36,871,956 B、sha256 `d176b3cf0600169a1333102a5cf4c6d072c6af01f238bfcdb99737dc8c30be5c`): `Distribution` の `<license>` は 0 件。xar 直下に 4 つの子 pkg (`1_-_AU` / `2_-_VST3` / `3_-_APP,_Uninstaller` / `4_-_Content`)。各 `Payload` (gzip cpio) を展開したファイル数は **427**。名前判定は 0 件。文書拡張子の通常ファイルは 3 件 (User Guide PDF、`SlateCore.core/Contents/Resources/tags.txt`、`USER Presets/dummy.txt`)。
- 件数の定義 (WORKFLOW §5): 「427」は **4 つの `Payload` の展開先 (`Payload.d`) にある通常ファイル数** (`find … -path '*Payload.d/*' -type f`。シンボリックリンク 0)。「446」は作業ディレクトリ全体の通常ファイル数 (`find … -type f`) で、427 + xar 直下のメタデータ 19 件 (`[TOC].xml`・`Distribution`・`Resources/en.lproj/Localizable.strings`、子 pkg ごとの `Bom`・`PackageInfo`・`Scripts`・`Payload` の 4 種 × 4) に一致する。Payload の件数としては 427 を正とする。
- 結論: ファイル名判定では同梱 EULA は無い (PDF 本文は未検索)。適用される規約は `[SLATE-ToS]` (オンライン版) のみで、版・適用範囲は未確認 (§7 の「入手元と保有ライセンス」は依頼者の記録事項として残す)。

再現 (fix round 3 の run で実行):

```sh
P="$RUNNER_TEMP/plugins-freshair"
sha256sum "$P/Fresh Air.Win.zip" "$P/Fresh Air.pkg"
python3 -c 'import sys,zipfile; print(len(zipfile.ZipFile(sys.argv[1]).namelist()))' "$P/Fresh Air.Win.zip"   # win zip のエントリ数 (期待 30)
unzip -Z1 "$P/Fresh Air.Win.zip" | grep -vc '/$'                                 # うち通常ファイル (期待 17)
unzip -Z1 "$P/Fresh Air.Win.zip" | grep -ciE 'licen|eula|agree|terms'            # 文書候補の件数 (期待 0)
unzip -Z1 "$P/Fresh Air.Win.zip" | grep -icE '\.(pdf|txt|rtf|html)$'             # 文書拡張子の件数 (期待 2)
W="$RUNNER_TEMP/fa-pkg-check"; rm -rf "$W"; mkdir -p "$W" && 7z x -y -o"$W" "$P/Fresh Air.pkg" >/dev/null   # xar を展開 (子 pkg の Payload が出る)
find "$W" -name Payload -type f | while read -r p; do d="$p.d"; mkdir -p "$d"; gunzip -c "$p" | (cd "$d" && cpio -idm --quiet); done
find "$W" -path '*Payload.d/*' -type f | wc -l                                   # Payload の件数 (期待 427)
find "$W" -type f | wc -l                                                        # 作業ディレクトリ全体 (期待 446 = 427 + 19)
find "$W" -path '*Payload.d/*' -type l | wc -l                                   # シンボリックリンク (期待 0)
find "$W" -path '*Payload.d/*' -type f | grep -ciE 'licen|eula|agree|terms'      # 文書候補の件数 (期待 0)
find "$W" -path '*Payload.d/*' -type f \( -iname '*.pdf' -o -iname '*.txt' -o -iname '*.rtf' -o -iname '*.html' \) | wc -l   # 文書拡張子の件数 (期待 3)
grep -c '<license' "$W/Distribution"                                             # Distribution の license 件数 (期待 0)
```

## 3. Xfer 公式規約ページ

2026-10-14 (fix round 3 の run で取得):

| URL | 結果 |
|---|---|
| `https://xferrecords.com/eula`・`/terms`・`/terms_of_service`・`/legal`・`/end-user-license-agreement`・`/eula-terms`・`/serum2` | 404 |
| `https://xferrecords.com/terms-of-use`・`/ott`・`/products/ott`・`/faq`・`/support` | 404 |
| `https://xferrecords.com/privacy_policy` | 200 (プライバシーポリシー。利用規約の文面ではない) |
| `https://xferrecords.com/` (トップ) | 200。HTML の href に terms / eula / licen / legal / agreement を含むリンク無し |
| `https://xferrecords.com/freeware` | 200。同上 |
| `https://xferrecords.com/products/serum-2` | 200。同上 |
| `https://xferrecords.com/license` | 302 → `https://xferrecords.com/users/sign_in` (200)。追従先の HTML にも terms / eula / licen / legal の文字列無し |

再現 (1 本 + `/license`):

```sh
for u in https://xferrecords.com/{eula,terms,terms_of_service,legal,end-user-license-agreement,eula-terms,serum2,privacy_policy,,freeware,products/serum-2,terms-of-use,ott,products/ott,faq,support}; do printf '%s %s\n' "$(curl -s -o /dev/null -m 20 -w '%{http_code}' "$u")" "$u"; done
curl -s -o /dev/null -m 20 -w '%{http_code} -> %{redirect_url}\n' https://xferrecords.com/license   # 302 -> /users/sign_in
```

結論: 公式の規約ページは確認できなかった (確認日 2026-10-14)。インストーラ版の文面は台帳 `xfer-eula` で保持済み。

## 4. 台帳

本回の run で新たに全文を取得できた規約は無い。台帳 (`docs/LEGAL_TERMS_LEDGER.json`) は変更なし。

## 5. 再測定の条件

- fix round 3 (2026-10-14、本版) の run では `$ARTIFACTS_DIR` に `fl-win64`・`plugins-massivex`・`plugins-freshair`・`plugins-ott` が実在した。`plugins-massivex` と `plugins-freshair` を `$RUNNER_TEMP/` に展開し、§1-5・§1-6・§2・§3 の全コマンドを本 run で実行した。
- 本 run で再実行していないもの: 調査用 innoextract (master `6e9e34ed` + 版表 6.4.2 のパッチ版) の結果 (commit `31068167` の記録)。`.dmg` の `osx-*.dat` の解読 (未実施)。
- `plugins-ott` は本 PR で測定していない (OTT の mac pkg・win の記述は既存の記録のまま)。
- Massive X は `python3 tools/legal/inno_probe/inno_probe.py <展開した exe> [header.bin]` で再測定する (展開先は repo 外)。CRC 不一致の原因は未確定 (§1-4)。
- 再測定の結果が前回と異なる場合は、本ファイルを更新して LEGAL.md 側に影響があるか確認する。
- 同じ値は、§1-5・§1-6・§2・§3 の再現コマンドを同じ素材で実行すれば再確認できる。
