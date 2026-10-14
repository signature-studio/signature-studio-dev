> **正本**: 本書 (`tools/pm/REPORT_APPENDIX_2461.md`) が #2461 の測定の正本。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない (`docs/DOC_MAP.md` §1)。PM Worker の他の測定は `tools/pm/REPORT.md` §10〜§12。

# #2461: user_answered の回答を MEMBER / OWNER / COLLABORATOR のコメントに限る

測定した commit: `d9d35ff5` (origin/main `6505235b` を取り込んだ merge。コードを変えた最後の commit)。PR の変更 commit は `836e71a8` (`fix(pm-worker): count user_answered only from MEMBER/OWNER/COLLABORATOR comments (#2461)`)。
取り込みで pm-worker に main 側の 11 ファイルの変更 (別 PR 由来) が入ったため、§2・§4 の数値は取り込み後の HEAD で取り直した。取り込み前の測定 (`836e71a8`・基点 `54bacdc0`) は §4 に旧値として残す。
本書を入れる commit は docs のみで、`git diff d9d35ff5 HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行 (差分 0)。
既知類型との関係: 該当なし (lift の欠陥ではなく PM 運用ツール)。

## 1. 問題と変更

- 問題 (#2423 review round 4 の指摘): `user_answered` の起票者の絞り込み (`authorAllowed`) は issue の作成者にしか掛かっていなかった。`needs-user-input` の issue に、起票者でない非 bot の第三者がコメントすると `oc-pm` が送られ得た (抑止は同じ ref で 24 時間に 3 回までで、有界)。
- 基準 (受入条件 1): **起票者とコメント者の両方**。起票者は従来どおり `authorAllowed` (MEMBER / OWNER / COLLABORATOR か許可 bot)。コメント者は `author_association` が MEMBER / OWNER / COLLABORATOR の非 bot のコメントだけで `sig.userAt` を立てる (`src/webhook.ts` の `applySignalComment`)。
- 許可 bot のコメントは回答の根拠にしない。非 bot 条件は #2333 からの仕様で、許可 bot を含めると、実装 agent 自身の run 結果コメントが `needs-user-input` の issue (run の途中でラベルが付いた場合) で `oc-pm` を起こし得る。受入条件の「だけ」を満たす部分集合として、この扱いにした。
- REST 同期 (`src/engine.ts` `syncComments` の `slim`): `author_association` を残すようにした。落とすと reconcile で読んだ正当な回答が検出から消える (ネガコン B)。
- `userAt` は書き込み時に絞るので、後から来た第三者のコメントは判定時刻 (`at`) を上書きしない (テスト b で確認)。
- 変更ファイル: `src/webhook.ts` (`ASSOC_OK` を export し、判定を追加)・`src/pm.ts` (`ASSOC_OK` を import に変更)・`src/engine.ts` (`slim`)・`test/pm_helpers.ts` (`commentEv` が `author_association` を入れる。既定は `NONE`)・`test/pmdispatch.test.ts` (テスト +3)・`README.md` (表 1 行)。

## 2. 件数

| 数えるもの | 値 | 定義・根拠 |
|---|---:|---|
| `npm test` の件数 (基点 main `6505235b` → PR HEAD `d9d35ff5`) | 160 → 163 | TAP の `# tests` (取り込み前は 147 → 150) |
| 追加テスト | 3 | §3 の a・b・c |
| 第三者の区分 (ネガコン) | NONE・CONTRIBUTOR | `OUTSIDER` (NONE) と `CONTRIB_USER` (CONTRIBUTOR) |
| 回答の区分 (正例) | OWNER・MEMBER・COLLABORATOR | `HUMAN` (OWNER)・`MEMBER_USER`・`COLLAB_USER` |

## 3. 追加したテスト (`test/pmdispatch.test.ts`)

- a. `ネガコン (user_answered): NONE / CONTRIBUTOR の第三者のコメントだけでは oc-pm を送らない。MEMBER の回答で送る` (送信まで。第三者だけで `oc-pm` 0 件 → MEMBER の回答後に `{kind: user_answered, ref: 57}` 1 件)
- b. `検出 user_answered (ネガコン): コメント者が NONE / CONTRIBUTOR の第三者なら起こさない。MEMBER・COLLABORATOR の回答は起こす` (検出のみ。後から来た第三者のコメントで判定時刻が動かない)
- c. `REST: 同期で読んだコメントも author_association で絞る (第三者の REST のコメントでは起こさない)` (`syncComments` の経路)

## 4. 測定 (HEAD = `d9d35ff5` の clean 作業ツリー。取り込み後の再測定)

コマンド: `cd infra/pm-worker && npm test` / `npm run test:workers`。環境: Node v22.23.3・4 コア・並列 1。負荷 (`uptime`): 測定中の load average 0.97〜1.57。

| 検査 | 回数 | 結果 | 所要 (wall) |
|---|---:|---|---|
| `npm test` (node --test) | 3 | 163 pass / 0 fail (各回) | 13.59〜14.13 s |
| `npm run test:workers` (vitest・workerd) | 3 | 3 pass / 0 fail (各回) | 2.45〜2.49 s (vitest の Duration 1.44〜1.45 s) |
| 基点 main `6505235b` の `npm test` (PR なし) | 1 | 160 pass / 0 fail | 14.35 s |
| (旧・取り込み前 `836e71a8`) `npm test` | 3 | 150 pass / 0 fail (各回) | 11.31〜11.54 s |

ネガティブコントロール (判定を 1 か所だけ外して FAIL を確認。測定後に元へ戻し、`git diff --quiet` で当該ファイルの差分 0 を確認):

| 控え | 外した箇所 | 結果 (`d9d35ff5`) |
|---|---|---|
| A | `webhook.ts` `applySignalComment` の `ASSOC_OK.includes(c.author_association)` | 163 件中 3 FAIL: a (#95 送信)・b (#96 検出)・c (#97 REST。webhook 側も通るため落ちる) |
| B | `engine.ts` `slim` の `author_association` | 163 件中 1 FAIL: c (#97 REST) |

その他の検査 (測定 commit `d9d35ff5` で実行): `find infra/pm-worker -type f -size +20M -not -path '*/node_modules/*' -not -path '*/dist/*'` は 0 件。`npm run build` (bun) は成功 (exit 0)。`git diff 6505235b HEAD -- infra/pm-worker/src infra/pm-worker/test` は 5 ファイル (webhook.ts・pm.ts・engine.ts・pm_helpers.ts・pmdispatch.test.ts。77 行追加・8 行削除。本 PR 自身の差分)。

## 5. 検証範囲 / 範囲外

- 範囲内: webhook の `issue_comment` (created) と REST 同期 (`/issues/comments`) での `userAt` の判定、`pmDispatch` の送信件数 (fake GitHub・fake clock)。
- 範囲外: 本番 Worker の状態。デプロイは PM の手作業で、この PR の merge では本番は変わらない (`.github/workflows` に Worker のデプロイは無い)。GitHub の実 payload の `author_association` 値 (fixture は GitHub の仕様どおりの文字列を使っている)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| デプロイ前に保存された `userAt` (第三者由来の時刻) は、デプロイ後も残る | その issue で `user_answered` が 1 回送られ得る (抑止の上限内)。PM が応答すると `pmAt` で閉じる | 親 #2333 へ提案 (保存値を一度消すかどうかは PM 判断) |
| 許可 bot のコメントを根拠に含めるか (コメント者側) | 親 #2461 の受入 1 から外した部分。現行の実装は含めない。含めると実装 agent 自身の run 結果コメントで `oc-pm` が起動し得る。理由は §1 | #2524 (`[CI-101]`・PM 判断) |
