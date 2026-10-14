// PM の本体: 状態の同期 (full / reconcile)・分類・launch の選定と実行・watchdog dispatch・status。
// 時刻・fetch・保管先は注入する (テストでは MemoryStore と fetch モック)。dry-run が既定で、LIVE=1 のときだけ GitHub に書く。
import { classify, type ClassifyInput, type Rows, type Snapshot } from "./classify.ts";
import type { Config } from "./config.ts";
import { Gh, GhError } from "./github.ts";
import { buildLaunchBody, inferArtifacts, planLaunch, validateArtLine } from "./launch.ts";
import type { Store } from "./store.ts";
import {
  applyEvent,
  EMPTY_STATE,
  type IssueState,
  type PmState,
  type PrState,
  type RunState,
  WEBHOOK_EVENTS,
  handleWebhook,
  type WebhookResult,
} from "./webhook.ts";

export const FULL_SYNC_EVERY_MS = 6 * 3_600_000;
// reconcile がこれ以上止まっていたら、状態が古いとみなして launch しない (誤った着手を避ける)。
export const STALE_AFTER_MS = 15 * 60_000;
const NO_PR_MAX_RELAUNCH = 3;

export interface Planned {
  n: number;
  art: string;
  relaunch: boolean;
}

export interface Plan {
  at: string;
  active: number;
  target: number;
  room: number;
  picks: Planned[];
}

interface Meta {
  fullSyncAt?: number;
  reconcileAt?: number;
  watchdogAt?: number;
  tickAt?: number;
  installationId?: number | null;
  lastPlan?: Plan;
  lastError?: { at: string; what: string };
  counters?: { launched: number; dispatched: number; wouldLaunch: number; wouldDispatch: number; reconciles: number };
}

export interface Log {
  at: string;
  kind: "would-launch" | "launch" | "would-dispatch" | "dispatch" | "error" | "skip";
  n?: number;
  art?: string;
  note?: string;
}

const BUCKETS = ["issues", "prs", "runs", "botLast", "pmArt", "blockedBy", "launchedAt"] as const;

export function loadState(store: Store): PmState {
  const s: PmState = structuredClone(EMPTY_STATE);
  for (const b of BUCKETS) {
    for (const [k, v] of store.all(b)) (s as any)[b][k] = v;
  }
  return s;
}

// 参照が変わったキーだけを書く (applyEvent は変更したキーの値を新しいオブジェクトにする)。
export function persistDiff(prev: PmState, next: PmState, store: Store): void {
  for (const b of BUCKETS) {
    const p = (prev as any)[b] as Record<string, unknown>;
    const n = (next as any)[b] as Record<string, unknown>;
    if (p === n) continue;
    for (const k of Object.keys(n)) if (p[k] !== n[k]) store.put(b, k, n[k]);
    for (const k of Object.keys(p)) if (!(k in n)) store.del(b, k);
  }
}

const iso = (ms: number): string => new Date(ms).toISOString();
const ART_LINE_RE = /^\s*`?(oc_artifacts:[^\n`]*)`?\s*$/m;

export interface EngineDeps {
  store: Store;
  cfg: Config;
  now: () => number;
  // App の installation token で認証した REST クライアント。未設定 (setup 前) なら null。
  gh: () => Promise<Gh | null>;
  // この App の bot ログイン (slug + "[bot]")。PM のコメントとして扱う。
  pmBotLogin: () => string | null;
}

export class Engine {
  s: PmState;
  meta: Meta;
  log: Log[] = [];
  dirty = false;
  private busy = false;

  private readonly d: EngineDeps;

  constructor(d: EngineDeps) {
    this.d = d;
    this.s = loadState(d.store);
    this.meta = d.store.get<Meta>("meta", "main") ?? {};
    this.log = d.store.get<Log[]>("meta", "log") ?? [];
  }

  private saveMeta(): void {
    this.d.store.put("meta", "main", this.meta);
  }
  private pushLog(l: Omit<Log, "at">): void {
    this.log.push({ at: iso(this.d.now()), ...l });
    if (this.log.length > 60) this.log = this.log.slice(-60);
    this.d.store.put("meta", "log", this.log);
    console.log(JSON.stringify({ pm: l.kind, n: l.n, art: l.art, note: l.note }));
  }
  private pmLogins(): string[] {
    const b = this.d.pmBotLogin();
    return b ? [...this.d.cfg.pmLogins, b] : this.d.cfg.pmLogins;
  }

  // ---------------------------------------------------------------- webhook
  // 署名の検証は handleWebhook の先頭で行う。検証に失敗したら state も store も変えない。
  receive(secret: string, event: string | null, signature: string | null, body: string): WebhookResult {
    const r = handleWebhook(this.s, {
      secret,
      event,
      signature,
      body,
      botLogin: this.d.cfg.botLogin,
      pmLogins: this.pmLogins(),
      repo: this.d.cfg.repo,
    });
    if (r.status === 202 && r.reason === "applied" && r.state !== this.s) {
      persistDiff(this.s, r.state, this.d.store);
      this.s = r.state;
    }
    if (r.status === 202 && r.reason === "applied") this.dirty = true;
    return r;
  }

  // ---------------------------------------------------------------- 同期
  private applyAll(event: (typeof WEBHOOK_EVENTS)[number], payload: unknown): void {
    const next = applyEvent(this.s, event, payload as any, this.d.cfg.botLogin, this.pmLogins());
    if (next !== this.s) {
      persistDiff(this.s, next, this.d.store);
      this.s = next;
    }
  }

  async fullSync(gh: Gh): Promise<void> {
    const R = this.d.cfg.repo;
    const issues = await gh.list<any>(`/repos/${R}/issues?state=open`, 30);
    const openNums = new Set<number>();
    for (const i of issues) {
      if (i.pull_request) continue;
      openNums.add(i.number);
      this.applyAll("issues", { issue: i });
    }
    for (const [k, v] of Object.entries(this.s.issues)) {
      if (v.state === "open" && !openNums.has(Number(k))) {
        const next: IssueState = { ...v, state: "closed", labels: [], body: "", updatedAt: iso(this.d.now()) };
        this.d.store.put("issues", k, next);
        this.s = { ...this.s, issues: { ...this.s.issues, [k]: next } };
      }
    }
    const prs = await gh.list<any>(`/repos/${R}/pulls?state=all`, 30);
    for (const p of prs) this.applyAll("pull_request", { pull_request: p });
    await this.syncRuns(gh);
    await this.syncComments(gh, this.d.now() - 48 * 3_600_000);
    await this.syncBlockers(gh, 80);
    this.meta.fullSyncAt = this.meta.reconcileAt = this.d.now();
    this.saveMeta();
  }

  private async syncRuns(gh: Gh): Promise<void> {
    const R = this.d.cfg.repo;
    const seen = new Set<string>();
    for (const st of ["in_progress", "queued", "pending", "waiting"]) {
      const runs = await gh.list<any>(`/repos/${R}/actions/runs?status=${st}`, 3, (j) => j?.workflow_runs ?? []);
      for (const w of runs) {
        seen.add(String(w.id));
        this.applyAll("workflow_run", { workflow_run: w });
      }
    }
    // 完了を取りこぼした run (webhook 欠落) は、一覧に無ければ completed とみなす。
    for (const [k, v] of Object.entries(this.s.runs)) {
      if (v.status !== "completed" && !seen.has(k)) {
        const next: RunState = { ...v, status: "completed", conclusion: v.conclusion ?? "unknown" };
        this.d.store.put("runs", k, next);
        this.s = { ...this.s, runs: { ...this.s.runs, [k]: next } };
      }
    }
  }

  private async syncComments(gh: Gh, sinceMs: number): Promise<void> {
    const R = this.d.cfg.repo;
    const cs = await gh.list<any>(`/repos/${R}/issues/comments?since=${encodeURIComponent(iso(sinceMs))}`, 40);
    for (const c of cs) {
      const n = Number(String(c.issue_url).split("/").pop());
      if (!Number.isInteger(n)) continue;
      this.applyAll("issue_comment", { action: "created", comment: c, issue: { number: n } });
    }
  }

  // blocked_by の一覧が不明な issue (件数 > 0 だが一覧が無い) を REST で取る。1 回の上限 max 件。
  private async syncBlockers(gh: Gh, max: number): Promise<void> {
    const R = this.d.cfg.repo;
    let left = max;
    for (const [k, v] of Object.entries(this.s.issues)) {
      if (left <= 0) break;
      if (v.state !== "open" || v.blockedByCount <= 0 || k in this.s.blockedBy) continue;
      left--;
      const j = await gh.list<any>(`/repos/${R}/issues/${k}/dependencies/blocked_by`, 3);
      // closed の blocker も含めて全件を持つ。open かどうかは分類側が issue の状態で判断する。
      const all = j.map((x) => x.number as number).sort((a, b) => a - b);
      this.d.store.put("blockedBy", k, all);
      this.s = { ...this.s, blockedBy: { ...this.s.blockedBy, [k]: all } };
    }
  }

  // webhook 欠落への備え: run の全件・直近更新の issue / PR / コメントだけを REST で突き合わせる。
  async reconcile(gh: Gh): Promise<void> {
    const R = this.d.cfg.repo;
    const since = (this.meta.reconcileAt ?? this.d.now() - 3_600_000) - 120_000;
    await this.syncRuns(gh);
    const issues = await gh.list<any>(`/repos/${R}/issues?state=all&since=${encodeURIComponent(iso(since))}&sort=updated`, 5);
    for (const i of issues) if (!i.pull_request) this.applyAll("issues", { issue: i });
    const prs = await gh.list<any>(`/repos/${R}/pulls?state=all&sort=updated&direction=desc`, 1);
    for (const p of prs) this.applyAll("pull_request", { pull_request: p });
    await this.syncComments(gh, since);
    await this.syncBlockers(gh, 30);
    this.prune();
    this.meta.reconcileAt = this.d.now();
    this.meta.counters = { ...(this.meta.counters ?? this.zero()), reconciles: (this.meta.counters?.reconciles ?? 0) + 1 };
    this.saveMeta();
  }

  private zero() {
    return { launched: 0, dispatched: 0, wouldLaunch: 0, wouldDispatch: 0, reconciles: 0 };
  }

  // 完了して 1 時間たった run は捨てる (順不同配送の判定に使う期間だけ持つ)。
  private prune(): void {
    const cut = this.d.now() - 3_600_000;
    for (const [k, v] of Object.entries(this.s.runs)) {
      if (v.status === "completed" && Date.parse(v.updatedAt) < cut) {
        this.d.store.del("runs", k);
        const { [k]: _, ...rest } = this.s.runs;
        this.s = { ...this.s, runs: rest };
      }
    }
  }

  // ---------------------------------------------------------------- 分類と計画
  snapshot(): { snap: Snapshot; input: ClassifyInput; unknown: Set<number> } {
    const s = this.s;
    const issues = Object.values(s.issues)
      .filter((i) => i.state === "open")
      .map((i) => ({ number: i.number, title: i.title, labels: i.labels, body: i.body, deps: { total_blocked_by: i.blockedByCount } }));
    const prs = (Object.values(s.prs) as PrState[]).map((p) => ({ number: p.number, state: p.state, ref: p.ref, body: p.body }));
    const runs = (Object.values(s.runs) as RunState[])
      .filter((r) => r.status !== "completed")
      .map((r) => ({ id: r.id, event: r.event, title: r.title }));
    const bot_last: Snapshot["bot_last"] = {};
    const fullBotBody: Record<string, string> = {};
    for (const [k, b] of Object.entries(s.botLast)) {
      const am = ART_LINE_RE.exec(b.body);
      bot_last[k] = { at: b.at, head: b.body.slice(0, 400), art: am ? am[1].trim() : null };
      fullBotBody[k] = b.body;
    }
    const liveBlockers: Record<string, number[]> = {};
    const unknown = new Set<number>();
    for (const i of issues) {
      if ((i.deps?.total_blocked_by ?? 0) > 0) {
        const lb = s.blockedBy[String(i.number)];
        if (lb) liveBlockers[String(i.number)] = lb;
        else {
          liveBlockers[String(i.number)] = [];
          unknown.add(i.number);
        }
      }
    }
    const relaunch: ClassifyInput["relaunch"] = {};
    for (const [k, v] of this.d.store.all<{ count: number; art: string | null }>("relaunch")) relaunch[k] = v;
    return {
      snap: { issues, prs, runs, bot_last, pm_art: s.pmArt },
      input: { nowMs: this.d.now(), launched: s.launchedAt, relaunch, manualDeps: this.d.cfg.manualDeps, liveBlockers, fullBotBody },
      unknown,
    };
  }

  countActive(): number {
    let n = 0;
    for (const r of Object.values(this.s.runs)) {
      if (r.status === "completed") continue;
      if (r.event === "issue_comment" || r.event === "workflow_dispatch" || r.event === "pull_request_review") n++;
      else if (r.event === "repository_dispatch" && r.title.startsWith("oc-fix")) n++;
    }
    return n;
  }

  // 規則は launch_issues.py の classify に、次の 3 点だけ足す (どれも本文を解析しない)。
  //  1. blocked_by の一覧が不明な issue は着手しない (誤着手より遅れを選ぶ)。
  //  2. open な子を持つ親 issue は着手対象から外す。
  //  3. ラベル oc:no-pr の issue は『PR を出さずに終わった』run の後。cooldown が過ぎるまで recent、過ぎたら再着手してよい
  //     (上限 NO_PR_MAX_RELAUNCH 回。超えたら stopped で人の判断に回す)。oc:stuck は user (人の判断待ち) に置く。
  plan(): { rows: Rows; plan: Plan; picks: Planned[] } {
    const { snap, input, unknown } = this.snapshot();
    const { rows, children } = classify(snap, input);
    const labels = new Map(snap.issues.map((i) => [i.number, i.labels] as const));
    const title = new Map(snap.issues.map((i) => [i.number, i.title] as const));
    const nowMs = this.d.now();
    const cool = this.d.cfg.noPrCooldownH * 3_600_000;
    const lastAct = (n: number): number =>
      Math.max(Date.parse(this.s.launchedAt[String(n)] ?? "") || 0, Date.parse(this.s.botLast[String(n)]?.at ?? "") || 0);
    const hasLabel = (n: number, l: string) => (labels.get(n) ?? []).includes(l);
    const npCount = (n: number): number => this.d.store.get<{ count: number }>("relaunch", `np:${n}`)?.count ?? 0;

    const moveTo = (n: number, from: keyof Rows, to: () => void) => {
      (rows as any)[from] = (rows as any)[from].filter((x: any) => (Array.isArray(x) ? x[0] : x) !== n);
      to();
    };

    for (const n of [...rows.ready]) {
      const kids = children[String(n)] ?? [];
      if (unknown.has(n)) moveTo(n, "ready", () => rows.blocked.push([n, []]));
      else if (kids.length) moveTo(n, "ready", () => rows.blocked.push([n, [...kids].sort((a, b) => a - b)]));
      else if (hasLabel(n, "oc:stuck")) moveTo(n, "ready", () => rows.user.push([n, "oc:stuck"]));
      else if (hasLabel(n, "oc:no-pr") && nowMs - lastAct(n) < cool) moveTo(n, "ready", () => rows.recent.push([n, "oc:no-pr cooldown"]));
      else if (hasLabel(n, "oc:no-pr") && npCount(n) >= NO_PR_MAX_RELAUNCH) moveTo(n, "ready", () => rows.stopped.push([n, "oc:no-pr x" + npCount(n)]));
    }
    for (const [n] of [...rows.relaunch]) {
      if ((children[String(n)] ?? []).length || hasLabel(n, "oc:stuck")) moveTo(n, "relaunch", () => rows.stopped.push([n, "parent/stuck"]));
    }
    // 親 (open な子を持つ) で、分類上 started / stopped / recent に入っているものは、そのままにする (着手対象ではないため)。
    // oc:no-pr で、分類が stopped / recent に置いたものも cooldown 後は再着手してよい。
    for (const [n] of [...rows.stopped]) {
      if (hasLabel(n, "oc:no-pr") && nowMs - lastAct(n) >= cool && npCount(n) < NO_PR_MAX_RELAUNCH && !(children[String(n)] ?? []).length && !hasLabel(n, "oc:stuck") && !unknown.has(n)) {
        moveTo(n, "stopped", () => rows.ready.push(n));
      }
    }

    const blocksCount = new Map<number, number>();
    const cls = classify(snap, input);
    for (const [k, v] of Object.entries(cls.blocksCount)) blocksCount.set(Number(k), v);
    const ready = rows.ready.map((n) => ({ n, title: title.get(n) ?? "", blocksCount: blocksCount.get(n) ?? 0 }));
    const active = this.countActive();
    const sel = planLaunch({ ready, relaunch: rows.relaunch.map(([n]) => n), active, target: this.d.cfg.target, batch: this.d.cfg.batch });
    const relMap = new Map(rows.relaunch);
    const picks: Planned[] = [];
    const issueOf = new Map(snap.issues.map((i) => [i.number, i] as const));
    for (const n of sel.picks) {
      const i = issueOf.get(n);
      if (!i) continue;
      const base = this.s.pmArt[String(n)]?.line;
      const cand = relMap.get(n) ?? (base && validateArtLine(base) ? base : inferArtifacts(i.title, i.labels));
      // 本文由来 (PM コメント・bot 報告) の行は、allowlist を通ったものだけを使う。通らなければ推定値に落とす。
      const art = validateArtLine(cand) ? cand : inferArtifacts(i.title, i.labels);
      picks.push({ n, art, relaunch: relMap.has(n) });
    }
    const plan: Plan = { at: iso(nowMs), active, target: this.d.cfg.target, room: sel.room, picks };
    return { rows, plan, picks };
  }

  // ---------------------------------------------------------------- 実行
  private fresh(): boolean {
    return !!this.meta.fullSyncAt && !!this.meta.reconcileAt && this.d.now() - this.meta.reconcileAt < STALE_AFTER_MS;
  }

  async launch(gh: Gh | null): Promise<Plan> {
    const { plan, picks } = this.plan();
    this.meta.lastPlan = plan;
    this.meta.counters = this.meta.counters ?? this.zero();
    if (!this.fresh()) {
      this.meta.lastError = { at: plan.at, what: "state not fresh: launch skipped" };
      this.saveMeta();
      return plan;
    }
    const live = this.d.cfg.live && gh;
    const planned = this.d.store.get<Record<string, number>>("meta", "planned") ?? {};
    for (const p of picks) {
      let body: string;
      try {
        body = buildLaunchBody(p.art);
      } catch {
        this.pushLog({ kind: "skip", n: p.n, note: "invalid artifacts line" });
        continue;
      }
      if (!live) {
        // dry-run: 同じ issue を 3 時間は再掲しない (計画の変化だけを残す)。投稿はしない。
        if (this.d.now() - (planned[String(p.n)] ?? 0) < 3 * 3_600_000) continue;
        planned[String(p.n)] = this.d.now();
        this.meta.counters.wouldLaunch++;
        this.pushLog({ kind: "would-launch", n: p.n, art: p.art, note: p.relaunch ? "relaunch" : undefined });
        continue;
      }
      try {
        await gh!.comment(p.n, body);
      } catch (e) {
        this.pushLog({ kind: "error", n: p.n, note: e instanceof GhError ? e.message : "comment failed" });
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) break;
        continue;
      }
      const at = iso(this.d.now());
      this.d.store.put("launchedAt", String(p.n), at);
      this.s = { ...this.s, launchedAt: { ...this.s.launchedAt, [String(p.n)]: at } };
      if (p.relaunch) {
        const prev = this.d.store.get<{ count: number; art: string | null }>("relaunch", String(p.n)) ?? { count: 0, art: null };
        this.d.store.put("relaunch", String(p.n), { count: prev.count + 1, art: p.art });
      }
      if ((this.s.issues[String(p.n)]?.labels ?? []).includes("oc:no-pr")) {
        const c = this.d.store.get<{ count: number }>("relaunch", `np:${p.n}`)?.count ?? 0;
        this.d.store.put("relaunch", `np:${p.n}`, { count: c + 1 });
      }
      this.meta.counters.launched++;
      this.pushLog({ kind: "launch", n: p.n, art: p.art });
    }
    this.d.store.put("meta", "planned", planned);
    this.saveMeta();
    return plan;
  }

  async watchdog(gh: Gh | null): Promise<"dispatched" | "would" | "skipped"> {
    const every = this.d.cfg.watchdogIntervalS * 1000;
    const last = this.meta.watchdogAt ?? 0;
    // cron と alarm の両方が呼ぶので、周期の半分以内の再送は捨てる。
    if (this.d.now() - last < every / 2) return "skipped";
    this.meta.counters = this.meta.counters ?? this.zero();
    if (!this.d.cfg.live || !gh) {
      this.meta.watchdogAt = this.d.now();
      this.meta.counters.wouldDispatch++;
      this.saveMeta();
      this.pushLog({ kind: "would-dispatch", note: "oc-watchdog" });
      return "would";
    }
    try {
      await gh.dispatch("oc-watchdog");
    } catch (e) {
      this.pushLog({ kind: "error", note: e instanceof GhError ? e.message : "dispatch failed" });
      return "skipped";
    }
    this.meta.watchdogAt = this.d.now();
    this.meta.counters.dispatched++;
    this.saveMeta();
    this.pushLog({ kind: "dispatch", note: "oc-watchdog" });
    return "dispatched";
  }

  // 1 回の点検。alarm (毎分・webhook 後 2 秒) と cron (毎分) の両方から呼ばれる。
  async tick(): Promise<{ ready: boolean }> {
    // cron と alarm が重なっても、同時に 2 回は走らせない (二重投稿の防止)。
    if (this.busy) return { ready: true };
    this.busy = true;
    try {
      return await this.tickInner();
    } finally {
      this.busy = false;
    }
  }

  private async tickInner(): Promise<{ ready: boolean }> {
    const now = this.d.now();
    this.meta.tickAt = now;
    this.dirty = false;
    let gh: Gh | null = null;
    try {
      gh = await this.d.gh();
    } catch (e) {
      this.meta.lastError = { at: iso(now), what: e instanceof GhError ? e.message : "auth failed" };
    }
    if (!gh) {
      this.saveMeta();
      return { ready: false };
    }
    try {
      if (!this.meta.fullSyncAt || now - this.meta.fullSyncAt > FULL_SYNC_EVERY_MS) await this.fullSync(gh);
      else if (now - (this.meta.reconcileAt ?? 0) >= this.d.cfg.reconcileIntervalS * 1000) await this.reconcile(gh);
      await this.watchdog(gh);
      await this.launch(gh);
      this.meta.lastError = undefined;
    } catch (e) {
      this.meta.lastError = { at: iso(now), what: e instanceof GhError ? e.message : "tick failed" };
      this.pushLog({ kind: "error", note: this.meta.lastError.what });
    }
    this.saveMeta();
    return { ready: true };
  }

  // 次の alarm までの待ち (ms)。dirty (webhook 直後) は 2 秒、それ以外は 60 秒。
  nextDelayMs(): number {
    return this.dirty ? 2000 : 60_000;
  }

  // ---------------------------------------------------------------- 観測
  // 集計だけを返す (本文・タイトルは含めない。issue 番号は公開 repo の情報)。
  status(extra: Record<string, unknown> = {}): Record<string, unknown> {
    const { rows, plan } = this.plan();
    const c = (k: keyof Rows) => rows[k].length;
    const open = Object.values(this.s.issues).filter((i) => i.state === "open").length;
    return {
      mode: this.d.cfg.live ? "live" : "dry-run",
      active_runs: plan.active,
      target: plan.target,
      room: plan.room,
      open_issues: open,
      open_prs: Object.values(this.s.prs).filter((p) => p.state === "open").length,
      blocked: c("blocked"),
      started: c("started"),
      ready: c("ready"),
      relaunch: c("relaunch"),
      user: c("user"),
      stopped: c("stopped"),
      recent: c("recent"),
      would_launch_now: plan.picks.map((p) => ({ n: p.n, art: p.art, relaunch: p.relaunch })),
      last_full_sync: this.meta.fullSyncAt ? iso(this.meta.fullSyncAt) : null,
      last_reconcile: this.meta.reconcileAt ? iso(this.meta.reconcileAt) : null,
      last_watchdog: this.meta.watchdogAt ? iso(this.meta.watchdogAt) : null,
      last_tick: this.meta.tickAt ? iso(this.meta.tickAt) : null,
      fresh: this.fresh(),
      counters: this.meta.counters ?? this.zero(),
      last_error: this.meta.lastError ?? null,
      log: this.log.slice(-20),
      ...extra,
    };
  }
}
