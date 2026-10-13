# REPORT — ST-T8 (#118): help-viewer — FL の Help を sandbox iframe に表示、error-offline.html 差替

検証起点: 親 `main` = `72cc968`、検証対象コミット = `9e04154` (§6)。素材 = `fl-win64` (FL Studio 26.1.7.5653、`FLEngine_x64.dll`)。
既知類型 (`docs/DEFECTS.md`) との関係: **該当なし** (lift/IR pass を扱わない。FLEngine の静的解析と、ブラウザ側 TS の実装・検証)。
受入条件は issue 本文に無いため、本 REPORT §0 で定義した。**全項目の達成ではない** (エンジン結線は未達、§5)。PR は `Refs #118`。

## 0. 結論

受入条件 (本 run で定義) と達成:

| # | 受入条件 | 結果 |
|---|---|---|
| A1 | FL が Help を開く経路 (どの関数が何を組み立て、最終的に何へ渡すか) を FLEngine の静的解析で確定 | **一部達成** — URL/パスの組立と外部 URL 側の最終段 (`ShellExecuteW`, 動詞 NULL) は確定。ローカル Help の最終段 (core 内部 interface vtbl+0xa0/+0xa8) の実体は**未確定** (§2.3) |
| A2 | `Help/index_offline.html` と `System/Internet/error-offline.html` の実ファイルを実測し、表示に必要な機能・遮断すべき参照を確定 | 達成 (§3) |
| A3 | `index_offline.html` を sandbox iframe で表示。外部通信なし・FL 由来 HTML は非同梱 | 達成 (§4・§6。実 Chrome で描画・遷移・遮断・CSP/sandbox を確認) |
| A4 | `error-offline.html` を FL のファイルを読まない自前ページに差替え | 達成 (§4.3) |
| A5 | lift 済みエンジンの Help 操作 → viewer 表示を実機で確認 | **未達** — boot が `CreateFruityInstance` に未到達で、エンジンを実行できない (§5 U1) |

1. **FL の Help 起動経路を確定**。`HelpUrl` (0x10be5c0) などが `Help\index_offline.html` と `Help\html\<topic>` のパスを組み立て、`OpenHelpTarget` (0x10bdbe0) へ渡す。
   **オフライン判定は `InternetGetConnectedState` が 0 を返すか、設定値 2 (UI の「Use offline help」と推定) のとき**。WinInet 常時オフライン (ST-T4) の下では
   `Help\index_offline.html` があれば自動でオフラインヘルプになる。トピックの `.htm` が無ければ `index_offline.html` に**フォールバック**する (§2.2)。
2. **基本インストールの `Help/` は 55 ファイル 2925770 B のスタブ**。`index_offline.html` (3999 B) は「オフラインマニュアルのインストーラを入れよ」という案内ページで、
   リンクは全て外部 (support.image-line.com)。全文マニュアルは別インストーラ (本素材に無い) で、`HelpAliases.scr` が指す `*.htm` (automation_eventeditor.htm 等) は 1 件も無い。
   → **実際に出るのは `index_offline.html` + `WhatsNew.htm` + ダイアログ用 `html/FD/web/documents/*.html` の 13 ページ**。
3. **実装**: `src/runtime/help_viewer.ts` (DOM 非依存の純ロジック) + `src/runtime/help_panel.ts` (パネル・`window.flHelp`・`/?help=1`)。
   Help の HTML は利用者の FL から実行時に供給 (`<input webkitdirectory>` / ドロップ / `flHelp.useHttp(base)`)。**リポジトリ・配信物に FL 由来 HTML を置かない** (`mcp_panel.ts` と同方針)。
4. **安全性は 3 重**: 書換え (script/iframe/外部参照の除去) + CSP (`default-src 'none'`) + iframe `sandbox="allow-scripts"` (same-origin なし)。
   CSP を剥がすと敵対的な img/link/fetch の**ビーコン 3 件が実際に到達**し、CSP ありでは 0 件 (ネガコン、§6)。
5. **`error-offline.html` は読まない**。FL ではオフライン時にブラウザ型ページ (0xdb0460) の error URL として使われる 44729 B の「You're offline」ページ (script なし・埋込フォント)。
   `classifyTarget` が `offline-notice` に分類し、**FL 由来物ゼロの自前ページ** (`buildNoticeSrcdoc`, en/ja) を出す。

## 1. 成果物

| パス | 内容 |
|---|---|
| `src/runtime/help_viewer.ts` | 純ロジック: `classifyTarget` (Win パス / `file:` / http(s) → help・offline-notice・external・unsupported)、`resolveLink`、`classifyShellExecute`、`prepareHelpPage` (HTML 安全化 + 資源埋込み)、`buildNoticeSrcdoc`、`filesFromMap` |
| `src/runtime/help_panel.ts` | DOM 側: `installFlHelp` (`window.flHelp`: `open` / `shellExecute` / `back` / `forward` / `setFiles` / `setFileList` / `useHttp`)、`mountHelpPanel` |
| `src/index.ts` | `installFlHelp()` 常時 + `/?help=1` でパネル (8 行追加) |
| `tools/startup/helpviewer/engine_claims.json` + `verify_engine.py` | FLEngine の静的根拠 (関数・文字列参照・call 辺・import thunk・機械語) の機械照合 (stdlib のみ) |
| `tools/startup/helpviewer/help_files.json` | FL の `Help/**` 55 件 + `error-offline.html` のパス・サイズ・sha256 (**メタデータのみ**。素材の特定と内容ピン) |
| `tools/startup/helpviewer/{lib.mjs,inspect_help.mjs}` | 素材から sha256 で実ファイルを特定 / 実 Help 全 13 ページへ適用して実測 |
| `tools/startup/helpviewer/e2e_browser.mjs` | 実アプリ `/?help=1` の headless Chrome e2e (CDP 直駆動、`tools/runtime/lib/chrome.mjs` 流用) |
| `tools/startup/helpviewer/test/help_viewer.test.mjs` | 純ロジックの単体テスト 11 本 (合成フィクスチャのみ) |
| `tools/startup/helpviewer/{e2e.sh,env.sh}` | 1 コマンド検証 `bash tools/startup/helpviewer/e2e.sh` |

## 2. FL の Help 起動経路 (FLEngine_x64.dll 静的解析。`verify_engine.py` が 54 件を機械照合)

数え方: 関数境界 = `.pdata`、文字列参照 = `.text` の RIP 相対 `lea/mov` の参照先が NUL 終端リテラルと一致、call 辺 = 関数内の `E8 rel32`、import = IAT 名。
下表の VA はすべて `engine_claims.json` に宣言があり照合済み。逆アセンブル (capstone) の読みから来る**意味づけ**は「読み」と明記する。

### 2.1 関数と役割

| VA | 役割 | 照合した根拠 |
|---|---|---|
| 0x64ba80 | `IsOnline` | `InternetGetConnectedState(&flags, 0) != 0` (import thunk 0x592a90 = `wininet!InternetGetConnectedState`) |
| 0x10bdaf0 | `HelpIsOffline` | 設定+0x3c0 と 2 の比較 (機械語 `83 b8 c0 03 00 00 02`)、`IsOnline` 呼出、`index_offline.html` 参照。呼出元 0xf1d660 (`WhatsNew.htm`) |
| 0x10be5c0 | `HelpUrl` (トピック名 → パス/URL) | 文字列 `index_offline.html` / `/html/%s` / `Help`、呼出 0x64ba80・0x10bdf30・0x10bdbe0。呼出元 0x10be820・0x10be840 |
| 0x10be8c0 | `HelpFdDocUrl` | 文字列 `/html/FD/web/documents/%s.html`、呼出元 0x10d0ff0 (ダイアログ) |
| 0x10bea60 / 0x10be860 | `HelpPluginUrl` / 呼出側 | 文字列 `/html/plugins/%s.htm`。0x10be860 が 0x10bea60 と 0x10bdbe0 を呼ぶ |
| 0x10bdf30 / 0x10bde00 | パス整形 / `Help\Redirects\<name>.url` | 文字列 `Redirects\` `.url` (オンライン時のリダイレクト表) |
| **0x10bdbe0** | **`OpenHelpTarget`** (最終段) | 末尾に `ShellExecuteW(NULL, **NULL**, url, NULL, NULL, SW_SHOW=5)` の機械語 (§2.3)。呼出元 0x10be5c0・0x10be860・0x10be8c0 |
| 0xdb0460 | ブラウザ型ページの初期化 | 文字列 `file://` + `error-offline.html`、`IsOnline` 呼出 (§2.4) |
| 0x11a57c0 | LoadSettings | 文字列 `OfflineHelpBox` (設定 UI の「Use offline help」と読む) |

### 2.2 オフライン判定とフォールバック (読み)

- `HelpIsOffline`: 設定値 == 2 なら強制オフライン、そうでなければ `IsOnline()` が真ならオンライン。どちらでも最後に「検索パス区分 0x40a で `index_offline.html` が見つかるか」を要求する。
  → **WinInet 常時オフライン (`InternetGetConnectedState`=0, ST-T4) では、`Help\index_offline.html` があれば自動でオフラインヘルプになる**。無ければオンライン URL (外部通信は不可) になる。
- `HelpUrl` のオフライン枝: `Help\html\<topic>` を検索し、**無ければ `index_offline.html` のパスに置換**してから `OpenHelpTarget` へ渡す。
  基本インストールにトピック `.htm` は無いので、**どの Help 操作でも実際に開かれるのは `index_offline.html`** (例外: ダイアログ用 `/html/FD/web/documents/*.html`・`WhatsNew.htm`)。
- オンライン枝は `Help\Redirects\<name>.url` (インターネットショートカット) を引く。`Redirects\` は基本インストールに無い。

### 2.3 最終段 `OpenHelpTarget` (0x10bdbe0)

- **外部扱い**: 対象が「ある基準ディレクトリ文字列」で始まらないとき (オンライン URL など。判定は `0x4150d0` の戻り値 == 1 の読み)、`ShellExecuteW(NULL, NULL, url, NULL, NULL, 5)` を直接呼ぶ。機械語 `33 c9 33 d2 49 89 c0 4d 33 c9 48 c7 44 24 20 00… c7 44 24 28 05 00 00 00 e8 <rel32>` を照合 (call 先 = `shell32!ShellExecuteW` thunk)。
  **動詞 (`lpOperation`) は NULL** で、`stub_plan.md` §5-B の "open" と同じに扱う必要がある (`classifyShellExecute` は NULL/""/"open" を open とする)。
- **内部扱い (読み)**: 基準ディレクトリで始まるローカルパス (= 基本インストールの `Help\…`) は、`[[g_core]+0x4c]` の interface の vtbl+0xa0 または +0xa8 へ渡る
  (設定+0x3c0 と修飾キー状態 — 0x818890 は `GetKeyState` の 0x10/0x11/0x12 を集約 — の組合せで選ぶと読める)。**(訂正: §7.1 で実体 = `TServerComms`、ローカル Help はここを通らず `ShellExecuteW` へ直行と確定)**。
  WebView2 は `LoadLibraryW("WebView2Loader.dll")`=NULL (GATES G13) で作られないため、**エンジン内部経路のままでは Help が何も出ない可能性が高い** (推定)。

### 2.4 `error-offline.html`

0xdb0460 は、`IsOnline()` が偽のとき `file://` + (検索区分 0x3fd のパス) + `error-offline.html` を自身の error URL に設定する (読み)。0x3fd は `System\Internet` (`Internet\` を登録する 0x9db5b0 と整合)。
= FL Cloud タブなどのブラウザ型ページが開けないときに出す「You're offline」。ヘルプ経路ではない。WebView2 が無いので FL 側では表示されず、本 viewer が肩代わりする。

## 3. Help 実ファイルの実測 (`inspect_help.mjs`、ピン済み 56 件が素材に全て存在)

`Help/` は 55 件 2925770 B (内容 52 種: 同一内容の別名あり)。種別: png 13 / jpg 18 / html 12 / htm 1 (`WhatsNew.htm` 980991 B) / css 2 / js 1 / scr 2 / フォント 4 / log 1 / svg 1。

| ページ (Help/ 相対) | 入力→出力 B | 埋込 | 欠落 | 外部参照を遮断 | script/embed 除去 |
|---|---:|---:|---:|---:|---:|
| `index_offline.html` | 3999→232139 | 3 | 4 | 3 | 2 / 2 |
| `WhatsNew.htm` | 980991→1208864 | 3 | 4 | 3 | 2 / 1 |
| `html/FD/web/index.html` (meta refresh → `documents/productinfo.html`) | 1533→18994 | 1 | 0 | 0 | 1 / 0 |
| `documents/productinfo.html` | 7526→63687 | 2 | 0 | 12 | 1 / 0 |
| `documents/regoftrial.html` | 12056→105822 | 4 | 0 | 28 | 2 / 0 |
| `documents/demoplugincannotbesaved.html` (最大の埋込み) | 21948→1128944 | 20 | 0 | 43 | 1 / 0 |
| 他 7 ページ (`_case6` `boxregreminder` `expirationregcode` `info` `internetconnection` `regcodeexpired` `toolsandapplications`) | 全て出力 ≤151126 | 1–4 | 0–1 | 1–21 | 1–2 / 0 |

- 全 13 ページ合計: 入力 1061457 B → 出力 3089048 B、埋込み 44 件、欠落 10 件、外部参照の遮断 139 件、script 除去 17 件、embed 除去 3 件。**変換後に残る危険要素 (script は bridge 1 本のみ・iframe/object/embed/base/form・on* 属性・外部 URL 参照・`@import`) は 0 件**。
  変換時間は最大 `demoplugincannotbesaved.html` 37.7 ms / `WhatsNew.htm` 28.7 ms (単発・n=1。§6 に 3 回の e2e)。
- **欠落 10 件の内訳**: `flstudio.css` が参照する `img_glob/{external_link.svg,global_kbd.svg,listbullet2.gif,listbullet3.gif}` (基本インストールに無い) を `index_offline.html` と `WhatsNew.htm` で各 4 件、
  `html/img_glob/FLStudio_UnlockWithAccount.png` を 2 ページで各 1 件。表示への影響はリスト記号・外部リンクアイコンの欠落のみ。
- **`index_offline.html` の構造**: `<script src="scripts.js">` (**素材に無い**) とインラインの script が左フレーム (`../index_frame_left_offline.html`、**素材に無い**) を差し込む。
  どちらも除去しても本文 (`<h1>Is your computer offline?</h1>` 以降) は完結して読める。YouTube の `<iframe>` と外部リンク 3 件 (`support.image-line.com/redirect/…`) は遮断対象。内部リンクは 1 件 (`envsettings_general.htm#settings_advanced`、全文マニュアル側で素材に無い)。
- `html/FD/web/index.html` は jquery.js + `<meta http-equiv=refresh content="0; url=documents/productinfo.html">`。viewer は refresh を辿る (深さ 3 まで)。
- `error-offline.html` (44729 B): script なし。埋込み base64 フォント (`gilroy`) + 文言 2 行 + `#offlineData` リンク。ネットワーク参照なし。

## 4. 設計

### 4.1 データの流れ

```
FL (lift 済みエンジン) ──ShellExecuteW(NULL, path)──▶ shimx shell hook ──▶ flHelp.shellExecute(verb, file)
                                                                              │ classifyShellExecute
        help 配下 ──▶ prepareHelpPage(HelpFiles, path) ──▶ iframe.srcdoc   ◀───┤ (33 を返す)
        error-offline ──▶ buildNoticeSrcdoc("offline")                         │
        http(s) ──▶ onExternal(url) 通知のみ (既定 no-op)・33 を返す            ┘
HelpFiles = 利用者の FL の Help フォルダ (webkitdirectory/ドロップ) | useHttp("/fl/Help/") (配信済みの場合) | Map (テスト)
```

### 4.2 書換えと隔離 (`prepareHelpPage`)

- 除去: `script` `iframe` `frame` `object` `applet` `noembed` (本体ごと)、`embed` `base` `param`、`form` タグ、`on*` / `srcdoc` / `background` / `srcset` / `ping` 属性、`a[target|download]`、`meta http-equiv=refresh|content-security-policy`。
- 埋込み (`data:`): 相対の `link[rel=stylesheet]` → `<style>` (CSS 内の `url()` も再帰せず 1 段で埋込み、`@import` は除去、旧式フォントの EOT と SVG フォントは埋込まない)、`img[src]`、`input[type=image]`、`style` 属性内 `url()`。
  1 資源 2 MiB・1 ページ 24 MiB の上限 (超過は `skippedLarge`)。見つからない資源は `missingResources` に記録して `data:,` / src 除去。
- 先頭に固定の CSP `default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; script-src 'nonce-<毎回乱数>'; base-uri/form-action/frame-src/connect-src/media-src/object-src 'none'` を置き、
  末尾に nonce 付きの bridge script 1 本 (リンククリックを捕まえて親へ `postMessage({flHelp: token, href})`。フラグメントのみのリンクは iframe 内でスクロール)。フラグメント文字列は `<` を `\u003c` にして JS 文字列へ入れる (`</script>` 注入の単体テストあり)。
- iframe は `sandbox="allow-scripts"` (same-origin なし = opaque origin)。親は `event.source === iframe.contentWindow` かつ token 一致のときだけ遷移を解決する。
- 遷移: `resolveLink(現在ページ, href)` → help 内なら `prepareHelpPage`、外部なら `external-blocked` イベント + `onExternal` (既定 no-op)。`..` での Help 外への脱出、`%2e%2e`・`%5c` による迂回、NUL、`javascript:`/`data:`/UNC は `unsupported` (単体テストで列挙)。

### 4.3 `error-offline.html` 差替

`classifyTarget` が `…\System\Internet\error-offline.html` (Win パス / `file:` URL とも) を `offline-notice` と判定し、FL のファイルを**読まず**に `buildNoticeSrcdoc` を出す。
自前ページは script・外部参照・フォント無し (CSP も `default-src 'none'`)。FL の埋込みフォントの先頭 64 文字・文言 "FL Cloud needs" を含まないことを `inspect_help.mjs` が検査する。

## 5. 未解決・限界

| # | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U1 | **エンジン側の結線**: ローカル Help は `OpenHelpTarget` の内部 interface (vtbl+0xa0/+0xa8) に渡り、`ShellExecuteW` を経由しない。実体 (WebView2 ページか) の確定と、`flHelp.shellExecute` / `flHelp.open` を呼ぶ結線が未実施。boot が `CreateFruityInstance` 未到達で実行トレース不可 | A5 未達。エンジンの Help 操作から viewer が開くことは未確認 | #554 ([ST-T17], 親 #118、依存 #227 / #105) |
| U2 | `ShellExecuteW` の shell hook への接続: `flHelp.shellExecute(verb, file)` は戻り値 33 を返す入口として用意したが、shimx の hook (`shimx_set_shell_execute_hook`) と未接続 | 同上 | #172 (SHX-T5, PR #505) と #554 で調整 |
| U3 | 全文オフラインマニュアル (FL の別インストーラ `offline_help_installer`) の Help フォルダでの表示は**未検証** (素材なし: `docs/REFERENCES.md` に該当項目なし)。左メニューは script 依存のため除去され、本文のみの表示になる (推定) | 全文マニュアルを使う場合の体験 | #554 に含める。素材は利用者持ち込み (ユーザ依頼事項は無し) |
| U4 | 検証ブラウザは Chrome/154.0.8037.97 のみ。Firefox/Safari の `srcdoc` + meta CSP + sandbox の挙動は未検証 | 他ブラウザでの隔離・表示 | `docs/STATUS.md` の e2e マトリクス拡張時に追加 (起票なし) |
| U5 | 本番配信での Help の供給元: `useHttp("/fl/Help/")` は用意したが、`tools/assets` の manifest が `Help/` を配信対象にするかは未確認。tier の推奨は #522 (PR) の §4 表 (help-entry T1, help-html T2) | 配信構成 | #105 (ST-T5)・`tools/assets` (PM 判断) |
| U6 | 外部リンクの扱い: 既定は通知のみ (`onExternal` 既定 no-op)。`stub_plan.md` §5-B の「ユーザ操作中のみ `window.open`」を実装する場合は `onExternal` に結線 | 外部ページへの導線 | #554 で方針確認 (D3 により既定 OFF) |

## 6. 検証

検証はコミット済み HEAD をクリーン worktree に展開して実行した (下の実測欄)。

```sh
bash tools/startup/helpviewer/e2e.sh     # FL_WIN64_DIR (fl-win64 展開先) が必要。Chrome (CHROME_BIN) と pnpm install 済みの node_modules が前提
```

| 検査 | 結果 | ネガコン |
|---|---|---|
| FLEngine 静的根拠 (`verify_engine.py`) | 54 件一致 / 不一致 0 | 文字列 1・call 辺 1・機械語 1 (`SW_SHOW` 5→6) を壊して 3 件検出 |
| 単体テスト (`node --test`) | 11 本 pass / fail 0 | 無加工の合成 HTML に検査関数を当てると 6 種の危険を検出 (検査自体が効く) |
| 実 Help 13 ページ (`inspect_help.mjs`) | 変換後の危険要素 0、ピン 56/56 一致 | 無加工の `index_offline.html` に同じ検査を当てて 5 件検出 |
| ブラウザ e2e (`e2e_browser.mjs`、実アプリ `/?help=1`、COOP/COEP 付き) | 24/24 ok | CSP を剥がすとビーコン 3 件到達・iframe 内 script 実行 (CSP ありは 0 件・未実行)。それでも親 document には触れない |
| `pnpm typecheck` | 0 エラー | — |

ブラウザ e2e の内訳: `shellExecute(NULL, …\Help\index_offline.html)` の戻り値 33 → iframe に本文描画 (`<h1>` 一致)、script 1 本 (bridge)・iframe 0、`flstudio.css` 541 規則が有効、`@font-face` 読込済み /
外部リンクのクリックで遷移なし・新規タブなし・`external-blocked` 1 件 / `html/FD/web/index.html` の meta refresh → `productinfo.html`、内部リンク → `toolsandapplications.html`、`back()` で `productinfo.html` /
`error-offline.html` は FL のファイルを取得せず自前ページ (リクエストログに無し) / 親自身からの偽 `postMessage` は無視。

実測 (コミット済み HEAD、n=3 のクリーン worktree 展開):

検証対象コミット = `9e04154` (feat)。`git worktree add --detach <dir> 9e04154` で展開し `pnpm install --frozen-lockfile` 後に `e2e.sh` を 3 回 (並列 1、同一 Actions runner、Chrome/154.0.8037.97、node v22.23.3):

| run | 所要 (e2e.sh 全体) | load average 開始→終了 (1 分値) | ブラウザ e2e: `index_offline.html` 表示 / `WhatsNew.htm` 表示 | 結果 |
|---:|---:|---|---|---|
| 1 | 23.9 秒 | 0.08 → 0.47 | 42 ms / 335 ms | exit 0・PASS |
| 2 | 23.4 秒 | 0.47 → 0.62 | 50 ms / 352 ms | exit 0・PASS |
| 3 | 23.9 秒 | 0.62 → 0.67 | 46 ms / 332 ms | exit 0・PASS |

- 範囲: 所要 23.4–23.9 秒、表示時間は `shellExecute` 呼出から iframe 内 `document.title` が期待値になるまでの壁時計 (CDP ポーリング 50 ms 間隔の分解能を含む)。
- `git diff 72cc968 9e04154 --stat`: 15 ファイル +1960 行。範囲は `src/runtime/help_{viewer,panel}.ts`・`src/index.ts`・`tools/startup/helpviewer/`・`docs/{DOC_MAP,STATUS}.md` のみ。
  `find tools/startup/helpviewer src -type f -size +20M -not -path '*/work/*'` は 0 件 (最大の追加物 `help_files.json` は 9382 B)。
- 別アルゴリズムでの検算: §2 の「読み」(意味づけ) は capstone による逆アセンブルで行い、機械照合 (`verify_engine.py`) は逆アセンブラを使わないバイト走査 + `.pdata` + IAT で行う (独立した 2 手法)。
- 検証範囲: 上記のとおり FL 26.1.7.5653 win64 の `Help/**` 55 件と `FLEngine_x64.dll` の宣言済み 54 事項。範囲外: lift 済みエンジンの実行 (U1)、全文オフラインマニュアル (U3)、Chrome 以外 (U4)。

## 7. エンジン結線 (#554 ST-T17、検証起点 `e3b9202`)

既知類型 (`docs/DEFECTS.md`) との関係: **該当なし** (静的解析 + ホスト橋渡しの追加。lift/IR pass は触らない)。PR は `Refs #554` (受入条件 3 の e2e は未達、下表)。

### 7.1 `[[g_core]+0x4c]` interface の実体 (受入条件 1)

静的解析 (capstone + pefile、`FLEngine_x64.dll` 26.1.7.5653)。以下は逆アセンブルの**読み**で、`verify_engine.py` の機械照合には未追加 (§7.3 U7):

| 事実 | 根拠 (VA) |
|---|---|
| `[g_core]+0x4c` への書込は 0x9770a0 のみ (`mov [rcx+0x4c], rdx`。rcx = g_core、rdx = 新規インスタンス)。呼出元は 0x11b2ac0 の 1 箇所 (0x11b2f2d)、引数は 0x11b2d05 で生成した `0xbf8f08` クラスのインスタンス | 0x9770a0 / 0x11b2d0a・0x11b2f2d |
| そのクラスの Delphi VMT の className = **`TServerComms`** (VMT 0xbf8f08、`-0x88` = ShortString 0xbf9141) | 0xbf8f08 |
| vtbl+0x100 (0xc02a50): 先頭が **`https://support.image-line.com/redirect/`** の文字列を `PosEx` し、無ければ付加して返す = redirect の基底 URL 取得 | 0xc02a50 |
| vtbl+0xa0 (0xc02620) / +0xa8 (0xc02840): `https://support.image-line.com/redirect/` + 名前を 0xbfa8a0 で組み、+0xa0 は 0x8ea880、+0xa8 は URL 返却 | 0xc02620 / 0xc02840 / 0xbfa8a0 (`lang=` / `?` を付加) |
| 0x8ea880 → 0x8ea830: `ShellExecuteW(hwnd, NULL, url, NULL, NULL, nShow)` を呼び戻り値 > 32 を返す | 0x8ea830 |

結論: **実体は WebView2 ではなく `TServerComms` (support.image-line.com の redirect URL を組み、ShellExecuteW か内部ブラウザ kind 0x19 に渡す通信クラス)**。
`OpenHelpTarget` の分岐 (0x10bdc8e `cmp eax, 1`) は「対象文字列が redirect 基底 URL で始まるか」であり、§2.3 の「基準ディレクトリ」の読みは**誤り (訂正)**:
`Help\...` のローカルパスは redirect 基底で始まらず、0x10bdd85 の `ShellExecuteW(NULL, NULL, path, NULL, NULL, SW_SHOW)` に直行する。`TServerComms` 側へ行くのは redirect URL (外部) のみで、D3 により対象外。

### 7.2 結線 (受入条件 2)

WebView2 の挙動確認は**不要** (ローカル Help は WebView2 経路を通らない)。`ShellExecuteW` → shimx の shell hook (`gui_shimx_attach()` が登録する `gui_shell_execute`、#172) の経路に、Help を足した。

- `tools/gui/src/gui_core_ext.inc`: `<FL>\Help\…` と `<FL>\System\Internet\error-offline.html` (大文字小文字不問、動詞 NULL/"open") だけを `GUI_HC_OPEN_HELP` (= 4) で host へ渡す。それ以外のローカルパス・`print`/`runas` は従来どおり拒否、http(s)/mailto は `GUI_HC_OPEN_URL` のまま。
- `src/runtime/gui_hostcall.ts`: `HC_OP.openHelp` と `HostCallEnv.openHelp?(path)` (= `window.flHelp.shellExecute(null, path)` を呼ぶ口)。viewer 未接続は 0 + log、例外は `HC_ERR`。
- 外部リンク (U6): 既定は通知のみ (D3)。`window.open` は **許さない** 方針とした (`onExternal` 既定 no-op のまま。変更なし)。

### 7.3 検証 (受入条件 3 のうち実行できた範囲)

| 検査 | 結果 | ネガコン |
|---|---|---|
| `bash tools/gui/test/selftest.sh` (native gcc + ASan/UBSan。新セクション `ShellExecuteW(Help)`: 受理 4 パス・verb open・大文字小文字・host 拒否・拒否 8 パス・print/runas・https 回帰・host 未接続) | exit 0、**426 passed / 0 failed** (所要 6.9 秒、load average 0.19 開始) | `help_path_ok` を `return 1` に壊すと **4 FAIL** (exit 1) |
| `node --test help_viewer.test.mjs hostcall_help.test.mjs` | 14 pass / 0 fail (新規 3 本: openHelp の true/false/未接続/例外、openUrl 回帰) | — |

コミット済み HEAD `11e79a8` をクリーン detached worktree に展開して再検証 (n=3、並列 1): `selftest.sh` は **run1 = exit 1 (ASan heap-use-after-free)** / run2 = exit 0・426 passed・7.0 秒 / run3 = exit 0・426 passed・6.9 秒 (load average 1 分値 0.25–0.49)、`node --test` 14 pass / 0 fail。
run1 の失敗は `gui_headless.c:33 blit_surf` が `surf_free` 済みの面を読む**既存の flake** (`tools/gui/shimx_coexist/REPORT.md` §4.2 / §6 に base でも発生と記録済み)。本変更と無関係であることの確認: base `e3b9202` を同じ手順で 12 回実行して 1 回同じ ASan エラー (11 回 exit 0)。新セクションの 426 件中の FAIL はどの実行にも 0 件。
§6 の `e2e.sh` 全体 (Chrome/typecheck) の再実行は**未実施** (job の 60 分上限のため)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U7: §7.1 の `TServerComms` 経路を `engine_claims.json` / `verify_engine.py` に追加していない (読みのまま) | 機械照合なし | #554 にコメント (後続) |
| U8: **lift 済みエンジンの F1 / Help メニュー / `WhatsNew` → viewer の実行 e2e は未達** (boot が `CreateFruityInstance` 未到達で実行不可、#227 closed でも実行未確認)。本 PR は C 側 hook 受理と host 橋渡しの単体検証まで | 受入条件 3 未達 → `Refs #554` | #554 は open のまま。#105 (ST-T5) の open() trace 待ち |
| U9: `HostCallBridge.start()` + `openHelp` → `flHelp.shellExecute` を呼ぶ起動 glue (src 側) 未結線 (coexist REPORT §6 と同じ未結線) | 実アプリで viewer が開かない | #177 [SHX-T9] |
| U11: `selftest.sh` の既存 flake (`blit_surf` use-after-free、base 12 回中 1 回) | CI で偶発 FAIL | 既存記録 (#172 shimx_coexist REPORT §6)。本件では起票せず #172 に追記済みの範囲 |
| U10: emcc (`toolchain-emsdk`) 未取得のため `tools/gui/shimx_coexist/coexist.sh` (wasm リンク) を再実行していない | wasm 共存リンクへの影響未確認 | 再実行は `oc_artifacts: fl-win64 toolchain-emsdk work-m11` を付けて #554 |
