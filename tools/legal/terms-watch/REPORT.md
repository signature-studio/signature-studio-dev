# terms-watch — 各社規約の差分監視 (LGL-5, #88)

> 既知類型との関係 (docs/DEFECTS.md): 該当なし (lift / IR 系ではない)。事実整理であり法的助言ではない (`docs/LEGAL.md` §6 R10・緩和策 5)。

## 結論

`pnpm terms-watch` の 1 コマンドで、各社規約 7 件を **取得 → テキスト化 → 正規化 → SHA-256 比較 → 台帳 (`docs/LEGAL_TERMS_LEDGER.{json,md}`) 更新**し、差分があれば **exit 1** (取得不能は exit 3) で落とす。**7 件すべての基準線が台帳に入った。**
Xfer EULA は公開 Web 版が無く、Win インストーラ (NSIS) のヘッダ内ライセンスページにしか無い。取得機構 (`kind: nsis-license`: NSIS インストーラのヘッダからライセンス文を取り出す) は実 `makensis` 3.09 製の合成インストーラで検証し (§NSIS 取得の検証)、基準線は **実 OTT インストーラ `Install_Xfer_OTT_137.exe` (`plugins-ott`)** から記録した (§Xfer 基準線)。
issue #88 の完了条件「全文書」は満たすが、定期実行・FL 追従への組込が残る (「未解決」表) ため、`Closes` にするかは PM 判断。

## 使い方 (1 コマンド)

```sh
export FL_WIN64_DIR=<fl-win64 展開先>              # docs/WORKFLOW.md §11。未設定/無しなら FL 同梱 2 文書は SKIP (= exit 3)
export PLUGINS_DIR=<plugins-ott 等の展開先>        # Xfer の NSIS インストーラを再帰探索 (--plugins-dir でも可)。無ければ xfer-eula のみ SKIP
pnpm terms-watch                                   # 取得・比較・台帳更新。差分/未レビュー変更で exit 1
pnpm terms-watch -- ack <id|all>                   # 差分を docs/LEGAL.md に反映した後、レビュー済みにする (pnpm は `--` をそのまま渡すので cli.mjs が先頭の `--` を除去する。`pnpm terms-watch ack <id|all>` も可)
pnpm terms-watch -- --only ni-eula --no-write      # 一部のみ・台帳を書かない
pnpm terms-watch:test                              # 単体テスト (素材・外部ネットワーク不要)
bash tools/legal/terms-watch/negative_control.sh   # 実素材でのネガティブコントロール (Web 文書の分はネットワークが要る)
python3 tools/legal/terms-watch/crosscheck.py "$FL_WIN64_DIR"   # 別算法 (Python 標準ライブラリのみ) の検算
bash tools/legal/terms-watch/nsis_e2e.sh           # xfer-eula の取得を実 makensis 製の合成インストーラで検証 (素材不要。makensis は apt-get download で work/ に取得)
python3 tools/legal/terms-watch/crosscheck_nsis.py <installer.exe> [<license.txt>]   # NSIS ライセンス文の別算法 SHA-256
```
Xfer の指定方法 (優先順): `TERMS_WATCH_XFER_EULA` (プレーンテキスト。Serum 2 mac pkg の `Resources/License.txt` 等) → `TERMS_WATCH_XFER_INSTALLER` (インストーラ exe を直接) → `PLUGINS_DIR` 配下の `*.exe` を再帰探索 (深さ 6、内容署名 `Licensee` + `reverse engineering` で選別)。

終了コード: 0 全件一致 (NEW は基準線の記録のみ) / 1 差分あり **または未レビュー変更が残存** / 2 引数不正 / 3 検証不能 (取得失敗・サニティ違反・素材なし)。1 と 3 が同時なら 1。
未レビュー変更は `ack` するまで同一内容でも exit 1 を返し続ける (一度検出した差分が次回実行で握りつぶされない)。`optional: true` の source (Xfer) の素材なしは警告のみ、`--strict` で exit 3、`--allow-skip` は全 SKIP を許容。

## 対象文書 (`sources.json`)

| id | 取得元 | 切出し | 版表記 |
|---|---|---|---|
| `fl-eula-html` | fl-win64 抽出物内の `EULA.html` | 全文 (内容署名 `<title>…IMAGE LINE SOFTWARE EULA` で探す。block 番号に依存しない) | 文書内になし |
| `fl-tou-rtf` | fl-win64 抽出物内の ToU (RTF、インストーラのライセンス画面) | 全文 (署名: `{\rtf1` + `TERMS OF USE`/`Applicability`/`Cracked`) | 文書内になし |
| `fl-tou-web` | `https://www.image-line.com/image-line-software-eula` (中身は Terms of Use) | 見出し `Image Line Terms of Use` 以降 (nav/header/footer/aside/form 除去) | 文書内になし |
| `kilohearts-eula` | `https://kilohearts.com/resources/media_static/documents/eula.pdf` | 全文 (PDF → `uv run --with pypdf==5.9.0`) | `Last updated: YYYY-MM-DD` |
| `slate-audiotonix-terms` | `https://slatedigital.com/terms-of-service/` | 見出し `Audiotonix General Terms of Use` 以降 | 取得したページ本文に日付表記なし |
| `ni-eula` | `https://www.native-instruments.com/pages/end-user-license-agreement` | `END USER LICENSE AGREEMENT` 〜 第三者ライセンス節の直前 | `Latest Version YYYY-MM-DD` |
| `xfer-eula` | Win インストーラ (NSIS 3 Unicode / deflate) のヘッダ内ライセンスページ (`PLUGINS_DIR` 内を署名で探索、または環境変数指定。optional) | 全文 (ヘッダの文字列表から。形式フラグ SF_TEXT / SF_RTF で text / RTF を判別) | 文書内になし |

- 値 (版表記・SHA-256・文字数・取得日) は台帳 `docs/LEGAL_TERMS_LEDGER.md` が正本。本文は保存しない (ハッシュのみ。差分表示用の正規化テキストは gitignore 済み `work/snapshots/`)。
- FL の 2 系統 (EULA.html と ToU) はどちらも文書本文に日付が無い (EULA.html の `<meta name="last-modified">` は 2018 年の雛形値で版表記として使えない) ため、取得日とハッシュだけが手掛かり。
- `fl-tou-rtf` (インストーラ同梱) と `fl-tou-web` (現行公開) は番号・箇条書きの表現が異なり、ハッシュは比較不能。別文書として個別に監視する (FL の新版取り込み時は両方が動く)。

## 正規化規則 (空白・エンコード差の除去)

1. 形式別にテキスト化: HTML (script/style/コメント除去・実体参照復号・ブロック要素の境界のみ改行、インライン要素は空白を挟まない) / RTF (`\'xx` cp1252・`\uN`・段落・リスト番号 `\listtext` を保持、フォント表等の destination を除去) / PDF。
2. 範囲切出し (`start`/`end` 正規表現) の後に正規化: Unicode NFKC → ゼロ幅文字・BOM・ソフトハイフン除去 → 引用符・ダッシュ類を ASCII へ → 連続空白を 1 つに → trim。**大文字小文字は保持** (改定として検出するため)。
3. サニティ (`minChars`・`mustContain`) に違反したら ERROR とし、**台帳には書かない** (エラーページ/ボット壁の基準線化を防ぐ)。
4. SHA-256 (UTF-8)。

## 実測

検証起点: コミット 727d34d (クリーン HEAD の detached worktree で以下すべてを実行)。環境: GitHub Actions runner、node v22.23.3、pnpm 12.10.1、load average 0.20〜0.26 (各実行の開始時点)、並列 1。素材: `fl-win64.tar.zst` 展開 (`extracted/` 25,166 エントリ)・`plugins-ott.tar.zst` 展開 (`Install_Xfer_OTT_137.exe` 8,397,928 B)。

| 項目 | 実測 | 定義 |
|---|---|---|
| 単体テスト | 11/11 PASS、0.95 / 0.96 / 0.96 s (n=3、`node --test` の duration_ms) | `pnpm terms-watch:test` (NSIS 系 3 件・pnpm 経由 argv の回帰 1 件を含む。合成 NSIS バイト列で makensis 不要) |
| 全文書の取得・比較 | UNCHANGED 7、exit 0、2.59 / 2.60 / 2.34 s (n=3、Web 取得 4 件を含む) | `FL_WIN64_DIR=… PLUGINS_DIR=… pnpm terms-watch -- --no-write` (台帳の既存 6 件は a65a73b の基準線のまま不変 = 回帰なし) |
| 台帳の安定性 | 基準線の記録後、同一セッション内 (約 5 分間) に Web 4 文書を含む全文書を 9 回取得して全回 UNCHANGED (a65a73b で測定、a8b0fd6 では未再測定) | 日・週単位の安定性は **未検証** |
| 再実行で台帳が変化しないこと | 書込モードで実行後、`git status --short` が空 | 同日内 |
| FL 同梱文書の探索 | 25,166 エントリ中の `*_DATA.bin` を内容署名で走査、各 1 件に特定 (同一内容の重複は許容、内容違いが複数なら ERROR) | `locateFlFile` |

### 別算法の検算

`crosscheck.py` (html.parser と正規表現 RTF トークナイザ。`lib.mjs` とコード非共有) の SHA-256 が、台帳の `fl-eula-html` / `fl-tou-rtf` と **2/2 一致** (文字数は台帳 `.md` が正本)。Web/PDF 文書は live 内容に依存するため対象外。

### ネガティブコントロール (`negative_control.sh`。実 FL 素材 / 実 Web / 実 OTT インストーラ。727d34d で 14 ケース全件期待どおり、6.49 s)

| 操作 | 期待 | 実測 |
|---|---|---|
| 無改変 | exit 0 | 0 |
| EULA.html と RTF を各 1 語改変 (`decompile`→`decompiles` / `Cracked`→`Cracker`) | 1 | 1 |
| EULA.html のみ 1 語改変 / RTF のみ 1 語改変 | 1 / 1 | 1 / 1 |
| 空白・改行・タブだけ改変 (偽陽性にならない) | 0 | 0 |
| FL 抽出物 dir 無し | 3 | 3 |
| 台帳の SHA-256 先頭 1 文字を改変 (Web 4 文書それぞれ) | 1 ×4 | 1 ×4 |
| 接続不能 URL (ni-eula を `127.0.0.1:9` に差替え) | 3 | 3 |
| xfer: 無改変の台帳 (実 OTT インストーラ) | 0 | 0 |
| xfer: 台帳の SHA-256 先頭 1 文字を改変 | 1 | 1 |
| xfer: `--plugins-dir` が無い dir + `--strict` | 3 | 3 |

単体テスト側で追加確認: ノイズ (nonce・ヘッダ/フッタ)・空白・charset 差 (本文に非 ASCII の é / en dash / € を含み、windows-1252 バイト列と UTF-8 で同一ハッシュ) で UNCHANGED、本文変更で CHANGED→PENDING→`ack`→UNCHANGED、404・短文ボット壁・必須語句欠落で ERROR かつ台帳不変、改変は `diff -u` で表示。

### NSIS 取得の検証 (`xfer-eula`、`nsis_e2e.sh`。実 Xfer インストーラではなく合成物)

方式: Xfer の Win インストーラは NSIS 3.10 Unicode / Deflate・非ソリッド (`tools/targets/serum2/REPORT.md`)、規約は NSIS ヘッダの文字列表にある (`docs/LEGAL.md` §1 `[XFER]`)。7-Zip 23.01 では `7z x` / `[NSIS].nsi` 指定のいずれでもライセンス文を取り出せなかった (実測) ため、`nsis.mjs` が firstheader → raw deflate ヘッダ → 文字列表 (block 3〜4) を自前で解析する。ライセンス文は先頭 1 文字が RichEdit の形式フラグ (SF_TEXT=1 / SF_RTF=2、Unicode ビルドは +0x10) で、makensis 3.09 製の実物で `0x11` を確認した。
検証材料: `makensis` v3.09-4 (Ubuntu noble の `nsis` deb を `apt-get download` + `dpkg -x`、root 不要) で `Unicode true` + `SetCompressor zlib` のインストーラを生成 (7z が `NSIS-3 Unicode / Deflate / Solid=-` と認識)。本文は 2288 文字 (正規化後) の合成文 (日本語・引用符・ダッシュ含む)。実在の規約文ではない。

| ケース (13) | 期待 exit | 実測 |
|---|---|---|
| A text 基準線 NEW / 再実行 UNCHANGED | 0 / 0 | 0 / 0 |
| D: 1 語改変 (`decompiling`→`decompilings`) | 1 (CHANGED) | 1 |
| E: 空白倍化・CRLF・折返し変更のみ | 0 (UNCHANGED) | 0 |
| R: 同一本文を RTF で格納 | 0 (UNCHANGED、text と同一ハッシュ) | 0 |
| C: LZMA 圧縮ヘッダ (dir 探索 / インストーラ直指定) | 3 / 3 (理由付き ERROR) | 3 / 3 |
| A と D が同じ dir (内容違い 2 種) | 3 | 3 |
| `PLUGINS_DIR` 無し / 同 + `--strict` | 0 (SKIP) / 3 | 0 / 3 |
| インストーラ直指定 / プレーンテキスト直指定 | 0 / 0 | 0 / 0 |

- 結果: 13/13 一致。727d34d で 2.35 s (初回、`apt-get download` 込み) / 0.81 s / 0.82 s (n=3)。非 NSIS の exe (乱数 300,000 B) が同じ dir にあっても無視される。
- 別算法: `crosscheck_nsis.py` (Python、zlib + struct。`nsis.mjs` とコード非共有) の抽出ハッシュ = 元 `License.txt` を同規則で正規化したハッシュ = JS の台帳値 (NSIS 経由・RTF 経由・平文直指定)、4 者が `de741d348d8e8b16200248f624b0bbf6885510098031299884c2fc46981970cb` (2288 文字) で一致。
- ネガティブコントロール (a8b0fd6 の複製を破壊して `nsis_e2e.sh`): 文字列表のブロック番号を 4 に変更 → 7 ケース FAIL + ハッシュ不一致 / 署名照合の空白圧縮を外す → E が FAIL (1 件) / 形式フラグ判定を外す (常に text 扱い) → R が FAIL (1 件)。なお文字列表の開始を entries ブロックまで広げる変更は上位集合を読むだけで検出されない (等価変異。許容)。

### Xfer 基準線 (`xfer-eula`、実 OTT インストーラ)

素材 `plugins-ott` の `Install_Xfer_OTT_137.exe` から `PLUGINS_DIR=<展開先> pnpm terms-watch -- --only xfer-eula` で記録 (台帳 `docs/LEGAL_TERMS_LEDGER.{json,md}` の `xfer-eula` 行、origin `nsis:Install_Xfer_OTT_137.exe`)。

| 項目 | 実測 | 定義 |
|---|---|---|
| 取得 | NEW、1914 文字、exit 0。0.008 / 0.009 / 0.008 s (n=3、load average 0.29。CLI 表示の処理時間) | 空の台帳 (`{"schema":1,"docs":{}}`) に対し `cli.mjs check --only xfer-eula --no-write --ledger <空台帳>` |
| 文字数の照合 | `docs/LEGAL.md` §1 `[XFER]` の「1,914 文字」と一致 | 正規化後の文字数 |
| 別算法 | `crosscheck_nsis.py` (Python、`nsis.mjs` とコード非共有) の抽出ハッシュ = 台帳値 (一致) | `python3 tools/legal/terms-watch/crosscheck_nsis.py <installer.exe>` |
| 台帳記録後の再取得 | UNCHANGED、exit 0 | 全文書チェックの行を参照 |
| ネガティブコントロール | 上表 xfer 3 ケース | `negative_control.sh` (`PLUGINS_DIR` 配下に `*.exe` がある時だけ実行) |

検証範囲: 台帳の基準線は OTT win インストーラ 1 本のみ。`docs/LEGAL.md` §1 が記す Serum 2 (win / mac pkg) との一致は本 PR で再検証していない (「未解決」表)。

### 開発中に直した誤り (記録)

pnpm 経由の ack (oc-reviewer 指摘 `b7038ef`・`f4f56fa`・`fda02b5`、修正 3c3cf2a): pnpm 12.10.1 は `pnpm terms-watch -- ack <id>` を `cli.mjs -- ack <id>` として渡す (実測 argv `["--","ack","ni-eula"]`)。`cli.mjs` は先頭の `--` をフラグ扱いして `check` に落とし、`pendingReview` が解除されなかった。先頭の `--` を除去して修正。単体テストは `node cli.mjs ack` を直接呼ぶだけで、この形を踏んでいなかった (回帰テストを追加。修正前の `cli.mjs` では FAIL することを確認)。同時に、charset テストが ASCII のみで非 ASCII の復号を検証していなかった (`decodeBody` が charset を無視する変異を旧テストは検出できず、新テストは検出する) ため、本文に非 ASCII を含めた。


NSIS 取得 (a8b0fd6): (1) `nsis_e2e.sh` の E (空白差のみ) が ERROR になった。内容署名を生テキストに適用しており、`reverse  engineering` (空白倍化) / 行折返しで外れた。空白圧縮後に照合するよう修正 (実規約は折返しを含み得る。FL の EULA.html も `reverse`/`engineer` の間で改行されている)。(2) 探索対象を「100,000 B 以上の exe」にしていたため 99,782 B の合成インストーラが走査 0 件になった。根拠のない下限だったので 4,096 B に下げた。(3) 実装前の下書きで firstheader の `length_of_header` の位置を 24 と書いたが、ダンプ (`5608` = offset 20) との照合で 20 に直した。

FL/Web 系 (a65a73b):

初版の HTML 変換は全タグを空白に置換しており、インラインタグ境界で語が分割された (`<span>Image Line</span>:` → `Image Line :`、`A<span>ny</span>` → `A ny`)。別算法の検算で FL EULA.html が 33332 / 33313 文字で不一致となり発覚。ブロック要素のみ改行・インラインは空白なしに修正し、2/2 一致。また `negative_control.sh` の初版は、EULA.html の改変対象 (`reverse engineer`) が原文では `reverse` と `engineer` の間で改行されており置換が空振りして exit 0 (期待 1) になった。空白改変側も同型の空振りを潜在していたため、改変が空振りしたら異常終了するガードを入れ、対象語を `decompile, disassemble` に変更した。

## 定期実行 (CI-11, #507)

`tools/legal/terms-watch/workflow/terms-watch.yaml` (**未配置**: 実装 run の GitHub App に `workflows` 権限が無く、`.github/workflows/` への push が `refusing to allow a GitHub App to create or update workflow` で拒否された。権限を持つ人が `cp tools/legal/terms-watch/workflow/terms-watch.yaml .github/workflows/terms-watch.yaml` で置く): 毎週月曜 03:17 UTC (`schedule`) + `workflow_dispatch`。素材不要の **Web 4 文書** (`--only fl-tou-web,kilohearts-eula,slate-audiotonix-terms,ni-eula --strict --no-write`) だけを回す。素材を要する `fl-eula-html` / `fl-tou-rtf` / `xfer-eula` は対象外で、FL 新版取り込み手順 (`docs/STATUS.md` MS11) から `pnpm terms-watch` を呼ぶ。
- `ci.sh`: 比較を実行し、exit 0 でも結果 JSON で **4 件すべてが UNCHANGED** でなければ exit 4 にする (NEW・SKIP の見逃し防止)。0 以外は全て job 失敗。`--tamper <id>` は台帳の SHA-256 先頭 1 文字を変えた複製で比較する (台帳本体は書き換えない)。
- `notify.sh`: 失敗時 (`if: failure()`) に、同題の open issue があればコメント、無ければ起票する。通知自体が失敗したら job も失敗のまま。
- `workflow_dispatch` の入力 `negative_control` に id を選ぶと `--tamper` 付きで実行し、job 失敗 + 自動起票 (題は「ネガコン」) を確認できる。
- Slate の 403: 取得は元からブラウザ相当の UA + Accept (`lib.mjs` `BROWSER_HEADERS`)。単体テスト 12 本目で UA が短いと 403 になる模擬サーバに対し取得成功・短い UA で `HTTP 403` を確認 (UA を `Mozilla/5.0` のみに変える変異で 12 本目だけ FAIL)。

実測 (検証起点 ea92a05、クリーン HEAD の detached worktree、runner、node v22.23.3、load average 0.23 (開始時点)、並列 1): 単体テスト 12/12 PASS、1.20 / 0.82 / 0.80 s (n=3、`pnpm terms-watch:test` の実時間)。`negative_control_ci.sh` 8/8 期待どおり、21.28 s (実 Web 取得 4 件 × 6 回を含む)。`notify_test.sh` 6/6、既存 issue 照合を壊した変異で FAIL (exit 1)。変異: UA を `Mozilla/5.0` のみに変えると単体テスト 12 本目だけ FAIL。未実測: Actions 上の実行 (「未解決」表の先頭行)。

| 再現 | 内容 |
|---|---|
| `bash tools/legal/terms-watch/notify_test.sh` | `notify.sh` を偽 `gh` で 6 ケース (既存 issue 無し → create / 同題 open issue 有り → comment / 別題のみ → create / list・create・comment の失敗 → 非 0)。実 issue は作らない |
| `bash tools/legal/terms-watch/negative_control_ci.sh` | `ci.sh` の 8 ケース: 無改変 → 0 / 台帳ハッシュ 1 文字改変 ×4 → 1 / 接続不能 URL → 3 / 台帳に無い文書 (cli は exit 0) → 4 / 引数不正 → 2 |

## 範囲 / 範囲外

検証範囲: 上記 7 文書 (Xfer は OTT win インストーラ) の取得・正規化・比較・台帳更新・終了コードと、Xfer の取得機構 (NSIS ヘッダ解析) の合成インストーラでの動作。範囲外 (主張しない): **Serum 2 の Xfer インストーラ・Serum 2 mac pkg からの取得** (`docs/LEGAL.md` §1 は OTT win / Serum 2 win / Serum 2 mac の 3 者が空白正規化後に一致と記載。本 PR で再検証していない)・NSIS の LZMA / bzip2 / ソリッド圧縮ヘッダ・ANSI (非 Unicode) NSIS・規約文に `$` 変数 (NSIS の内部コード化) を含む場合・mac 同梱文書 (`FL_MAC_DIR`。`docs/LEGAL.md` §1 では win と同一と記載、本 run では未検証)・プラグインインストーラ同梱の EULA (Kilohearts `EULA.txt` 等)・Image-Line の他の Specific Terms (Mobile EULA 等)・日本語等の言語別版・変更の法的意味の判定 (1 文字の誤植修正でも CHANGED になる)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Xfer 基準線は OTT win インストーラ 1 本から記録した。Serum 2 の Xfer インストーラ (win / mac pkg) では取得を未検証 | Serum 2 側だけ規約が改定されても、この 1 本の基準線では検出できない可能性 | #88 にコメント。`oc_artifacts: plugins-serum2` で `PLUGINS_DIR=<展開先> pnpm terms-watch -- --only xfer-eula --no-write` を実行し、UNCHANGED になるか確認 |
| NSIS ヘッダの LZMA / bzip2 / ソリッド圧縮・ANSI ビルド・`$` 変数入りの規約文は未対応 | その形式の Xfer インストーラでは ERROR (exit 3、理由付き) | 本 REPORT の限界。実インストーラで ERROR になったら #88 にコメントし対応を追加 |
| 週次 workflow が `.github/workflows/` に未配置 (App に `workflows` 権限なし)。配置後も PR の workflow は merge 後に初めて有効 (review ジョブは base の workflow)。`workflow_dispatch` のネガコン (台帳ハッシュ改変 → job 失敗 + issue 起票) は merge 後でないと走らせられない | #507 の受入条件 1・3 が未達 (ローカルでの `ci.sh` / `negative_control_ci.sh` は実測済み。`notify.sh` の実 issue 起票は未実測) | #507 に残す。人が workflow を配置して merge 後に `gh workflow run terms-watch.yaml -f negative_control=ni-eula` → run が failure・issue 起票を確認し、起票された issue を close |
| FL 新版取り込み手順の実体が repo に無い (STATUS.md MS11 に `pnpm terms-watch` 呼出を明記しただけ) | 素材を要する 3 文書 (fl-eula-html / fl-tou-rtf / xfer-eula) は人が実行しないと検出できない | MS11 の親チケットで手順化 (#88 にコメント) |
| Slate の 403 は UA 指定で回避済み (`BROWSER_HEADERS`、実測: `Mozilla/5.0` のみ → 403、ブラウザ相当 UA + Accept → 200)。ボット対策がさらに強化されたら取得不能 (exit 3) になり得る | 週次 job が exit 3 で失敗し issue 起票 | 発生したら #88 にコメント |
| Kilohearts PDF の抽出が `uv` と PyPI の `pypdf==5.9.0` に依存 | `uv` 無し/PyPI 不達の環境では ERROR (exit 3) | 本 REPORT の限界 (pypdf を上げると抽出結果が変わり得るため pin を維持) |
| 差分の `diff -u` は旧版スナップショットが手元 `work/snapshots/` にある場合のみ | 新規 checkout/CI ではハッシュ差のみ表示 | 規約本文を commit しない方針の帰結。必要なら CI artifact 保存を `[CI-n]` に含める |
| Web ページ構造変更 (見出し・フッタ) | 切出し失敗 → ERROR、または誤って別範囲を基準線化 | サニティ (`minChars`/`mustContain`) で緩和。`sources.json` の更新で対応 |
