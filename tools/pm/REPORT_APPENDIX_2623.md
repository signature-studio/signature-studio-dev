# tools/pm REPORT §16 の付録: Refs のみ判定の統一 (#2623・[CI-115])

REPORT.md の §16 (refs_orphan 検出 #2337) の未解決を解消した記録。250 行上限のため本付録に全文を置く (REPORT.md の §16 は結論 1 行と本付録へのリンク)。

## 1. 結論

- 指標 `refs_only_merge_rate_24h` (`src/webhook.ts` の `refsOnlyBody`) と refs_orphan (`src/refs.ts` の `refsOnlyNumbers`) の判定を、`src/refs.ts` の `refsOnlyNumbers` 1 関数に一本化した。`refsOnlyBody` は `refsOnlyNumbers(body).length > 0` を返すだけになった。
- 受入 1 (表の 4 入力で両者が同じ値): 満たした (§3 の表・単体テスト)。
- 受入 2 (`test/autonomy_status.test.ts` と `test/refsorphan.test.ts` の両方が通る): `npm test` 396 件 PASS / 0 FAIL (§4)。
- 受入 3 (指標の変更点を実測値で書く): **実データでは変化 0 件**。直近 24 時間 (merge 860 件) と直近 7 日 (merge 1598 件) の両方で、統一前後の判定が変わった PR は 0 件。判定が変わるのは閉じ方が `Closes:#N`・`Closes owner/repo#N` 等の PR だけだが、その形式は両窓とも 1 件も無かった (§2)。

## 2. 実測 (指標の変更点・再現スクリプト)

- 測定 commit: `d61f2a8c` (コードを変えた最後の commit。再測定スクリプトの重複除去)。窓の終端 `2026-10-15T00:00:48Z` (固定。スクリプトの `--end` の既定値)。
- 再現スクリプト: [`refs_only_remeasure.ts`](refs_only_remeasure.ts)。1 コマンド: `cd <repo> && node --experimental-strip-types --no-warnings tools/pm/refs_only_remeasure.ts` (既定のまま。読み取りだけ)。測定 commit `d61f2a8c` で既定のまま実行: 10.9 秒。
- 旧判定: 固定 commit `7c85004e` (統一前の `webhook.ts`。`889ec098` の親) の `infra/pm-worker/src/webhook.ts` から `REFS_RE`・`CLOSE_RE` の正規表現リテラルを読み出して評価した (手写しをしない)。既定を `origin/main` にしない: 統一後の main には `REFS_RE` が無く、merge 後にスクリプトが止まるため。新判定: HEAD の `refsOnlyBody` (`src/webhook.ts`)。`refsOnlyNumbers` (`src/refs.ts`) との不一致も数えた。
- 母集団: REST の `repos/<repo>/pulls` を updated 降順に、窓の始点まで読み切って取り、merged_at が窓内の PR を数えた。読んでいる途中に更新された PR は二度読まれることがあるため、番号で重複を除く。初版 (`234d6599`) は 7 日の窓で 1 件を二度数えて 1599 件になった。重複を除いた後は、`d61f2a8c` を含む 4 回の実行すべてで 1598 件。

| 窓 (終端 2026-10-15T00:00:48Z) | merged | 旧 refs_only (率) | 新 refs_only (率) | 統一前後で値が変わった PR | `refsOnlyNumbers` と `refsOnlyBody` の不一致 |
|---|---|---|---|---|---|
| 直近 24 時間 (2026-10-14T00:00:48Z 〜) | 860 | 363 (0.4221) | 363 (0.4221) | 0 | 0 |
| 直近 7 日 (2026-10-08T00:00:48Z 〜) | 1598 | 901 (0.5638) | 901 (0.5638) | 0 | 0 |

- 形式の出現数 (判定が変わり得る形): 両窓とも 0 件。`Closes:#N`・`Closes#N` (空白なし)・`Closes owner/repo#N`・`Refs:#N`・`Refs#N` (空白なし)・`Refs owner/repo#N`・`Refs` の後の 8 桁の番号・`Refs` と `#N` の間の改行 (統一後は `\s*` で数える形)。
- 母集団の検算: `gh pr list --search` (GraphQL) による検算は、測定時に installation の GraphQL 制限に掛かって取得できなかった (スクリプトは検算を省き、REST の件数だけで判定する)。初版の検算 (`889ec098` の時点) では、24 時間の窓で search は 859 件、REST は 860 件だった。REST のみの 1 件は #2073 (merged 2026-10-14T11:49:08Z・本文 `Closes #1998`)。判定は旧も新も false で件数には影響しない。search が取りこぼしたため、母集団は REST に切り替えた。7 日の窓は search の上限 (1000 件) では取れなかったため、REST で窓を取り直した。
- レビューの再現値との差: レビュー (round 1・round 2) の 362 件 (0.4214・母数 859) は再現しなかった。本測定 (REST の 860 件) でも、レビュー側の独立検算 (Python・REST 母集団) でも、旧判定は 363 件だった (round 2 の報告)。差 1 件の原因は特定できていない (§6)。

## 3. 表の 4 入力 (HEAD `889ec098`)

| 入力 | 旧指標 | 新指標 (`refsOnlyBody`) | refs_orphan (`refsOnlyNumbers`) |
|---|---|---|---|
| `Closes:#6 Refs #5` | true | false | `[]` |
| `Refs owner/repo#5` | true | false | `[]` |
| `Refs:#5` | false | true | `[5]` |
| `Refs #12345678` | true | false | `[]` |

旧指標と refs_orphan は、表の 4 入力すべてで食い違っていた (#2623 の起票時の表と同じ)。統一後は 4 件とも一致する。

refs_orphan の判定 (`refsOnlyNumbers`) の中身は変えていない。`src/refs.ts` の差分はコメントだけ。よって refs_orphan の検出 (`src/pm.ts` の `refsOnlyNums` の利用) の結果は変わらない。

## 4. 検証 (コミット済み HEAD)

- `cd infra/pm-worker && npm test` (HEAD `d61f2a8c`): 396 件 PASS / 0 FAIL。実行時間 22335.6 ms。(うち 1 件は本 PR で追加した『Refs のみの判定の統一』)
- `npm run test:workers` (vitest): 2 ファイル・7 件 PASS (測定 commit `889ec098` で実行)。HEAD の `infra/pm-worker` は `889ec098` から変わっていない (下記の差分 0 行) ので、同じ結果とみなす。HEAD では再実行していない (vitest の依存が worktree に無い)。
- ネガコン: 指標の `refsOnlyBody` を旧判定 (REFS_RE・CLOSE_RE) に作業ツリーで一時的に戻すと、統一テストが FAIL (`pass 14 / fail 1`)。戻した後は HEAD と一致 (`git status` 0 行)。
- 差分の証跡: `git diff 889ec098 HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行。再測定スクリプトの差分 `git diff d61f2a8c HEAD -- tools/pm/refs_only_remeasure.ts` も 0 行 (本付録を commit した後の HEAD で確認)。

## 5. 本番への影響 (launch 経路)

- `refsOnlyBody` は `/status` の指標 `refs_only_merge_rate_24h` にだけ使う。停止条件・既定値・launch の経路は変えていない。
- 保存値: merge 時の `refsOnly` (真偽) は PM の状態に保存される (`src/webhook.ts` の `applyPr`)。deploy 前に merge された PR は、24 時間の窓から出るまで旧判定の値のまま残る。今回の実測では新旧の差が 0 件なので、この混在による数値の差も 0。

## 6. 未解決

- レビューの 362 件 (§2) との差 1 件。原因は未特定。本測定 (REST の 860 件・1598 件) と独立検算では再現しなかった。判定の変更は 0 件。起票なし (PR 本文の未解決表に記載)。
- 判定の形式 (`Closes:#N` 等) が将来の PR に現れれば、指標の値はその時点で変わる (仕様どおり。実測の時点では現れていない)。
- 受入 1〜3 は満たした (§1)。Issue #2623 は `Closes #2623` で閉じる。
