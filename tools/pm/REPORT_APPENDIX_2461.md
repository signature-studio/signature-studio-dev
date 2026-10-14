> **正本**: 本書 (`tools/pm/REPORT_APPENDIX_2461.md`) が #2461 の測定の正本。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない (`docs/DOC_MAP.md` §1)。PM Worker の他の測定は `tools/pm/REPORT.md` §10〜§12。

# #2461: user_answered の回答を MEMBER / OWNER / COLLABORATOR のコメントに限る

測定した commit: `836e71a8` (`fix(pm-worker): count user_answered only from MEMBER/OWNER/COLLABORATOR comments (#2461)`)。検証起点は origin/main `54bacdc0`。
本書を入れる commit は docs のみで、`git diff 836e71a8 HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行 (差分 0)。
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
| `npm test` の件数 (変更前 → 後) | 147 → 150 | TAP の `# tests` |
| 追加テスト | 3 | §3 の a・b・c |
| 第三者の区分 (ネガコン) | NONE・CONTRIBUTOR | `OUTSIDER` (NONE) と `CONTRIB_USER` (CONTRIBUTOR) |
| 回答の区分 (正例) | OWNER・MEMBER・COLLABORATOR | `HUMAN` (OWNER)・`MEMBER_USER`・`COLLAB_USER` |

## 3. 追加したテスト (`test/pmdispatch.test.ts`)

- a. `ネガコン (user_answered): NONE / CONTRIBUTOR の第三者のコメントだけでは oc-pm を送らない。MEMBER の回答で送る` (送信まで。第三者だけで `oc-pm` 0 件 → MEMBER の回答後に `{kind: user_answered, ref: 57}` 1 件)
- b. `検出 user_answered (ネガコン): コメント者が NONE / CONTRIBUTOR の第三者なら起こさない。MEMBER・COLLABORATOR の回答は起こす` (検出のみ。後から来た第三者のコメントで判定時刻が動かない)
- c. `REST: 同期で読んだコメントも author_association で絞る (第三者の REST のコメントでは起こさない)` (`syncComments` の経路)

## 4. 測定 (HEAD = `836e71a8` の clean 作業ツリー)

コマンド: `cd infra/pm-worker && npm test` / `npm run test:workers`。環境: Node v22.23.3・4 コア・並列 1。負荷 (`uptime`): 測定中の load average 0.37〜1.52。

| 検査 | 回数 | 結果 | 所要 (wall) |
|---|---:|---|---|
| `npm test` (node --test) | 3 | 150 pass / 0 fail (各回) | 11.31〜11.54 s |
| `npm run test:workers` (vitest・workerd) | 3 | 3 pass / 0 fail (各回) | 2.16〜2.20 s (vitest の Duration 1.26〜1.29 s) |
| 変更前 `54bacdc0` の `npm test` | 1 | 147 pass / 0 fail | TAP の duration_ms 11.83 s |

ネガティブコントロール (判定を 1 か所だけ外して FAIL を確認。測定後に元へ戻し、`git status` が 0 行であることを確認):

| 控え | 外した箇所 | 結果 |
|---|---|---|
| A | `webhook.ts` `applySignalComment` の `ASSOC_OK.includes(c.author_association)` | 150 件中 3 FAIL: a (送信)・b (検出)・c (REST。webhook 側も通るため落ちる) |
| B | `engine.ts` `slim` の `author_association` | 150 件中 1 FAIL: c (REST) |

その他の検査 (測定 commit の HEAD で実行): `find infra/pm-worker -type f -size +20M -not -path '*/node_modules/*' -not -path '*/dist/*'` は 0 件。`npm run build` (bun) は成功。

## 5. 検証範囲 / 範囲外

- 範囲内: webhook の `issue_comment` (created) と REST 同期 (`/issues/comments`) での `userAt` の判定、`pmDispatch` の送信件数 (fake GitHub・fake clock)。
- 範囲外: 本番 Worker の状態。デプロイは PM の手作業で、この PR の merge では本番は変わらない (`.github/workflows` に Worker のデプロイは無い)。GitHub の実 payload の `author_association` 値 (fixture は GitHub の仕様どおりの文字列を使っている)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| デプロイ前に保存された `userAt` (第三者由来の時刻) は、デプロイ後も残る | その issue で `user_answered` が 1 回送られ得る (抑止の上限内)。PM が応答すると `pmAt` で閉じる | 親 #2333 へ提案 (保存値を一度消すかどうかは PM 判断) |
| 許可 bot のコメントを根拠にしない | 受入条件 1 の文言 (『許可 bot のコメント』) と字面が違う。理由は §1 | PR 本文の未解決表 (PM 判断) |
