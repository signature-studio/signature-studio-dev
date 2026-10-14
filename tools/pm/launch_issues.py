#!/usr/bin/env python3
"""launch_issues.py — 指示 130〜133 の運用 (REST のみ)。

  python3 launch_issues.py plan      # 仕分けと『今着手できる issue』を表示する (何も変更しない)
  python3 launch_issues.py blocked   # 依存関係を GitHub の issue dependencies (blocked_by) に設定する (冪等)
  python3 launch_issues.py launch    # フェーズと同時数を守って、未着手・非ブロックの issue に /oc コメントで着手する

規則 (依頼者の指示):
  - 130: Opened PR が 10 件を下回ったら Review-Only Phase を解除、80 件を超えたら開始 (間は直前の状態)。
  - 131: 同時着手は最低 30 以上・可能な限り多く。60 を超えても queue に入る。TARGET (既定 50) まで補充する。
  - 132: 全チケットは『ブロックされている』か『着手済み』のどちらか。ブロック要因 (blocked_by に open issue) が無く
         未着手の issue は /oc コメントで即座に着手する。

  - Opened PR の数は oc:stuck の付いた PR を除く (stuck は人の処理待ちで、着手の律速にしない)。
    stuck の open PR が STUCK_HIGH を超えたら launch を止める。

env: TARGET=50 BATCH=25 DRY=1(launch でも実コメントしない) ONLY=番号,番号 FORCE_PHASE=1 (フェーズを無視)
     STUCK_HIGH=40 (stuck の open PR の上限)
"""
import json, os, re, subprocess, sys, time, collections
from datetime import datetime, timezone

R = "signature-studio/signature-studio-dev"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "issues_state.json")
PHASE = os.path.join(HERE, "phase.json")
LAUNCHED = os.path.join(HERE, "launched.json")
RELAUNCH = os.path.join(HERE, "relaunch.json")
TARGET = int(os.environ.get("TARGET", "50"))
BATCH = int(os.environ.get("BATCH", "25"))
DRY = os.environ.get("DRY") == "1"
ONLY = {int(x) for x in os.environ.get("ONLY", "").split(",") if x}
LOW, HIGH = 10, 80
STUCK_HIGH = int(os.environ.get("STUCK_HIGH", "40"))


def gh(args, input_=None):
    out = subprocess.run(["gh"] + args, capture_output=True, text=True, input=input_)
    return out.returncode, out.stdout, out.stderr


def now():
    return datetime.now(timezone.utc)


def age_h(ts):
    return (now() - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() / 3600


def snapshot():
    rc = subprocess.run([sys.executable, os.path.join(HERE, "issue_snapshot.py")], capture_output=True, text=True).returncode
    if rc:
        raise SystemExit("snapshot failed")
    return json.load(open(STATE))


def load_json(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default


_live_cache = {}


def live_blockers(n):
    """issue n を塞いでいる open な blocker (GitHub の dependencies)。取得できなければ止める (着手を誤らないため)。"""
    if n not in _live_cache:
        rc, o, e = gh(["api", f"repos/{R}/issues/{n}/dependencies/blocked_by", "--paginate", "--jq",
                       '.[]|select(.state=="open")|.number'])
        if rc:
            raise SystemExit(f"blocked_by fetch failed for #{n}: {e.strip()[:150]}")
        _live_cache[n] = {int(x) for x in o.split()}
    return _live_cache[n]


def graph(d):
    iss = {i["number"]: i for i in d["issues"]}
    nums = set(iss)
    children = collections.defaultdict(list)
    for n, i in iss.items():
        m = re.search(r"^親\s*[:：]\s*(.+)$", i["body"], re.M)
        if m:
            for pn in re.findall(r"#(\d+)", m.group(1))[:1]:
                pn = int(pn)
                if pn in nums and pn != n:
                    children[pn].append(n)
    dep = collections.defaultdict(set)
    pats = [r"blockedBy\s*[:：]?\s*(.+)", r"依存\s*[:：]\s*(.+)", r"先行\s*[:：]\s*(.+)", r"前提\s*[:：*]+\s*(.+)"]
    for n, i in iss.items():
        for line in i["body"].splitlines():
            for p in pats:
                m = re.search(p, line)
                if m:
                    for x in re.findall(r"#(\d+)", m.group(1)):
                        x = int(x)
                        if x in nums and x != n:
                            dep[n].add(x)
            for x in re.findall(r"#(\d+)\s*(?:が|は)?\s*ブロッカー", line):
                x = int(x)
                if x in nums and x != n:
                    dep[n].add(x)
    # 『親: #N』は集合体 (epic) とは限らない。N 自身が実装 PR を持つなら実装チケットなので、子を blocker にしない。
    has_pr = set()
    for p in d["prs"]:
        m = re.match(r"(\d+)-", p["ref"])
        if m:
            has_pr.add(int(m.group(1)))
    blockers = collections.defaultdict(set)  # n -> open な blocker
    for n, ds in dep.items():
        blockers[n] |= ds
    for n, ds in load_json(os.path.join(HERE, "manual_deps.json"), {}).items():
        blockers[int(n)] |= {b for b in ds if b in nums}
    # GitHub に設定された issue dependencies (blocked_by) の open な blocker も、本文の記述と同じく待ちの根拠にする
    for n, i in iss.items():
        if (i.get("deps") or {}).get("total_blocked_by", 0) > 0:
            blockers[n] |= live_blockers(n) & nums
    for pn, cs in children.items():
        if pn not in has_pr:
            blockers[pn] |= set(cs)
    # 循環は『親が子に待つ』向きだけを残す (子 -> 親の依存は捨てる)
    for n in list(blockers):
        blockers[n] = {b for b in blockers[n] if not (n in blockers.get(b, set()) and b not in children.get(n, []))}
    return iss, children, blockers


def started_map(d, iss):
    st = collections.defaultdict(list)
    for p in d["prs"]:
        if p["state"] != "open":
            continue
        m = re.match(r"(\d+)-", p["ref"])
        if m and int(m.group(1)) in iss:
            st[int(m.group(1))].append(f"PR#{p['number']}")
        for n in re.findall(r"(?:Closes|Refs|Fixes)\s+#(\d+)", p["body"]):
            if int(n) in iss:
                st[int(n)].append(f"PR#{p['number']}")
    for r in d["runs"]:
        if r["event"] in ("issue_comment", "workflow_dispatch"):
            for n, i in iss.items():
                if r["title"].strip() == i["title"].strip():
                    st[n].append(f"run{r['id']}")
    return st


def infer_artifacts(i):
    t = (i["title"] + " " + " ".join(i["labels"])).lower()
    a = ["fl-win64", "toolchain-retdec", "toolchain-emsdk"]
    def add(*xs):
        for x in xs:
            if x not in a:
                a.append(x)
    if "serum" in t or "sr-" in t: add("plugins-serum2")
    if "massive" in t or "mx-" in t: add("plugins-massivex")
    if "kilohearts" in t or "kh-" in t: add("plugins-kilohearts")
    if "freshair" in t or "fresh air" in t or "fa-" in t: add("plugins-freshair")
    if "ott" in t: add("plugins-ott", "analysis-ott-binaries", "work-m6-ott", "work-liftlib")
    if re.search(r"m11|fle-|boot|startup|survey|ld-|liftdiff", t): add("work-m11", "work-liftdiff")
    if re.search(r"liftlib|icall|ipp", t): add("work-liftlib", "work-icall")
    if re.search(r"gui|shim", t): add("apt-mingw")
    if re.search(r"plg-", t): add("work-fw-stage1", "work-liftlib", "plugins-ott")
    if re.search(r"t-sh-1[2-6]|mac|dylib|libkio|beat_tracker|ildsp|libreverb|directwave", t): add("analysis-mac-shared")
    return "oc_artifacts: " + " ".join(a)


def artifacts_for(n, d, i):
    pm = d.get("pm_art", {}).get(str(n))
    return pm["line"] if pm else infer_artifacts(i)


def phase_update(open_prs):
    st = load_json(PHASE, {"review_only": True})
    prev = st["review_only"]
    if open_prs > HIGH:
        st["review_only"] = True
    elif open_prs < LOW:
        st["review_only"] = False
    if st["review_only"] != prev or "since" not in st:
        st["since"] = now().isoformat()
    st["open_prs"] = open_prs
    json.dump(st, open(PHASE, "w"))
    return st


def count_open_prs(pulls):
    """open PR の (oc:stuck を除いた数, oc:stuck の数)。"""
    stuck = sum(1 for p in pulls if any(l.get("name") == "oc:stuck" for l in p.get("labels", [])))
    return len(pulls) - stuck, stuck


def open_pr_count():
    rc, o, e = gh(["api", "--paginate", "--slurp", f"repos/{R}/pulls?state=open&per_page=100"])
    if rc:
        raise SystemExit(f"open PR count failed: {e[:150]}")
    return count_open_prs([p for page in json.loads(o) for p in page])


def launch_stop_reason(stuck):
    """launch を止める理由。止めないなら None。"""
    if stuck > STUCK_HIGH:
        return f"oc:stuck の open PR {stuck} 件が上限 {STUCK_HIGH} を超えている (人の処理待ち)"
    return None


def active_runs(d):
    n = 0
    for r in d["runs"]:
        e, t = r["event"], r["title"]
        if e in ("issue_comment", "workflow_dispatch", "pull_request_review") or (e == "repository_dispatch" and t.startswith("oc-fix")):
            n += 1
    return n



ALLOW_ARTS = ["fl-win64", "plugins-ott", "plugins-freshair", "plugins-serum2", "plugins-massivex", "plugins-kilohearts",
              "toolchain-retdec", "toolchain-emsdk", "work-m11", "work-liftdiff", "work-m6-ott", "work-liftlib-targets",
              "work-liftlib", "work-icall", "work-fw-stage1", "analysis-ott-binaries", "analysis-mac-shared", "apt-mingw"]
NEED_RE = re.compile(r"不足|無い|無く|無かった|ない|存在しな|必要|依頼|欠|足りな|未配置|未展開|入っていな|のみ|だけ|揃っ")
# 日次 digest の rolling issue (pm.md の digest 節・Worker の DIGEST_ROLLING_RE と同じ題名)。本文だけを更新する issue なので着手しない。
DIGEST_ROLLING_RE = re.compile(r"\[[A-Za-z]+-\d+\] 自律運転ダイジェスト \(rolling\)")
_full_cache = {}


def full_bot_body(n):
    if n not in _full_cache:
        rc, o, e = gh(["api", f"repos/{R}/issues/{n}/comments", "--paginate", "--jq",
                       '[.[]|select(.user.login=="opencode-for-signature-studio[bot]")'
                       '|select((.body|contains("<!-- oc-run-outcome:")|not) and (.body|contains("<!-- oc-pm-")|not))]'
                       '|last|.body // ""'])
        _full_cache[n] = o if rc == 0 else ""
    return _full_cache[n]


def needed_arts(n):
    """停止報告の本文で、『無い・不足・必要』と一緒に挙がった素材名 (allowlist 内) を返す。"""
    out = []
    for line in full_bot_body(n).splitlines():
        if NEED_RE.search(line):
            for a in ALLOW_ARTS:
                if re.search(r"(?<![\w-])" + re.escape(a) + r"(?![\w-])", line) and a not in out:
                    out.append(a)
    return out


def classify(d):
    iss, children, blockers = graph(d)
    st = started_map(d, iss)
    launched = load_json(LAUNCHED, {})
    rows = {"blocked": [], "started": [], "user": [], "stopped": [], "recent": [], "relaunch": [], "ready": []}
    blocks_count = collections.Counter()
    for n, bs in blockers.items():
        for b in bs:
            blocks_count[b] += 1
    for n, i in sorted(iss.items()):
        if DIGEST_ROLLING_RE.fullmatch(i["title"]):
            continue
        if "needs-user-input" in i["labels"]:
            rows["user"].append((n, ""))
        elif blockers.get(n):
            rows["blocked"].append((n, sorted(blockers[n])))
        elif n in st:
            rows["started"].append((n, st[n]))
        else:
            bl = d["bot_last"].get(str(n))
            # 着手後に agent が報告している (= run は終わっている) なら、3 時間待たずに停止判定へ進む
            reported = bool(bl) and (str(n) not in launched or age_h(bl["at"]) < age_h(launched[str(n)]))
            stop_re = r"着手不可|着手できません|着手に必要|素材不足|停止します|停止報告|ブロック|PM に.*依頼|判断を"
            if str(n) in launched and age_h(launched[str(n)]) < 3 and not reported:
                rows["recent"].append((n, "launched %.1fh ago" % age_h(launched[str(n)])))
            elif bl and reported and age_h(bl["at"]) < 24 and re.search(stop_re, bl["head"]):
                rl = load_json(RELAUNCH, {}).get(str(n), {"count": 0, "art": None})
                base_line = artifacts_for(n, d, i)
                base = base_line.replace("oc_artifacts:", "").split()
                extra = [a for a in needed_arts(n) if a not in base]
                cand = ("oc_artifacts: " + " ".join(base + extra)) if extra else None
                if not cand and bl.get("art") and bl["art"] != base_line:
                    cand = bl["art"]
                if cand and rl["count"] < 2 and cand != rl["art"]:
                    rows["relaunch"].append((n, cand))
                else:
                    rows["stopped"].append((n, bl["head"][:90].replace("\n", " ")))
            elif bl and age_h(bl["at"]) < 1.5:
                rows["recent"].append((n, "bot comment %.1fh ago" % age_h(bl["at"])))
            elif bl and age_h(bl["at"]) < 24 and re.search(stop_re, bl["head"]):
                rl = load_json(RELAUNCH, {}).get(str(n), {"count": 0, "art": None})
                if bl.get("art") and bl["art"] != rl["art"] and rl["count"] < 2 and bl["art"] != artifacts_for(n, d, i):
                    rows["relaunch"].append((n, bl["art"]))
                else:
                    rows["stopped"].append((n, bl["head"][:90].replace("\n", " ")))
            else:
                rows["ready"].append(n)
    rows["ready"].sort(key=lambda n: (-blocks_count.get(n, 0), "任意" in iss[n]["title"], n))
    return iss, children, blockers, rows


def cmd_plan():
    d = snapshot()
    iss, children, blockers, rows = classify(d)
    op, stuck = open_pr_count()
    ph = phase_update(op)
    print(f"open issues={len(iss)} open PRs={op} (stuck={stuck}) phase={'REVIEW-ONLY' if ph['review_only'] else 'LAUNCH'} active runs={active_runs(d)} target={TARGET}")
    for k in ("blocked", "started", "user", "stopped", "recent"):
        print(f"{k}: {len(rows[k])}")
    print(f"relaunch (停止報告の素材名で再投入): {len(rows['relaunch'])}")
    print(f"ready (未着手・非ブロック): {len(rows['ready'])}")
    for n, why in rows["stopped"][:30]:
        print(f"  STOPPED #{n}: {why}")
    for n in rows["ready"][:15]:
        print(f"  READY   #{n} {iss[n]['title'][:70]} | {artifacts_for(n, d, iss[n])}")


def cmd_blocked():
    d = snapshot()
    iss, children, blockers = graph(d)
    made = removed = failed = same = 0
    ids = {n: i["id"] for n, i in iss.items()}
    for n in sorted(iss):
        if ONLY and n not in ONLY:
            continue
        want = set(blockers.get(n, set()))
        have = set()
        if (iss[n].get("deps") or {}).get("total_blocked_by", 0) > 0 or want:
            rc, o, e = gh(["api", f"repos/{R}/issues/{n}/dependencies/blocked_by", "--paginate", "--jq", ".[]|\"\\(.number) \\(.id) \\(.state)\""])
            if rc == 0:
                for line in o.splitlines():
                    num, iid_, st = line.split()
                    ids.setdefault(int(num), int(iid_))
                    if st == "open":  # close 済みの blocker は無害なので触らない
                        have.add(int(num))
        for b in sorted(want - have):
            if DRY:
                print(f"DRY +#{n} blocked_by #{b}")
                continue
            rc, o, e = gh(["api", "-X", "POST", f"repos/{R}/issues/{n}/dependencies/blocked_by", "-F", f"issue_id={ids[b]}"])
            if rc and "unexpected end of JSON" not in e:
                failed += 1
                print(f"FAILED +#{n} <- #{b}: {e.strip()[:120]}")
            else:
                made += 1
            time.sleep(0.4)
        for b in sorted(have - want):
            if DRY:
                print(f"DRY -#{n} blocked_by #{b}")
                continue
            rc, o, e = gh(["api", "-X", "DELETE", f"repos/{R}/issues/{n}/dependencies/blocked_by/{ids[b]}"])
            if rc and "unexpected end of JSON" not in e:
                failed += 1
                print(f"FAILED -#{n} <- #{b}: {e.strip()[:120]}")
            else:
                removed += 1
            time.sleep(0.4)
        same += len(want & have)
    print(f"blocked_by: added={made} removed={removed} unchanged={same} failed={failed}")


BODY = """/oc oc_actions_allow_write
{art}
PM が着手を依頼します (1 issue = 1 run)。この issue は、ブロックしている open な issue が無く、未着手です。
1. issue 本文と該当 REPORT・過去コメントを読み、**未達の受入条件を特定**してください。
   - 全て達成済みなら、根拠 (PR・commit・実測) をコメントして issue を close してください。
   - 未達があれば、`N-<slug>` ブランチで実装し、PR (--base main) を作成してください。受入条件を全て満たしたときだけ `Closes #N`、部分達成なら `Refs #N` とし、未解決は起票先付きで書いてください。
2. 着手から 10 分以内と、完了・停止時に、必ず `gh issue comment` で結果を投稿してください。60 分で終わらない場合は、その時点の成果を ready の PR にして区切ってください。
   - **1 run (60 分) に収まらないと判断したら、停止せずに分割してください**: 受入条件の一部として最小で完結する単位を選んで実装し、ready の PR で区切る。残りは、重複を `gh api -X GET search/issues` で確認したうえで、子 issue として**自分で起票**する (題名は `[AREA-n]` 形式、本文に `親: #N`・受入条件・必要な `oc_artifacts:` 行を書く)。起票した番号を最終回答と issue コメントに書く。「PM に分割を依頼する」で止まらない。
3. 素材が足りない場合は、必要な `oc_artifacts` 名を報告して停止してください。他の issue に依存することが分かった場合も、その issue 番号を報告して停止してください (PM が blocked_by を設定します)。
"""


def cmd_launch():
    d = snapshot()
    iss, children, blockers, rows = classify(d)
    op, stuck = open_pr_count()
    ph = phase_update(op)
    act = active_runs(d)
    print(f"open PRs={op} (stuck={stuck}) phase={'REVIEW-ONLY' if ph['review_only'] else 'LAUNCH'} active={act} target={TARGET} ready={len(rows['ready'])}")
    why = launch_stop_reason(stuck)
    if why:
        print(f"停止: {why}")
        return
    if ph["review_only"] and os.environ.get("FORCE_PHASE") != "1":
        print("Review-Only Phase: 新規着手しない (Opened PR が 10 件未満になったら解除)")
        return
    room = max(0, TARGET - act)
    n_launch = min(room, BATCH, len(rows["ready"]))
    relaunch = {n: art for n, art in rows["relaunch"]}
    if ONLY:
        picks = [n for n in list(relaunch) + rows["ready"] if n in ONLY]
    else:
        picks = (list(relaunch) + rows["ready"])[: max(n_launch, len(relaunch))]
    launched = load_json(LAUNCHED, {})
    rl_state = load_json(RELAUNCH, {})
    for n in picks:
        art = relaunch.get(n) or artifacts_for(n, d, iss[n])
        body = BODY.format(art=art)
        if n in relaunch:
            body += "\n前回の停止報告で「無い・必要」とされた素材を足して再投入します。展開されたことを ls で確認してから使ってください。\n"
        if DRY:
            print(f"DRY launch #{n} {iss[n]['title'][:60]} | {art}" + (" (relaunch)" if n in relaunch else ""))
            continue
        rc, o, e = gh(["api", f"repos/{R}/issues/{n}/comments", "-f", f"body={body}", "--jq", ".html_url"])
        if rc:
            print(f"FAILED #{n}: {e.strip()[:120]}")
            continue
        launched[str(n)] = now().isoformat()
        if n in relaunch:
            st_ = rl_state.get(str(n), {"count": 0, "art": None})
            rl_state[str(n)] = {"count": st_["count"] + 1, "art": relaunch[n]}
        print(f"launched #{n}" + (" (relaunch)" if n in relaunch else ""))
        time.sleep(1.5)
    json.dump(launched, open(LAUNCHED, "w"))
    json.dump(rl_state, open(RELAUNCH, "w"))
    print(f"launched {len(picks)} (room={room})")


if __name__ == "__main__":
    {"plan": cmd_plan, "blocked": cmd_blocked, "launch": cmd_launch}.get(sys.argv[1] if len(sys.argv) > 1 else "plan", cmd_plan)()
