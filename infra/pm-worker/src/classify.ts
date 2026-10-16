// tools/pm/launch_issues.py の graph / started_map / needed_arts / classify の移植 (純関数のみ)。
// GitHub・現在時刻・ローカルファイルは読まず、呼び出し側が ClassifyInput で渡す。
// Python の defaultdict のキー挿入順を保つ (循環除去の結果が順序に依るため)。
import { ALLOW_ARTS, addArts, defaultArtLine, effectivePrioMap, sortReady } from "./launch.ts";
import type { LaunchState } from "./launchobs.ts";
import { parentOf } from "./refs.ts";
import { DIGEST_ROLLING_RE, OC_HOLD_LABEL } from "./pm.ts";

// recent の窓 (時間)。holdinfo.ts の解除見込みも同じ値を使う (#5110)。
// BOT_COMMENT_WINDOW_H は OC_DOUBLE_MS (30 分) と同値。RUN_WINDOW_H は engine.ts の dry-run の再掲間隔も兼ねる (#5596)。
// prio:critical の issue は bot コメントの窓と run 完了の窓の対象外 (#5596)。
export const BOT_COMMENT_WINDOW_H = 0.5;
export const RUN_WINDOW_H = 1;

export interface SnapIssue {
  number: number;
  title: string;
  labels: string[];
  body: string;
  // 本文の検証済み素材行 (engine の snapshot が入れる)。無ければ未設定。
  artLine?: string;
  deps?: { total_blocked_by?: number } | null;
  // sub-issue の親 (sig.subParent の n)。本文の『親: #N』が無いときの区分の継承に使う (#3989)。
  subParent?: number | null;
}
export interface SnapPr {
  number: number;
  state: string;
  ref: string;
  body: string;
}
export interface SnapRun {
  id: number;
  event: string;
  title: string;
}
export interface BotLast {
  at: string;
  head: string;
  art: string | null;
}
export interface Snapshot {
  issues: SnapIssue[];
  prs: SnapPr[];
  runs: SnapRun[];
  bot_last: Record<string, BotLast>;
  // 直前の報告 (run-outcome・PM のマーカーを含むコメントを除く)。停止報告の判定と素材の再投入に使う。bot_last は run-outcome で上書きされる。
  bot_report: Record<string, BotLast>;
  pm_art: Record<string, { at: string; line: string }>;
}
export interface RelaunchState {
  count: number;
  art: string | null;
}
export interface ClassifyInput {
  nowMs: number;
  launched: Record<string, string>;
  // 投稿の観測状態 (launchobs.ts)。無い issue は観測記録の無い古い launch (従来の 3 時間判定)。
  launchState?: Record<string, LaunchState>;
  // 観測済み launch の、観測した run の完了時刻 (launchobs.ts の doneAt)。ある観測済み launch は完了から 3 時間を recent の基準にする。無ければ投稿から 3 時間。
  launchDoneAt?: Record<string, string>;
  relaunch: Record<string, RelaunchState>;
  // manual_deps.json (キーは issue 番号の文字列)。
  manualDeps: Record<string, number[]>;
  // issue dependencies (blocked_by) の open な番号。total_blocked_by > 0 の issue ごとに必要。
  liveBlockers: Record<string, number[]>;
  // 最後の bot コメントの全文 (run-outcome・PM 応答の除外判定 = stopHit に使う)。素材名は reportBody から読む。
  fullBotBody: Record<string, string>;
  // 直前の報告の全文 (run-outcome を除く)。素材名の抽出に使う (neededArts)。
  reportBody: Record<string, string>;
  // 最後の run-outcome の reason (stop / split / blocked / artifact / unknown)。素材による再投入は artifact のときだけ。
  outcomeReason: Record<string, string>;
  // PM の応答の最新時刻 (sig.pmAt)。bot の最後のコメント以降に PM の応答があれば、その bot コメントの窓 (BOT_COMMENT_WINDOW_H) は解けている (#5226)。
  pmAt?: Record<string, string>;
}
export interface Rows {
  blocked: Array<[number, number[]]>;
  started: Array<[number, string[]]>;
  user: Array<[number, string]>;
  // oc:hold の issue (#2651)。Worker の自動着手を見送る。launch_issues.py に無い区分 (Worker 版の拡張)。
  hold: Array<[number, string]>;
  stopped: Array<[number, string]>;
  recent: Array<[number, string]>;
  relaunch: Array<[number, string]>;
  ready: number[];
}

const NEED_RE = /不足|無い|無く|無かった|ない|存在しな|必要|依頼|欠|足りな|未配置|未展開|入っていな|のみ|だけ|揃っ/;
// 停止報告の構造化マーカー (PM 判断 R7・#5111)。散文の語では停止と判定しない。先頭行の見出しだけを見る。
const STOP_HEAD_RE = /^## 停止報告/;
// stopped の判定根拠 (/status.launch_holds の basis。#5234)。
export const STOP_BASIS_HEAD = "見出し ## 停止報告";
// run-outcome (record-run-outcome.sh の定型文) と PM の応答は、停止報告ではない (VM 版と同じ規則)。
const OUTCOME_OR_PM_RE = /<!-- oc-run-outcome:|<!-- oc-pm-/;
const WORD = "\\p{L}\\p{N}_\\-";

function wordBounded(a: string): RegExp {
  return new RegExp(`(?<![${WORD}])${a}(?![${WORD}])`, "u");
}

// PM の応答 (pmAt) が bot の最後のコメント (botAt) 以降なら、PM はその後に判断済み。窓を解く (#5226)。
const pmAnswered = (pmAt: string | undefined, botAt: string): boolean => !!pmAt && Date.parse(pmAt) >= Date.parse(botAt);

const lines = (s: string): string[] => s.split(/\r\n|\r|\n/);
const allNums = (s: string): number[] => [...s.matchAll(/#(\d+)/g)].map((m) => Number(m[1]));

function addTo(m: Map<number, Set<number>>, n: number, xs: Iterable<number>): void {
  let s = m.get(n);
  if (!s) {
    s = new Set();
    m.set(n, s);
  }
  for (const x of xs) s.add(x);
}

function graph(d: Snapshot, input: ClassifyInput) {
  const iss = new Map<number, SnapIssue>();
  for (const i of d.issues) iss.set(i.number, i);
  const nums = new Set(iss.keys());

  const children = new Map<number, number[]>();
  for (const [n, i] of iss) {
    const pn = parentOf(i.body);
    if (pn !== null && nums.has(pn) && pn !== n) {
      const c = children.get(pn) ?? [];
      c.push(n);
      children.set(pn, c);
    }
  }

  const pats = [/blockedBy\s*[:：]?\s*(.+)/, /依存\s*[:：]\s*(.+)/, /先行\s*[:：]\s*(.+)/, /前提\s*[:：*]+\s*(.+)/];
  const dep = new Map<number, Set<number>>();
  for (const [n, i] of iss) {
    for (const line of lines(i.body)) {
      for (const p of pats) {
        const m = p.exec(line);
        if (m) for (const x of allNums(m[1])) if (nums.has(x) && x !== n) addTo(dep, n, [x]);
      }
      for (const m of line.matchAll(/#(\d+)\s*(?:が|は)?\s*ブロッカー/g)) {
        const x = Number(m[1]);
        if (nums.has(x) && x !== n) addTo(dep, n, [x]);
      }
    }
  }

  const hasPr = new Set<number>();
  for (const p of d.prs) {
    const m = /^(\d+)-/.exec(p.ref);
    if (m) hasPr.add(Number(m[1]));
  }

  const blockers = new Map<number, Set<number>>();
  for (const [n, ds] of dep) addTo(blockers, n, ds);
  for (const [k, ds] of Object.entries(input.manualDeps)) addTo(blockers, Number(k), ds.filter((b) => nums.has(b)));
  for (const [n, i] of iss) {
    if ((i.deps?.total_blocked_by ?? 0) > 0) {
      const lb = input.liveBlockers[String(n)];
      if (!lb) throw new Error(`live blockers missing for #${n}`);
      addTo(blockers, n, lb.filter((b) => nums.has(b)));
    }
  }
  for (const [pn, cs] of children) if (!hasPr.has(pn)) addTo(blockers, pn, cs);

  // 循環は『親が子に待つ』向きだけを残す (子 -> 親の依存は捨てる)
  for (const n of [...blockers.keys()]) {
    const cur = blockers.get(n) ?? new Set<number>();
    const kids = children.get(n) ?? [];
    blockers.set(
      n,
      new Set([...cur].filter((b) => !((blockers.get(b)?.has(n) ?? false) && !kids.includes(b)))),
    );
  }
  return { iss, children, blockers };
}

function startedMap(d: Snapshot, iss: Map<number, SnapIssue>): Map<number, string[]> {
  const st = new Map<number, string[]>();
  const push = (n: number, s: string) => {
    const a = st.get(n) ?? [];
    a.push(s);
    st.set(n, a);
  };
  for (const p of d.prs) {
    if (p.state !== "open") continue;
    const m = /^(\d+)-/.exec(p.ref);
    if (m && iss.has(Number(m[1]))) push(Number(m[1]), `PR#${p.number}`);
    for (const m2 of p.body.matchAll(/(?:Closes|Refs|Fixes)\s+#(\d+)/g)) {
      const n = Number(m2[1]);
      if (iss.has(n)) push(n, `PR#${p.number}`);
    }
  }
  for (const r of d.runs) {
    if (r.event === "issue_comment" || r.event === "workflow_dispatch") {
      for (const [n, i] of iss) if (r.title.trim() === i.title.trim()) push(n, `run${r.id}`);
    }
  }
  return st;
}

export function neededArts(n: number, input: ClassifyInput): string[] {
  return neededArtsOf(input.reportBody[String(n)] ?? "");
}
// 報告本文から、不足と書かれた行の allowlist 内の素材名を取る (neededArts の本体。engine の oc-pm 検出も使う)。
export function neededArtsOf(body: string): string[] {
  const out: string[] = [];
  for (const line of lines(body)) {
    if (!NEED_RE.test(line)) continue;
    for (const a of ALLOW_ARTS) if (wordBounded(a).test(line) && !out.includes(a)) out.push(a);
  }
  return out;
}

const artTokens = (line: string | null | undefined): string[] =>
  (line ?? "").replaceAll("oc_artifacts:", "").split(/\s+/).filter(Boolean);
// 行の素材名 (allowlist 内) のうち、base に無いもの。
const newArts = (line: string | null | undefined, base: string[]): string[] =>
  artTokens(line).filter((a) => ALLOW_ARTS.includes(a) && !base.includes(a));
export const isStopReport = (text: string): boolean => STOP_HEAD_RE.test(text);
const head90 = (s: string): string => Array.from(s).slice(0, 90).join("").replaceAll("\n", " ");
const fmt1 = (x: number): string => x.toFixed(1);

export interface Classified {
  rows: Rows;
  blocksCount: Record<string, number>;
  // 親 (open) -> open な子の番号。
  children: Record<string, number[]>;
  // stopped の行の判定根拠 (issue 番号 -> 根拠の語。STOP_BASIS_HEAD など)。
  stopBasis: Map<number, string>;
}

export function classify(d: Snapshot, input: ClassifyInput): Classified {
  const { iss, blockers, children } = graph(d, input);
  const st = startedMap(d, iss);
  const ageH = (ts: string) => (input.nowMs - Date.parse(ts)) / 3_600_000;
  const rows: Rows = { blocked: [], started: [], user: [], hold: [], stopped: [], recent: [], relaunch: [], ready: [] };
  const stopBasis = new Map<number, string>();

  const blocksCount = new Map<number, number>();
  for (const bs of blockers.values()) for (const b of bs) blocksCount.set(b, (blocksCount.get(b) ?? 0) + 1);
  // 区分は親からの継承を含む (#3973)。snapshot は open な issue だけなので、closed の親は引けず継承しない (engine の prioMap と同じ値)。
  const prios = effectivePrioMap(d.issues.map((i) => ({ number: i.number, state: "open" as const, labels: i.labels, body: i.body, subParent: i.subParent ?? null })));

  const artifactsFor = (n: number, i: SnapIssue): string => defaultArtLine(d.pm_art[String(n)]?.line, i.artLine, i.title, i.labels);
  const rlOf = (n: number): RelaunchState => input.relaunch[String(n)] ?? { count: 0, art: null };

  for (const [n, i] of [...iss].sort((a, b) => a[0] - b[0])) {
    // 日次 digest の rolling issue (CI-70) は PM agent が本文を更新するだけ。どの行にも入れず、着手も再投入もしない。
    if (DIGEST_ROLLING_RE.test(i.title)) continue;
    const k = String(n);
    const launchedAt = input.launched[k];
    const isLaunched = Object.hasOwn(input.launched, k);
    const bs = blockers.get(n);
    const bl = d.bot_last[k];
    if (i.labels.includes("needs-user-input")) {
      rows.user.push([n, ""]);
    } else if (i.labels.includes(OC_HOLD_LABEL)) {
      rows.hold.push([n, ""]);
    } else if (bs && bs.size > 0) {
      rows.blocked.push([n, [...bs].sort((a, b) => a - b)]);
    } else if (st.has(n)) {
      rows.started.push([n, st.get(n) ?? []]);
    } else {
      const reported = !!bl && (!isLaunched || ageH(bl.at) < ageH(launchedAt));
      const stopHit = !!bl && STOP_HEAD_RE.test(bl.head) && !OUTCOME_OR_PM_RE.test(input.fullBotBody[k] ?? "");
      // 素材による再投入は、直前の報告 (rep) が停止報告で、最後の run-outcome が artifact のときだけ。
      const rep = d.bot_report[k];
      const repStop = !!rep && STOP_HEAD_RE.test(rep.head);
      const material = repStop && input.outcomeReason[k] === "artifact";
      const ls = input.launchState?.[k];
      // 観測済みで完了を見た run があれば、その完了から RUN_WINDOW_H を recent にする (run が進行中は started が先に効く)。
      const doneAt = ls === "observed" ? input.launchDoneAt?.[k] : undefined;
      // prio:critical は bot コメントの窓と run 完了の窓の対象外 (#5596)。投稿直後の窓 (launch 未観測・投稿からの窓) は残す。
      const critical = prios.get(n) === "critical";
      // 観測できなかった投稿は再投稿しない (stopped で止める)。観測するまでは recent (run が現れれば started になる)。
      if (ls === "failed") {
        rows.stopped.push([n, "launch-unobserved"]);
        stopBasis.set(n, "launch 観測 failed");
      } else if (isLaunched && ls === "launched" && !reported) {
        rows.recent.push([n, `launch not observed yet (${fmt1(ageH(launchedAt) * 60)} min)`]);
      } else if (isLaunched && doneAt !== undefined && ageH(doneAt) < RUN_WINDOW_H && !reported && !critical) {
        rows.recent.push([n, `run finished ${fmt1(ageH(doneAt))}h ago`]);
      } else if (isLaunched && doneAt === undefined && ls !== "launched" && ageH(launchedAt) < RUN_WINDOW_H && !reported) {
        rows.recent.push([n, `launched ${fmt1(ageH(launchedAt))}h ago`]);
      } else if (bl && reported && ageH(bl.at) < 24 && stopHit) {
        const rl = rlOf(n);
        const baseLine = artifactsFor(n, i);
        const base = artTokens(baseLine);
        let cand: string | null = material ? addArts(baseLine, neededArts(n, input)) : null;
        if (!cand && material && newArts(rep?.art, base).length) cand = rep?.art ?? null;
        if (cand && rl.count < 2 && cand !== rl.art) rows.relaunch.push([n, cand]);
        else {
          rows.stopped.push([n, head90(bl.head)]);
          stopBasis.set(n, STOP_BASIS_HEAD);
        }
      } else if (bl && !critical && ageH(bl.at) < BOT_COMMENT_WINDOW_H && !pmAnswered(input.pmAt?.[k], bl.at)) {
        rows.recent.push([n, `bot comment ${fmt1(ageH(bl.at))}h ago`]);
      } else if (bl && ageH(bl.at) < 24 && stopHit) {
        const rl = rlOf(n);
        const cand = material && newArts(rep?.art, artTokens(artifactsFor(n, i))).length ? (rep?.art ?? null) : null;
        if (cand && rl.count < 2 && cand !== rl.art) rows.relaunch.push([n, cand]);
        else {
          rows.stopped.push([n, head90(bl.head)]);
          stopBasis.set(n, STOP_BASIS_HEAD);
        }
      } else {
        rows.ready.push(n);
      }
    }
  }

  const ready = rows.ready.map((n) => ({ n, title: iss.get(n)?.title ?? "", blocksCount: blocksCount.get(n) ?? 0, prio: prios.get(n) ?? "normal" }));
  rows.ready = sortReady(ready).map((r) => r.n);
  return {
    rows,
    blocksCount: Object.fromEntries(blocksCount),
    children: Object.fromEntries([...children].map(([k, v]) => [String(k), [...v]])),
    stopBasis,
  };
}
