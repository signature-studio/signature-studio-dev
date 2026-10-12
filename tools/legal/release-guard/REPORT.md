# release guard (LGL-2, #85)

> 既知類型との関係 (docs/DEFECTS.md): 該当なし (lift / IR 系ではない)。事実整理であり法的助言ではない (`docs/LEGAL.md` §6「共通の緩和策 1」)。

## 結論

公開物 (`dist` / stage 入力 / stage 済み `deploy/work/site`) を走査し、`[ANALYSIS-DIR]`/* 由来の deny-list に一致したら **非ゼロ終了**するゲートを実装し、deploy 経路 (`05-stage.mjs`・`20-worker.mjs --phase release`・`deploy.sh`) に組込んだ。
バイパスは `--skip-release-guard` の明示のみ。deny-list が無い場合も **fail-closed (exit 4)**。

## 使い方 (1 コマンド)

```sh
# deny-list 生成 (素材のある環境のみ。出力は gitignore 済み tools/legal/release-guard/work/denylist)
pnpm release-guard:build -- --from <FL 抽出物 dir> [--from <plugin dir> ...] [--manifest tools/assets の manifest.json ...]
# 走査 (dist / 任意の manifest / パス一覧)
pnpm release-guard -- --src <dist> [--manifest deploy manifest.json] [--list paths.txt --root dir] [--allowlist f] [--json out.json]
pnpm release-guard:test          # 単体テスト (素材不要)
```
deploy 経路: `bash deploy/scripts/deploy.sh --src <dist>` が 05-stage (入力) と 20-worker release (配備物。part 分割後) で自動実行。環境変数 `RELEASE_GUARD_DENYLIST` / `RELEASE_GUARD_ALLOWLIST` で場所を上書き。

終了コード: 0 PASS / 2 引数不正・走査対象 0 件 / 4 deny-list 欠落 / 5 deny-list 不正 / 6 違反検出。

## 検出方式

| 種別 | deny-list の中身 | 検出 |
|---|---|---|
| file | 素材ファイル (512 B 以上) の sha256 | 公開物のファイル全体の sha256 一致 |
| window (代表バイト列) | 内容定義サンプリング (buzhash・窓 48 B・mask 0x3ff) で選んだ窓の sha256 先頭 8 B。ASCII テキストのみの窓と distinct byte < 16 の窓は除外 | 同じ方式で公開物をサンプルし 1 つでも一致 (オフセット・結合・埋込に依存しない) |
| chunk | `tools/assets` manifest の `chunks.id` (内容アドレス 32hex) | `c/<xx>/<id>.{raw,br,zst}` のキー一致 |

- `.br` / `.zst` / `.gz` は **展開後ストリームも**走査する (tools/assets の圧縮 chunk を想定)。展開失敗は raw のみ走査 + note。
- allow-list (`allowlist.json`): `{path: glob, sha256, kinds, reason(必須)}`。自作コード・shim・OSS 再ビルド物を運用形態 (LGL-1) に従って許容する。既定は空。
- deny-list 本体 (windows.bin) は素材由来の指紋 (8 B ハッシュ) であり原バイトは復元できないが、素材由来物なので **commit しない** (`work/` は gitignore)。

## 実測 (検証起点: 下記コミット済み HEAD。素材 = `fl-win64.tar.zst` 展開 3,419,555,130 B / 25,168 files)

環境: GitHub Actions runner、node v22.23.3、ほぼ単独実行 (load average 0.2〜1.3、並列 1)。

| 項目 | 実測 | 定義 |
|---|---|---|
| deny-list 生成 | 34.3 s (n=2: 34.306 / 34.325) | 25,168 files を 1 パス (sha256 + サンプル) |
| deny-list 規模 | windows 2,067,704 件 (windows.bin 16.5 MB) / file sha256 18,351 件 | file は 512 B 以上のファイルの distinct sha256 |
| クリーン走査 | PASS 1970 files 23,421,976 B / 0.82 s | `git ls-files` の追跡全ファイルを別 dir にコピーしたもの |
| 単体テスト | 12/12 PASS (所要は下の「クリーン HEAD 再現」) | `pnpm release-guard:test` |

### ネガティブコントロール (実 FL 素材。いずれも exit 6 = FAIL を確認)

| 混入の仕方 | 結果 |
|---|---|
| `block24835_PE.bin` (141,384 B) をそのままコピー | file 一致 + window 99 件 |
| `block25164_PE.bin` (201,742,544 B) の 40,000 B 部分切出し | window 35 件 |
| 上記 141,384 B を brotli / zstd 圧縮 (`a.br` / `a.zst`) | 展開後 file 一致 + window 99 件 (各 FAIL) |
| 正規インストーラ exe (1,106,033,456 B) をコピー | file 一致 + window 1,077,087 件 / 9.84 s |
| `20-worker.mjs --phase release --site <違反 dir>` | exit 6 (wrangler に到達せず)。`--skip-release-guard` 付きのみ exit 0 + 警告 |
| deny-list 無し | exit 4 (`--skip-release-guard` 無しでは通過不可) |

### 検出下限 (`measure.mjs`、実 FL 抽出物の 1MiB 以上のファイルからランダム n=60 の逐語 slice)

| slice 長 | 512 B | 1 KiB | 2 KiB | 4 KiB | 8 KiB | 16 KiB | 64 KiB |
|---|---|---|---|---|---|---|---|
| 検出数 / 60 | 18 | 25 | 47 | 51 | 54 | 55 | 56 |

別算法の検算: 切出し元に対する `Buffer.indexOf` で全 slice (各 60/60) が逐語に存在することを確認済み (= 検出対象である)。64 KiB で 56/60 に留まるのは、窓サンプルの除外条件 (ASCII 窓・低多様性窓) により、テキスト/ゼロ埋め中心の領域には窓が無いため。そのような領域は **file sha256 一致でのみ**検出される。

### 開発中に直した誤検知 (記録)

初版は窓除外条件なしで、実リポジトリの追跡ファイル 1970 files 中 **20 files が誤検知** (`docs/LEGAL.md`、`tools/ipp/shim/fft/pffft/*` の BSD ライセンス文、`tools/python/analysis/mcp/mcp_tools.json` の API 名)。FL 同梱の OSS ライセンス文・API 名と共有される ASCII テキスト窓が原因。ASCII のみの窓を除外して 0/1970 にした。副作用: テキスト資産の**部分**コピーは検出範囲外 (下表)。

## 範囲 / 範囲外

検証範囲: fl-win64 素材由来の deny-list・上記のネガティブコントロール・deploy の stage/release ゲート。
範囲外 (主張しない): plugins-* (OTT / Kilohearts / Serum2 / Fresh Air / Massive X) 由来の deny-list (素材未取得。`--from` を足して再生成すれば同じ手順で対応)・mac 素材・wasm 化で**変換された**バイト列 (命令列が別物になるため一致しない。逐語/断片の混入のみが対象)・暗号化/未知形式の圧縮・難読化・実デプロイ。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| plugins-* と mac 素材から deny-list を生成して実測していない | 当該素材の混入は未検出 | #85 にコメント (素材名: `plugins-*`, mac) → 素材取得後に `release-guard:build --from` を追加で再実行 |
| deny-list が commit されないため CI/他環境では fail-closed (exit 4) になる | CI で deploy するには R2 素材から生成する工程が要る | #8 / #36 (R2 同期・実デプロイ) へ前段条件としてコメント |
| 変換済み wasm (lift 出力) が FL バイトを含まないため検出されない | 変換物の再配布可否は本ゲートの対象外 | LGL-1 (運用形態の確定) の判断事項として LGL-1 の issue にコメント。`docs/LEGAL.md` §6 R2 |
| ASCII テキスト資産の部分コピー・64 KiB でも約 7% の slice が未検出 | 小断片・テキスト断片は取りこぼしうる | 本 REPORT の限界として明記。必要なら mask を下げて再生成 (`--mask 0xff` 等・deny-list 肥大とのトレードオフ) |
