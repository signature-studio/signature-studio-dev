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

## 範囲 / 範囲外

検証範囲: fl-win64 素材 (FL 同梱表記 15 本・ファイル一覧)・emsdk 6.0.12 で実行した上記 7 本の build.sh・`vite build`・`05-stage.mjs`。
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
