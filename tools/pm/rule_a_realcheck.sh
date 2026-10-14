#!/usr/bin/env bash
# 規則 A の実データ dry-run と照合 (#2336)。読み取りのみ (GitHub へは GET だけ・書き込みなし)。
#   1. REST の生 JSON を取る (open issue / open PR / closed PR 全履歴 / blocked_by)
#   2. Worker の経路 (infra/pm-worker/scripts/rule_a_dryrun.ts → applyEvent → detectRuleA) で候補を出す
#   3. 別実装 (tools/pm/rule_a_realcheck.py) で再計算し、集合の差分を見る
# usage: tools/pm/rule_a_realcheck.sh   (gh のログインが要る。作業ディレクトリは repo のルート)
set -euo pipefail
R=${R:-signature-studio/signature-studio-dev}
D=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/rule_a.XXXXXX")
gh api --paginate --slurp "repos/$R/issues?state=open&per_page=100" > "$D/issues_open.json"
gh api --paginate --slurp "repos/$R/pulls?state=open&per_page=100" > "$D/pulls_open.json"
gh api --paginate --slurp "repos/$R/pulls?state=closed&sort=updated&direction=desc&per_page=100" > "$D/pulls_closed.json"
python3 - "$D" "$R" <<'PY'
import json, subprocess, sys
d, repo = sys.argv[1], sys.argv[2]
issues = [i for p in json.load(open(f"{d}/issues_open.json")) for i in p if "pull_request" not in i]
out = open(f"{d}/blocked.jsonl", "w")
for i in issues:
    if (i.get("issue_dependencies_summary") or {}).get("total_blocked_by", 0) > 0:
        r = subprocess.run(["gh", "api", f"repos/{repo}/issues/{i['number']}/dependencies/blocked_by", "--jq", "[.[].number]"], capture_output=True, text=True, check=True)
        out.write(json.dumps({"k": i["number"], "v": json.loads(r.stdout or "[]")}) + "\n")
out.close()
PY
node --experimental-strip-types --no-warnings infra/pm-worker/scripts/rule_a_dryrun.ts "$D" > "$D/worker.json"
python3 tools/pm/rule_a_realcheck.py "$D" "$D/worker.json"
echo "data: $D"
