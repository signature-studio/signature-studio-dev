# PM Worker の launch 停止を watchdog から障害 issue に出す (#2848・CI-135)

> **正本**: 本付録 (`tools/pm/REPORT_2848.md`)。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない (`docs/DOC_MAP.md` §1)。
> 運用の正本は `docs/WORKFLOW.md` §11 の『PM Worker の停止検知』の『launch の停止』の項。規則の正本は `infra/pm-worker/README.md`『launch の停止と通知 (#2795)』。

## 1. 変更

- `.github/scripts/watchdog.sh`: `launch_parse` (`launch_halted` の形を読む)・`launch_abnormal`・`launch_hold`・`worker_launch` を追加。`worker_down` と `worker_body` に種別 (`worker` / `launch`) の引数を足し、起票・追記・題名だけを分ける。
  - `launch_halted_overdue` が true (15 分以上止まり、着手待ちと空き枠がある) のとき、障害 issue (`pm-worker-down`) に理由 (`reason`) と止まり始め (`since`) を追記する。無ければ `worker_down` と同じ規則で起票する (題名 `[CI-n] PM Worker launch 停止 (日付)`)。重複排除と 60 分の間隔は停止検知と共有する。
  - `reason` が `review-only` (意図した停止) のときは追記しない。
  - 止まっている間 (`review-only` を除く) と、形が読めない `launch_halted` の間は、fresh でも回復の close をしない (close すると、止まっている launch を回復と誤記するため)。`launch_halted` が null に戻れば、従来の回復の処理 (`worker_recovered`) が回復を書いて close する。
  - 形が読めない (`launch_halted` が文字列、`launch_halted_overdue` が真偽でない等) ときは警告だけ出し、追記も回復もしない。
  - `launch_halted` が無い Worker (本変更より前の `/status`) では従来どおり。
  - `/status` が読めないときは、launch の判定も PR の点検も従来どおり (`worker_check` の早期 return より後にだけ `launch_parse` が動く)。
- `.github/scripts/tests/test-watchdog.sh`: 33i〜33i8 (11 expect)。
- `docs/WORKFLOW.md` §11: 『launch の停止』の項。`docs/DOC_MAP.md`: 本付録の登録。

## 2. 測定 (測定 commit `df410ac06`)

| 測定 | 結果 |
|---|---|
| `bash .github/scripts/tests/test-watchdog.sh` (HEAD `df410ac06`) | rc 0・**155 ok / 0 FAIL**・wall 19.6 s・loadavg (1 分値) 0.38 → 0.70 |
| 同 (33i〜33i8 の 11 expect を含む。前回 (`6d7ec87f5`) は 144) | 11 件すべて ok。ネガコンは 33i3 (5 分では追記しない)・33i4 (review-only)・33i7 (形が読めない)・33i8 (読めない) |
| `bash .github/scripts/tests/test-pr-lint.sh` (ARTIFACT_RE を読む) | rc 0・30 ok / 0 FAIL・1.5 s |
| `shellcheck -S warning .github/scripts/watchdog.sh` | 警告 0 |

**規則を壊したときの FAIL (一時コピーで実行。本物のツリーは変えない)**:

| 変異 | 落ちたテスト |
|---|---|
| M1: 止まっている間も回復として close する (`launch_hold` を偽にする) | 33i・33i2・33i3・33i7 の 6 件 |
| M2: `review-only` を障害として扱う (追記・保留の対象にする) | 33i4 の 2 件 |
| M3: overdue を見ない (15 分未満でも追記する) | 33i3 の 1 件 |
| M4: 形が読めない `launch_halted` を止まっていないとみなす | 33i7 の 2 件 |

clean (変異なし) は 155 ok / 0 FAIL。

## 3. 本番の読み取り (変更を入れる前、読み取りのみ)

`curl -fsS -m 10 <tools/pm/worker_url>/status` (2026-10-15 02:04Z):
`mode` live・`configured` true・`installed` true・`fresh` true・`last_tick` 02:04:51Z・`launch_halted` null・`launch_halted_overdue` false・`rest_remaining` 4945・`rate_limit_alert` false。
本番は既に `launch_halted` を返す (#2854 の deploy 済み)。今の状態では、新しい判定は『回復』の経路に入るだけで、開いた障害 issue が無いため何も書かない (変更前と同じ)。

本番の launch 停止 (overdue) での発火は、この時点では未観測 (overdue が false)。実際に止まったときの issue の見え方は、次の停止で確かめる。

## 4. 差分 (測定 commit 以降のコード差分)

測定 commit `df410ac06` 以降に `.github/scripts` を変える commit は無い (本付録は `tools/pm` と `docs` だけを変える)。
`git diff df410ac06 HEAD -- .github/scripts` の出力は 0 行。取り込み後の再測定は不要。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 本番で launch が overdue で止まったときの発火を、まだ実観測していない | 停止の検知が実際に出るかは次の停止まで未確認 | 次の停止時に PM が確認 (本 issue の範囲外) |
| `digest` の PM run は `launch_halted` を読まない | 通知を受けた PM agent は『launch が止まっている』とは分からない。本変更は障害 issue の表示だけを変えた | 範囲外 (`infra/pm-worker/README.md`『限界』に記載済み。PM Worker の通知経路の変更は別 issue) |
