# LEGAL.md — ライセンス/利用規約上の運用制約サマリ (事実整理)

> **行数目安**: 本ファイルは 250 行を超過 (`docs/DOC_MAP.md` §1 の上限ルール参照)。
> 超過分は Git 履歴に残る形での分割移動を推奨 (**内容は削除しない**)。

> **法的助言ではない。** 本書は同梱テキスト (一部は公式サイトの公開文面) から条項を抽出し、技術チームが「何を同梱・公開しないか」「どんなアクセス制御が要るか」を決めるための論点整理である。適用可否・有効性・解釈は断定していない (「論点」と記したものは未決)。実際の判断は弁護士等の専門家が、ユーザが実際に承諾した版の規約に基づいて行うこと。
>
> 作成: 2026-10-10 (担当 O: legal) / 対象: FL Studio 26.1.7 (mac 5419 / win64 5653)、Xfer OTT 1.37・Serum 2 2.1.5、Fresh Air 1.0.9、Kilohearts Installer (2026-03 release)。
> 方針前提: `docs/REFERENCES.md` `[STRATEGY]` §6 (成果物の再配布はしない / 外部通信機能は対象外 / DRM 回避を目的としない)。
> 運用規程 (確定 2026-10-10): ライセンス機構の無力化 / アクティベーション無条件通過 / 運用形態 B — §6.0。OSS 再配布論点は別件・未回答のまま (§6.0-7)。

## 目次
0. 結論先出し — 特に重要な 5 点
1. 対象文書・出典の凡例と所在
2. Image-Line (FL Studio) の条項
   - 2.1 二系統の文書 (EULA.html / Terms of Use) と差分
   - 2.2 リバース・改変・派生物
   - 2.3 再配布・ホスティング・SaaS・公開アクセス・レンタル (論点整理)
   - 2.4 認証・アクティベーション・オンライン検証・テレメトリ・アカウント
   - 2.5 トライアル/デモの制限
3. サードパーティ/OSS (FL 同梱分)
   - 3.1 OSS 一覧と条件 / 3.2 LGPL 等 (wasm 静的リンク時) / 3.3 非 OSS の第三者技術
4. プラグイン各社の条項 (Xfer / Kilohearts / Slate Digital / Native Instruments)
5. 各社条項の差異表
6. 運用形態別の論点増減表と共通の緩和策 (6.0 運用規程 — 確定)
7. 見つからなかった/確認できなかった文書、出所に関する事実
8. ユーザ確認事項と次タスク案
付録: 抽出・再現手順

---

## 0. 結論先出し — 特に重要な 5 点

1. **手法そのものが条項の禁止行為に直接触れる (全社共通)。** Image-Line は逆アセンブル・逆コンパイル・改変・翻訳・派生物作成を列挙して禁止し、個人利用の例外を置かない (`[FL-EULA] §7(i)` / `[FL-ToU] art.11 General restrictions 1(i)`)。Xfer `(c)`、Kilohearts `§2(c)` (法令上許される範囲は除外)、Slate/Audiotonix `§16` (「port」「入出力監視による再現」まで明記)、NI `§3.1` も同趣旨。運用形態を変えても「作業そのもの」の論点は消えず、変わるのは *誰が行うか* と *成果物が誰の手に渡るか* だけ (§6)。
2. **ライセンスは「本人1名」単位で、ネットワーク越しの利用も各人の個別ライセンスが前提。** `[FL-EULA] §4` (L559–; 引用箇所は L572): "Any, even non-simultaneous, use by multiple people of a personally licensed copy … is strictly prohibited." → Cloudflare Access の許可リストは「正規ライセンス保有者本人」に限る設計が前提 (複数人に開けるなら各人が個別に保有)。ASP 条項 (`§7(ii)` / ToU 11.1(ii): "service bureau, application service provider, or similar business") はサーバ実行型 (FL をサーバで動かす) に直接関係する条項である。クライアント側 wasm 実行は設計上これを避けるが、「サーバが FL 派生物を配る」行為は別論点 (2.3)。
3. **「Cracked」の定義とライセンス stub の線引き。** `[FL-EULA] §1` "Cracked": ライセンス機構を回避して支払い無しにアンロックしたソフト。`§2` / ToU art.3-3 / art.10-1: Cracked 複製には **権利が一切付与されない**。ToU art.11 General restrictions 2 は "creation or distribution of cracked versions" も禁止。strategy §6.7 の「ローカルでの起動検通に限定した stub」は、**未登録 (トライアル/デモ) のまま起動する設計**と、**アンロック済みを装う設計**で意味が大きく異なる。後者は Cracked 定義に近づく懸念があり、前者でも「トライアルは個人利用限定・成果物の商用利用禁止」(2.5) が付く。登録キーが第三者アクセス可能な場所に出ると失効し得る (ToU art.12-7)。→ **2026-10-10 ユーザ指示**: 本プロジェクトの方針は「登録済みとして振る舞う (無条件アクティベーション)」に確定 (§6.0 運用規程)。上記は条項上の事実の記載として残し、Cracked 定義と本方針の関係について新たな判断は加えない。
4. **Slate/Audiotonix の規約が最も厳しく、Fresh Air は同梱 EULA がファイル名判定では無い。** 公式 ToS (オンライン取得・非同梱・適用版は未確認) `§16`: "modify, port, adapt, or translate", "reverse engineer (including … monitoring or tracking the inputs and outputs … to recreate that system)", AI/ML 学習禁止 (C)。`§6`: "copy, modify, host, stream, sublicense, or resell" / "hosted service"。Fresh Air のインストーラ (zip/pkg) にはファイル名判定で EULA 文書が見当たらず、バイナリ内に iLok 実装も見当たらず、pkg の識別子は `com.MakingGreatestPizza…` (§7)。**入手元・保有ライセンスの確認が先決。** また Xfer `(e)` は無償の OTT でも "share, publish or distribute … without prior consent" を禁じるため、OTT バイナリの再ホストは (無料でも) 同意が要る論点。
5. **OSS 側にも運用上の義務があり、FL 側 EULA と衝突し得る箇所がある。** FFmpeg は LGPL (`ffmpeg.txt` は v2.1 と表記、win 同梱ビルドの実コンフィグは `--enable-version3` = LGPLv3+、`--enable-gpl` なし)。LGPL-2.1 §6 は結合物の条件が「改変と、その改変のデバッグ目的のリバースエンジニアリングを許す」ことを要求し (`ffmpeg.txt` L103)、"contradicts the license restrictions of other proprietary libraries … you cannot use both them and the Library together" (L115)。→ 方針どおり upstream から wasm 再ビルドし、**FL 由来 (リフト済み) コードと同一 wasm に静的リンクしない** (別 side module / 差し替え可能) 設計が論点を最小化する。FreeType は謝辞の掲載が必須 (FTL §2)。`LAME MP3 encoder/LGPL.txt` の実体は **GPL v2 本文** で名称と不一致 (3.1)。

---

## 1. 対象文書・出典の凡例と所在

パス短縮: `MAC` = `mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL` / `WIN` = `win64/extracted` / `TGT` = `tools/targets`。
**外部パスの正本は `docs/REFERENCES.md` (`[MAC]` / `[WIN]` / `[ANALYSIS-PLUGINS]` / `[LEGAL-WORK]`)。本書ではその配下を上記の相対表記で示す。**
行番号は原ファイルの行 (HTML/テキスト)。RTF・NSIS ヘッダ由来は条項番号で示す。

| 凡例 | 文書 | 所在 | 検証した事実 |
|---|---|---|---|
| `[FL-EULA]` | IMAGE LINE SOFTWARE EULA (HTML, 23 条) | `MAC/System/Legal/EULA.html` (247,104 B, mtime 2025-09-24)。win: `WIN/block24719_DATA.bin` | win/mac は `cmp` で **バイト同一**。win の NSIS ファイル一覧 (`block25163`) にも `System\Legal\EULA.html/247104` |
| `[FL-ToU]` | Image-Line **TERMS OF USE** (RTF, 約 32 条) = インストーラのライセンス画面 | mac: `MAC/../Resources/en.lproj/license.rtf` (88,736 B, mtime 2026-07-02、`Distribution` に `<license file="license.rtf"/>`)。win: `WIN/block00029_DATA.bin` | 両者 `cmp` で **バイト同一**。win は NSIS ヘッダ (LZMA 解凍 3,519,116 B) 内に同文があり、同ヘッダに "License Agreement / You must accept the agreement to install" を確認 → ライセンスページ本文と判断 (推定)。条項番号は RTF 印字の番号 (原文に "19." が 2 回出る誤番あり) |
| `[FL-LIC]` | OSS 表記 15 ファイル `System/Texts/Licenses/*.txt` | `MAC/System/Texts/Licenses/` / win: `WIN/block24735`–`24749` | win/mac 各 15 本が **空白・BOM・文字コード差を除き同一** (自作比較) |
| `[FL-LAME]` | `System/Legal/LAME MP3 encoder/LGPL.txt` (18,329 B) | `MAC/System/Legal/...` / win `block24720` | win/mac `cmp` 同一。**中身は GNU GPL v2 本文** (1991 年版) |
| `[FL-ABOUT]` | クレジット/"Used technologies" | `MAC/System/Texts/About/AboutTxt.txt` | 第三者技術の一覧 (ライセンス本文なし) |
| `[FL-TXT]` | デモ/未登録/更新の画面文言 | `MAC/System/Texts/{DemoTxt,NotReggedTxt,NewVersion,BoxEdition}.txt` | — |
| `[NSIS-FL]` | win インストーラ UI 文言 (INI) | `WIN/block00030_DATA.bin` ほか | — |
| `[XFER]` | Xfer Records EULA (1,914 文字) | Serum 2 mac pkg: `TGT/serum2/work/pkg_extract/Resources/License.txt` (`Distribution` に `<license>`)。OTT/Serum 2 win: NSIS ヘッダ (zlib 解凍) 内ライセンスページ文 | **OTT win / Serum 2 win / Serum 2 mac の 3 者が空白正規化後に完全一致**。OTT mac pkg には `<license>` なし |
| `[KH]` | Kilohearts EULA (全 6 条) | `TGT/kilohearts/work/dmg/Kilohearts Installer/Kilohearts Installer.app/Contents/Resources/EULA.txt`。win: `Kilohearts Installer.exe` 内 (file offset 15,125,160) | win 埋込と mac は空白正規化後に一致 |
| `[SLATE-ToS]` | Audiotonix General Terms of Use (Slate Digital) | <https://slatedigital.com/terms-of-service/> を 2026-10-10 に取得 | **同梱ではない**。Fresh Air に適用される版かは未確認。同梱 EULA はファイル名判定では無し (`tools/legal/REPORT.md` §2) |
| `[NI-EULA]` | Native Instruments EULA | <https://www.native-instruments.com/pages/end-user-license-agreement> (2026-10-10。作成時は検索スニペットのみ、検収時に全文を取得: 契約主体 inMusic NI GmbH、ページ表記 "Latest Version 2026-07-01") | **同梱ではない**。Massive X の同梱 EULA は未確認 (`.exe` 展開不能、`tools/legal/REPORT.md` §1、§7) |

補足: FL mac の dmg に Software License Agreement リソースは無い (dmg XML plist に `LPic`/`STR#`/`RTF `/`TEXT` 無し)。抽出物の置き場はリポジトリ外 (`docs/REFERENCES.md` `[LEGAL-WORK]`) (抽出作業用 dir は当時 `.gitignore` 対象外だったため)。

---

## 2. Image-Line (FL Studio) の条項

### 2.1 二系統の文書 (EULA.html / Terms of Use) と差分

アプリ同梱の `[FL-EULA]` (ファイル mtime 2025-09-24) と、インストーラ画面の `[FL-ToU]` (ファイル mtime 2026-07-02) が **併存**している (どちらも文書本文内に日付の記載は無く、日付は pkg 内ファイルの mtime のみ)。どちらが優先されるかは文書からは判断できない (ToU art.20 "Complete agreement … supersedes all other or prior understandings" とあるが、EULA.html は引き続き `System\Legal` に導入される)。主な差:

| 論点 | `[FL-EULA]` | `[FL-ToU]` |
|---|---|---|
| 対象物 | "Software" (FL, Mobile, **plugins, plugin content** を含む) §1 | "Products" (Software + FL Cloud + Digital Content + Tools) art.2(i) |
| ライセンス性質 | personal / non-exclusive / non-transferable / worldwide / revocable §4 | 左に **non-rentable** が加わる art.10-2 |
| RE・改変禁止 | §7(i) | art.11 General restrictions 1(i) (対象が Products に拡大。EULA §7(i) の列挙にあった "download" は 1(i) から外れ、(iii) の末尾に付く節 "nor shall the User give anyone permission to download the Products" になった) |
| 第三者ソフト | §8: 第三者ソフトの複製・改変・派生物を禁止、"duplicate or download (even for free), such plugins" も禁止 | art.11 "Third Party software": 第三者/OSS ライセンスに従う旨に書換え。§8 相当の禁止文は無い |
| 譲渡 | §6 | art.11 General restrictions 2: "gift" 追加、"creation or distribution of cracked versions" 追加 |
| 責任 | 上限額の定め無し | art.17-8: 支払額が上限 |
| 終了 | §11 即時終了 | art.19-2 3 か月予告の任意解約 / 19-3 即時の停止・アカウント失効 |
| 利用者素材 | — | art.14-8: アップロード素材への sublicensable な利用許諾 (サンプル解析エンジンの学習含む)。FL Cloud Storage 内容の AI 学習は art.32 で除外 |
| 準拠法 | ベルギー法 / ゲント §20 | 同 art.24 |
| 改定 | 公開 30 日後に発効、拒否は失効 §19 | 同 art.23 |

### 2.2 リバース・改変・派生物

- `[FL-EULA] §7` (L636–645): "download, duplicate, rent, lease, alter, modify, translate, reverse engineer, decompile, disassemble or create derivative works based on the Software" — "nor give anyone permission to"。法令による例外の但し書き **なし**。
- `[FL-ToU] art.11 General restrictions 1(i)`: 同列挙を "from the Products" に拡張。
- `[FL-EULA] §5` (L594–): ソースコード・構造・組織を含め Image-Line/パートナーの専有、権利は留保。§5 は表示の削除・改変も禁じる。
- `[FL-EULA] §8`: 同梱第三者ソフトにも同様の禁止 (+ "give anyone permission to duplicate or download (even for free), such plugins")。
- 関連: ベルギー法準拠 (§20)。EU ソフトウェア指令 (2009/24/EC) の相互運用目的の逆コンパイル等の法定例外は、**本書の同梱テキストには現れない一般論点**であり、適用範囲 (「FL の機能を再現する wasm 化」が該当するか) は専門家確認事項。開発者の居住国法も別論点。

### 2.3 再配布・ホスティング・SaaS・公開アクセス・レンタル (論点整理)

条項側のキーワードと、ブラウザ配信でそれに触れ得る行為:

| 条項 (出典) | 要旨 | ブラウザ配信での論点 (断定しない) |
|---|---|---|
| 譲渡・提供の禁止 `[FL-EULA] §6` / ToU art.11 General restrictions 2 | ライセンス・キー・アカウント等、"any other mechanism that grants a person, other than the User, access" を提供しない | 公開サーバ上のアプリが「他人に FL 利用を可能にする機構」と評価され得るか (成果物に FL 由来物を含む場合) |
| 利用形態 `[FL-EULA] §4` (L559–; 非同時共用禁止は L572) / ToU art.10-2,3 | 単独の個人が自分の複数 PC で使用可。ネットワーク経由も可だが、**アクセスする全員が個別ライセンス**。非同時でも複数人共用は禁止。**同時使用ライセンスではない** | Access の許可リスト対象。各人のライセンス保有の担保 |
| ASP 禁止 `[FL-EULA] §7(ii)` / ToU art.11 1(ii) | "make access to the Software available to others in connection with a service bureau, application service provider, or similar business" | **サービス提供**: サーバで FL を実行して配信する形は直接の検討対象。クライアント実行の wasm を配る形が「access を available にする」に当たるか、非営利・限定公開が "similar business" か、は論点 |
| 複製の制限 `[FL-EULA] §4` (バックアップ 1 部) / §7(iv) / §2 | 追加複製を禁止。§2 (L510) は "Unauthorized duplication, whether in whole or in part, **temporary or definitive**" を著作権侵害と明記 | **配布 vs 公開**: サーバ上の複製、ブラウザキャッシュ/IndexedDB 上の複製を、適法な保有者本人が行う場合と第三者が行う場合の差 |
| ダウンロード許可の禁止 `[FL-EULA] §7(i)` / ToU art.11 1 ((iii) の末尾に付く節) | "nor shall the User give anyone permission to download the Products" | 公開 URL から FL 由来物を取得可能にする行為 |
| レンタル `[FL-EULA] §7(i)` / ToU art.10-2 | rent/lease 禁止、non-rentable | 時間貸し的な有償提供 (本プロジェクトの想定外) |
| 譲渡・サブライセンス不可 `[FL-EULA] §14` / ToU art.19 (2 つ目) | 第三者への再許諾不可 | — |

3 分類に対する整理 (いずれも未決):
- **「公開」**: URL が誰でも到達可能であること自体と、そこに FL 由来物が含まれるかは別。含まない自作コードのみの公開は FL EULA の直接対象外に見える一方、FL ABI へ依存する shim が「派生物」かは論点。
- **「配布」**: 変換済み wasm・IR・抽出資産を第三者ブラウザへ送る行為。Access で限定してもサーバ→ブラウザの送信は複製の頒布とみなされ得るか、「本人への返送」と評価できるかが論点 (本人限定でも "download" 許可の禁止 art.11 1 ((iii) 末尾の節) は残る)。
- **「サービス提供」**: サーバ側実行は ASP 条項に直接関係する。クライアント側実行でも、サーバ運営者が "access を available にする" 主体になるか。
- **BYO (利用者持込み)**: サーバに FL 由来物が無ければ「配布」「ホスティング」の論点は大きく減るが、**ユーザ手元で行われる変換・翻訳そのものが §7(i) の禁止行為**である点は残る (行為主体が利用者になるだけ)。また現行計画は AOT リフト (RetDec/Ghidra) 後の wasm を配る形で、ブラウザ内で installer を受けて変換する形 (動的変換/エミュレーション) とは **技術的に別アーキテクチャ** — 運用形態 C を採るなら設計の再検討が必要 (§8)。

### 2.4 認証・アクティベーション・オンライン検証・テレメトリ・アカウント

外部通信機能は本プロジェクトで対象外 (`docs/DECISIONS.md` D3 / 元戦略 `docs/REFERENCES.md` `[STRATEGY]` §6.7)。条項との関係:

- **アンロックはアカウント認証前提**: ToU art.5-1 "unlock FL Studio by email and password"、"logging in and unlocking FL Studio confirms … the Software activation"。インストーラ画面文言 `[NSIS-FL]` も "enter your Image-Line account e-mail and password in the About window to unlock the program from trial mode"。既存解析の外部 URL: `support.image-line.com/member/regfile_unlock.php`, `/action/license/serial`, `/action/redirect/FLStudioAuthentication` (`docs/REFERENCES.md` `[MAC]` の REPORT §5.3)。→ オンライン認証不能なので wasm 版は**未登録 (トライアル) 状態が既定**になる (※ 2026-10-10 ユーザ指示により設計上方針確定: ライセンス機構を無力化し「登録済み」として振る舞う — §6.0)。
- **未登録でも主要機能は使える** (ToU art.8-1: "fully-functional … does not require registration to enable its primary functionality")。ただし無料版は "does not allow the User to open stored items after closing the Software" (art.4-4)、デモ版 plugin は保存プロジェクト再読込時に空スロットへ置換 (`[FL-EULA] §4` 末尾 / ToU art.10-6)。登録が無効なら demo モードで動作する旨の画面文言あり (`NotReggedTxt.txt`)。
- **Cracked の定義**と無権利条項 (§0-3)。登録コード/アンロック用データを自作・偽装・流通させる設計は避け、必要なら **利用者本人の正規データをローカルに入れる**形に限る (※ 2026-10-10 ユーザ指示により、ライセンス状態データの配置・合成は正規保有者であるユーザの承認の下で許容する方針に確定 — §6.0。本節は条項の事実整理のまま残す)。
- **キー管理**: ToU art.12-7 "In case the Users registration key is found to be available or accessible to any third party on any website, ftp site or otherwise, … blocked and rendered unusable"。サーバ (R2) に利用者のキー・アカウント情報を保存しない (strategy §6.7 の「ローカル IndexedDB のみ」と整合)。art.12-3: 不正使用/配布を知った場合は Image-Line へ通知義務、art.13: 身分証による所有者確認の可能性。
- **テレメトリ/データ**: 専用のテレメトリ条項は無い。`[FL-EULA] §9`: 一部インストーラは推奨ソフトの収益化ソリューションが **インストール中のみ** 非個人情報を収集。`§16` / ToU art.15: プライバシーは別ポリシー参照。ToU art.14-8 は **Image-Line サービスへアップロードした素材**の利用許諾 (外部通信対象外なので wasm 版では通常発生しない)。ランタイムの通信内容自体は本調査の対象外 (strings 由来の URL 一覧のみ既存解析にある)。
- **補助ツール**: win に `System\Tools\License\CopyLicenseToAllUsers.exe`, `RemoveLicenses\RemoveLicenses.exe` (登録情報の配置/削除用。文言/EULA 的含意は未調査)。

### 2.5 トライアル/デモの制限

- `[FL-EULA] §7` (L658–): トライアル/デモ版の利用は **私的利用のみ**、作成物の商用 (営利/非営利とも) 利用は禁止。違反時は成果物の所有権・収益を Image-Line が取得し得る旨と帳簿提出義務まで規定。ToU art.11 "Demo or trial versions" も同旨。
- → 外部認証なしで動かす wasm 版を使った成果物の扱いは、未登録=トライアル扱いか、利用者が別途登録済みかで変わる (確認事項 §8)。

---

## 3. サードパーティ/OSS (FL 同梱分)

### 3.1 OSS 一覧と条件

`[FL-LIC]` に本文があるもの (mac/win 同一)。「wasm 再ビルド時の主な条件」は条文の要旨 (転載ではない)。

| 名称 (出典 `System/Texts/Licenses/…`) | ライセンス | wasm 再ビルド/配布時に効く主な条件 |
|---|---|---|
| FFmpeg (`ffmpeg.txt`) — mac 同梱 n4.4.3 / win 同梱 n4.4.2 (`avcodec-58` 系、`WIN/block24433`–`24439`。※ `docs/REFERENCES.md` `[WIN64]` の REPORT §4.2 の「FFmpeg 6.x」は誤り) | `ffmpeg.txt` 冒頭は LGPL-2.1+ と記載 (本文 LGPL-2.1)。**win 実ビルド**の configure 文字列は `--enable-version3` (=LGPLv3+)、`--disable-libx264/x265/xvid`、`--enable-libmp3lame --enable-libopus --enable-libvorbis --enable-libsrt …`、`--enable-gpl` は無し。バイナリ内の license 文字列は win `libavcodec license: LGPL version 3 or later`、mac (x86_64/arm64 とも) `LGPL version 2.1 or later` (mac の configure 文字列 `--enable-shared --disable-programs --disable-avfilter …` に `--enable-gpl`/`--enable-version3` 無し) | 通知・ライセンス本文の同梱 (§6 L105)、完全なソース or 書面オファー (§6a/c, L107–109)、**差し替え可能なリンク機構** (§6b, L108)、結合物条件が改変とそのデバッグ目的 RE を許すこと (§6, L103)。GPL 部品 (`--enable-gpl`/libx264 等) を有効にしない。version3 系の部品を避ければ v2.1 のまま。「GPL 部分が使われると全体に GPL」(`ffmpeg.txt` L3) |
| LAME (`lame.txt`; `System/Legal/LAME MP3 encoder/LGPL.txt`) | `lame.txt`: LGPL。**別ライブラリとしてリンク**、LAME への謝辞とサイトリンク、改変は LGPL で還元。**デコード機能 (mpglib) は GPL** で GPL でないプログラムは使えない旨の注意 (L18–27)。同梱 `LGPL.txt` は実体 **GPL v2 本文** (名称不一致) | encoder のみ使用・差し替え可能な別モジュール化・mpglib デコード部を使わない。upstream から再ビルドする場合は upstream の COPYING を採用 |
| Python 3.12.1 (`python.txt`, mac `Python.framework/.../LICENSE.txt`, win `Shared\Python\LICENSE.txt`) | PSF License (+ BeOpen/CNRI/CWI/0BSD の歴史的文書、組込 SW の表記: OpenSSL (Apache-2.0)、expat、zlib、libffi、mpdecimal 等) | PSF 著作権表示の保持 (§2)、派生物提供時に変更の要約 (§3)。組込ライブラリの表記一式を NOTICE に |
| FreeType (`freetype.txt`) | FreeType Project License (BSD 系 + 謝辞条項) | 配布物の文書に "based in part of the work of the FreeType Team" 相当の **謝辞必須** (§2, L118–)、ソース再配布時は FTL.TXT 保持・変更明示 (§2, L111–)、名称の広告利用禁止 (§3, L129) |
| Blend2D (`blend2d.txt`) | zlib | 出所を偽らない、改変版の明示、表示の削除禁止。謝辞は任意 |
| Ogg/Vorbis (`ogg vorbis.txt`)・FLAC (`flac.txt`) (Xiph) | BSD-3-Clause | 著作権表示・免責の再掲 (バイナリは文書中)、名称での宣伝禁止 |
| WavPack (`wavpack.txt`) | BSD-3-Clause (Conifer) | 同上 |
| PyTorch (`pytorch.txt`) | BSD-3-Clause 系 (Facebook ほか多数の著作権表示) | 同上 (推論用途で wasm に入れるかは別問題) |
| Demucs (`demucs.txt`) / svgren (`svgren.txt`) / ZGameEditor (`zgameeditor.txt`) | MIT | 著作権表示・許諾表示を全複製物に |
| Symbiosis (`symbiosis.txt`) | BSD-2 (雛形のまま `<YEAR>`/`<COPYRIGHT HOLDER>` が未置換) | 同上。原文が雛形のため権利者表記は上流確認が必要 |
| DelphiFFmpeg ヘッダ (`delphiffmpeg.txt`) / DelphiZip (`delphizip.txt`) | BSD 系 (二条項/三条項相当) | FL の Delphi バイナリ内に静的に含まれる部品 (lift 対象側)。個別再配布の扱いは §3.3 の非再配布方針に従う |
| フォント (`MAC/Shared/Artwork/Fonts/*`) | ライセンス本文あり: SIL OFL (Cuprum, Francois One, Barlow, Italianno, Josefin Sans, Khand, Orbitron, Oswald, PT Sans, Revalia, Share, WebSymbols) / Apache-2.0 (Open Sans Condensed, Roboto Condensed)。**本文なし**: Ubuntu 系、04b03、American-Captain、Antaris、Chosence、ornamentsFont ほか | OFL: 単体販売不可・予約フォント名・同ライセンス維持。Apache: NOTICE/表示の維持。本文なしのフォントは出所未確認のため、wasm 同梱前に要確認 |

メモ:
- Xfer OTT 自体も Roboto Condensed (Apache-2.0)、zlib 1.2.3 を内蔵 (`docs/REFERENCES.md` `[ANALYSIS-PLUGINS]` の `plugins/ott/REPORT.md` / binaries strings)。Kilohearts Installer は Roboto フォントを同梱 (`Resources/fonts`、ライセンス本文は未確認。Roboto は通常 Apache-2.0)。
- `[FL-ABOUT]` の "FFmpeg … under the LGPLv2.1" と win 実ビルド (`--enable-version3`) の **記載差** がある。LGPLv3 の追加条項 (ユーザ製品での Installation Information 等) が効くかは再ビルド側が選べば避けられる。
- **Open Sans (代替フォント候補、LGL-9 #816)**: FL 同梱の `Artwork/Fonts/OpenSans-{Regular,Light,Semibold,CondBold,CondLight}.ttf` (`tools/legal/notices/fonts.json`) は同じ dir に OFL 本文が無く `origin-unverified` (出所未確認)。本文の出所として確認できたのは upstream `googlefonts/opensans` 3.003 の `OFL.txt` (SIL OFL 1.1、Reserved Font Name 指定なし) で、commit 固定・sha256 付きで `tools/legal/notices/registry.json` の `open-sans` (`kind: font-asset`、`bundled: true`) に登録済み (#616 / LGL-8 成果、`tools/legal/notices/REPORT.md`)。wasm 同梱する場合の条件は OFL §1〜§5 (単体販売不可・同ライセンス維持・著作権表示と本文の同梱・改変版での予約名不使用)。代替フォントは無改変で、FL 同梱の旧版とはバイト列が異なる。NOTICES への反映は registry 経由で自動生成し、生成ゲートは #86 [LGL-3] の範囲 (未完)。法的助言ではない。

### 3.2 LGPL 等 — wasm 静的リンク時に効く論点

- **結合物 (combined work)**: 1 つの wasm モジュールに LGPL ライブラリと独自コードを静的リンクすると、LGPL-2.1 §6 の「結合物を任意条件で配布できるが、顧客自身の改変と、改変デバッグのための RE を許す条件であること」が要る (`ffmpeg.txt` L103)。FL 由来のリフト済みコードは Image-Line EULA の下にあり、改変・RE を禁止している (§2.2) → **同一モジュールに入れる設計は衝突の論点**を生む。L115 に "such a contradiction means you cannot use both them and the Library together in an executable that you distribute" と明記。
- **差し替え可能性**: §6(b) の "suitable shared library mechanism" (実行時にライブラリを使い、改変版でも正しく動く) を wasm で満たす方法 = Emscripten の `SIDE_MODULE` (別 .wasm ファイル) 化、または再リンク可能なオブジェクト/ビルドスクリプトの提供 (§6(a))。ブラウザの動的ロードが「適切な機構」に当たるかは専門家確認事項。
- **ソース提供**: §4 / §6(a),(c),(d): 同一サイトからの配布なら同一場所でソース提供で足りる (L91)。upstream をそのまま再ビルドする方針なら、使用 upstream のバージョン・configure 引数・パッチを公開物に添える運用が要る。
- **GPL 混入防止**: FFmpeg/LAME の configure に `--enable-gpl`/`--enable-nonfree`/`--enable-version3`/GPL 系外部ライブラリ (x264/x265 等) が入っていないことを CI で確認 (FL 同梱ビルドのコンフィグ文字列は GPL 無しだが version3)。
- **謝辞/表記**: FreeType (必須)、BSD 系 (著作権表示+免責)、MIT、PSF、Apache (NOTICE) を成果物の文書に出す仕組みが必要 (自動生成を推奨、§8)。
- **GPL**: LilyPond (win `System\Tools\LilyPond`, `…\share\doc\licoli\README`)、Pango/GLib 系 DLL は別プロセス/別ツールで、wasm 本体に取り込む計画は無い (本書では条件を調べていない)。

### 3.3 非 OSS の第三者技術 (`[FL-ABOUT]` "Used technologies")

本文は同梱されず、条件不明。FLEngine 内にあるものはリフトの結果 wasm に含まれる/依存することになる:
zplane (Auftakt / élastique Pro / Metering / Restore)、Chicken Systems (Sample Format Translator)、SoftVoice、Reeverb (Ultrafunk)、BeatSlicer (P. Segerdahl)、SimSynth (D. Billen)、DrumSynth (P. Kellett)、Intel IPP (win: `dsp_ippv2`)、ReWire/REX (Reason Studios)、ASIO/VST (Steinberg)、CLAP / CLAP for Delphi、NDI (win `Processing.NDI.Lib.x64.dll`)、WebView2/Edge (win)。

- `[FL-EULA] §8` はこれら第三者ソフトにも複製・改変・派生物禁止を及ぼす (ToU では書換え、§2.1 参照)。zplane 等が個別に再許諾条件を持つかは不明。**これらは upstream から再ビルドできない商用コード**であり、wasm 化物に含まれる以上、再配布不可方針 (strategy §6) に従う。

---

## 4. プラグイン各社の条項

### 4.1 Xfer Records (OTT / Serum 2) — `[XFER]`
- (a) "intended to be used only by the individual who purchased it" / (b) 複数台インストール可だが "every machine is under personal ownership and care of Licensee" / (b) 複製はバックアップ目的のみ。
- (c) "prohibited from reverse engineering, decompiling, translating, disassembling, deciphering, decrypting, or otherwise attempting to discover the source code" — **法令による例外の但し書き無し**。
- (e) "may not share, publish or distribute the software without prior consent from Xfer Records"。
- 無し: ホスティング/ASP 条項、認証条項、準拠法、損害賠償の上限 (免責のみ)。
- OTT は無償 (Xfer freeware ページ: `v1.37 freeware`) だが、win インストーラのライセンス画面は上記と同一文で、(a) の「購入者」記述と整合しない。**無償でも (e) により再ホストは同意が要る**論点。OTT mac pkg にはライセンス画面なし。
- Serum 2 は Xfer アカウントのブラウザ認可 + Machine ID + オフライン license ファイル (`TGT/serum2/REPORT.md` §5.2、外部サポート記事に基づく記述)。認可は wasm 版では実行不能 → demo 動作か外部注入かの方針が要る (同 REPORT §8-1)。

### 4.2 Kilohearts — `[KH]`
- §1(a): 有効な License Key が必要、鍵を第三者と共有しない。有償製品は複数 PC に入れられるが **同時に別 PC で使えない** (または 1 台で全員が物理的に同席)。無償 ESSENTIALS は同時使用も可。§1(d): TRIAL (約 10 日・商用不可・譲渡不可) / NFR / GIFT。§1(e): FULL ライセンスは別の Kilohearts アカウントへ無償で移転可 (Content Bank 除く、移転でキーが変わる)。
- §2(c): "may not reverse engineer, decompile, or disassemble … except and only to the extent … permitted by applicable law" — **法令例外あり**。「改変」「派生物」「ホスティング」への言及なし。§2(a) 著作権表示を除去しない。§3: 違反時に終了・全複製破棄。
- 技術側: HeartCore に PACE iLok/Eden + Kilohearts 独自 LicenseManager (`TGT/kilohearts/REPORT.md` §5)。ライセンス層の扱いは方針事項 (同 REPORT §7・KH-8)。

### 4.3 Slate Digital (Fresh Air) — `[SLATE-ToS]` (オンライン・非同梱)
- Fresh Air のインストーラ/zip に **EULA は含まれない** (ファイル名判定。`tools/legal/REPORT.md` §2)。同梱 User Guide は "An iLok license is required to use Fresh Air. … Fresh Air will not function without a valid license" (`TGT/freshair/work/guide.txt` 相当、PDF p.5, p.11)。
- 公式 ToS (Audiotonix General Terms of Use; 契約主体は地域で Slate Digital LLC / Audiotonix Group Ltd / Klang Technologies GmbH、準拠法 California / England & Wales / Germany):
  - §3.1: "Each license is to be used by only one (1) person and cannot be shared."
  - §6: "copy, modify, host, stream, sublicense, or resell the Services and Software"; "…as a part of a hosted service, or on behalf of any third party"; "circumvent any access or use restrictions"; "data scraping for machine learning".
  - §16: "modify, port, adapt, or translate"; "reverse engineer (including but not limited to monitoring or tracking the inputs and outputs flowing through a system or an application in order to recreate that system), decompile, disassemble"; AI/ML への利用禁止 (C); 法令上の逆コンパイル権がある場合も **事前に情報を請求**する義務。
  - → 既存の `tools/targets/freshair` の「実機機械語との入出力 bit-exact 比較」型の検証は §16(B) の括弧書きに文言上近い、という論点がある。
- Fresh Air は Kilohearts "HeartCore" 上の製品 (`TGT/freshair/REPORT.md`)。Kilohearts EULA は Kilohearts 製品に適用され、Fresh Air にどちらが適用されるかは文書からは不明。

### 4.4 Native Instruments (Massive X) — `[NI-EULA]` (オンライン・非同梱)
- 同梱版の有無・Web 版との同一性は未確認 (`tools/legal/REPORT.md` §1、§7)。作成時は検索スニペットのみだったが、検収時に公式ページ全文 ("Latest Version 2026-07-01", 契約主体 inMusic NI GmbH) を取得して確認:
  - §3.1 "not entitled to copy or have copied, decompile or have decompiled, reverse engineer or have reverse engineered the Product or parts thereof"、データマイニング (Sec. 44b German Copyright Act)・AI 学習目的の利用禁止。§3.5 改変は機能維持・復旧目的を除き不可。
  - §3.3 3 台まで・同時使用不可、"may not be used on a network by multiple users, unless each user possesses a license"。§3.6 レンタル・貸与は禁止、恒久譲渡は一定条件で可。§3.7 サウンドライブラリ作成の禁止 (Sound License Agreement)。
  - §2.1 Native Access でのアカウント作成とシリアル登録が必要 (未アクティベートは "demo mode")。§7.3 ドイツ法。ホスティング/ASP/service bureau に当たる文言は無い。

---

## 5. 各社条項の差異表

| 観点 | Image-Line EULA.html | Image-Line ToU | Xfer | Kilohearts | Slate/Audiotonix (online) | NI (online) |
|---|---|---|---|---|---|---|
| RE/逆コンパイル | §7(i) 禁止 (例外なし) | art.11-1(i) 同 | (c) 禁止 (例外なし) | §2(c) 禁止、**法令許容分は除外** | §16 禁止 + 入出力監視型 RE + AI/ML 禁止。法令権がある場合も事前請求 | §3.1 禁止 + AI/データマイニング禁止 |
| 改変/翻訳/派生物 | §7(i) 明記 | 同 | RE 列挙内の "translating" のみ | 明記なし | §16(A) "modify, port, adapt, translate, derivative works" | §3.1 (他の使用は書面同意要)、§3.5 改変不可 (機能維持・復旧目的を除く) |
| 再配布/共有 | §6, §7 | art.11 | (e) 共有・公開・配布は事前同意 | 鍵の共有禁止 (§1(a)) のみ、本体再配布条項なし | §3.1 共有不可、§6 resell/sublicense | 貸与禁止、譲渡は条件付 |
| ホスティング/ASP | §7(ii) | art.11-1(ii) | 明記なし | 明記なし | §6 host/stream/hosted service/service bureau | 明記なし |
| 複数人/同時利用 | §4: 個別ライセンス、非同時でも共用不可 | art.10-3 | (a)(b) 本人+本人所有機材 | §1(a) 有償は同時に別 PC 不可、無償は可 | §3.1 1 人 1 ライセンス | §3.3 3 台まで・同時使用不可、ネットワーク利用は各ユーザ個別ライセンス |
| 認証/アカウント | アカウント/登録コード、Cracked 定義 | art.5-1,12-7,13 | Serum 2: アカウント認可/Machine ID。OTT: なし | License Key + PACE iLok | iLok (User Guide) | Native Access + シリアル登録、未アクティベートは demo mode (§2.1) |
| トライアル制限 | 私的利用のみ、成果物の商用不可 | 同 | — | TRIAL 商用不可 / NFR 私的・商用とも不可 | trial/beta 条項あり (§3) | — |
| 準拠法/管轄 | ベルギー/ゲント | 同 | 記載なし | 記載なし | California / England & Wales / Germany、北米は仲裁 | ドイツ法 §7.3 (商人は Berlin §7.2) |
| 規約変更 | 30 日後に発効 §19 | 同 art.23 | — | — | 公表で即時 §1.4 | — |

---

## 6. 運用形態別の論点増減表と共通の緩和策

### 6.0 運用規程 (確定)

**2026-10-10 ユーザ指示により確定。** 指示原文: 「全てのライセンス機構は無力化してください。アクティベーションは無条件で通過します。必要であれば cracked リソースを配置可能です。」

1. **運用形態 B (確定)**: Cloudflare Access で限定公開・非頒布。ユーザは FL Studio および対象プラグイン (Serum 2 / Massive X / Kilohearts / Fresh Air) の正規保有者であり、限定公開環境での自己運用を目的とする。
2. **ライセンス/アクティベーション機構の無力化**: FL 本体・同梱プラグインの全ライセンス/アクティベーション機構を無効化する。ライセンス状態は常に「アクティブ済み/登録済み」として振る舞う (無条件アクティベーション)。
3. **オフライン**: オンライン認証・アクティベーション通信は行わない。Gopher / FL Cloud / 更新確認など他の外部通信も既定方針どおり無効のまま (方針の正本は `docs/DECISIONS.md` D3)。
4. **ライセンス状態データ**: レジストリ値・ライセンスファイル等、ライセンス状態を示すデータはユーザ (正規保有者) の承認の下で配置・合成してよい (「必要であれば cracked リソースを配置可能」の指示を含む)。
5. **stub 方針の確定**: §0-3 / §8 で「未回答」だった「未登録のまま起動 vs 登録済みを装う」は **「登録済みとして振る舞う (無条件アクティベーション)」** に確定 (ユーザ指示 2026-10-10)。
6. **Cracked 定義との関係 (事実の参照のみ)**: `[FL-EULA] §1` の "Cracked" 定義・無権利条項との関係は §0-3 / §2.4 の既存記載を参照すること。本節では新たな判断・断定を行わない (本書は法的助言ではない)。
7. **適用範囲**: 本方針はアクティベーション/ライセンス機構に関するもの。élastique/REX/GPC/NI 派生など OSS 再配布ライセンスの論点 (§3 / 下表 R7) は **別件であり未回答のまま** (CAB-162)。→ 2026-10-14 に運用方針としては `docs/DECISIONS.md` D20 (配布 tier で扱いを分ける。法的助言ではない) で答えた。

以下の論点増減表・緩和策は、規程確定後も「条項上の論点の多寡」の参照情報として残す (適法/違法の判定ではない)。

凡例: ● 論点が直接発生 / △ 解釈・設計次第で発生 (要確認) / ○ 軽減される (消えるとは限らない) / – 通常は発生しない。これは「条項上の論点の多寡」であり、適法/違法の判定ではない。

形態: **A** 非公開ローカル PoC (現状、成果物を外に出さない) / **B** Cloudflare Access で限定公開 + 変換済み wasm をサーバ (R2) に置く / **C** Access 限定公開 + 利用者が正規インストーラを持込み、ブラウザ内で処理 (サーバに FL/プラグイン由来物なし) / **D** 手元ビルド用ツールだけ配布 (成果物は配らない、strategy §6.6) / **E** 無認証公開 + 変換済み wasm 配置。

| 論点 (主な出典) | A | B | C | D | E |
|---|---|---|---|---|---|
| R1 RE・逆コンパイル・翻訳・改変・派生物 (作業そのもの) FL §7(i)/ToU 11-1(i)、Xfer (c)、KH §2(c)、Slate §16、NI §3.1 | ● 開発者本人 | ● | ● 実施者が利用者へ移動 (消えない) | ● 同左 | ● |
| R2 変換済み成果物 (wasm/IR/資産) が他者環境へ渡る FL §6,§7、ToU 11-1 ((iii) 末尾の節)、Xfer (e) | – | △ 許可リスト内でも「送信=頒布」か | – | – (ツールが FL 固有解析結果を内包すれば △) | ● |
| R3 複数人/ネットワーク利用 FL §4、KH §1(a)、Slate §3.1、Xfer (a)(b) | – | △ 許可者全員が個別に保有 | △ 同左 | – | ● 誰でも |
| R4 ホスティング/ASP/service bureau FL §7(ii)、Slate §6 | – | △ サーバが FL 派生物を提供 | ○ サーバは FL を持たず実行もしない | – | ● |
| R5 複製・保管 (installer/抽出物) FL §4 (バックアップ 1 部)・§7(iv)・§2 (一時複製も) | ○ | △ クラウド側に複製が存在 | △ ブラウザ内ストレージ (利用者機材) | ○ | ● |
| R6 認証/鍵/Cracked FL §1-2、ToU 3-3・11-2・12-7 | △ 起動検通 stub の線引き | △ + 鍵のサーバ保管は避ける | △ 本人データをローカルのみ | △ | ● stub 付き成果物の公開は "distribution of cracked versions" の懸念 |
| R7 OSS 条件 (LGPL 差替え/ソース提供/表記) `[FL-LIC]` | – 非頒布 | △ 頒布に当たるなら | ● 自作+upstream OSS を頒布 | ● ツール/ソース頒布 | ● |
| R8 非 OSS 第三者技術 (zplane/IPP 等) が成果物に混在 FL §8 | △ | ● 派生物に同梱 | – | – | ● |
| R9 トライアル制限 (外部認証不可→未登録) FL §7、ToU 4-4・8-1・11 | △ 共通 | △ | △ | △ | △ |
| R10 規約改定/失効 (30 日で発効、拒否=失効) FL §19、ToU 19-3・23 | △ 共通 | △ | △ | △ | △ |

運用形態を問わず効く緩和策 (技術側で実装できる線引き):
1. **再配布物にバイナリを含めない**ことを機械的に担保 (公開前に dist を走査し、FL/プラグイン由来のバイト列・資産ハッシュを拒否する「release guard」)。
   - 2026-10-13 実測: ilmcp の名称 JSON 2 件は release guard PASS・dist 非収録。名称は FL 由来文字列を含むが、guard の PASS は配布可否を代替しない (法的助言ではない・配布可否は未決 LGL-1)。詳細は `tools/legal/release-guard/REPORT.md` の LGL-7 節。
2. Access の許可リストは **本人 (ライセンス保有者) のみ**。複数人に開く場合は各人の個別保有を前提に文書化。
3. **利用者の登録キー/アカウント情報はサーバに送らず保存しない** (ローカルのみ)。ライセンス stub 方針は 2026-10-10 ユーザ指示により「登録済みとして振る舞う (無条件アクティベーション)」に確定 (§6.0)。ライセンス状態データはローカルでの配置・合成とし、サーバには保存しない。
4. OSS は upstream から再ビルド、**FL 由来コードと別モジュール (差し替え可能)**、`--enable-gpl` 等を禁止、NOTICE を自動生成。
5. 各社規約の最新版を取得・差分監視 (FL は 30 日で規約改定が発効)。→ 実装: `pnpm terms-watch` (LGL-5 #88、`tools/legal/terms-watch/REPORT.md`)。台帳は `docs/LEGAL_TERMS_LEDGER.md`。

---

## 7. 見つからなかった/確認できなかった文書、出所に関する事実

見つからない/読めなかった:
- **Native Instruments (Massive X)**: 同梱 EULA は**未確認** (`tools/legal/REPORT.md` §1)。Web 版 EULA は検収時に全文確認済み (§4.4)。Web 版と同梱版の同一性は**未確認**のまま。
- **Slate Digital (Fresh Air)**: 同梱 EULA はファイル名判定では**なし** (`tools/legal/REPORT.md` §2)。公式 ToS はオンライン版のみで、適用される版は未確認。
- **Xfer OTT (mac)**: pkg に `<license>` なし。OTT 専用の規約文書は未確認 (共通 Xfer EULA が win ライセンス画面に出る)。Xfer の公式規約ページは**公式ページなし** (確認日 2026-10-14、`tools/legal/REPORT.md` §3)。
- **Image-Line FAQ (公開)**: 未確認。LGL-6 の範囲だが本文書では扱っていない。
- **Image-Line (実際に承諾した版)**: 公開 ToU / EULA は台帳 `fl-tou-web`・`fl-tou-rtf`・`fl-eula-html` の 3 版で保持済み (§2.1)。依頼者が実際に承諾した版は依頼者の記録事項で確認できないため**未確認**。運用形態 B では他の作業の前提にしない (§6.0)。
- **Intel IPP / zplane / Chicken Systems / SoftVoice / Ultrafunk / ReWire / NDI / WebView2 / Edge Update** の個別ライセンス本文: 同梱なし。
- **win の NSIS ヘッダは全体を読んだわけではない** (ライセンス関連語での検索のみ)。`CopyLicenseToAllUsers.exe`/`RemoveLicenses.exe` の挙動・文言は未調査。
- ランタイムのテレメトリ/通信内容の実測は対象外 (静的な文字列由来の URL のみ)。

出所に関する事実 (Fresh Air、評価はしない):
- win zip は導入後ツリーを平坦化した形 (`C__Program Files_Common Files_VST3/...`)、Inno Setup 5.5.7 の `unins000.exe`/`unins000.dat` (更新 2026-10-09) を同梱 (`TGT/freshair/REPORT.md` §1)。
- mac pkg: `Packages` 1.2.10 で作成、識別子 `com.MakingGreatestPizza.pkg.FreshAirGUSEPPE{au,vst3,uninstaller,content}`、arm64 のみ。
- win コアには PACE/iLok 実装が見当たらず (User Guide は iLok 必須と記載)、AAX にのみ Kilohearts AB / PACE "ILokCC" の署名鎖がある (`TGT/freshair/REPORT.md` §4.1「不一致」)。
- 以上からファイルだけでは「正規の未改変インストーラか」を確認できない。Image-Line ToU の "Cracked" 定義は Image-Line 製品に関するもので、Slate 製品側の同種条項は ToS (§6 "circumvent any access or use restrictions") を参照。**入手元の確認をユーザに依頼 (§8)。**

整合しない記述 (メモ):
- `docs/REFERENCES.md` `[WIN64]` の REPORT §4.2 (L110) と §7 の表 (L185) は FFmpeg を「6.x」とするが、同梱 DLL の ident は `n4.4.2-2-g7ffb7d4b04-20220622` (`avcodec-58`/`avutil-56`)。mac 同梱 dylib は `n4.4.3-1-ga1f13b592b`。
- `LAME MP3 encoder/LGPL.txt` が GPL v2 本文。`[FL-ABOUT]` は FFmpeg を LGPLv2.1 と記載するが win ビルドは `--enable-version3`。
- README の「プロプリエタリ plugin を wasm 化して**同梱**」の「同梱」は、strategy §6 の「第三者へ頒布しない」と文言上緊張関係 (意図の確認、§8)。

---

## 8. ユーザ確認事項と次タスク案

確認事項:
1. **運用形態の意向** — **確定 (2026-10-10)**: §6 の **B** (Cloudflare Access で限定公開・非頒布)。ユーザは FL・対象プラグインの正規保有者として限定公開運用を行う (§6.0 運用規程)。C (持込みインストーラ) / D (手元ビルドツール) に付随していた論点は運用形態 B の採用により当面未浮上。
2. **Image-Line の保有ライセンス**: 登録済みか、トライアルか、エディション/購入経路 (Box・Payment Plan・Academic 等)。実際に承諾した版 (installer の ToU か、アプリ同梱 EULA.html か)。
3. **ライセンス stub の方針** — **確定 (ユーザ指示 2026-10-10)**: 「登録済みとして振る舞う (無条件アクティベーション)」。ライセンス機構は無力化し、ライセンス状態データ (レジストリ値・ライセンスファイル等) はユーザ (正規保有者) の承認の下でローカルに配置・合成する。詳細は §6.0 運用規程。Cracked 定義との関係は §0-3 / §2.4 の事実整理を参照 (判断は加えない)。
4. **Fresh Air / Kilohearts / Serum 2 の入手元と保有ライセンス** (Slate/Audiotonix アカウント、iLok、Xfer アカウント)。OTT の再ホスト可否 (Xfer への同意取得の意向)。
5. **Massive X** を対象に残すなら NI のインストーラ/EULA の提供。
6. 専門家 (弁護士) 確認を取るか、ベンダへの許諾問い合わせを行うか (本書は問い合わせを開始しない)。

次タスク案 (下流チケット):
- **LGL-1**: 運用形態を確定し本書 §6 を単一形態の「運用規程」に書き換え (M11「EULA/非再配布運用固定化」と統合)。
- **LGL-2**: `release guard` — 公開前に dist/R2 同期対象を走査し、FL/プラグイン由来バイト列・資産ハッシュ (`[ANALYSIS-DIR]`/* から生成した deny-list) を検出したら失敗させる。
- **LGL-3**: `THIRD_PARTY_NOTICES` 自動生成 (FreeType 謝辞、BSD/MIT 表示、PSF、Apache NOTICE) + upstream バージョン/configure 記録。
- **LGL-4**: FFmpeg/LAME 等の LGPL 部品を side module (差し替え可能) として upstream から再ビルドする設計 + `--enable-gpl`/`--enable-version3` 検出 CI。
- **LGL-5**: 規約差分監視 (FL ToU/EULA.html、Xfer、Kilohearts、Slate、NI の最新版取得・ハッシュ比較) を FL 追従プロセスに追加。 → 実装済み (7 件の基準線を台帳に記録。Xfer は OTT win インストーラの NSIS ヘッダから取得。`tools/legal/terms-watch/REPORT.md`)。
- **LGL-6**: 一次文書の補完取得 (NI Massive X インストーラ同梱版 EULA ※Web 版は確認済み、Slate Fresh Air 個別条項、Xfer 公式規約、Image-Line の公開 ToU/FAQ)。

---

## 付録: 抽出・再現手順

```
# FL EULA (HTML) → テキスト
python3 -c "import re,html,sys;s=open(sys.argv[1],encoding='utf-8',errors='replace').read();s=re.sub(r'(?is)<(script|style).*?</\1>','',s);s=re.sub(r'(?i)<br\s*/?>|</(p|div|li|h\d|tr)>','\n',s);print(html.unescape(re.sub(r'<[^>]+>','',s)))" "$MAC/System/Legal/EULA.html"
# win/mac 同一性
cmp "$WIN/block24719_DATA.bin" "$MAC/System/Legal/EULA.html"                      # EULA.html
cmp "$WIN/block00029_DATA.bin" "$MAC/../Resources/en.lproj/license.rtf"   # ToU (RTF)
# FFmpeg ビルド構成 (win)
rg -a -o -m1 -- '--prefix=/ffbuild[^\x00]{0,3000}' "$WIN/block24434_PE.bin"
rg -a -o 'FFmpeg version [^\x00]{0,60}' "$WIN/block24433_PE.bin"
# NSIS ヘッダ (非 BI 版: OTT/Serum 2) のライセンスページ文: 先頭 2MB から DEADBEEF"NullsoftInst" を探し
#   [u32 flags][sig16][u32 hdrsize][u32 arcsize][u32 csize|bit31] の後を zlib raw (-15) か LZMA で解凍し、
#   UTF-16LE として "Licensee is prohibited" 周辺を取り出す (実装: `docs/REFERENCES.md` `[LEGAL-WORK]` の `nsis_hdr.py`)
# FL win (BI flags=0x30) は `docs/REFERENCES.md` `[WIN64]` の `tools/nsis_extract.py` と同じ LZMA(raw, lc3 lp0 pb2, dict 8MB) でヘッダ解凍
# win ファイル一覧: WIN/block25163_DATA.bin (path/size/mtime のテキスト)
```
抽出物 (リポジトリ外・所在は `docs/REFERENCES.md` `[LEGAL-WORK]`): `{fl_mac_eula.txt, win_terms_of_use.txt, ott_nsis_license.txt, serum2_nsis_license.txt, nsis_hdr.py, fa/guide.txt}`。
