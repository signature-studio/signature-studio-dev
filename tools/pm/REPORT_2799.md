# tools/pm 付録 — #2799 VM 状態の取り込み手順の是正と補助スクリプトの測定

> **正本の宣言**: 取り込みの手順と値域は `infra/pm-worker/README.md` (『VM の状態の取り込みと書き出し』) が正本。本付録は補助スクリプト `infra/pm-worker/scripts/build_import.mjs` の測定値の正本 (`docs/DOC_MAP.md` §4)。合成データの生成と検査は `infra/pm-worker/scripts/measure_import.mjs` (§2 のコマンド)。
> `tools/pm/REPORT.md` は 249 行で上限 250 行のため、本付録に置いた (本体は無変更)。

**結論**: 取り込み手順の 2 つの誤り (整形出力で 413、説明文・`none` 混在の素材行で 400) を、README の手順の修正と補助スクリプトで直した。合成データで、整形出力と `jq -cn` の出力は Worker の検証で 400 (問題 48 件) になり、補助スクリプトの出力は通ることを確かめた。実 VM の状態では測っていない (§6)。

## 0. 測定の条件

- 測定 commit: `7c861c6b` (`infra/pm-worker/scripts/measure_import.mjs` を入れた、コードを変えた最後の commit)。`build_import.mjs` と `test/unit/build_import.test.ts` は `1958e1c3` から変えていない。
- 差分 (コード範囲): `git diff 7c861c6b HEAD -- infra/pm-worker/src infra/pm-worker/scripts infra/pm-worker/test` の出力は 0 行 (後の commit は本付録と `docs/DOC_MAP.md` だけ)。よって測定は HEAD でも同じ結果になる。
- 環境: runner (4 CPU)。各測定の直前の load average (1 分平均) は 0.75〜0.82 (`uptime`)。node v22.23.3・pnpm 12.10.1・vitest 4.1.11・jq 1.7。`pnpm install --frozen-lockfile` は変更なし。
- 生成物 (合成データと 3 本文) は `infra/pm-worker/work/` (gitignore) に置き、コミットしていない。

## 1. 手順の誤り (PM の報告。実測は §2〜§3)

- **413**: 旧手順の `jq -n` は整形して出力し、PM の報告では 220 KB になり `/admin/import` の上限 (`MAX_IMPORT_BYTES` = 200 * 1024 = 204,800 バイト) を超えた。README の『200 KB』は 200 KiB と書き直した。
- **400**: `relaunch.json` の `art` と `issues_state.json` の `pm_art` の行に、説明文・括弧書き・`none` と素材名の混在が付いていた (PM の報告)。`launch_issues.py` の relaunch の作り方 (`cand = base + extra`) は、`base` が `oc_artifacts: none` のとき `oc_artifacts: none fl-win64` を作る。`pm_art` は PM の投稿の最後の `oc_artifacts:` 行をそのまま保存する (`tools/pm/issue_snapshot.py`)。

## 2. 合成データでの比較 (実 VM の値ではない)

- 再現 (リポジトリの root で。`jq` と Node が要る):

  ```sh
  node --experimental-strip-types --no-warnings infra/pm-worker/scripts/measure_import.mjs
  ```

  合成データを `infra/pm-worker/work/import/` に書き、3 本文の大きさと Worker の検証 (`parseVmState`・`src/vmstate.ts`) の結果を表で出す。出力は下の表と一致する。
- 合成データ: issue 番号 **11〜90 の連番 80 件** (`launched`・`relaunch`・`pm_art` の各 80 件)。
  - `relaunch`: n が 5 の倍数 (16 件: 15, 20, …, 90) は `none` と素材名の混在。6 の倍数で 5 の倍数でない (11 件: 12, 18, 24, 36, 42, 48, 54, 66, 72, 78, 84) は括弧書き。それ以外は `null`。
  - `pm_art`: 4 の倍数 (20 件: 12, 16, …, 88) は括弧書き。90 は許可外の `fetchsh` (1 件)。それ以外は素材名だけ (3 種の組み合わせ)。
- 結果 (バイトは書いたファイルの大きさ。`jq` の出力は末尾の改行 1 B を含む):

| 本文 | バイト | parseVmState | 問題数 | うち relaunch | うち pm_art |
|---|---|---|---|---|---|
| `jq -n` (整形・旧手順) | 18684 | 400 | 48 | 27 | 21 |
| `jq -cn` (README の式) | 13837 | 400 | 48 | 27 | 21 |
| `build_import.mjs` | 12585 | ok | 0 | 0 | 0 |

- 問題 48 件 = relaunch 27 (混在 16 + 括弧書き 11) + pm_art 21 (括弧書き 20 + 許可外 1)。`parseVmState` の問題の上限 (`MAX_PROBLEMS` = 50) には届いていない。
- 整形を外すと 18684 → 13837 B (4847 B 小さい)。`build_import.mjs` は 13837 → 12585 B (1252 B 小さい。jq の末尾改行 1 B を含む)。
- 合成データは 200 KiB (204800 B) に届かない。413 は再現していない (PM の報告の 220 KB は、PM の実データの件数が分からないため未測定)。
- `build_import.mjs` の標準エラーは 2 行 (issue #90 の `pm_art` の許可外の語と、行ごと除いたこと)。

## 3. 補助スクリプトの単体テスト (`npm run test:unit`)

- 測定 commit `7c861c6b` の HEAD で実行 (`infra/pm-worker`): 5 files・**70 件 PASS** (うち `build_import.test.ts` 25 件)。vitest Duration 1.60 s、wall 1.94 s、exit 0 (測定直前の load average 0.82)。
- 件数の内訳: 既存の `test/unit/` が 4 files・45 件 PASS (`--exclude test/unit/build_import.test.ts` で実測)。本変更で足したのは `build_import.test.ts` の 25 件。
- `build_import.test.ts` の内容: 許可リストと上限が `src/launch.ts` と `src/vmstate.ts` の値と一致すること。素材行の正規化 13 件 (括弧書き・全角の括弧・`none` と名前の混在・許可外の語・バッククォート・カンマ区切り・重複)。組み立ての結果 (relaunch の全落ちは `null`・count は残す、pm_art の全落ちは行ごと除く)。出力が `parseVmState` を通ること。落とした語が issue 番号と一緒に出ること。phase が null・pm_art が無いときは失敗すること。整形しない JSON であること。200 KiB を超えると投げること。CLI の正常系・上限超過 (終了 1・標準出力は空)・phase null (終了 1)・引数不足 (終了 2)。

## 4. 既存の全体 (`npm test`・node の test runner)

- 測定 commit `7c861c6b` の HEAD で実行: **327 件 PASS・fail 0**、node の duration 16,401.7 ms、wall 16.51 s、exit 0 (測定直前の load average 0.75)。
- 件数は本変更で増えない (新しいテストは `test/unit/` にあり、`npm test` の対象 `test/*.test.ts` の外)。

## 5. Negative control (テストが効くこと)

測定 commit `7c861c6b` で、`infra/pm-worker/scripts/build_import.mjs` を 1 か所だけ壊し、`npx vitest run --config vitest.unit.config.ts test/unit/build_import.test.ts` (`infra/pm-worker`) を実行した。FAIL したテストは下の通り。元に戻して `cmp` で HEAD のファイルと一致することを確かめた。

- M1: `normalizeArtLine` で `none` を名前より優先する (判定の 2 行の順を入れ替える) → **2 件 FAIL** (25 件中 23 件 PASS)。
  - `素材行の正規化` › `oc_artifacts: none fl-win64`
  - `本文の組み立て` › `正規化した値になる (relaunch.art の全落ちは null・count は残す / pm_art の全落ちは行ごと除く)`
  - 「出力は Worker の検証を通る」テストは PASS する。出力の `oc_artifacts: none` は Worker の検証を通る行のため。
- M2: 200 KiB の上限の判定を外す (`if (false && bytes > MAX_IMPORT_BYTES)`) → **2 件 FAIL** (25 件中 23 件 PASS)。
  - `本文の組み立て` › `200 KiB を超える本文は投げる (何も返さない)`
  - `コマンド` › `上限を超えると終了 1・標準出力は空 (何も書かない)`
- ログは repo の外の作業用 dir に置き、コミットしていない。

## 6. 未解決

- **実 VM の状態での再現は未測定**。VM の `relaunch.json`・`issues_state.json` は本環境に無い。413 (220 KB) と 400 の件数は PM の報告のみ。実機の取り込み (`?apply=1`) は依頼者 (PM) の操作で、本変更では行わない。
- `IMPORT_REQUIRED` の既定の変更 (#2795) は未 merge。README は『#2795 の後は』と条件を書いた (本付録の範囲外)。
- `npm run test:workers` (workerd) は本変更で Worker のコードを変えていないため実行していない (`src/` の差分は 0 行。§0)。
