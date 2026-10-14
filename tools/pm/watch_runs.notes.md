2026-10-13 (UTC 01:xx): 共通サブスクリプションのレート制限 (rate_limit_error: All credentials for model
claude-sonnet-5-5 are cooling down) で、稼働中の実装/review run が全て exit 1 で落ちた (依頼者通知)。
対処: restart_failed.sh [impl|review|both] が失敗/中断 run を再投入する
  - impl: 直近の失敗 run の issue に、bot の完了報告が失敗後に無く open なら、元の oc_artifacts を引き継いで /oc を再コメント
  - review: find_unreviewed.sh (head に oc-reviewer の review が無い ready PR) に rerun_review.sh
再開は PM の通常サイクル (watch 完了通知 → watcher 再起動 → restart_failed.sh) に含める。
Bedrock へのフォールバックは依頼者側で検討中 (PM は当面考慮しない)。

## find_silent_runs.sh (2026-10-13 追加)
success 終了なのに完了報告が無い実装 run を検出する (PR #411 の修正 run が着手報告だけで終了した事例)。
  SINCE=<ISO8601> MAX=30 bash $PM_DIR/find_silent_runs.sh
出力: <run id> NO-POST|STARTED-ONLY #<対象> <title>。該当は同じ対象に /oc を再投入する (前回の続きと、何も push せず終了しないことを明記)。
BOT 名は `opencode-for-signature-studio[bot]` ([bot] 接尾辞が必要。外すと全件が NO-POST になる)。
watch_runs.sh の完了通知ごとに、結果処理と合わせて実行する。

## 補充時の oc_artifacts の注意 (2026-10-13 04:40Z 実測)
- oc_artifacts: を指定すると agent-setup の既定 (fl-win64) が置き換わる。FL 本体 (PE/DLL) が要る作業は必ず fl-win64 を書く。
  (#83 #115 #154 #161 が fl-win64 を書かず素材不足で停止した)
- toolchain-* だけを書いた run では fl-win64 は無い。mingw-w64 は run 内で apt install gcc-mingw-w64-x86-64 で入る。
- agent は素材が無いと停止報告を出す。停止報告は gh issue view <N> --json comments の最後の bot コメントの先頭行 (## 停止報告) で分かる。
- 補充前に open issue の bot 停止報告 (素材不足) が無いかを確認し、あれば必要な素材名を指定して再投入する。

## 2026-10-13 指示 121 (歴史的経緯・現行の launch 規則ではない)
指示 121 は 2026-10-13 時点の一時的な停止指示だった。現在の launch 規則は指示 130〜132 (`launch_issues.py`) が正本。
この節の内容 (新規投入の停止・sweep_prs.sh の継続) は、現在の運用としては使わない (`sweep_prs.sh` は廃止、後継は `rest_heal.py`)。
- 当時の内容: 新規タスクの着手禁止 (解除条件 = Project V2 の In review が 0 件)。既存 PR の解決 (競合解消・修正 run・review 再起動・approve 済みの merge)・起票・レトロは可。補充のための新規 issue 投入も禁止。

## 2026-10-13 13:10Z 追記 (heartbeat 処理で判明)
- 差し戻しが 6〜10 回に積み上がる主因は、reviewer が『実装 agent では解消しない』と書いた PM 判断・起票を PM が決めていなかったこと。
  `python3 $PM_DIR/pm_needs.py` で、最新の差し戻しが PM 判断を求めていて PM の応答が無い PR を洗い出す (REST のみ。所要は REPORT §8)。当時は 30 分版の heartbeat のたびに実行した。現在は Worker の `needs.ts` が同じ検出を担い、監査専用の heartbeat (指示 145) からは実行しない。
- 積み PR の merge 順はブランチの積み方で決まる (判断前に `git log origin/main..<branch>` / 差分に含まれる他 PR の commit を確認する)。
  例: #551(merged) → #624 → #676 → #708 → #720。誤って逆順を指示したら、すぐ PR と issue に訂正コメントを出す。
- WORKFLOW §3 (#835) に従い実装 agent が起票してよい。milestone・優先度・Status は PM が確定する。reviewer が『起票先番号』を要求したら、起票前に `gh api "search/issues?q=repo:R+%22CI-13%22+in:title"` で番号の重複を必ず確認 (CI-13 が #725 と重複しかけた)。
- fix run が exit code 143 (SIGTERM) で cancelled になる場合は、エージェントの `kill 0` / `pkill` が step の bash を落としている疑い (#744, PR #745 で setsid 対応)。annotation に shutdown signal が無いことを確認する。
- 競合 PR の fix は repository_dispatch (watchdog) で実機動作を確認済み (#576, #689。計測値は REPORT §8)。schedule(*/5) は発火が無く、repository_dispatch (oc-watchdog) で起こす経路を使う。

## 2026-10-13 13:24Z 追記
- watchdog を VM から起こす: `pm-watchdog.timer` (systemd user、5 分おき、`pm_watchdog_ping.sh` が repository_dispatch oc-watchdog を送る)。ログ: `$PM_DIR/pm_watchdog_ping.log`。実機で run 名 `watchdog` の起動を確認済み (13:22:51Z)。schedule(*/5) の発火実測は [REPORT §8](REPORT.md) を参照。止めるとき: `systemctl --user disable --now pm-watchdog.timer`。
- keyring がロックされると gh が失敗し、ping が FAILED とログに残る (推測・平文保存はしない。依頼者に解錠を依頼)。
- 新しい shell で `cf` を使うとき: PATH に bun が無いことがある。`mkdir -p "$PM_TMP/shim"; ln -sf "$(command -v bun)" "$PM_TMP/shim/node"; export PATH="$PM_TMP/shim:$PATH"`。
- R2 投入の一時昇格ポリシー: `$PM_TMP/r2up/pol-rw.json` / `pol-ro.json` (消えたら再作成する: 対象は R2 バケット `signature-studio-artifacts` のリソース、権限は「Workers R2 Storage Bucket Item Read」と「Write」。Cloudflare のアカウント ID は `docs/REFERENCES.md` を参照)。
- work-m11 は R2 に再投入しても無意味: ir_conditions.json が生成時の PE の絶対パスを持ち m11_build.sh が一致を要求する。使う側が m11_gen_ir2.sh を最初に実行する (所要は REPORT §8)。
