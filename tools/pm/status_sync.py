#!/usr/bin/env python3
"""docs/STATUS.md の自動節を、直近に merge された PR の事実から更新する (#2361)。

REST のみ (GraphQL は使わない)。書き換えるのは `<!-- status-auto:begin -->` と
`<!-- status-auto:end -->` の間だけで、それ以外の byte は変えない (変わるなら書かずに終了 2)。
測定値は書かない (件数・PR 番号・時刻のみ)。

入力:
  - `pulls?state=closed&base=main&sort=updated&direction=desc` の `merged_at` が期間内の PR
  - PR 本文の `Closes|Refs|Fixes #N` が指す issue (題名 `[AREA-n]`・ラベル・本文)
  - 写像表: STATUS.md 内の `<!-- status-map ... -->` (JSON)
写像の優先順 (最初に当たったもの): 紐づく issue の題名 AREA → PR 題名の AREA → ラベル →
  題名の MS<数字> → PR 題名の conventional commit scope → 本文の MS<数字> → その他。
題名が `docs(status): sync merged PRs` の PR (本スクリプトの自動 PR) は数えない
(数えると、自分の merge が次の差分を生む)。

終了コード: 0 = 正常 (更新済み・差分なし・debounce で何もしない) / 1 = `--check` で差分あり /
  2 = 入力不正・自動節の外が変わる (書かない) / 3 = rate limit の残りが 1,500 未満で中断。
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BEGIN = "<!-- status-auto:begin -->"
END = "<!-- status-auto:end -->"
MAP_RE = re.compile(r"<!-- status-map[ \t]*\n(.*?)\n-->", re.S)
OTHER = "その他"
SELF_TITLE = "docs(status): sync merged PRs"
MIN_REMAINING = 1500
PER_PAGE = 100
MAX_PAGES = 30
PRELOAD_MIN = 30
DEFAULT_REPO = "signature-studio/signature-studio-dev"
MAX_REPS = 3
VOLATILE = re.compile(r"^- (?:期間|updated):.*$", re.M)
LINK_RE = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\b[ \t]*:?[ \t]+#(\d+)")
MS_RE = re.compile(r"\bMS(\d{1,2})\b")
AREA_RE = re.compile(r"^\s*\[([^\]]+)\]")
SCOPE_RE = re.compile(r"^[a-z]+\(([^)]+)\)!?:")


class RateLimited(Exception):
    pass


class Invalid(Exception):
    pass


def parse_ts(s):
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"時刻の形式が不正: {s!r}")


def fmt_ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%MZ")


class GitHub:
    """REST のみの最小クライアント。応答ごとに X-Ratelimit-Remaining を見て、閾値未満なら中断する。"""

    def __init__(self, repo, token, opener=urllib.request.urlopen, min_remaining=MIN_REMAINING):
        self.repo, self.token, self.opener, self.min_remaining = repo, token, opener, min_remaining
        self.urls, self.remaining = [], None

    def _check(self, headers):
        rem = headers.get("X-Ratelimit-Remaining") if headers is not None else None
        if rem is None:
            return
        self.remaining = int(rem)
        if self.remaining < self.min_remaining:
            raise RateLimited(f"X-Ratelimit-Remaining={self.remaining} < {self.min_remaining}")

    def get(self, path, params=None):
        url = f"https://api.github.com/repos/{self.repo}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "status_sync",
        })
        for attempt in range(3):
            self.urls.append(url)
            try:
                with self.opener(req, timeout=30) as r:
                    self._check(r.headers)
                    return json.load(r)
            except urllib.error.HTTPError as e:
                self._check(e.headers)
                if e.code == 404:
                    return None
                if e.code < 500 or attempt == 2:
                    raise
            except urllib.error.URLError:
                if attempt == 2:
                    raise
            time.sleep(attempt + 1)


def load_map(text):
    m = MAP_RE.search(text)
    if not m:
        raise Invalid("写像ブロック `<!-- status-map ... -->` が STATUS.md に無い")
    try:
        d = json.loads(m.group(1))
    except ValueError as e:
        raise Invalid(f"写像ブロックの JSON が不正: {e}")
    for k, t in (("ms", list), ("subsystems", list), ("areas", dict), ("labels", dict), ("scopes", dict)):
        if not isinstance(d.get(k), t):
            raise Invalid(f"写像ブロックの `{k}` が {t.__name__} でない")
    return d


class Mapper:
    def __init__(self, d):
        self.ms = set(d["ms"])
        self.subsystems = set(d["subsystems"])
        self.areas = {k.upper(): v for k, v in d["areas"].items()}
        self.labels = d["labels"]
        self.scopes = {k.lower(): v for k, v in d["scopes"].items()}

    def area_target(self, title):
        m = AREA_RE.match(title or "")
        if not m:
            return None
        c = m.group(1).upper()
        best = None
        for k, tgt in self.areas.items():
            if c.startswith(k) and (len(c) == len(k) or not c[len(k)].isalpha()):
                if best is None or len(k) > len(best[0]):
                    best = (k, tgt)
        return best[1] if best else None

    def ms_target(self, text):
        for m in MS_RE.finditer(text or ""):
            if f"MS{int(m.group(1))}" in self.ms:
                return f"MS{int(m.group(1))}"
        return None

    def scope_target(self, title):
        m = SCOPE_RE.match(title or "")
        if not m:
            return None
        s = m.group(1).split(",")[0].strip().lower()
        if s in self.scopes:
            return self.scopes[s]
        while s:
            if s in self.subsystems:
                return s
            s = s.rpartition("/")[0]
        return None

    def classify(self, pr, issues):
        linked = [issues[n] for n in linked_numbers(pr) if issues.get(n)]
        for i in linked:
            t = self.area_target(i.get("title"))
            if t:
                return t
        t = self.area_target(pr.get("title"))
        if t:
            return t
        for src in linked + [pr]:
            for lab in src.get("labels") or []:
                if lab.get("name") in self.labels:
                    return self.labels[lab["name"]]
        for text in [pr.get("title")] + [i.get("title") for i in linked]:
            t = self.ms_target(text)
            if t:
                return t
        t = self.scope_target(pr.get("title"))
        if t:
            return t
        for text in [pr.get("body")] + [i.get("body") for i in linked]:
            t = self.ms_target(text)
            if t:
                return t
        return OTHER


def linked_numbers(pr):
    out = []
    for m in LINK_RE.finditer(pr.get("body") or ""):
        n = int(m.group(1))
        if n != pr.get("number") and n not in out:
            out.append(n)
    return out


def paged(get, path, params, cutoff, what):
    """updated 降順の一覧を、最後の項目が cutoff より古くなるまで取る。"""
    for page in range(1, MAX_PAGES + 1):
        items = get(path, dict(params, per_page=PER_PAGE, page=page)) or []
        yield from items
        if len(items) < PER_PAGE or parse_ts(items[-1]["updated_at"]) < cutoff:
            return
    raise Invalid(f"{what}: {MAX_PAGES} ページでも期間の端に届かない (取得が不完全)")


def list_merged(get, cutoff, now):
    seen, out = set(), []
    for p in paged(get, "pulls", {"state": "closed", "base": "main", "sort": "updated", "direction": "desc"}, cutoff, "pulls"):
        mt = p.get("merged_at")
        if not mt or p["number"] in seen:
            continue
        if not (cutoff <= parse_ts(mt) <= now) or (p.get("base") or {}).get("ref", "main") != "main":
            continue
        if (p.get("title") or "").startswith(SELF_TITLE):
            continue
        seen.add(p["number"])
        out.append(p)
    return out


def load_issues(get, prs, cutoff):
    need = sorted({n for p in prs for n in linked_numbers(p)})
    cache = {}
    if len(need) >= PRELOAD_MIN:
        for i in paged(get, "issues", {"state": "all", "since": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                       "sort": "updated", "direction": "desc"}, cutoff, "issues"):
            cache[i["number"]] = i
    for n in need:
        if n not in cache:
            cache[n] = get(f"issues/{n}")
    return cache


def summarize(prs, issues, mapper):
    by = {}
    for p in prs:
        by.setdefault(mapper.classify(p, issues), []).append(p["number"])
    return by


def sort_key(item):
    t, nums = item
    if t.startswith("MS"):
        return (0, int(t[2:]), "")
    if t == OTHER:
        return (2, 0, "")
    return (1, -len(nums), t)


def render(now, hours, total, by):
    rows = dict(by)
    rows.setdefault(OTHER, [])
    lines = [f"- 期間: {fmt_ts(now - timedelta(hours=hours))} 〜 {fmt_ts(now)} (直近 {hours} 時間)",
             f"- merge 件数: {total}",
             f"- updated: {fmt_ts(now)}",
             "",
             "| 対象 | 件数 | 代表 PR (番号の大きい順・最大 3) |",
             "|---|---:|---|"]
    for t, nums in sorted(rows.items(), key=sort_key):
        label = t if (t.startswith("MS") or t == OTHER) else f"`{t}`"
        reps = "—" if (t == OTHER or not nums) else ", ".join(f"#{n}" for n in sorted(nums, reverse=True)[:MAX_REPS])
        lines.append(f"| {label} | {len(nums)} | {reps} |")
    return "\n".join(lines)


def find_auto(text):
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise Invalid(f"STATUS.md に {BEGIN} と {END} がちょうど 1 組必要")
    b, e = text.index(BEGIN) + len(BEGIN), text.index(END)
    if b > e:
        raise Invalid(f"{END} が {BEGIN} より前にある")
    return b, e


def outside(text):
    b, e = find_auto(text)
    return text[:b] + text[e:]


def splice(text, inner):
    b, e = find_auto(text)
    return text[:b] + "\n" + inner + "\n" + text[e:]


def content_of(inner):
    return VOLATILE.sub("-", inner.strip("\n"))


def main(argv=None, get=None, now=None, out=sys.stdout, err=sys.stderr, opener=urllib.request.urlopen):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="STATUS.md の自動節を直近の merge から更新する")
    ap.add_argument("--status", default=os.path.join(here, "..", "..", "docs", "STATUS.md"))
    ap.add_argument("--repo", default=os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO)
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--min-interval-hours", type=float, default=0)
    ap.add_argument("--check", action="store_true", help="書き込まず、差分があれば終了コード 1")
    ap.add_argument("--now", help="現在時刻の固定 (YYYY-MM-DDTHH:MMZ。テスト・再現用)")
    a = ap.parse_args(argv)

    try:
        with open(a.status, encoding="utf-8", newline="") as f:
            text = f.read()
        find_auto(text)
        mapper = Mapper(load_map(text))
    except (OSError, Invalid) as e:
        print(f"status_sync: {e}", file=err)
        return 2

    if now is None:
        now = parse_ts(a.now) if a.now else datetime.now(timezone.utc)
    now = now.replace(second=0, microsecond=0)

    b, e = find_auto(text)
    old_inner = text[b:e]
    m = re.search(r"^- updated: (\S+)", old_inner, re.M)
    if a.min_interval_hours > 0 and m:
        try:
            age = (now - parse_ts(m.group(1))).total_seconds()
        except ValueError:
            age = None
        if age is not None and 0 <= age < a.min_interval_hours * 3600:
            print(f"status_sync: no-op (updated: {m.group(1)} から {a.min_interval_hours:g} 時間未満)", file=out)
            return 0

    client = None
    if get is None:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
            token = r.stdout.strip() if r.returncode == 0 else ""
        if not token:
            print("status_sync: GH_TOKEN / GITHUB_TOKEN が無い", file=err)
            return 2
        client = GitHub(a.repo, token, opener=opener)
        get = client.get

    cutoff = now - timedelta(hours=a.hours)
    try:
        prs = list_merged(get, cutoff, now)
        issues = load_issues(get, prs, cutoff)
    except RateLimited as ex:
        print(f"status_sync: 中断 ({ex})。STATUS.md は変更しない", file=err)
        return 3
    except (Invalid, urllib.error.URLError) as ex:
        print(f"status_sync: {ex}", file=err)
        return 2
    if client:
        print(f"status_sync: requests={len(client.urls)} graphql={sum('graphql' in u for u in client.urls)} "
              f"ratelimit_remaining={client.remaining} merged={len(prs)}", file=err)

    new_inner = render(now, a.hours, len(prs), summarize(prs, issues, mapper))
    new_text = splice(text, new_inner)
    try:
        intact = outside(new_text) == outside(text)
    except Invalid:
        intact = False
    if not intact:
        print("status_sync: 自動節の外が変わるため書かない", file=err)
        return 2
    if content_of(new_inner) == content_of(old_inner):
        print("status_sync: 差分なし", file=out)
        return 0
    if a.check:
        diff = difflib.unified_diff(old_inner.strip("\n").splitlines(), new_inner.splitlines(),
                                    "STATUS.md (現状)", "STATUS.md (更新後)", lineterm="")
        print("\n".join(diff), file=out)
        return 1
    with open(a.status, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    print(f"status_sync: 更新 (merge {len(prs)} 件)", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
