# tools/pm 付録 — #2799 VM 状態の取り込み手順の是正と補助スクリプトの測定

> **正本の宣言**: 取り込みの手順と値域は `infra/pm-worker/README.md` (『VM の状態の取り込みと書き出し』) が正本。本付録は補助スクリプト `infra/pm-worker/scripts/build_import.mjs` の測定値の正本 (`docs/DOC_MAP.md` §4)。
> `tools/pm/REPORT.md` は 249 行で上限 250 行のため、本付録に置いた (本体は無変更)。

**結論**: 取り込み手順の 2 つの誤り (整形出力で 413、説明文・`none` 混在の素材行で 400) を、README の手順の修正と補助スクリプトで直した。合成データで、整形出力と `jq -c` の出力は Worker の検証で 400 になり、補助スクリプトの出力は通ることを確かめた。実 VM の状態では測っていない (下の §6)。

## 0. 測定の条件

- 測定 commit: `1958e1c3` (`infra/pm-worker/scripts/build_import.mjs` と `test/unit/build_import.test.ts` を入れた、コードを変えた最後の commit)。
- 差分 (コード範囲): `git diff 1958e1c3 HEAD -- infra/pm-worker/src infra/pm-worker/scripts infra/pm-worker/test` の出力は 0 行 (後の commit は README と本付録と `docs/DOC_MAP.md` だけ)。よって測定は HEAD でも同じ結果になる。
- 環境: runner (4 CPU)。測定開始時の load average `0.14 0.49 0.32` (2026-10-14 19:37 頃)。node v22.23.3・pnpm 12.10.1・vitest 4.1.11。`pnpm install --frozen-lockfile` は変更なし。
- 作業用の一時ファイル (合成データ・検査の script・ログ) はリポジトリの外の一時 dir に置き、コミットしていない。

## 1. 手順の誤り (PM の報告。実測は §2〜§3)

- **413**: 旧手順の `jq -n` は整形して出力し、PM の報告では 220 KB になり `/admin/import` の上限 (`MAX_IMPORT_BYTES` = 200 * 1024 = 204,800 バイト) を超えた。README の『200 KB』は 200 KiB と書き直した。
- **400**: `relaunch.json` の `art` と `issues_state.json` の `pm_art` の行に、説明文・括弧書き・`none` と素材名の混在が付いていた (PM の報告)。`launch_issues.py` の relaunch の作り方 (`cand = base + extra`) は、`base` が `oc_artifacts: none` のとき `oc_artifacts: none fl-win64` を作る。`pm_art` は PM の投稿の最後の `oc_artifacts:` 行をそのまま保存する (`tools/pm/issue_snapshot.py`)。

## 2. 合成データでの比較 (実 VM の値ではない)

- 作り方: issue 80 件 (`launched` 80 件、`relaunch` 80 件、`pm_art` 80 件)。素材は 3 種の許可内の組み合わせ。`relaunch` は n が 5 の倍数のとき `none` と素材名の混在 (16 件)、6 の倍数で 5 の倍数でないとき括弧書き (11 件)、それ以外は `null`。`pm_art` は 4 の倍数で括弧書き (20 件)、それ以外は素材名だけ。`pm_art` の 90 番だけ許可外の `fetchsh` (1 件)。
- 本体のサイズ (バイト):

| 出力 | バイト | Worker の検証 (`parseVmState`) |
|---|---|---|
| `jq -n` (整形・旧手順) | 23,903 | 400 (問題 48 件) |
| `jq -cn` (整形しない・README の新しい jq 版) | 19,029 | 400 (問題 48 件) |
| `build_import.mjs` | 17,210 | ok (問題 0 件) |

- 問題 48 件の内訳は、`relaunch` の混在 16 件、括弧書き 11 件、`pm_art` の括弧書き 20 件、許可外 1 件 (合計 48)。
- 合成データは 200 KiB を超えない。413 は再現していない (PM の報告の 220 KB は、PM の実データの件数が分からないため未測定)。整形を外すだけで約 20% 小さくなることは確かめた (23,903 → 19,029)。

## 3. 補助スクリプトの単体テスト (`npm run test:unit`)

- 測定 commit `1958e1c3` の HEAD で実行: 5 files・**70 件 PASS** (うち `build_import.test.ts` 25 件)。vitest Duration 4.19 s、wall 5.09 s、exit 0。
- 変更前 (`3b866a61`・worktree) の基準: 4 files・45 件 PASS (Duration 3.85 s、wall 4.8 s)。
- `build_import.test.ts` の内容: 許可リストと上限が `src/launch.ts` と `src/vmstate.ts` の値と一致すること。素材行の正規化 13 件 (括弧書き・全角の括弧・`none` と名前の混在・許可外の語・バッククォート・カンマ区切り・重複)。組み立ての結果 (relaunch の全落ちは `null`・count は残す、pm_art の全落ちは行ごと除く)。出力が `parseVmState` を通ること。落とした語が issue 番号と一緒に出ること。phase が null・pm_art が無いときは失敗すること。整形しない JSON であること。200 KiB を超えると投げること。CLI の正常系・上限超過 (終了 1・標準出力は空)・phase null (終了 1)・引数不足 (終了 2)。

## 4. 既存の全体 (`npm test`・node の test runner)

- 測定 commit `1958e1c3` の HEAD で実行: **327 件 PASS・fail 0**、node の duration 22,433.8 ms、wall 22.58 s、exit 0。
- 変更前の基準: 327 件 PASS (wall 22.5 s)。件数は変わらない (本変更の新しいテストは `test/unit/` にあり、`npm test` の対象 `test/*.test.ts` の外)。

## 5. Negative control (テストが効くこと)

スクリプトを一時的に壊し、テストが FAIL することを確かめた後、元に戻して `cmp` で一致を確認した。

- M1: `none` と名前が混在したとき、`none` を残す (名前の優先を外す) → **3 件 FAIL** (`oc_artifacts: none fl-win64`・正規化の組み立ての結果・Worker の検証)。ログ: 一時 dir の `m1.log`。
- M2: 200 KiB の上限の判定を外す (`if (false && …)`) → **2 件 FAIL** (200 KiB を超える本文・CLI の上限超過)。ログ: 一時 dir の `m2.log`。
- 注: 同じ M1・M2 の最初の試行では、各 5 件の FAIL が出た。直後の再実行 (上の件数と、ログを残したもの) では 3 件・2 件だった。最初の試行の差の原因は特定していない。上の件数は再実行のログに基づく。

## 6. 未解決

- **実 VM の状態での再現は未測定**。VM の `relaunch.json`・`issues_state.json` は本環境に無い。413 (220 KB) と 400 の件数は PM の報告のみ。実機の取り込み (`?apply=1`) は依頼者 (PM) の操作で、本変更では行わない。
- `IMPORT_REQUIRED` の既定の変更 (#2795) は未 merge。README は『#2795 の後は』と条件を書いた (本付録の範囲外)。
- `npm run test:workers` (workerd) は本変更で Worker のコードを変えていないため実行していない (`src/` の差分は 0 行。§0)。
