// PM agent (oc-pm) を起こすべき終端状態の検出と、送信の抑止。どちらも純関数 (時刻・保管先は呼び出し側が渡す)。
// 検出に LLM は使わない。自由文は解析しない: ラベル・マーカー・番号の正規表現だけ (needs.ts・refs.ts)。issue / PR の自由文は payload に入れない。
import { parentNumbers } from "./refs.ts";
import { ASSOC_OK, hasOpenPr, KILLED_STOP_AT, NEEDS_USER_LABEL, type PmState } from "./webhook.ts";

// repository_dispatch の event_type "oc-pm" の kind (列挙 9 値)。prepare-event-context.sh の許可リストと同じ。
export const PM_KINDS = ["stuck", "no_pr", "refs_orphan", "needs_decision", "stopped_report", "user_answered", "supply", "digest", "retro"] as const;
export type PmKind = (typeof PM_KINDS)[number];

// この Worker が状態から検出する kind。着手の優先順 (人の回答待ち・PM 判断待ちを先に送る)。
// refs_orphan は [CI-58]、supply は [CI-71] が担当する。
export const DETECTED_KINDS = ["user_answered", "needs_decision", "stuck", "no_pr", "refs_orphan"] as const;
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
}

export interface HistoryEntry {
  kind: string;
  ref: number;
  at: number;
}

// 抑止の上限 (同じ (kind, ref) は 60 分に 1 回、全体で 1 時間に 12 起動、同じ ref に 24 時間で 3 回)。
export const PM_LIMITS = { dupMs: 60 * 60_000, hourMs: 3_600_000, hourMax: 12, dayMs: 24 * 3_600_000, refDayMax: 3 };
// 種類ごとの上限 (PM_LIMITS に加えて効く)。refs_orphan は同じ N に 24 時間 1 回、1 日 10 件まで。
export const KIND_LIMITS: Partial<Record<DetectedKind, { dupMs: number; dayMax: number }>> = {
  refs_orphan: { dupMs: 24 * 3_600_000, dayMax: 10 },
};

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
  // Worker が oc:no-pr の issue を再投入した回数 (relaunch バケットの np:<n>)
  npCount: (n: number) => number;
}

const t = (s: string | undefined): number => (s ? Date.parse(s) : NaN);
// PM 応答が根拠より後にあるか (厳密に後。同時刻は応答とみなさない)
const answeredAfter = (pmAt: string | undefined, at: string): boolean => !!pmAt && t(pmAt) > t(at);

export function detectPm(s: PmState, o: DetectOpts): PmTarget[] {
  const out: PmTarget[] = [];
  for (const p of Object.values(s.prs)) {
    if (p.state !== "open" || !authorAllowed(p, o.bots)) continue;
    const sig = s.sig[String(p.number)];
    if (!sig) continue;
    if (p.labels?.includes(STUCK_LABEL) && sig.stop && sig.stop.intent !== null && !answeredAfter(sig.pmAt, sig.stop.at)) {
      out.push({ kind: "stuck", ref: p.number, at: sig.stop.at });
    }
    if (sig.review?.state === "CHANGES_REQUESTED" && sig.review.needs && !answeredAfter(sig.pmAt, sig.review.at)) {
      out.push({ kind: "needs_decision", ref: p.number, at: sig.review.at });
    }
  }
  for (const i of Object.values(s.issues)) {
    if (i.state !== "open" || !authorAllowed(i, o.bots)) continue;
    const k = String(i.number);
    const sig = s.sig[k];
    if (!sig) continue;
    const oc = sig.outcome;
    if (i.labels.includes(NO_PR_LABEL) && !i.labels.some((l) => HOLD_LABELS.includes(l)) && oc && !answeredAfter(sig.pmAt, oc.at)) {
      // split / stop は即。unknown は、Worker が再投入した後の run (outcome が最新の launch より後) でも終わった場合だけ。
      const relaunched = o.npCount(i.number) >= 1 && t(oc.at) > t(s.launchedAt[k]);
      if (oc.reason === "split" || oc.reason === "stop" || (oc.reason === "unknown" && relaunched)) {
        out.push({ kind: "no_pr", ref: i.number, at: oc.at });
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
      out.push({ kind: "no_pr", ref: i.number, at: kill.at });
    }
    if (i.labels.includes(NEEDS_USER_LABEL) && sig.labelAt && sig.userAt && t(sig.userAt) > t(sig.labelAt) && !answeredAfter(sig.pmAt, sig.userAt)) {
      out.push({ kind: "user_answered", ref: i.number, at: sig.userAt });
    }
  }
  // Refs のみで merge された PR の親 N。N が open で、open の子 (本文の `親: #N`) が無く、起票者が許可対象のとき。
  const parents = new Set<number>();
  for (const i of Object.values(s.issues)) if (i.state === "open") for (const n of parentNumbers(i.body)) parents.add(n);
  const orphans = new Set<number>();
  for (const p of Object.values(s.prs)) {
    if (!p.merged || !p.refsOnlyNums?.length) continue;
    for (const n of p.refsOnlyNums) {
      const parent = s.issues[String(n)];
      if (orphans.has(n) || !parent || parent.state !== "open" || parents.has(n) || !authorAllowed(parent, o.bots)) continue;
      orphans.add(n);
      out.push({ kind: "refs_orphan", ref: n, at: p.updatedAt });
    }
  }
  const rank = (k: string): number => (DETECTED_KINDS as readonly string[]).indexOf(k);
  return out.sort((a, b) => rank(a.kind) - rank(b.kind) || a.ref - b.ref);
}

export type SkipWhy = "dup" | "hour" | "ref" | "kind";

// 送ってよいものを順に選ぶ。選んだものは履歴に加えたものとして次を判定する (1 回の tick で上限を超えない)。
// targets は優先順 (detectPm の戻り値)。
export function selectDispatch(
  now: number,
  targets: PmTarget[],
  history: HistoryEntry[],
): { send: PmTarget[]; skipped: Array<{ kind: string; ref: number; why: SkipWhy }> } {
  const hist = [...history];
  const send: PmTarget[] = [];
  const skipped: Array<{ kind: string; ref: number; why: SkipWhy }> = [];
  // まだ送っていない対象を先に、送った対象は古い順に (毎時の再送が、未送信の対象を枠から押し出さないように)。
  const lastSent = (tg: PmTarget): number => Math.max(0, ...history.filter((h) => h.kind === tg.kind && h.ref === tg.ref).map((h) => h.at));
  const order = new Map(targets.map((tg, i) => [tg, i] as const));
  const ordered = [...targets].sort((a, b) => lastSent(a) - lastSent(b) || (order.get(a) as number) - (order.get(b) as number));
  for (const tg of ordered) {
    const within = (ms: number) => hist.filter((h) => now - h.at < ms);
    const kl = KIND_LIMITS[tg.kind];
    let why: SkipWhy | null = null;
    if (within(kl?.dupMs ?? PM_LIMITS.dupMs).some((h) => h.kind === tg.kind && h.ref === tg.ref)) why = "dup";
    else if (within(PM_LIMITS.hourMs).length >= PM_LIMITS.hourMax) why = "hour";
    else if (within(PM_LIMITS.dayMs).filter((h) => h.ref === tg.ref).length >= PM_LIMITS.refDayMax) why = "ref";
    else if (kl && within(PM_LIMITS.dayMs).filter((h) => h.kind === tg.kind).length >= kl.dayMax) why = "kind";
    if (why) {
      skipped.push({ kind: tg.kind, ref: tg.ref, why });
      continue;
    }
    hist.push({ kind: tg.kind, ref: tg.ref, at: now });
    send.push(tg);
  }
  return { send, skipped };
}

export const pruneHistory = (now: number, h: HistoryEntry[]): HistoryEntry[] => h.filter((x) => now - x.at < PM_LIMITS.dayMs);
