# tools/pm — oc-pm の停止行の再検出 (#5901): 条件の確定と流入の内訳

停止行 (`run-outcome` が stop / split のまま止まっている open issue) を oc-pm の判断キューへ送る
`stopped_report` の再検出について、条件 (コード) と流入の実測を記録する。PM 判断 (2026-10-16 16:37Z・R7 ①):
**応答済みの再検出は残す** (挙動は変えない)。本付録は測定値の正本。

## 1. 条件 (コード)

- 規則: `infra/pm-worker/src/pm.ts` の `stopped_report` 節 (L165-178)。起点は `run-outcome` の stop / split だけ。
- 除外: `oc:no-pr` の `no_pr` として送る分・`oc:stuck` / `oc:hold` / `pm-apply` / `needs-user-input`・open PR あり・
  停止の後に `/oc` を投稿済み・open な子を持つ親。
- 応答後の扱い: 応答 (PM の投稿) があっても対象に残す。ただし **応答から `PM_INTAKE_GRACE_MS` (3,600,000 ms = 1 時間) は送らない**
  (`pm.ts` L74)。
- 上限: 送信の枠は `selectDispatch` (1 時間・同一 issue 24 時間 3 件、`pm.ts` L209〜)。

## 2. 実測 (取得方法)

- 取得: `gh run list --repo signature-studio/signature-studio-dev --limit 3000 --json name,createdAt,databaseId > runs.json`
  (run 題名 `oc-pm stopped_report #N`)。送信時刻は run の `createdAt`。
  PM 応答は各 issue の `gh api --paginate repos/<repo>/issues/N/comments` のうち、先頭行が `PM` で始まる / `oc-pm-decision` を含む /
  `PM 判断`・`PM 注記` を含むコメントの `created_at`。送信 1 件ごとに、送信時刻以前の最後の PM 応答との差 (分) を取る。
- 取得範囲: run 一覧 (最新 3000 件) は 2026-10-16T11:29:38Z 〜 17:29:38Z (取得時点のスナップショット。再取得では範囲が動く)。このうち oc-pm dispatch は 368 件 (本検算の対象外・参考値)。
- 窓 (stopped_report の最初〜最後の送信): 2026-10-16T11:37:52Z 〜 17:29:22Z = **5.858 時間**。前回の見積り (19.8 時間・759 件・本検算の対象外) とは窓が違うため、直接比較はしない。
- 結果 (run 一覧の再計算、取得時点の `runs.json` sha256 先頭 12 桁 `b46307222b13`):
  - `stopped_report` の送信: **192 件 / 191 issue** (run の databaseId は 192 件すべて異なる)。
    同じ issue の 2 回送信は **#5730 の 1 件** (12:28:34Z と 14:28:41Z)。
  - #3775 は本取得では **1 run のみ** (12:28:42Z・databaseId 38900778897)。同一秒の 2 run は再現しなかった。
  - 送信ごとの内訳: 応答済み **189 件 (98.4%)**・新規 (応答なし) **3 件 (1.6%)**。
    新規は #5282 (14:28:49Z)・#5328 (15:36:10Z)・#5478 (16:36:15Z)。
  - 応答済みの送信は、直前の PM 応答から **最短 60.4 分・最長 1,595 分** 経ってから送られた。
    **猶予 1 時間以内の送信は 0 件** (規則どおり)。
  - 毎時の送信数 (UTC・送信時刻): 11 時 2・12 時 24・13 時 24・14 時 24・15 時 48・16 時 48・17 時 22 (17:29:22 まで)。合計 192。
    15 時台以降は 48/h (枠 24/h の 2 倍)。
- #5730 の例 (受入 1 の実例): PM 応答は 10:42:33Z と 12:30:20Z。送信は 12:28:34Z (前回応答から 106 分) と
  14:28:41Z (応答 12:30:20Z から 118 分)。いずれも猶予 1 時間を超えたため送信された (規則どおり)。

## 3. 読み取り

- 応答済みの送信 189 件のうち、同じ issue の 2 回送信は #5730 の 2 件 (12:28:34Z・14:28:41Z) だけ。
  つまり大半は「応答の後に初めて停止行として届いた」件で、猶予切れの届け直し (再送) は #5730 の 1 件分 (2 送信) だけ。
  応答済みの送信の多さは、再送よりも応答の後の停止行の流入による。
  (送信の回数は run 題名の issue 番号から数えた。本文・ラベルの変化は見ていない。)
- 本窓の送信は 192 件 / 5.858 時間 = **32.8/h** (実測の割算)。前回の推定値 (約 48/h) は本実測に置き換える。
- 同一秒の二重 dispatch (#3775 の 12:28:42Z 2 run) は本取得では確認できなかった。review で指摘された件は、取得時点の差 (run 一覧の再取得) か別の run の可能性がある。原因は未確定。

## 3.1 再現手順 (数値の検算用)

```sh
gh run list --repo signature-studio/signature-studio-dev --limit 3000 --json name,createdAt,databaseId > runs.json
python3 -c "
import json,re,collections
runs=json.load(open('runs.json'))
sr=sorted([r for r in runs if r['name'].startswith('oc-pm stopped_report')],key=lambda r:r['createdAt'])
iss=collections.Counter(re.search(r'#(\d+)',r['name']).group(1) for r in sr)
print('runs',len(sr),'issues',len(iss),'dup',{k:v for k,v in iss.items() if v>1})
print('hourly',sorted(collections.Counter(r['createdAt'][:13] for r in sr).items()))
"
```

PM 応答の突き合わせは、上の issue 番号ごとに `gh api --paginate repos/<repo>/issues/N/comments` を取り、
送信時刻以前の最後の PM 応答時刻との差 (分) を取る (本件は 191 issue すべて取得・突き合わせ済み)。

## 4. 未解決

- 15 時台以降の 48/h の原因 (枠 24/h の上限との対応)。起票先: PM (oc-pm) の判断。本窓は 5.858 時間のみの実測。
- 応答済みの再送の是非 (A: 現状維持 / B: 応答後は再送しない): PM 判断 (2026-10-16 16:37Z) で A に決定済み。
