// PM agent (oc-pm) を起こすべき終端状態の検出と、送信の抑止。どちらも純関数 (時刻・保管先は呼び出し側が渡す)。
// 検出に LLM は使わない。自由文は解析しない: ラベル・マーカー・番号の正規表現だけ (needs.ts・refs.ts)。issue / PR の自由文は payload に入れない。
import { effectivePrioMap, PRIO_RANK, prioOf, type Prio } from "./launch.ts";
import { parentNumbers } from "./refs.ts";
import { ASSOC_OK, hasOpenPr, KILLED_STOP_AT, NEEDS_USER_LABEL, prioIssues, type PmState, type PrState } from "./webhook.ts";

// repository_dispatch の event_type "oc-pm" の kind (列挙 9 値)。prepare-event-context.sh の許可リストと同じ。
export const PM_KINDS = ["stuck", "no_pr", "refs_orphan", "needs_decision", "stopped_report", "user_answered", "supply", "digest", "retro"] as const;
export type PmKind = (typeof PM_KINDS)[number];

// この Worker が状態から検出する kind。着手の優先順 (人の回答待ち・PM 判断待ちを先に送る)。
// refs_orphan は [CI-58]、supply は [CI-71] が担当する。stopped_report は停止行 (run-outcome が stop / split) の受け渡し (CI-239・#5722)。
export const DETECTED_KINDS = ["user_answered", "needs_decision", "stuck", "no_pr", "refs_orphan", "stopped_report"] as const;
export type DetectedKind = (typeof DETECTED_KINDS)[number];

// 日次のダイジェスト (CI-70)。状態ではなく時刻で送る。ref は常に 0。内容は PM agent が pm.md の digest 節で集計する。
export const DIGEST_KIND = "digest";
export const DIGEST_REF = 0;
export const DIGEST_EVERY_MS = 24 * 3_600_000;
// rolling issue (題名 `[CI-n] 自律運転ダイジェスト (rolling)`) は本文だけを更新する issue。launch・再投入の対象から外す (classify)。
// tools/pm/launch_issues.py の DIGEST_ROLLING_RE と同じ形にする (test-dispatch-context.sh が題名の一致を検査する)。
export const DIGEST_ROLLING_RE = /^\[[A-Za-z]+-\d+\] 自律運転ダイジェスト \(rolling\)$/;

export const STUCK_LABEL = "oc:stuck";
export const NO_PR_LABEL = "oc:no-pr";
// Worker の自動着手を見送る印 (#2651)。付いた open な issue は classify の hold 行に置き、着手 (picks) も relaunch の意図も投稿しない。
export const OC_HOLD_LABEL = "oc:hold";
// PM の判断待ちの印 (/status の集計だけに使う。検出の対象ではない)。
export const NEEDS_PM_LABEL = "needs-pm";
// 実装 agent が着手しても PR を出さない/出せない issue (pm-apply は PM が PAT で適用する workflow 変更、needs-user-input は依頼者待ち)。
// no_pr の検出・再投入の対象から除く。
export const HOLD_LABELS = ["pm-apply", "needs-user-input"];
export const REF_MAX = 9_999_999;

export interface PmTarget {
  kind: DetectedKind;
  ref: number;
  // 検出の根拠になった時刻 (停止コメント・outcome・review・ユーザーのコメント)
  at: string;
  // 優先の区分 (launch の effectivePrioMap と同じ規則。親からの継承を含む)。送る順の先頭のキー (selectDispatch)。
  prio: Prio;
}

export interface HistoryEntry {
  kind: string;
  ref: number;
  at: number;
  // 送ったときの区分。古い保存値には無いので、参照側で未設定を normal とする。
  prio?: Prio;
}

// 抑止の上限 (同じ (kind, ref) は 60 分に 1 回、全体で 1 時間に 72 起動、同じ ref に 24 時間で 6 回)。
export const PM_LIMITS = { dupMs: 60 * 60_000, hourMs: 3_600_000, hourMax: 72, dayMs: 24 * 3_600_000, refDayMax: 6 };
// 種類ごとの毎時の最低配分 (#3704)。毎時の枠 (PM_LIMITS.hourMax) のうち、その kind に送れる対象がある間は N 件を残す。
// 残した枠は他の kind に使わせない (送れる対象が無い・抑止で送れない分は他の kind に回す)。最低配分より先に送る kind は MIN_EXEMPT_KINDS。
export const KIND_MIN_PER_HOUR: Partial<Record<DetectedKind, number>> = { refs_orphan: 3 };
export const MIN_EXEMPT_KINDS: readonly string[] = ["user_answered"];
// 種類ごとの上限 (PM_LIMITS に加えて効く)。refs_orphan は同じ N に 24 時間 1 回、1 日 24 × 最低配分 (= 72) まで。
// 1 日の上限が最低配分を 24 時間続けられる値。これより小さいと、最低配分は 1 日の上限で途中から止まる (#3704)。
export const KIND_LIMITS: Partial<Record<DetectedKind, { dupMs: number; dayMax: number }>> = {
  refs_orphan: { dupMs: 24 * 3_600_000, dayMax: 24 * (KIND_MIN_PER_HOUR.refs_orphan ?? 0) },
};

// 停止行 (run-outcome の reason が stop / split のまま止まっている issue) を oc-pm の判断キューへ回す上限 (CI-239・#5722)。
// 1 時間に STOPPED_INTAKE_PER_H 件 (config。既定 DEFAULT_STOPPED_INTAKE_PER_H) まで、同じ issue は 24 時間に STOPPED_REF_DAY_MAX 件まで。
// 同じ issue の上限は全体の上限 (PM_LIMITS.refDayMax = 6) より厳しくする (判断済みの停止行を毎時送り続けない)。
// 2026-10-16 の実測: 停止行 511 件 (うち split 333・stop 74 = 407 件) が滞留し、oc-pm の判断の入力に載っていなかった。
// 既定 24/h の根拠: 滞留 407 件でも 1 巡に ~17 時間・oc-pm の全体の枠 (PM_LIMITS.hourMax = 72) に余裕がある。
// 枠が厳しければ wrangler.toml の値を下げる (12 で 1 巡 ~34 時間)。
export const STOPPED_REF_DAY_MAX = 3;
export const DEFAULT_STOPPED_INTAKE_PER_H = 24;
// PM が停止行の判断 (応答) を書いた直後に、同じ停止行をすぐ送り直さない猶予 (CI-239・#5722)。
// no_pr の検出 (未回答のときだけ送る) と stopped_report (応答後も上限まで送る) が同じ行を続けて 2 回送るのを防ぐ。
export const PM_INTAKE_GRACE_MS = 3_600_000;

// 対象の起票者が MEMBER / OWNER / COLLABORATOR か許可 bot か。未設定 (古い保存値) は許可しない。
export function authorAllowed(x: { author?: string; authorType?: string; assoc?: string }, bots: string[]): boolean {
  if (x.assoc && ASSOC_OK.includes(x.assoc)) return true;
  return x.authorType === "Bot" && !!x.author && bots.includes(x.author);
}

export function validPayload(kind: string, ref: number): kind is DetectedKind {
  return (DETECTED_KINDS as readonly string[]).includes(kind) && Number.isInteger(ref) && ref >= 1 && ref <= REF_MAX;
}

export interface DetectOpts {
  bots: string[];
  // いまの時刻 (ms)。停止行 (stopped_report) の応答の猶予 (PM_INTAKE_GRACE_MS) に使う。
  nowMs: number;
  // Worker が oc:no-pr の issue を再投入した回数 (relaunch バケットの np:<n>)
  npCount: (n: number) => number;
  // 新しい素材の無い artifact で、unknown の枠 (再投入 1 回) を使い切ったか、再投入の上限に達したか (#3185。engine が数える。無ければ偽)
  artSpent?: (n: number) => boolean;
}

const t = (s: string | undefined): number => (s ? Date.parse(s) : NaN);
// PM 応答が根拠より後にあるか (厳密に後。同時刻は応答とみなさない)
const answeredAfter = (pmAt: string | undefined, at: string): boolean => !!pmAt && t(pmAt) > t(at);

// PR 起点の区分: PR 自体のラベルと、PR が指す issue の区分 (effectivePrioMap。親からの継承を含む) の高い方 (critical > normal > low)。指す issue は、ブランチ名の先頭の番号・Closes/Refs・本文の #N。
// 引けない issue は数えない (PR 自体のラベルも無ければ normal)。
const prPrio = (s: PmState, p: PrState, prios: Map<number, Prio>): Prio => {
  const head = /^(\d+)-/.exec(p.ref);
  const nums = [...(head ? [Number(head[1])] : []), ...(p.closes ?? []), ...(p.mentions ?? [])];
  const linked = nums.flatMap((n) => (s.issues[String(n)] ? [prios.get(n) ?? "normal"] : []));
  return [prioOf(p.labels ?? []), ...linked].reduce((a, b) => (PRIO_RANK[b] < PRIO_RANK[a] ? b : a));
};

export function detectPm(s: PmState, o: DetectOpts): PmTarget[] {
  const out: PmTarget[] = [];
  const prios = effectivePrioMap(prioIssues(s));
  // open な子 (本文の `親: #N`) を持つ親の集合。refs_orphan と stopped_report (停止行) の両方で使う。
  const parents = new Set<number>();
  for (const i of Object.values(s.issues)) if (i.state === "open") for (const n of parentNumbers(i.body)) parents.add(n);
  for (const p of Object.values(s.prs)) {
    if (p.state !== "open" || !authorAllowed(p, o.bots)) continue;
    const sig = s.sig[String(p.number)];
    if (!sig) continue;
    const prio = prPrio(s, p, prios);
    if (p.labels?.includes(STUCK_LABEL) && sig.stop && sig.stop.intent !== null && !answeredAfter(sig.pmAt, sig.stop.at)) {
      out.push({ kind: "stuck", ref: p.number, at: sig.stop.at, prio });
    }
    if (sig.review?.state === "CHANGES_REQUESTED" && sig.review.needs && !answeredAfter(sig.pmAt, sig.review.at)) {
      out.push({ kind: "needs_decision", ref: p.number, at: sig.review.at, prio });
    }
  }
  for (const i of Object.values(s.issues)) {
    if (i.state !== "open" || !authorAllowed(i, o.bots)) continue;
    const k = String(i.number);
    const sig = s.sig[k];
    if (!sig) continue;
    const oc = sig.outcome;
    const prio = prios.get(i.number) ?? "normal";
    if (i.labels.includes(NO_PR_LABEL) && !i.labels.some((l) => HOLD_LABELS.includes(l)) && oc && !answeredAfter(sig.pmAt, oc.at)) {
      // split / stop は即。unknown は、Worker が再投入した後の run (outcome が最新の launch より後) でも終わった場合だけ。
      // artifact は、新しい素材が無く unknown の枠を使い切った (または上限に達した) 後の run でも終わった場合だけ (新しい素材がある分は Worker が足して 1 回再投入する)。
      const relaunched = o.npCount(i.number) >= 1 && t(oc.at) > t(s.launchedAt[k]);
      const artDone = oc.reason === "artifact" && !!o.artSpent?.(i.number);
      if (oc.reason === "split" || oc.reason === "stop" || (relaunched && (oc.reason === "unknown" || artDone))) {
        out.push({ kind: "no_pr", ref: i.number, at: oc.at, prio });
      }
    }
    // 実装 run が PR も出さずに打ち切られ (cancelled / failure / timed_out) 続けて自動の再着手を止めた issue。oc:no-pr の標識は付かない (runner の shutdown では
    // record-run-outcome.sh が走らない) ので、Worker が数えた sig.kill で検出する。oc:no-pr の検出と重なる issue は 1 回だけ送る。
    const kill = sig.kill;
    if (
      kill &&
      kill.count >= KILLED_STOP_AT &&
      !i.labels.some((l) => HOLD_LABELS.includes(l) || l === STUCK_LABEL) &&
      !answeredAfter(sig.pmAt, kill.at) &&
      !hasOpenPr(s, i.number) &&
      !out.some((x) => x.kind === "no_pr" && x.ref === i.number)
    ) {
      out.push({ kind: "no_pr", ref: i.number, at: kill.at, prio });
    }
    if (i.labels.includes(NEEDS_USER_LABEL) && sig.labelAt && sig.userAt && t(sig.userAt) > t(sig.labelAt) && !answeredAfter(sig.pmAt, sig.userAt)) {
      out.push({ kind: "user_answered", ref: i.number, at: sig.userAt, prio });
    }
    // 停止行 (run-outcome が stop / split のまま止まっている open issue) を oc-pm の判断キューへ回す (CI-239・#5722)。
    // 起点は run-outcome だけ (本文は解析しない)。次は送らない:
    //   - oc:no-pr の no_pr として送る分 (同じ ref を二重に送らない)
    //   - oc:stuck / oc:hold / pm-apply / needs-user-input (人の判断・PM 適用の待ち)
    //   - open PR がある・停止の後に /oc を投稿済み (run が進行中。結果は新しい outcome として届く)
    //   - open な子を持つ親 (子で進める状態で、停止行ではない)
    // PM の応答後も対象に残す (応答が再投入の意図でも、実行されず停止行に残った issue を届け直すため)。
    // ただし応答から PM_INTAKE_GRACE_MS の間は送らない (no_pr の直後の二重送信を防ぐ)。再送の上限は selectDispatch (1 時間・同一 issue 24 時間 3 件)。
    const ocStop = !!oc && (oc.reason === "stop" || oc.reason === "split");
    const answered = !!oc && answeredAfter(sig.pmAt, oc.at);
    if (
      oc &&
      ocStop &&
      !out.some((x) => x.kind === "no_pr" && x.ref === i.number) &&
      !i.labels.some((l) => HOLD_LABELS.includes(l) || l === STUCK_LABEL || l === OC_HOLD_LABEL) &&
      !hasOpenPr(s, i.number) &&
      !parents.has(i.number) &&
      (Date.parse(s.launchedAt[k] ?? "") || 0) <= t(oc.at) &&
      (!answered || o.nowMs - (t(sig.pmAt) || 0) >= PM_INTAKE_GRACE_MS)
    ) {
      out.push({ kind: "stopped_report", ref: i.number, at: oc.at, prio });
    }
  }
  // Refs のみで merge された PR の親 N。N が open で、open の子 (本文の `親: #N`) が無く、起票者が許可対象のとき。
  const orphans = new Set<number>();
  for (const p of Object.values(s.prs)) {
    if (!p.merged || !p.refsOnlyNums?.length) continue;
    for (const n of p.refsOnlyNums) {
      const parent = s.issues[String(n)];
      if (orphans.has(n) || !parent || parent.state !== "open" || parents.has(n) || !authorAllowed(parent, o.bots)) continue;
      orphans.add(n);
      out.push({ kind: "refs_orphan", ref: n, at: p.updatedAt, prio: prios.get(n) ?? "normal" });
    }
  }
  const rank = (k: string): number => (DETECTED_KINDS as readonly string[]).indexOf(k);
  // 停止行 (stopped_report) は停止の古い順 (oldest-first。CI-239・#5722)。他の kind は従来どおり ref の小さい順。
  const isStopped = (x: PmTarget): boolean => x.kind === "stopped_report";
  return out.sort((a, b) => rank(a.kind) - rank(b.kind) || (isStopped(a) && isStopped(b) ? t(a.at) - t(b.at) || a.ref - b.ref : a.ref - b.ref));
}

export type SkipWhy = "dup" | "hour" | "ref" | "kind" | "reserve";

// 送信の上限の上書き (engine が config から渡す。テストは直接渡せる)。省略時は既定 (DEFAULT_STOPPED_INTAKE_PER_H)。
export interface DispatchCaps {
  // 停止行 (stopped_report) を 1 時間に送る件数の上限 (CI-239・#5722)。
  stoppedPerHour?: number;
}

// 送ってよいものを順に選ぶ。選んだものは履歴に加えたものとして次を判定する (1 回の tick で上限を超えない)。
// targets は優先順 (detectPm の戻り値)。
export function selectDispatch(
  now: number,
  targets: PmTarget[],
  history: HistoryEntry[],
  caps: DispatchCaps = {},
): { send: PmTarget[]; skipped: Array<{ kind: string; ref: number; why: SkipWhy }> } {
  const hist = [...history];
  const send: PmTarget[] = [];
  const skipped: Array<{ kind: string; ref: number; why: SkipWhy }> = [];
  const stoppedPerHour = caps.stoppedPerHour ?? DEFAULT_STOPPED_INTAKE_PER_H;
  // 優先の区分 (critical → normal → low) を先頭のキーにする (prio:critical を、古い normal の後ろに回さないように)。
  // 同じ区分の中は、まだ送っていない対象を先に、送った対象は古い順に (毎時の再送が、未送信の対象を枠から押し出さないように)。
  const lastSent = (tg: PmTarget): number => Math.max(0, ...history.filter((h) => h.kind === tg.kind && h.ref === tg.ref).map((h) => h.at));
  const order = new Map(targets.map((tg, i) => [tg, i] as const));
  const ordered = [...targets].sort(
    (a, b) => PRIO_RANK[a.prio] - PRIO_RANK[b.prio] || lastSent(a) - lastSent(b) || (order.get(a) as number) - (order.get(b) as number),
  );
  const within = (ms: number) => hist.filter((h) => now - h.at < ms);
  // 枠以外の抑止 (同じ (kind, ref) の再送・同じ ref の 24 時間の上限・kind の 1 日の上限)。hist は送るたびに増えるだけなので、抑止された対象は同じ tick で送られない。
  const blocked = (tg: PmTarget): SkipWhy | null => {
    // 停止行の受け渡し (stopped_report) は専用の枠を持つ (CI-239・#5722): 1 時間に stoppedPerHour 件・同じ issue は 24 時間に STOPPED_REF_DAY_MAX 件。
    // 専用の枠を使い切った分は他の kind に回さない (判断キューが溢れないように止める。why=hour は毎時の見送りの数に入る)。
    if (tg.kind === "stopped_report") {
      if (within(PM_LIMITS.hourMs).filter((h) => h.kind === tg.kind).length >= stoppedPerHour) return "hour";
      if (within(PM_LIMITS.dayMs).filter((h) => h.kind === tg.kind && h.ref === tg.ref).length >= STOPPED_REF_DAY_MAX) return "kind";
    }
    const kl = KIND_LIMITS[tg.kind];
    if (within(kl?.dupMs ?? PM_LIMITS.dupMs).some((h) => h.kind === tg.kind && h.ref === tg.ref)) return "dup";
    if (within(PM_LIMITS.dayMs).filter((h) => h.ref === tg.ref).length >= PM_LIMITS.refDayMax) return "ref";
    if (kl && within(PM_LIMITS.dayMs).filter((h) => h.kind === tg.kind).length >= kl.dayMax) return "kind";
    return null;
  };
  // 他の kind の最低配分の残り。まだ足りない分 (今の窓での送信数との差) を、後ろにあって今送れる対象の数で頭打ちにする (送れる対象が無ければ予約しない)。
  const reservedFor = (kind: string, idx: number): number => {
    let n = 0;
    for (const [k, min] of Object.entries(KIND_MIN_PER_HOUR)) {
      const owed = (min ?? 0) - within(PM_LIMITS.hourMs).filter((h) => h.kind === k).length;
      if (k === kind || owed <= 0) continue;
      const open = ordered.slice(idx + 1).filter((t) => t.kind === k && !blocked(t)).length;
      n += Math.min(owed, open);
    }
    return n;
  };
  for (let i = 0; i < ordered.length; i++) {
    const tg = ordered[i];
    const cap = blocked(tg);
    let why: SkipWhy | null = null;
    if (cap === "dup") why = "dup";
    else if (within(PM_LIMITS.hourMs).length >= PM_LIMITS.hourMax) why = "hour";
    else if (cap) why = cap;
    else if (!MIN_EXEMPT_KINDS.includes(tg.kind) && within(PM_LIMITS.hourMs).length + 1 + reservedFor(tg.kind, i) > PM_LIMITS.hourMax) why = "reserve";
    if (why) {
      skipped.push({ kind: tg.kind, ref: tg.ref, why });
      continue;
    }
    hist.push({ kind: tg.kind, ref: tg.ref, at: now, prio: tg.prio });
    send.push(tg);
  }
  return { send, skipped };
}

export const pruneHistory = <T extends { at: number }>(now: number, h: T[]): T[] => h.filter((x) => now - x.at < PM_LIMITS.dayMs);

// 毎時上限 (hourMax) で見送った件数。tick ごとに 1 件 (時刻と件数)。pruneHistory と同じ 24 時間の窓で捨てる (#3462)。
export interface SkipEntry {
  at: number;
  n: number;
}
