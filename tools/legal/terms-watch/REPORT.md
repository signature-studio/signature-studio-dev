# terms-watch — 各社規約の差分監視 (LGL-5, #88)

> 既知類型との関係 (docs/DEFECTS.md): 該当なし (lift / IR 系ではない)。事実整理であり法的助言ではない (`docs/LEGAL.md` §6 R10・緩和策 5)。

## 結論

`pnpm terms-watch` の 1 コマンドで、各社規約 7 件のうち **6 件を取得 → テキスト化 → 正規化 → SHA-256 比較 → 台帳 (`docs/LEGAL_TERMS_LEDGER.{json,md}`) 更新**し、差分があれば **exit 1** (取得不能は exit 3) で落とす。
**未達: Xfer EULA の基準線が未取得** (公開 Web 版が無く、インストーラ同梱の `License.txt` が要る。素材 `plugins-serum2` 等が本 run に無かった)。issue #88 の完了条件「全文書」を満たさないため PR は `Refs #88`。

## 使い方 (1 コマンド)

```sh
export FL_WIN64_DIR=<fl-win64 展開先>              # docs/WORKFLOW.md §11。未設定/無しなら FL 同梱 2 文書は SKIP (= exit 3)
pnpm terms-watch                                   # 取得・比較・台帳更新。差分/未レビュー変更で exit 1
pnpm terms-watch -- ack <id|all>                   # 差分を docs/LEGAL.md に反映した後、レビュー済みにする
pnpm terms-watch -- --only ni-eula --no-write      # 一部のみ・台帳を書かない
pnpm terms-watch:test                              # 単体テスト (素材・外部ネットワーク不要)
bash tools/legal/terms-watch/negative_control.sh   # 実素材でのネガティブコントロール (Web 文書の分はネットワークが要る)
python3 tools/legal/terms-watch/crosscheck.py "$FL_WIN64_DIR"   # 別算法 (Python 標準ライブラリのみ) の検算
```

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
| `xfer-eula` | 環境変数 `TERMS_WATCH_XFER_EULA` のファイル (optional) | 全文 | — (**基準線未取得**) |

- 値 (版表記・SHA-256・文字数・取得日) は台帳 `docs/LEGAL_TERMS_LEDGER.md` が正本。本文は保存しない (ハッシュのみ。差分表示用の正規化テキストは gitignore 済み `work/snapshots/`)。
- FL の 2 系統 (EULA.html と ToU) はどちらも文書本文に日付が無い (EULA.html の `<meta name="last-modified">` は 2018 年の雛形値で版表記として使えない) ため、取得日とハッシュだけが手掛かり。
- `fl-tou-rtf` (インストーラ同梱) と `fl-tou-web` (現行公開) は番号・箇条書きの表現が異なり、ハッシュは比較不能。別文書として個別に監視する (FL の新版取り込み時は両方が動く)。

## 正規化規則 (空白・エンコード差の除去)

1. 形式別にテキスト化: HTML (script/style/コメント除去・実体参照復号・ブロック要素の境界のみ改行、インライン要素は空白を挟まない) / RTF (`\'xx` cp1252・`\uN`・段落・リスト番号 `\listtext` を保持、フォント表等の destination を除去) / PDF。
2. 範囲切出し (`start`/`end` 正規表現) の後に正規化: Unicode NFKC → ゼロ幅文字・BOM・ソフトハイフン除去 → 引用符・ダッシュ類を ASCII へ → 連続空白を 1 つに → trim。**大文字小文字は保持** (改定として検出するため)。
3. サニティ (`minChars`・`mustContain`) に違反したら ERROR とし、**台帳には書かない** (エラーページ/ボット壁の基準線化を防ぐ)。
4. SHA-256 (UTF-8)。

## 実測

検証起点: コミット a65a73b (クリーン HEAD の detached worktree で実行)。環境: GitHub Actions runner、node v22.23.3、load average 0.09〜0.16、並列 1。素材: `fl-win64.tar.zst` 展開 (`extracted/` 25,166 エントリ)。

| 項目 | 実測 | 定義 |
|---|---|---|
| 単体テスト | 7/7 PASS、0.68 / 0.71 / 0.69 s (n=3) | `pnpm terms-watch:test` |
| 全文書の取得・比較 | UNCHANGED 6 / SKIP 1 (xfer)、exit 0、3.65 / 2.25 / 2.42 s (n=3、Web 取得 4 件を含む) | `pnpm terms-watch -- --no-write` (台帳は a65a73b の値) |
| 台帳の安定性 | 基準線の記録後、同一セッション内 (約 5 分間) に Web 4 文書を含む全文書を 9 回取得して全回 UNCHANGED | 日・週単位の安定性は **未検証** |
| 再実行で台帳が変化しないこと | 書込モードで実行後、`git status --short` が空 | 同日内 |
| FL 同梱文書の探索 | 25,166 エントリ中の `*_DATA.bin` を内容署名で走査、各 1 件に特定 (同一内容の重複は許容、内容違いが複数なら ERROR) | `locateFlFile` |

### 別算法の検算

`crosscheck.py` (html.parser と正規表現 RTF トークナイザ。`lib.mjs` とコード非共有) の SHA-256 が、台帳の `fl-eula-html` / `fl-tou-rtf` と **2/2 一致** (文字数 33313 / 64633)。Web/PDF 文書は live 内容に依存するため対象外。

### ネガティブコントロール (`negative_control.sh`。実 FL 素材 / 実 Web)

| 操作 | 期待 | 実測 |
|---|---|---|
| 無改変 | exit 0 | 0 |
| EULA.html と RTF を各 1 語改変 (`decompile`→`decompiles` / `Cracked`→`Cracker`) | 1 | 1 |
| EULA.html のみ 1 語改変 / RTF のみ 1 語改変 | 1 / 1 | 1 / 1 |
| 空白・改行・タブだけ改変 (偽陽性にならない) | 0 | 0 |
| FL 抽出物 dir 無し | 3 | 3 |
| 台帳の SHA-256 先頭 1 文字を改変 (Web 4 文書それぞれ) | 1 ×4 | 1 ×4 |
| 接続不能 URL (ni-eula を `127.0.0.1:9` に差替え) | 3 | 3 |

単体テスト側で追加確認: ノイズ (nonce・ヘッダ/フッタ)・空白・charset 差で UNCHANGED、本文変更で CHANGED→PENDING→`ack`→UNCHANGED、404・短文ボット壁・必須語句欠落で ERROR かつ台帳不変、改変は `diff -u` で表示。

### 開発中に直した誤り (記録)

初版の HTML 変換は全タグを空白に置換しており、インラインタグ境界で語が分割された (`<span>Image Line</span>:` → `Image Line :`、`A<span>ny</span>` → `A ny`)。別算法の検算で FL EULA.html が 33332 / 33313 文字で不一致となり発覚。ブロック要素のみ改行・インラインは空白なしに修正し、2/2 一致。また `negative_control.sh` の初版は、EULA.html の改変対象 (`reverse engineer`) が原文では `reverse` と `engineer` の間で改行されており置換が空振りして exit 0 (期待 1) になった。空白改変側も同型の空振りを潜在していたため、改変が空振りしたら異常終了するガードを入れ、対象語を `decompile, disassemble` に変更した。

## 範囲 / 範囲外

検証範囲: 上記 6 文書の取得・正規化・比較・台帳更新・終了コード。範囲外 (主張しない): Xfer EULA の基準線・mac 同梱文書 (`FL_MAC_DIR`。`docs/LEGAL.md` §1 では win と同一と記載、本 run では未検証)・プラグインインストーラ同梱の EULA (Kilohearts `EULA.txt` 等)・Image-Line の他の Specific Terms (Mobile EULA 等)・日本語等の言語別版・変更の法的意味の判定 (1 文字の誤植修正でも CHANGED になる)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Xfer EULA の基準線が未取得 (`xfer-eula` は SKIP) | Xfer の改定を検出できない。完了条件「全文書」未達 | #88 に残す。再実行は `oc_artifacts: fl-win64 plugins-serum2` (`License.txt` が `plugins-serum2` に含まれるかは未確認。含まれなければ別素材名を #88 に要望) で `TERMS_WATCH_XFER_EULA=<License.txt>` を指定 |
| 定期実行・通知が未配線 (FL 追従プロセスの実体も repo に無い) | 30 日ルール (FL) を人が実行しないと検出できない | 新規子チケット `[CI-n]`: 週次 schedule で Web 4 文書 (`--only fl-tou-web,kilohearts-eula,slate-audiotonix-terms,ni-eula`) を回し exit 1/3 で失敗通知。FL 追従手順 (新版取り込み) からの `pnpm terms-watch` 呼出は #88 / MS11 (`docs/STATUS.md`) へコメント |
| Slate は短い UA (`Mozilla/5.0` のみ) の curl で HTTP 403、ブラウザ相当の UA + Accept で 200 | ボット対策の強化で取得不能 (exit 3) になり得る | 本 REPORT の限界。発生したら #88 にコメント |
| Kilohearts PDF の抽出が `uv` と PyPI の `pypdf==5.9.0` に依存 | `uv` 無し/PyPI 不達の環境では ERROR (exit 3) | 本 REPORT の限界 (pypdf を上げると抽出結果が変わり得るため pin を維持) |
| 差分の `diff -u` は旧版スナップショットが手元 `work/snapshots/` にある場合のみ | 新規 checkout/CI ではハッシュ差のみ表示 | 規約本文を commit しない方針の帰結。必要なら CI artifact 保存を `[CI-n]` に含める |
| Web ページ構造変更 (見出し・フッタ) | 切出し失敗 → ERROR、または誤って別範囲を基準線化 | サニティ (`minChars`/`mustContain`) で緩和。`sources.json` の更新で対応 |
