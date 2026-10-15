# tools/pm 付録 — #2611 `infra/pm-worker/README.md` の release-age の測定値 (CI-113・親 #2585・PR #2592)

> **正本の宣言**: release-age (pnpm 12 `minimumReleaseAge` = 1440 分) の公開時刻・違反の内訳・再現の結果の正本は本書 (`docs/DOC_MAP.md` §4)。
> `infra/pm-worker/README.md` の『Workers Builds の接続状態と pnpm 経路』の release-age の項は、結論 1 行とこの付録へのリンクだけにした。
> `tools/pm/REPORT.md` (250 行上限) には §21 の 1 行のリンクだけを足した (§19 の見出しと正本行を 1 行に統合して行数を保った)。

## 1. 移した内容

- 移し元: `infra/pm-worker/README.md` の release-age の段落 (測定基準の commit `97bfd673` = origin/main)。
- 移した値: 2026-10-14 公開の 3 版の時刻、既定設定の install が落ちた内容 (件数・版・cutoff)、範囲を下げた経緯 (#2691)。
- README に残した結論: 「公開から 24 時間未満の版 (一覧は本書 §2) を含む lock は、その版のうち最も新しいものの公開から 24 時間が過ぎるまで、既定設定の `pnpm install --frozen-lockfile` が失敗する。」(版名と時刻は README に書かない。`pnpm add` の自動除外の 1 行を含む。時刻の正本は §2)
- **issue 本文の案からの変更**: 案は「既定設定の `pnpm install --frozen-lockfile` は 2026-10-15 05:55Z まで失敗する」だった。§3 (a) の実測で現在の lock は既定設定のまま通る (rc=0) ため、この文は現在の lock については成り立たない。失敗するのは 2026-10-14 公開の版を含む lock だけなので、README は条件を付けた文にした。

## 2. 公開時刻 (実測)

取得: `cd infra/pm-worker && pnpm view <pkg> time --json` (registry の `time` 欄)。cutoff = 公開時刻 + 24 時間。

| 版 | 公開時刻 (registry) | cutoff (+24 時間) | 扱い |
|---|---|---|---|
| `miniflare@5.20261012.0-beta` | 2026-10-14T05:43:27.769Z | 2026-10-15T05:43:27Z | 違反 (§3 b) |
| `wrangler@4.151.0` | 2026-10-14T05:50:43.466Z | 2026-10-15T05:50:43Z | 違反 (§3 b) |
| `@cloudflare/vitest-plugin@1.4.2` | 2026-10-14T05:54:48.543Z | 2026-10-15T05:54:48Z | 最遅の cutoff。3 版を同じ lock に含むときは、この時刻を過ぎるまで既定設定の install が失敗する |
| `wrangler@4.150.0` (現 lock) | 2026-10-13T09:24:25.595Z | 2026-10-14T09:24:25Z | 通る (§3 a) |
| `@cloudflare/vitest-plugin@1.4.1` (現 lock) | 2026-10-13T09:30:41.383Z | 2026-10-14T09:30:41Z | 通る |
| `miniflare@5.20261006.2-beta` (現 lock) | 2026-10-13T09:18:46.987Z | 2026-10-14T09:18:46Z | 通る |
| `workerd@1.20261006.1` (現 lock) | 2026-10-06T01:26:30.282Z | 2026-10-07T01:26:30Z | 通る |

- 時刻の取得元の差: install の検証ログ (下の §3 b) の公開時刻と registry の `time` は一致しない。`miniflare@5.20261012.0-beta` は 05:43:25.000Z (検証ログ) と 05:43:27.769Z (registry) で 2.769 秒の差、`wrangler@4.151.0` は 05:48:57.000Z と 05:50:43.466Z で 106.466 秒の差。cutoff の最大 (`@cloudflare/vitest-plugin@1.4.2` の 05:54:48Z) は、どちらの取得元でも 05:55Z の丸めに影響しない。
- 差の原因は未確認 (registry の応答が取得ごとに違うのか、検証ログが別の時刻源を読むのか)。

## 3. 再現 (ネガティブコントロール)

作業は `git worktree add ../ws-2611` で作った `origin/main` (`97bfd673`) の clean な HEAD と、隔離した temp ディレクトリで行った。`~/.npmrc`・`pnpm-workspace.yaml` の既定 (`minimumReleaseAge` 変更なし) のまま。

**(a) 現在の lock: 既定設定の install は通る**

```
cd infra/pm-worker && pnpm install --frozen-lockfile
```

- 結果: rc=0。`Lockfile passes supply-chain policies (159 entries in 982ms)`。`+ wrangler 4.150.0`・`+ @cloudflare/vitest-plugin 1.4.1`・`+ vitest 4.1.11`。`Done in 2s`。
- 測定時刻: 2026-10-15 00:16Z 前後 (install のログに時刻は無い。直前後の `date -u` で確認)。再確認 2026-10-15 00:30Z (HEAD のアーカイブを一時ディレクトリに展開して同じコマンド): rc=0。

**(b) 2026-10-14 公開の版を含む lock: 既定設定の install は落ちる (ネガコン)**

```
# 隔離: packageManager pnpm@12.10.1・allowBuilds (esbuild・workerd) を置いた空の project
pnpm add -D wrangler@4.151.0 --config.minimum-release-age=0   # lock を作る (rc=0)
rm -rf node_modules && pnpm install --frozen-lockfile          # 既定設定 (rc=1)
```

- 結果: rc=1、`ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`。`2 lockfile entries failed verification`:
  - `miniflare@5.20261012.0-beta was published at 2026-10-14T05:43:25.000Z, within the minimumReleaseAge cutoff (2026-10-14T00:16:53.544Z)`
  - `wrangler@4.151.0 was published at 2026-10-14T05:48:57.000Z, within the minimumReleaseAge cutoff (2026-10-14T00:16:53.544Z)`
- 注: この検証の lock には `@cloudflare/vitest-plugin@1.4.2` を入れていない。3 版のうち `@cloudflare/vitest-plugin@1.4.2` の違反は、この実測では出していない (公開時刻 §2 のみ)。
- cutoff (`2026-10-14T00:16:53.544Z`) は検証時点の now − 24 時間。時間の経過で、各版は §2 の cutoff を過ぎると通るようになる。再確認 2026-10-15 00:30Z: lock 生成 (`--config.minimum-release-age=0`) は rc=0、既定設定の install は rc=1、違反は同じ 2 件 (`miniflare@5.20261012.0-beta`・`wrangler@4.151.0`)。

**(c) `pnpm add` は既定設定で違反版を拒否せず、除外へ書き足す (観測)**

```
# 隔離: packageManager pnpm@12.10.1 だけの空の project (allowBuilds なし)
pnpm add -D wrangler@4.151.0                                   # 既定設定 (rc=1)
```

- 結果: 違反版 (`miniflare@5.20261012.0-beta`・`wrangler@4.151.0`) を `pnpm-workspace.yaml` の `minimumReleaseAgeExclude` へ書き足したうえで、rc=1 (`ERR_PNPM_IGNORED_BUILDS`: build script の拒否。release-age の拒否ではない)。書き足しのログは `Added 2 entries to minimumReleaseAgeExclude in pnpm-workspace.yaml (set minimumReleaseAgeStrict to true to gate these updates with a prompt)`。再確認 2026-10-15 00:30Z で同じ結果。
- 含意: `install --frozen-lockfile` は違反版を拒否するが、`pnpm add` は既定設定で違反版を除外に書き足す (その後の失敗は別の理由)。除外が commit されると、既定の拒否は外れる。README の『除外しない理由』は手で除外を書く場合の戒めとして書かれている。README に 1 行足して注意し、方針は子 #3342 で PM が決める (§7)。

## 4. 範囲を下げた経緯 (#2691 の記録)

- 旧 README の記述: 2026-10-14 に 3 版 (`miniflare@5.20261012.0-beta`・`wrangler@4.151.0`・`@cloudflare/vitest-plugin@1.4.2`) で既定設定の install が落ちた (#2691 で実測)。範囲を `wrangler` `^4.150.0`・`@cloudflare/vitest-plugin` `^1.4.1` に下げ、公開から 24 時間以上たつ版の組 (`wrangler@4.150.0` が依存する `miniflare@5.20261006.2-beta`・`workerd@1.20261006.1`) で lock を作り直した。
- 現在の範囲 (`infra/pm-worker/package.json`): `"@cloudflare/vitest-plugin": "^1.4.1"`・`"wrangler": "^4.150.0"` (本付録の取得時点で確認)。
- 版の選び方と『除外しない理由』は README に残した (手順と方針であり、測定値ではない)。

## 5. 取得コマンド (再現)

```
cd infra/pm-worker
pnpm view wrangler time --json | grep -E '"4\.15[01]\.0"'
pnpm view miniflare time --json | grep -E '"5\.20261012\.0-beta"|"5\.20261006\.2-beta"'
pnpm view @cloudflare/vitest-plugin time --json | grep -E '"1\.4\.[12]"'
pnpm view workerd time --json | grep -E '"1\.20261006\.1"'
pnpm install --frozen-lockfile                                 # (a) 現在の lock
```

## 6. 検証範囲

- 測定 commit: `97bfd673` (origin/main)。作業ツリーは clean な HEAD を展開した worktree (`../ws-2611`)。
- 差分の証跡: `git diff 97bfd673 HEAD -- infra/pm-worker/src infra/pm-worker/test infra/pm-worker/package.json infra/pm-worker/pnpm-lock.yaml infra/pm-worker/pnpm-workspace.yaml infra/pm-worker/wrangler.toml` の出力は 0 行 (本付録を commit した後の HEAD で確認)。README の変更は文書だけ。
- 範囲外: Workers Builds の実際の install 結果 (README 既存の注記どおり未確認)。Cloudflare 側の挙動。

## 7. 未解決

なし。`pnpm add` が既定設定で違反版を `minimumReleaseAgeExclude` に自動で書き足す問題 (§3 c) は、PM 判断 (a) で解決した (`minimumReleaseAgeStrict: true`・§8)。
ただし CLI の `--config.minimum-release-age=0` で違反版を通す経路は strict の下でも残る (§8 の結論)。その lock は cutoff までは既定設定の install で止まる。

## 8. #3342 — `minimumReleaseAgeStrict: true` で `pnpm add` の自動除外を止める (実測)

- 方針: PM 判断 (#3342・2026-10-15) の (a)。`infra/pm-worker/pnpm-workspace.yaml` に `minimumReleaseAgeStrict: true` を入れた。`minimumReleaseAge` の値・lock の版・`package.json` は変えない。
- 測定 commit: `233b96584` (strict を入れた commit)。変更前は `233b96584~1` (origin/main)。その後にコードは変えていない (下の差分の証跡)。
- 隔離: 各 project は `packageManager: pnpm@12.10.1` だけの `package.json` と、対象の `pnpm-workspace.yaml` (変更前 / 変更後) を置いた temp dir。`pnpm add` は `</dev/null` の非対話。測定時刻は 2026-10-15 02:00Z 前後 (表の 1〜5 行) と 02:07Z (表の 6・7 行)。

| 条件 | コマンド | 結果 | `pnpm-workspace.yaml` |
|---|---|---|---|
| 変更前 | `pnpm add -D wrangler@4.151.0` | rc=0。`Added 2 entries to minimumReleaseAgeExclude`: `miniflare@5.20261012.0-beta`・`wrangler@4.151.0` (§3 c の再現) | 除外 2 件を書き足した |
| 変更後 | `pnpm add -D wrangler@4.151.0` | rc=1。`ERR_PNPM_NO_MATURE_MATCHING_VERSION`。2 版が minimumReleaseAge cutoff を満たさない (`miniflare@5.20261012.0-beta`・`wrangler@4.151.0`) | 変化なし (diff 0)。`package.json` に wrangler なし |
| 変更後 | `pnpm add -D @cloudflare/vitest-plugin@1.4.2` | rc=1。`ERR_PNPM_NO_MATURE_MATCHING_VERSION`。`@cloudflare/vitest-plugin@1.4.2` と上の 2 版が cutoff 外 | 変化なし (diff 0) |
| 変更後 | `pnpm add -D wrangler@4.150.0` (公開から 24 時間以上) | rc=0。`+ wrangler 4.150.0` | 変化なし (diff 0)。通常の追加は通る |
| 変更後 | `pnpm add -D wrangler@4.151.0 --config.minimum-release-age=0` (CLI で cutoff を 0 にする・02:07Z) | rc=0。`+ wrangler 4.151.0` | 変化なし (diff 0)。`package.json` に `"wrangler":"4.151.0"` が入り、lock に違反版が入る。除外への書き足しは無い |
| 変更後 | 上の行の lock で `rm -rf node_modules && pnpm install --frozen-lockfile` (既定設定・02:07Z) | rc=1。`ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`。`2 lockfile entries failed verification` (`miniflare@5.20261012.0-beta`・`wrangler@4.151.0`) | 変化なし (diff 0) |
| 変更後 | `git archive HEAD infra/pm-worker` を展開し `pnpm install --frozen-lockfile` | rc=0。`Lockfile passes supply-chain policies (verified 1m ago)`・`Lockfile is up to date` | (lock・既定値は変えていない) |

- 結論: strict を入れると、`pnpm add` は既定設定で違反版を除外へ書き足さず、失敗する (表の 2・3 行。除外への書き足しが起きるのは、strict なしの変更前の 1 行目だけ)。通常の版の追加と、現在の lock の `--frozen-lockfile` は変わらない。
- 違反版を通す経路は strict の下でも残る。(i) cutoff を過ぎるまで待つ。(ii) `minimumReleaseAgeExclude` を手で書く。(iii) CLI で `pnpm add -D <pkg>@<版> --config.minimum-release-age=0` を付ける (表の 5 行。README『除外しない理由』が挙げる経路と同じ)。strict は (iii) を止めない。(iii) で入った違反版は、`pnpm-workspace.yaml` を変えずに lock へ入る。その lock は、cutoff までは既定設定の `pnpm install --frozen-lockfile` が `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` で rc=1 になる (表の 6 行)。cutoff (§2) を過ぎると、同じ install は通る。
- (ii)・(iii) は除外や release-age の緩和なので、手で行う場合は README『除外しない理由』に従って判断する。
- 差分の証跡: `git diff 233b96584 HEAD -- infra/pm-worker/src infra/pm-worker/test infra/pm-worker/package.json infra/pm-worker/pnpm-lock.yaml infra/pm-worker/pnpm-workspace.yaml infra/pm-worker/wrangler.toml` の出力は 0 行 (本節を含む commit の後の HEAD で確認)。
- 範囲外: Workers Builds の実際の install 結果 (README 既存の注記どおり未確認)。strict の挙動は pnpm 12.10.1 でだけ確認した。
