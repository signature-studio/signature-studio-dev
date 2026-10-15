# tools/pm REPORT §16 の付録: Refs のみ判定の統一 (#2623・[CI-115])

REPORT.md の §16 (refs_orphan 検出 #2337) の未解決を解消した記録。250 行上限のため本付録に全文を置く (REPORT.md の §16 は結論 1 行と本付録へのリンク)。

## 1. 結論

- 指標 `refs_only_merge_rate_24h` (`src/webhook.ts` の `refsOnlyBody`) と refs_orphan (`src/refs.ts` の `refsOnlyNumbers`) の判定を、`src/refs.ts` の `refsOnlyNumbers` 1 関数に一本化した。`refsOnlyBody` は `refsOnlyNumbers(body).length > 0` を返すだけになった。
- 受入 1 (表の 4 入力で両者が同じ値): 満たした (§3 の表・単体テスト)。
- 受入 2 (`test/autonomy_status.test.ts` と `test/refsorphan.test.ts` の両方が通る): `npm test` 396 件 PASS / 0 FAIL、`npm run test:workers` 7 件 PASS (§4)。
- 受入 3 (指標の変更点を実測値で書く): **実データでは変化 0 件**。PM 判断の記録は『値が変わる』だったが、実測では変わらなかった。判定が変わるのは閉じ方が `Closes:#N`・`Closes owner/repo#N` 等の PR が merge されたときだけで、直近 24 時間 (859 件) と 7 日 (1000 件) の merge 済み PR には、その形式が 1 件も無かった (§2)。

## 2. 実測 (指標の変更点)

- 測定 commit: `889ec098` (コードを変えた最後の commit)。窓の終端 2026-10-15T00:00:48Z。
- 方法: `gh pr list --repo signature-studio/signature-studio-dev --state merged --search "merged:>=<窓の始点>" --limit 2000 --json number,body,mergedAt` で本文を取り、各本文に旧判定と新判定を当てた。旧判定は `origin/main` の `src/webhook.ts` の `REFS_RE`・`CLOSE_RE` をその場で取り直して評価した (手写しの正規表現を使わない)。新判定は HEAD の `refsOnlyBody` と `refsOnlyNumbers`。測定スクリプトはリポジトリ外の作業用で、repo には入れていない。
- 注: `gh` の search は 1 回で最大 1000 件しか返さない。7 日分は 1000 件で打ち切られた (7 日間の全件ではない)。

| 窓 | merged | 旧 refs_only (率) | 新 refs_only (率) | 旧新で値が変わった PR | 新指標と refs_orphan の不一致 |
|---|---|---|---|---|---|
| 直近 24 時間 | 859 | 363 (0.4226) | 363 (0.4226) | 0 | 0 |
| 直近 7 日 (取得上限 1000 件) | 1000 | 482 (0.4820) | 482 (0.4820) | 0 | 0 |

判定が変わる形式の出現数 (両窓とも 0 件): `Closes:#N` (コロンの直後に空白なしで `#`)・`Closes owner/repo#N`・`Refs:#N`・`Refs owner/repo#N`・`Refs #` の後に 8 桁の番号。

## 3. 表の 4 入力 (HEAD `889ec098`)

| 入力 | 旧指標 | 新指標 (`refsOnlyBody`) | refs_orphan (`refsOnlyNumbers`) |
|---|---|---|---|
| `Closes:#6 Refs #5` | true | false | `[]` |
| `Refs owner/repo#5` | true | false | `[]` |
| `Refs:#5` | false | true | `[5]` |
| `Refs #12345678` | true | false | `[]` |

旧指標と refs_orphan は、表の 4 入力すべてで食い違っていた (#2623 の起票時の表と同じ)。統一後は 4 件とも一致する。

refs_orphan の判定 (`refsOnlyNumbers`) の中身は変えていない。`src/refs.ts` の差分はコメントだけ。よって refs_orphan の検出 (`src/pm.ts` の `refsOnlyNums` の利用) の結果は変わらない。

## 4. 検証 (測定 commit `889ec098`・コミット済みの HEAD)

- `cd infra/pm-worker && npm test`: 396 件 PASS / 0 FAIL (うち 1 件は本 PR で追加した『Refs のみの判定の統一』)。実行時間 23317 ms。load 0.18。Node v22.23.3。
- `npm run test:workers` (vitest): 2 ファイル・7 件 PASS。
- ネガコン: 指標の `refsOnlyBody` を旧判定 (REFS_RE・CLOSE_RE) に作業ツリーで一時的に戻すと、統一テストが FAIL (`pass 14 / fail 1`)。戻した後は HEAD と一致 (`git status` 0 行)。
- 差分の証跡: `git diff 889ec098 HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行 (本付録を含む REPORT の commit は tools/ 配下だけを変える)。

## 5. 本番への影響 (launch 経路)

- `refsOnlyBody` は `/status` の指標 `refs_only_merge_rate_24h` にだけ使う。停止条件・既定値・launch の経路は変えていない。
- 保存値: merge 時の `refsOnly` (真偽) は PM の状態に保存される (`src/webhook.ts` の `applyPr`)。deploy 前に merge された PR は、24 時間の窓から出るまで旧判定の値のまま残る。今回の実測では新旧の差が 0 件なので、この混在による数値の差も 0。

## 6. 未解決

- 無し。受入 1〜3 を満たし、Issue #2623 は `Closes #2623` で閉じる。
- 判定の形式 (`Closes:#N` 等) が将来の PR に現れれば、指標の値はその時点で変わる (仕様どおり。実測の時点では現れていない)。
