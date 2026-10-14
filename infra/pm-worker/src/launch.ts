// tools/pm/launch_issues.py の規則の移植 (純関数のみ。GitHub へは書き込まない)。

export const DEFAULT_TARGET = 50;
export const DEFAULT_BATCH = 25;

// launch_issues.py の ALLOW_ARTS と同じ並び・同じ中身。
export const ALLOW_ARTS: readonly string[] = [
  "fl-win64", "plugins-ott", "plugins-freshair", "plugins-serum2", "plugins-massivex", "plugins-kilohearts",
  "toolchain-retdec", "toolchain-emsdk", "work-m11", "work-liftdiff", "work-m6-ott", "work-liftlib-targets",
  "work-liftlib", "work-icall", "work-fw-stage1", "analysis-ott-binaries", "analysis-mac-shared", "apt-mingw",
];

const ART_PREFIX = "oc_artifacts:";

// 空白区切りの素材名が、すべて allowlist に入っていて 1 つ以上ある。
export function artsAllowed(names: string): boolean {
  const xs = names.trim().split(/\s+/).filter(Boolean);
  return xs.length > 0 && xs.every((a) => ALLOW_ARTS.includes(a));
}

export function validateArtLine(line: string): boolean {
  if (!line.startsWith(ART_PREFIX)) return false;
  if (line.slice(ART_PREFIX.length).trim() === "none") return true;
  return artsAllowed(line.slice(ART_PREFIX.length));
}

export function inferArtifacts(title: string, labels: string[]): string {
  const t = (title + " " + labels.join(" ")).toLowerCase();
  const a = ["fl-win64", "toolchain-retdec", "toolchain-emsdk"];
  const add = (...xs: string[]) => {
    for (const x of xs) if (!a.includes(x)) a.push(x);
  };
  if (t.includes("serum") || t.includes("sr-")) add("plugins-serum2");
  if (t.includes("massive") || t.includes("mx-")) add("plugins-massivex");
  if (t.includes("kilohearts") || t.includes("kh-")) add("plugins-kilohearts");
  if (t.includes("freshair") || t.includes("fresh air") || t.includes("fa-")) add("plugins-freshair");
  if (t.includes("ott")) add("plugins-ott", "analysis-ott-binaries", "work-m6-ott", "work-liftlib");
  if (/m11|fle-|boot|startup|survey|ld-|liftdiff/.test(t)) add("work-m11", "work-liftdiff");
  if (/liftlib|icall|ipp/.test(t)) add("work-liftlib", "work-icall");
  if (/gui|shim/.test(t)) add("apt-mingw");
  if (/plg-/.test(t)) add("work-fw-stage1", "work-liftlib", "plugins-ott");
  if (/t-sh-1[2-6]|mac|dylib|libkio|beat_tracker|ildsp|libreverb|directwave/.test(t)) add("analysis-mac-shared");
  return ART_PREFIX + " " + a.join(" ");
}

const BODY_LINES = [
  "/oc oc_actions_allow_write",
  "{art}",
  "PM が着手を依頼します (1 issue = 1 run)。この issue は、ブロックしている open な issue が無く、未着手です。",
  "{focus}",
  "1. issue 本文と該当 REPORT・過去コメントを読み、**未達の受入条件を特定**してください。",
  "   - 全て達成済みなら、根拠 (PR・commit・実測) をコメントして issue を close してください。",
  "   - 未達があれば、`N-<slug>` ブランチで実装し、PR (--base main) を作成してください。受入条件を全て満たしたときだけ `Closes #N`、部分達成なら `Refs #N` とし、未解決は起票先付きで書いてください。",
  "2. 着手から 10 分以内と、完了・停止時に、必ず `gh issue comment` で結果を投稿してください。60 分で終わらない場合は、その時点の成果を ready の PR にして区切ってください。",
  "   - **1 run (60 分) に収まらないと判断したら、停止せずに分割してください**: 受入条件の一部として最小で完結する単位を選んで実装し、ready の PR で区切る。残りは、重複を `gh api -X GET search/issues` で確認したうえで、子 issue として**自分で起票**する (題名は `[AREA-n]` 形式、本文に `親: #N`・受入条件・必要な `oc_artifacts:` 行を書く)。起票した番号を最終回答と issue コメントに書く。「PM に分割を依頼する」で止まらない。",
  "3. 素材が足りない場合は、必要な `oc_artifacts` 名を報告して停止してください。他の issue に依存することが分かった場合も、その issue 番号を報告して停止してください (PM が blocked_by を設定します)。",
];

// 固定テンプレート。可変なのは素材行と focus (受入条件の番号 1〜9) だけで、allowlist を通ったものと数字しか入らない。
export function buildLaunchBody(artLine: string, focus?: number): string {
  if (!validateArtLine(artLine)) throw new Error(`invalid artifacts line: ${artLine}`);
  if (focus !== undefined && !(Number.isInteger(focus) && focus >= 1 && focus <= 9)) throw new Error(`invalid focus: ${focus}`);
  const focusLine = `この issue の受入条件 ${focus} だけを実装して PR を出してください。他の条件は子 issue にしてください。`;
  return BODY_LINES.flatMap((l) => (l === "{focus}" ? (focus === undefined ? [] : [focusLine]) : [l === "{art}" ? artLine : l])).join("\n") + "\n";
}

// PM の再投入の意図 (<!-- oc-pm-intent: relaunch issue=N arts="..." focus=K -->) を、Worker が /oc として投稿してよいか。
// bot: コメントの書き手が実装 App か。issue: マーカーの issue=、arts: 素材名の並び、focus: 生の字句 (無ければ null)。
export interface RelaunchIntent {
  bot: boolean;
  issue: string;
  arts: string;
  focus: string | null;
}
export type IntentReject = "author" | "issue" | "arts" | "focus" | "limit";
export const RELAUNCH_WINDOW_MS = 24 * 3_600_000;
export const RELAUNCH_MAX_PER_WINDOW = 3;

// executedMs は、同じ issue に実際に投稿した時刻 (ms)。窓 (24 時間) の中の件数が上限に達していたら拒否する。
export function checkRelaunchIntent(
  n: number,
  r: RelaunchIntent,
  executedMs: number[],
  nowMs: number,
): { ok: true; art: string; focus?: number } | { ok: false; reason: IntentReject } {
  if (!r.bot) return { ok: false, reason: "author" };
  if (r.issue !== String(n)) return { ok: false, reason: "issue" };
  if (!artsAllowed(r.arts)) return { ok: false, reason: "arts" };
  if (r.focus !== null && !/^[1-9]$/.test(r.focus)) return { ok: false, reason: "focus" };
  if (executedMs.filter((t) => nowMs - t < RELAUNCH_WINDOW_MS).length >= RELAUNCH_MAX_PER_WINDOW) return { ok: false, reason: "limit" };
  const art = ART_PREFIX + " " + r.arts.trim().split(/\s+/).join(" ");
  return { ok: true, art, ...(r.focus === null ? {} : { focus: Number(r.focus) }) };
}

export type Prio = "critical" | "normal" | "low";
const PRIO_RANK: Record<Prio, number> = { critical: 0, normal: 1, low: 2 };

// 優先の区分。prio:critical が付いていれば critical、prio:low なら low、どちらも無ければ normal (両方付いたら高い方)。
export function prioOf(labels: string[]): Prio {
  if (labels.includes("prio:critical")) return "critical";
  if (labels.includes("prio:low")) return "low";
  return "normal";
}

export interface ReadyIssue {
  n: number;
  title: string;
  blocksCount: number;
  labels?: string[];
}

// 並び順: 区分 (critical → normal → low) が先。同じ区分の中は launch_issues.py の並び順: (-被ブロック数, 『任意』を含む, 番号)
export function sortReady(ready: ReadyIssue[]): ReadyIssue[] {
  return [...ready].sort(
    (x, y) =>
      PRIO_RANK[prioOf(x.labels ?? [])] - PRIO_RANK[prioOf(y.labels ?? [])] ||
      y.blocksCount - x.blocksCount ||
      Number(x.title.includes("任意")) - Number(y.title.includes("任意")) ||
      x.n - y.n,
  );
}

// oc:no-pr の再着手までの間隔 (ms)。prio:critical は半分にして、臨界経路の再投入を早める。
export function noPrCooldownMs(labels: string[], cooldownH: number): number {
  const ms = cooldownH * 3_600_000;
  return prioOf(labels) === "critical" ? ms / 2 : ms;
}

// prio:low の同時実行の上限 (LOW_CAP)。applied は『着手済みか launch 可能で blocked でない prio:critical が 1 件以上ある』ときだけ真 (engine が決める)。
// 真の間は、未完了の prio:low の run (running) を数えて、新しい prio:low の launch を cap までに抑える。実行中の run は止めない。
export interface LowCap {
  cap: number;
  running: number;
  applied: boolean;
}

// 新しく launch してよい prio:low の残り。上限が効かないときは無限。
export function lowAllowance(low: LowCap): number {
  return low.applied ? Math.max(0, low.cap - low.running) : Infinity;
}

export interface LaunchInput {
  ready: ReadyIssue[];
  relaunch: number[];
  active: number;
  target?: number;
  batch?: number;
  low?: LowCap & { isLow: (n: number) => boolean };
}

// 1 tick の枠: room = TARGET - active、枠 = min(room, BATCH, relaunch + ready)。relaunch も枠に入り、残りを ready が使う。
// relaunch は枠 (room・BATCH) を超えても全件出す。枠を ready の件数で頭打ちにする launch_issues.py の式とは、
// relaunch がある tick で最大 relaunch 件だけ差が出る。
// picks = (relaunch + ready)[: max(枠, len(relaunch))]。prio:low の上限 (low) に達した分は、枠に入る前に落とす (並びの末尾なので他を遊ばせない)。
export function planLaunch(input: LaunchInput): { room: number; picks: number[] } {
  const target = input.target ?? DEFAULT_TARGET;
  const batch = input.batch ?? DEFAULT_BATCH;
  const room = Math.max(0, target - input.active);
  let left = input.low ? lowAllowance(input.low) : Infinity;
  const admit = (n: number): boolean => {
    if (!input.low?.isLow(n)) return true;
    if (left <= 0) return false;
    left--;
    return true;
  };
  const relaunch = input.relaunch.filter(admit);
  const ready = sortReady(input.ready).map((r) => r.n).filter(admit);
  const frame = Math.min(room, batch, relaunch.length + ready.length);
  return { room, picks: [...relaunch, ...ready].slice(0, Math.max(frame, relaunch.length)) };
}
