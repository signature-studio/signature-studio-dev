# notices REPORT — THIRD_PARTY_NOTICES 自動生成と upstream 版・configure 引数の記録 (LGL-3, #86)

> 既知類型との関係 (docs/DEFECTS.md): 該当なし (lift / IR 系ではない)。**事実整理であり法的助言ではない** (`docs/LEGAL.md` §3.2・§6 緩和策 4)。
> 検証起点: コミット `17a3f15` (クリーン detached worktree)。素材 = `fl-win64.tar.zst` (FL Studio 26.1.7 win64 5653)。環境: GitHub Actions runner、nproc=4、node v22.23.3 (emsdk 同梱 node v24.19.0 は wasm64 テスト用)、emcc 6.0.12。

## 結論

- `THIRD_PARTY_NOTICES.{txt,html}` を**決定的**に生成する仕組みを実装した (同じ入力 → 同じバイト列。n=3 で `cmp` 一致)。入力は
  (1) 部品台帳 `registry.json` (2) OSS wasm 再ビルドごとの記録 `records/*.json` (3) FL 同梱表記 `System/Texts/Licenses` 15 本 (sha256 を pin し読み出し時に検証)
  (4) FL 同梱フォント一覧 `fonts.json`。FreeType の謝辞 (FTL §2)・BSD/MIT 表示・PSF・LGPL 部品の「upstream 版 / ソース sha256 / configure 引数 / パッチ / 差し替え方法」を出力する。
- 再ビルド記録は各 `build.sh` が**成功時に** `record.mjs` で書く。実際に **7 本の build.sh を実行して 12 件の記録を生成**した (freetype / ogg (libogg+libvorbis) / flac (1.5.0, 1.3.1) / wavpack (4.80.0, 4.60.1) / sidemod (FFmpeg n4.4.2 + LAME 3.99.5) / blend2d (+AsmJit) / CPython 3.12.1)。
- 欠落検出は 3 層: (a) `check` (素材不要): 同梱 OSS の記録欠落・build.sh の未登録・repo 内の未登録ライセンスファイル・記録の不整合・GPL 系フラグ (b) 成果物走査: NOTICES の欠落/不完全/古さ + 記録なし OSS の痕跡 + GPL 系の痕跡 (c) deploy `05-stage.mjs` ゲート (exit 7)。
- **未達 (Closes にしない理由)**: GitHub Actions の job は**この App に `workflows` 権限が無く push できなかった** (実測: `refusing to allow a GitHub App to create or update workflow ... without workflows permission`)。job 定義は `ci/notices.yaml` に置いた。有効化は §未解決 1。

## 使い方 (1 コマンド)

```sh
pnpm notices:test                     # 単体テスト (素材不要)
pnpm notices:check [-- --artifact <dist>...]   # registry / 記録 / repo の整合 + 成果物の欠落検出 (素材不要。違反は exit 1)
FL_WIN64_DIR=<FL 抽出物> pnpm notices -- --out <dir> --strict   # NOTICES 生成 (FL 同梱表記を読めないと strict は exit 3)
FL_WIN64_DIR=<FL 抽出物> bash tools/legal/notices/e2e.sh [--wasm <実 wasm の dir>]   # 上記 + vite build + ネガティブコントロール + deploy ゲート
node tools/legal/notices/cli.mjs fonts|pins --fl-dir <FL 抽出物>   # fonts.json / registry.flTexts の再生成 (FL 追従時)
```
`vite build` は `thirdPartyNotices()` プラグインで NOTICES を dist に出す (FL 素材が無いと**不完全**で警告のみ。`NOTICES_STRICT=1` で build を失敗させる)。
`deploy/scripts/05-stage.mjs` は NOTICES が無い/不完全/registry と不一致、記録なし OSS・GPL 系の痕跡があると exit 7 (バイパスは `--skip-notices-gate` の明示のみ)。
再ビルド記録の更新: 該当 `bash tools/shared/oss/<name>/build.sh` を再実行する (成功時に `records/<id>.json` を上書き)。

## 構成

| ファイル | 役割 |
|---|---|
| `registry.json` | 部品台帳 20 件 (rebuilt 11 / vendored 1 / fl-embedded 8、うち同梱 18)。種別・ライセンス・謝辞・`records`・`flTexts`・`coveredBy`・走査用 `signatures`、FL 同梱表記 15 本の pin (block・size・sha256)、同梱禁止 `forbidden` |
| `records/*.json` | 再ビルド記録 12 件 (計 106,140 B)。upstream URL・ソース tarball sha256 または git commit・**ライセンス本文 (upstream)**・configure/cmake 引数・パッチ (path+sha256+要約)・toolchain 版・ターゲット。時刻と絶対パスは入れない |
| `fonts.json` | FL 同梱フォント 129 件 (`license-text` 2 / `origin-unverified` 127)。同じ dir に `OFL.txt` 等が無いものは出所未確認 (`docs/LEGAL.md` §3.1) |
| `lib.mjs` / `cli.mjs` / `record.mjs` / `vite-plugin.mjs` | 生成・検査・記録・vite 組込み |
| `notices.test.mjs` / `e2e.sh` / `xcheck.py` / `ci/notices.yaml` | 単体テスト 37 件 / 1 コマンド E2E / 別算法の検算 / Actions job 定義 (未有効化) |

設計判断:
- **upstream 本文は記録に埋め込む** (sha256 で改ざん検出)。CI に素材が無くても、再ビルド OSS の NOTICES は記録だけで生成できる。FL 同梱表記は素材 (FL) 由来なので repo に複製せず (release guard の file sha256 一致を避ける)、registry に sha256 を pin して**読み出し時に検証**する。FL 更新で本文が変わると不完全になる (FL 追従の検出)。
- NOTICES の Appendix A に FL 同梱表記 15 本を**原文のまま**全て載せる。FL 側の `blend2d.txt` は © が二重エンコード (`C3 82 C2 A9`) のままだが、原文どおり出す。
- fl-embedded (DelphiFFmpeg / DelphiZip / svgren / ZGameEditor / Demucs / PyTorch / Symbiosis) は lift 範囲が未確定のため**保守的に掲載** (`bundled=true`)。外す場合は `bundled=false` + `reason` を registry に書く。
- 記録は**スナップショット**。build.sh の引数を変えたのに再実行しないと食い違う (未解決 4)。

## 実測 (検証起点 17a3f15・クリーン worktree。n=3 は min–max)

| 項目 | 実測 | 定義 |
|---|---|---|
| `e2e.sh --wasm` 全体 | **ALL PASS**・4.11 / 4.17 / 4.12 s (n=3、load average 終了時 0.31–0.42、並列 1) | PASS 20 項目 = 単体 37 件を 1 項目 + check + vite build (strict) と出力 3 + 実 wasm 8 本の走査 + NEG 9 + stage ゲート 3 (NEG 1 を含まない) |
| 単体テスト | 37/37 PASS・0.36–0.37 s (n=3) | `node --test notices.test.mjs`。うち NEG 系 22 |
| `check` (素材不要) | PASS・0.05 s (n=3) | components=20 (bundled 18)・records=12・fonts=129 |
| `generate --strict` | 0.06 s (n=3)・txt 228,484 B / html 229,311 B・18 component | txt の sha256 `8d865fec…` が 3 回とも同一 |
| 成果物走査の速度 | 335,544,340 B の単一 wasm: 2.87–2.88 s (n=3)・最大 RSS 224 MB | 16 MiB chunk・境界は最長 signature-1 B 重ね。signature 23 + 禁止 9 |
| 実 wasm での検出 | 8 本中 7 本で再ビルド OSS (7 component) を検出 | 各 build.sh が出した wasm をそのまま走査。検出内訳は下記 |

実 wasm (各 build.sh の成果物) の検出結果: ffmpeg.wasm (4 signature) / lame.wasm (2) / freetype (`FREETYPE_PROPERTIES`) / ogg_vorbis (`Xiph.Org libVorbis`) / wavpack (2) / flac (`reference libFLAC`) / python.wasm (`Fatal Python error`)。
**検出できなかった**: blend2d の試験用 wasm (ライブラリ由来の識別文字列が無い。共有 API 名が export される本番モジュールなら `blContextInit` で検出する設計だが未確認)、libogg (固有文字列なし)。

build.sh 実行の所要 (逐次、emsdk 6.0.12 を `$RUNNER_TEMP` に導入):

| build.sh | 結果 | 秒 | load average 終了時 |
|---|---|---:|---|
| freetype | rc=0 (native==wasm32==wasm64) | 73 | 2.73 |
| ogg | rc=0 | 15 | 1.42 |
| wavpack | rc=0 | 21 | 1.45 |
| flac | rc=0 | 35 | 1.25 |
| sidemod (FFmpeg + LAME) | rc=0 | 120 | 3.14 |
| blend2d (+AsmJit) | rc=0 | 169 | 7.86 |
| tools/python/build_cpython_wasm.sh | rc=0 | 279 | 3.38 |

### 別算法の検算 (lib.mjs / record.mjs を使わない・`python3 tools/legal/notices/xcheck.py --fl-tar $HOME/artifacts/fl-win64.tar.zst`)
- 記録 12 件 × (ソース tarball の sha256 を `hashlib` で再計算 / ライセンス本文を **tarball 直読み** (`tarfile`) または `git show` から正規化して再計算 / git commit を `git rev-parse` / パッチ sha256) = **27 件一致・不一致 0**。
- FL 同梱表記 15 本の pin を `tar --zstd -x` で素材から直接取り出して sha256 + サイズ再計算 = **15/15 一致** (同スクリプトの合計は `ok=42 bad=0`)。
- 件数の検算: registry の `bundled=true` 18 件 = 生成物の `[component:` 行 18 件 (`grep -c`)。

### ネガティブコントロール (全て期待どおり FAIL = exit 1。素材は実 FL / 実 wasm)

| 壊し方 | 結果 |
|---|---|
| `records/freetype-2.7.json` を削除 | `records/freetype-2.7.json が無い` (exit 1) |
| 記録の configure 引数に `--enable-gpl` を追加 | `禁止フラグ --enable-gpl` (exit 1) |
| registry の ffmpeg から `coveredBy` を外す | `oss/ffmpeg/build.sh: OSS 再ビルドスクリプトが registry の coveredBy に無い` (exit 1) |
| NOTICES の無い dist | `THIRD_PARTY_NOTICES.txt が成果物に無い` (exit 1) |
| 実 `ffmpeg.wasm` を載せ registry の ffmpeg を `bundled=false` に | `ffmpeg の痕跡 … bundled=false` (exit 1) |
| 同 `ffmpeg.wasm` を brotli 圧縮 (`.br`) して載せる | 展開後を走査して同じく exit 1 |
| 実 `ffmpeg.wasm` 末尾に `libavcodec license: GPL version 2 or later` を注入 | `同梱禁止の部品 ffmpeg-gpl-build` (exit 1) |
| NOTICES の `Registry digest` を書換え | `現在の registry / records と一致しない` (exit 1) |
| 05-stage に NOTICES の無い dist | `notices-gate[05-stage]: FAIL` で **exit 7** (stage 済み site は作られない) |
| FL 同梱表記の内容が pin と違う (単体) | `sha256 mismatch` で不完全 → strict は exit 3 |
| 単体 22 件 | 記録の改ざん・patches 欠落・toolchain 無し・孤児記録・reason 欠落・未登録 build.sh・未登録 LICENSE・chunk 境界を跨ぐ signature ほか |

クリーン HEAD 検証で**実際に 1 件バグを検出**した: ライセンスファイル名の正規表現が `notices.test.mjs` に一致し `check` が自滅 (最初の worktree 検証 `7a36c8d` で FAIL → `a505069` で修正し、単体テストを追加)。

### 既存の 05-stage 呼び出し元への影響 (レビュー指摘対応・検証起点 `32d6a18`・クリーン worktree)

notices ゲートは 05-stage の**全**呼び出しに掛かる。NOTICES を作らない検証用の呼び出しは `--skip-notices-gate` を明示する (リリース物ではない)。呼び出し元の洗い出し: `grep -rn "05-stage"` (*.mjs / *.sh / *.yaml / *.json / *.ts、`node_modules`・`work/` 除く) のうち 05-stage を実際に起動する箇所は 6 か所: `tools/assets/deploy-manifest/e2e.sh:35` (初版で対応済) / `tools/legal/notices/e2e.sh:64-67` (本 PR のゲート検証。フラグの有無を意図して使い分け) / `guard.test.mjs` の `s()` / `chunked.test.mjs:39` / `probe.sh:55` / `deploy/scripts/deploy.sh:23` (リリース経路。`"$@"` を渡すだけで、ゲートは効かせたまま)。`deploy.sh` を呼ぶ repo 内スクリプトは無い (`grep -rn "deploy\.sh"`)。

| 呼び出し元 | 対応 | 実測 (`a57aa0a` = 修正前 → `32d6a18` = 修正後) |
|---|---|---|
| `guard.test.mjs` の `s()` (#11 が 4 回起動) | `s()` の引数に `--skip-notices-gate` | `pnpm release-guard:test`: 修正前 **n=3 全て 11/12** (#11 が `7 !== 0`) → 修正後 **n=13 のうち 11 回が 12/12**、残り 2 回は #6 のみ失敗 (#11 は 13/13 PASS)。所要 0.81–1.02 s (最初の n=3、load average 0.82–0.83、並列 1) |
| `chunked.test.mjs:39` | 引数に `--skip-notices-gate` | 合成 deny-list (`RELEASE_GUARD_DENYLIST`) を与えた環境で 修正前 0/8 PASS (`THIRD_PARTY_NOTICES.txt が成果物に無い`) → 修正後 **7/7 PASS ×3** (0.36–0.43 s)。deny-list が無い環境 (この runner) は修正前後とも exit 4 で 0/8 PASS (n=3、本変更と無関係) |
| `probe.sh:55` | 引数に `--skip-notices-gate` | 実行不可 (Cloudflare 認証が要る)。差分 1 引数のみ |

- #6 (`壊れた .br は raw のみ走査して note を残す`) は本変更と無関係の既存の不安定なテスト: `randomBytes(2000)` を「壊れた brotli」に使っているが、乱数 2000 B が brotli として復号成功したのは 791/20000 標本 (`zlib.brotliDecompressSync` の成否)。復号成功すると `notes.length` が 0 になり `0 !== 1`。修正は本 PR の範囲外 → 未解決 8。
- notices 側に回帰なし (`32d6a18`、fl-win64 展開済): `bash tools/legal/notices/e2e.sh` (`--wasm` なし) は **ALL PASS ×3**・1.14 / 1.58 / 1.60 s (load average 0.68–0.70、PASS 17 項目・FAIL 0)、`notices.test.mjs` は 37/37 ×3 (0.21–0.22 s)。`--wasm` 側 (emsdk が要る 3 件の NEG) は今回再実行していない (build.sh の再実行を伴うため)。PR 本文の `oc_artifacts:` に `toolchain-emsdk` を足したので、再レビューの run で実行できる。
- ネガティブコントロール: 修正前 `a57aa0a` で #11 が 3/3 失敗 (上表) = 指摘の再現。`notices.test.mjs` 側のゲート検証 (`05-stage に NOTICES の無い dist` で exit 7) は変更なし。

## 代替フォント Open Sans / Barlow の登録 (LGL-8, #616。検証起点: コミット `3ec58b5`・クリーン worktree・fl-win64 展開済)

GUI-9 (#186) は Windows 標準フォントを同梱せず Open Sans / Barlow へ alias する。この 2 つを NOTICES に登録し、release guard (#85) と矛盾しないことを実測した。**事実整理であり法的助言ではない**。

- registry に `kind: "font-asset"` を追加し `open-sans` (3.003) / `barlow` (1.408) を `bundled=true` で登録。NOTICES に版・著作権表示・upstream の repo と **commit (40hex 固定)**・ファイルの URL / size / sha256・OFL 1.1 本文 (upstream の `OFL.txt` を sha256 付きで埋込) を出す。取得元は `tools/gui/test/fetch_fonts.sh` (`coveredBy`)。
- 取得物はどちらも Reserved Font Name 指定なし (`OFL.txt` に指定行なし)・無改変。FL 同梱の同名フォント (`fonts.json` の origin-unverified) とは**別バイト列** (FL の Barlow-Regular 98,812 B / OpenSans-Regular 217,360 B に対し、代替は 104,068 B / 147,528 B)。
- `check` は font-asset を検査する: commit/URL の固定・本文 sha256・`coveredBy` の取得スクリプト・検証値台帳 (`fetch_fonts.sh`・`fonts.tsv`) の検証値との一致 (registry だけ更新して取得物が変わる事故の検出)・release-guard allow-list への登録。成果物走査は**ファイル全体の sha256** (size で絞る) で代替フォントを検出し、`bundled=false` なら失敗する。
- **release guard との矛盾を実測で発見**: allow-list 無しだと代替フォントは FL 同梱の旧版と窓を共有し **exit 6** (Barlow 48 窓・OpenSans 10 窓)。公開物に載せられないので `release-guard/allowlist.json` に 2 件を `kinds:["window"]` + sha256 で追加した (file / chunk 一致は許容しない)。

### 実測 (`3ec58b5`。n=3)

| 項目 | 実測 |
|---|---|
| `FL_WIN64_DIR=<fl-win64> bash tools/legal/notices/e2e.sh` | **ALL PASS ×3**・22.45 / 22.65 / 23.76 s (load average 終了時 0.86–1.17、並列 1)。PASS 27 項目・FAIL 0 (うち NEG 12) |
| `notices.test.mjs` | 54/54 PASS ×3・0.24–0.25 s (今回 +17 件。font-asset の NEG 10 + registry 経由 1 + allow-list 1 ほか。FL 素材と `fetch_fonts.sh` 取得物が無いと実フォントの 3 件は skip) |
| `pnpm release-guard:test` | 12/12 PASS ×3 |
| deny-list 生成 (e2e §7) | 18,350 file sha256 / 1,315,811 windows (抽出物 25,166 files のみ。インストーラ exe は含めない) |

ネガティブコントロール (e2e §7。全て期待どおり):

| 壊し方 | 結果 |
|---|---|
| 代替フォント 2 本 + NOTICES を載せた成果物 | notices-check PASS・検出 `barlow,open-sans`・release guard PASS (allow-list 許容 2 files) |
| allow-list 無しで同じ成果物を走査 | release guard exit 6 (window) = allow-list が効いている証拠 |
| FL 同梱の `Barlow-Regular.ttf` (block24367) を載せる | exit 6 (file sha256 一致 + window 78 件)。allow-list があっても通らない |
| 代替 OpenSans を 1 B 付加 | exit 6 (sha256 が変わり allow-list から外れる) |
| FL の PE (block25164) 先頭 40,000 B | exit 6 (window 38 件) = allow-list 追加後も検出力は落ちていない |
| registry の open-sans を `bundled=false` にして実フォントを載せる | notices-check exit 1 (`open-sans の痕跡 … bundled=false`) |
| NOTICES から `[component:open-sans]` を削除 | exit 1 (`同梱 component open-sans が無い`) |
| 単体: sha256 の食い違い・本文改ざん・commit 非固定・allow-list 欠落・取得スクリプト無しほか 10 件 | 各々 `validateFontAsset` が検出 |

- e2e §7 は `fetch_fonts.sh` (ネットワーク + sha256 検証) が失敗したら **FAIL** にする (黙って skip しない)。
- 同じ変更で、main 時点で既に `check` が失敗していた件 (`tools/startup/license_obs/license_obs.sh` が未登録のライセンス名ファイルとして検出。`920f837` 由来) を `ignoreLicensePaths` に登録した。本ファイルは OSS のライセンス文ではなくスクリプト (名前が `license_*` に一致するだけ)。登録しないと `notices:check` が通らず本 PR の検証ができなかった。

範囲外 (主張しない): 他のウェイト (Bold / Light 等) は fetch していないため未登録 (alias 表が要求した時点で追加)。実フォントを公開物へ載せる結線 (VFS #22 からの配布) はまだ無く、`bundled=true` は**載せる前提の保守的登録**。改変・subset 化した版は sha256 が変わるため成果物走査では検出されない (その版を載せるなら registry の追加が要る)。upstream (GitHub raw) の可用性に依存する。

### 回帰の修正 (#935。測定 commit: `d7050457`・ws-2747・fl-win64 は `$RUNNER_TEMP/fl-win64` へ展開・node_modules は main checkout のものを symlink)

- 回帰: #615 (`4890d607`) で `fetch_fonts.sh` の sha256 を台帳 `tools/gui/test/fonts.tsv` へ移したのに、検査は `coveredBy` の先頭ファイル (`fetch_fonts.sh`) 本文だけを見ていたため、`8d632b57` では `notices.test.mjs` 4 件 FAIL (`#1`・`#36`・`#37`・`#53`) と `cli.mjs check` exit 1 (`open-sans`・`barlow` の sha256 が「取得スクリプトの検証値に無い」)。registry と台帳の値は一致しており、取得物の食い違いではない。
- 修正 1 (`f673876e`): `validateFontAsset` は `coveredBy` の存在するファイルを全て連結して検証値を探す。font-asset の `coveredBy` に `tools/gui/test/fonts.tsv` を追加。
- 修正 2 (`d7050457`・レビュー指摘): 修正 1 は sha256 が連結本文のどこかに有るかだけを見ており、名前と sha256 の対応を見ていなかった。修正 1 の `lib.mjs` (`f673876e`) で、`open-sans` の sha256 を `barlow` の値に取り替えると `cli.mjs check` が exit 0 (PASS) になることを実測した。修正 2 は台帳の同名行 (1 列目 = file 名、3 列目 = sha256) で照合する。単体テストと e2e に NEG を 4 件追加。

| 項目 (`d7050457`・n=3。min–max) | 実測 |
|---|---|
| `node --test tools/legal/notices/notices.test.mjs` | 52 pass / 0 fail / 3 skipped・391–396 ms (修正前 `8d632b57` は 47 pass / 4 fail / 3 skipped) |
| `node tools/legal/notices/cli.mjs check` | PASS components=22 (bundled 20) records=12 fonts=129 artifacts=0 (exit 0。修正前 `8d632b57` は exit 1) |
| `FL_WIN64_DIR=<fl-win64> TMPDIR=$RUNNER_TEMP bash tools/legal/notices/e2e.sh` | ALL PASS・PASS 30 / FAIL 0・35.1 / 34.3 / 35.9 s (load average 0.61–0.92、並列 1) |

ネガティブコントロール (検証起点 `d7050457`。e2e §5 と同じ壊し方。出力は `cli.mjs check` の実出力の抜粋。台帳を壊す 3 件は `$RUNNER_TEMP` の複製台帳を `coveredBy` で指す registry を `NOTICES_REGISTRY` で渡す。リポジトリの台帳は触らない):

| NEG | 壊し方 | exit | 出力 (抜粋) |
|---|---|---:|---|
| 再ビルド記録の欠落 (freetype) | `records/freetype-2.7.json` を除く | 1 | `component freetype: 記録 records/freetype-2.7.json が無い (該当 build.sh を実行して記録する)` |
| build.sh が registry に無い (oss/ffmpeg) | registry の ffmpeg の `coveredBy` を空にする | 1 | `tools/shared/oss/ffmpeg/build.sh: OSS 再ビルドスクリプトが registry の coveredBy に無い (記録なしの OSS)` |
| NOTICES の無い成果物 | NOTICES を置かない dir を `--artifact` に渡す | 1 | `[artifact …/empty] THIRD_PARTY_NOTICES.txt が成果物に無い (vite build で出力される…)` |
| 台帳の sha256 を壊す (open-sans) | `fonts.tsv` の OpenSans 行の sha256 を `0` で埋める | 1 | `component open-sans: OpenSans-Regular.ttf: sha256 が取得スクリプトの検証値に無い (台帳の同名行と食い違う。…)` |
| 台帳から行を消す (barlow) | `fonts.tsv` から Barlow 行を削除 | 1 | `component barlow: Barlow-Regular.ttf: sha256 が取得スクリプトの検証値に無い (台帳の同名行と食い違う。…)` |
| sha256 の取り違え (open-sans に barlow の sha256) | registry の open-sans の sha256 を barlow の値に替える | 1 | `component open-sans: OpenSans-Regular.ttf: sha256 が取得スクリプトの検証値に無い (台帳の同名行と食い違う。…)` |

- 修正前の lib.mjs (`f673876e`) で「sha256 の取り違え」を実行すると exit 0 (PASS)。修正 2 で exit 1 になる。
- 単体テスト: `validateFontAsset NEG: 別の部品の sha256 を当てる (名前と sha256 の対応が食い違う)` を追加 (52 pass)。
- 鮮度 (`docs/WORKFLOW.md` §6): `git diff d7050457 HEAD -- tools/legal/notices ':!tools/legal/notices/REPORT.md'` の出力は空 (0 行)。検証 HEAD は本 REPORT 更新 commit。

## 範囲 / 範囲外

検証範囲: 既存 05-stage 呼び出し元の回帰 (`pnpm release-guard:test`・`chunked.test.mjs`)・fl-win64 素材 (FL 同梱表記 15 本・ファイル一覧)・emsdk 6.0.12 で実行した上記 7 本の build.sh・`vite build`・`05-stage.mjs`。
範囲外 (主張しない): GitHub Actions 上での job 実行 (未有効化)・`20-worker.mjs` ゲート・mac 素材・plugins-* 素材由来の同梱 OSS・非 OSS の第三者技術の謝辞 (`docs/LEGAL.md` §3.3)・LGPL §6 の充足判断 (法的判断)・wasm 変換された FL 由来バイト列中の OSS (lift で命令列が変わるため signature は主に export 名/文字列定数頼り)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1. Actions job を有効化できていない (App に `workflows` 権限なし) | CI 上の自動失敗は未稼働。ローカル/`05-stage` ゲートは稼働 | 新規 `[CI-n]` (親 [CI-1] #284): 権限のある人が `cp tools/legal/notices/ci/notices.yaml .github/workflows/notices.yaml`。#86 にコメント済 |
| 2. mac `Shared/Artwork/Fonts` の OFL 本文 (12 family) を NOTICES に反映していない (win の一覧のみ。win で本文があるのは Cuprum / Francois One の 2 つ) | OFL 本文のあるフォントも「出所未確認」に入る | LGL-6 (一次文書の補完取得) に mac 素材付きで依頼 |
| 3. plugins-* 由来の同梱 OSS (OTT の Roboto Condensed (Apache-2.0)・zlib 1.2.3 等) は registry 未登録 | plugin wasm を同梱するとき NOTICES から漏れる | 新規子チケット案 `[LGL-3b]` (素材 `plugins-ott` 等が必要) |
| 4. 記録は build.sh のスナップショットで、引数を変えて再実行しないと食い違うのを自動検出しない | 記録と実ビルドの乖離 | #86 のフォローアップ (build.sh の sha256 を記録して stale 検出する案。再実行コストとのトレードオフ) |
| 5. Blend2D / AsmJit / libogg / pffft は固有の文字列が無く、バイト走査では検出できない (build.sh・vendored 台帳の網羅検査のみ) | 当該部品を記録なしで同梱しても走査では検出できない | #86 のフォローアップ (本番モジュールの export 名で signature を検証) |
| 6. `oss/ffmpeg`・`oss/lame` (PoC ハーネス) と `oss/ilsvg` は record を書かない (配布用の `sidemod` が書く。ilsvg は `bundled=false`) | ilsvg を同梱化するとき記録が必要 | [T-SH-18] #19 にコメント |
| 7. LGPL §6(b) の「適切な共有ライブラリ機構」に side module が当たるかは未確定 | NOTICES の案内文は事実記述のみ | LGL-4 #87 (既出) |
| 8. `guard.test.mjs` #6 が `randomBytes` 依存で不安定 (上記 791/20000)。本 PR は未修正 | `pnpm release-guard:test` が偶発的に 11/12 になる | 新規 `[LGL-n]` (LGL-2 の test fix: 固定バイト列にする)。PM が起票 |
