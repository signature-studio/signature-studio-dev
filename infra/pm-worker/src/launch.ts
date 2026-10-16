// tools/pm/launch_issues.py の規則の移植 (純関数のみ。GitHub へは書き込まない)。
import { parentOf } from "./refs.ts";

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

// issue 本文の素材行を読む先頭の字数 (#2758)。これより後ろの行は見ない。
export const BODY_ART_CHARS = 4000;
const BODY_ART_RE = /^\s*`?(oc_artifacts:[^`]*)`?\s*$/;

// 素材名の並びに fl-win64 を先頭から補う (既に有れば位置はそのまま)。既定で取得されるのは fl-win64 のみ。
const withFlWin64 = (names: string[]): string[] => (names.includes("fl-win64") ? names : ["fl-win64", ...names]);

// issue 本文の先頭 BODY_ART_CHARS 字の、最後の oc_artifacts: 行を検証済みの 1 行にする。
// allowlist 外の名前は落とし、残りが 1 つ以上ならその行を返す。残りが 0 なら null (呼び出し側は推定に戻る)。
// `oc_artifacts: none` は単独の行のときだけ有効 (validateArtLine と同じ)。最後の行だけを見る (前の行には戻らない)。
// 字数で切った境界をまたぐ行 (改行で終わっていない末尾の行) は見ない。
// fl-win64 が無ければ先頭に補う (addArts と同じ。本文の行が素材を明示していないときも既定の fl-win64 を取る)。
export function bodyArtLine(body: string): string | null {
  const chars = Array.from(body ?? "");
  const lines = chars.slice(0, BODY_ART_CHARS).join("").split(/\r\n|\r|\n/);
  if (chars.length > BODY_ART_CHARS) lines.pop();
  let last: string | null = null;
  for (const l of lines) {
    const m = BODY_ART_RE.exec(l);
    if (m) last = m[1];
  }
  if (last === null) return null;
  const names = last.slice(ART_PREFIX.length).trim().split(/\s+/).filter(Boolean);
  if (names.length === 1 && names[0] === "none") return ART_PREFIX + " none";
  const keep = [...new Set(names.filter((a) => ALLOW_ARTS.includes(a)))];
  if (keep.length === 0) return null;
  const line = ART_PREFIX + " " + withFlWin64(keep).join(" ");
  return validateArtLine(line) ? line : null;
}

// 素材行 line に、allowlist 内の素材名 extra のうち、まだ無いものを足した行 (足すものが無ければ null)。
// `none` は素材 0 件とみなして外す (none と他の名前は混在できない)。足すときは fl-win64 を先頭に補う (既定で取得されるのは fl-win64 のみ)。
// extra に fl-win64 があって line に無い場合も、補った先頭と足す分で二重にしない (重複は除く)。
export function addArts(line: string, extra: string[]): string | null {
  const names = line.replace(ART_PREFIX, "").trim().split(/\s+/).filter((a) => a && a !== "none");
  const add = extra.filter((a) => ALLOW_ARTS.includes(a) && !names.includes(a));
  if (add.length === 0) return null;
  const out = ART_PREFIX + " " + [...new Set([...withFlWin64(names), ...add])].join(" ");
  return validateArtLine(out) ? out : null;
}

const artNames = (line: string): string[] => line.slice(ART_PREFIX.length).trim().split(/\s+/).filter((a) => a && a !== "none");

// launch の素材行の既定: PM の行 (検証済み) と issue 本文の行 (検証済み) の素材名の和集合 → 題名・ラベルからの推定。
// 名前を持つ行が 1 つだけならその行をそのまま返す。両方が名前を持つときは PM の行の名前の後に本文の行の名前を並べ、fl-win64 を先頭に補う。
// none は名前を持たない側とみなす (両方 none なら none)。pm_art の保存値は書き換えず、読み出し側でだけ和集合を作る (#3050)。
export function defaultArtLine(pmLine: string | null | undefined, bodyLine: string | null | undefined, title: string, labels: string[]): string {
  const lines = [pmLine, bodyLine].filter((l): l is string => !!l && validateArtLine(l));
  if (lines.length === 0) return inferArtifacts(title, labels);
  const named = lines.filter((l) => artNames(l).length > 0);
  if (named.length === 0) return ART_PREFIX + " none";
  if (named.length === 1) return named[0];
  return ART_PREFIX + " " + withFlWin64([...new Set(named.flatMap((l) => artNames(l)))]).join(" ");
}

const BODY_LINES = [
  "/oc oc_actions_allow_write",
  "{art}",
  "PM が着手を依頼します (1 issue = 1 run)。この issue は、ブロックしている open な issue が無く、未着手です。",
  "{recheck}",
  "{focus}",
  "1. issue 本文と該当 REPORT・過去コメントを読み、**未達の受入条件を特定**してください。",
  "   - 全て達成済みなら、根拠 (PR・commit・実測) をコメントして issue を close してください。",
  "   - 未達があれば、`N-<slug>` ブランチで実装し、PR (--base main) を作成してください。受入条件を全て満たしたときだけ `Closes #N`、部分達成なら `Refs #N` とし、未解決は起票先付きで書いてください。",
  "2. 着手から 10 分以内と、完了・停止時に、必ず `gh issue comment` で結果を投稿してください。60 分で終わらない場合は、その時点の成果を ready の PR にして区切ってください。",
  "   - **1 run (60 分) に収まらないと判断したら、停止せずに分割してください**: 受入条件の一部として最小で完結する単位を選んで実装し、ready の PR で区切る。残りは、重複を `gh api -X GET search/issues` で確認したうえで、子 issue として**自分で起票**する (題名は `[AREA-n]` 形式、本文に `親: #N`・受入条件・必要な `oc_artifacts:` 行を書く)。起票した番号を最終回答と issue コメントに書く。「PM に分割を依頼する」で止まらない。",
  "3. 素材が足りない場合は、必要な `oc_artifacts` 名を報告して停止してください。他の issue に依存することが分かった場合も、その issue 番号を報告して停止してください (PM が blocked_by を設定します)。",
];

// 新しい素材の無い artifact の再投入 (#3185) だけに足す。前回の停止の理由が素材不足でない可能性がある。
const RECHECK_LINE = "前回の停止の理由を再確認し、素材が足りない以外の理由 (分割要・依存・判断待ち) なら、その種類の手順に従ってください。";
// 固定テンプレート。可変なのは素材行と focus (受入条件の番号 1〜9) だけで、allowlist を通ったものと数字しか入らない。
export function buildLaunchBody(artLine: string, focus?: number, recheck = false): string {
  if (!validateArtLine(artLine)) throw new Error(`invalid artifacts line: ${artLine}`);
  if (focus !== undefined && !(Number.isInteger(focus) && focus >= 1 && focus <= 9)) throw new Error(`invalid focus: ${focus}`);
  const focusLine = `この issue の受入条件 ${focus} だけを実装して PR を出してください。他の条件は子 issue にしてください。`;
  return (
    BODY_LINES.flatMap((l) => {
      if (l === "{focus}") return focus === undefined ? [] : [focusLine];
      if (l === "{recheck}") return recheck ? [RECHECK_LINE] : [];
      return [l === "{art}" ? artLine : l];
    }).join("\n") + "\n"
  );
}

// PM の再投入の意図 (<!-- oc-pm-intent: relaunch issue=N arts="..." focus=K -->) を、Worker が /oc として投稿してよいか。
// 書き手の区分 (author): impl = 実装 App、pm = PM App (oc-pm の run の identity。#5146 以降の PM agent)、other = 第三者 (拒否する)。
// 2026-10-16 の実測 (#5722): #5146 で oc-pm の投稿が実装 App から PM App に変わり、PM の意図が author で全件拒否されていた (counters.intentRejected.author = 70)。
export type RelaunchAuthor = "impl" | "pm" | "other";
// 保存値の互換: 旧版 (#5146 まで) の値は bot (実装 App の投稿か) だけを持つ。author が無ければ bot=true を impl とし、それ以外は other (第三者と同じ扱い)。
export const relaunchAuthorOf = (r: { author?: RelaunchAuthor; bot?: boolean }): RelaunchAuthor => r.author ?? (r.bot ? "impl" : "other");
export interface RelaunchIntent {
  author?: RelaunchAuthor;
  // 旧版の保存値だけが持つ (author が無いときの互換に使う)。
  bot?: boolean;
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
  if (relaunchAuthorOf(r) === "other") return { ok: false, reason: "author" };
  if (r.issue !== String(n)) return { ok: false, reason: "issue" };
  if (!artsAllowed(r.arts)) return { ok: false, reason: "arts" };
  if (r.focus !== null && !/^[1-9]$/.test(r.focus)) return { ok: false, reason: "focus" };
  if (executedMs.filter((t) => nowMs - t < RELAUNCH_WINDOW_MS).length >= RELAUNCH_MAX_PER_WINDOW) return { ok: false, reason: "limit" };
  const art = ART_PREFIX + " " + r.arts.trim().split(/\s+/).join(" ");
  return { ok: true, art, ...(r.focus === null ? {} : { focus: Number(r.focus) }) };
}

export type Prio = "critical" | "normal" | "low";
export const PRIO_RANK: Record<Prio, number> = { critical: 0, normal: 1, low: 2 };

// 優先の区分。prio:critical が付いていれば critical、prio:low なら low、どちらも無ければ normal (両方付いたら高い方)。
// 自身のラベルだけを見る。親からの継承を含む区分は effectivePrioMap を使う (#3973)。
export function prioOf(labels: string[]): Prio {
  if (labels.includes("prio:critical")) return "critical";
  if (labels.includes("prio:low")) return "low";
  return "normal";
}

// 自身のラベルに明示された区分 (無ければ null)。両方付いたら critical (prioOf と同じ)。
const explicitPrio = (labels: string[]): Prio | null => (labels.includes("prio:critical") ? "critical" : labels.includes("prio:low") ? "low" : null);

export interface PrioIssue {
  number: number;
  state: "open" | "closed";
  labels: string[];
  body: string;
  // GitHub の sub-issue の親 (sub_issues の webhook で取り込んだ番号。取り込めていなければ未設定 = 継承しない)。本文の『親: #N』が優先 (#3989)。
  subParent?: number | null;
}

// 親の番号: 本文の『親: #N』を優先し、無ければ sub-issue の親。どちらも無ければ null。
const parentNoOf = (i: PrioIssue): number | null => parentOf(i.body) ?? i.subParent ?? null;

// 親 (番号 p) が open の issue として引けるときだけその issue を返す。無い・closed・自己参照なら null。
function openParentOf(i: PrioIssue, byNo: Map<number, PrioIssue>): PrioIssue | null {
  const p = parentNoOf(i);
  if (p === null || p === i.number) return null;
  const parent = byNo.get(p);
  return parent?.state === "open" ? parent : null;
}

// 自身に明示の区分が無い issue の継承 (#3973)。親に明示の区分があればそれ (critical だけ継承し、low は継承しない)。
// 親に明示の区分が無ければ、親の親 (open) の明示が prio:critical のときだけ critical。それより上はたどらない。
function inheritedPrio(i: PrioIssue, byNo: Map<number, PrioIssue>): Prio {
  const parent = openParentOf(i, byNo);
  if (!parent) return "normal";
  const p = explicitPrio(parent.labels);
  if (p !== null) return p === "critical" ? "critical" : "normal";
  const grand = openParentOf(parent, byNo);
  return grand && explicitPrio(grand.labels) === "critical" ? "critical" : "normal";
}

// 区分の実効値 (#3973)。自身の明示の区分があればそれ。無ければ親 (open) からの継承 (inheritedPrio)。
// closed・無い・自己参照・循環の親からは継承しない (normal)。issues は closed も含めて渡してよい (親の状態を見る)。
export function effectivePrioMap(issues: Iterable<PrioIssue>): Map<number, Prio> {
  const byNo = new Map([...issues].map((i) => [i.number, i] as const));
  const out = new Map<number, Prio>();
  for (const i of byNo.values()) out.set(i.number, explicitPrio(i.labels) ?? inheritedPrio(i, byNo));
  return out;
}

export interface ReadyIssue {
  n: number;
  title: string;
  blocksCount: number;
  // 区分 (effectivePrioMap の値)。無ければ labels の明示だけを見る。
  prio?: Prio;
  labels?: string[];
}

// 並び順: 区分 (critical → normal → low) が先。同じ区分の中は launch_issues.py の並び順: (-被ブロック数, 『任意』を含む, 番号)
export function sortReady(ready: ReadyIssue[]): ReadyIssue[] {
  return [...ready].sort(
    (x, y) =>
      PRIO_RANK[x.prio ?? prioOf(x.labels ?? [])] - PRIO_RANK[y.prio ?? prioOf(y.labels ?? [])] ||
      y.blocksCount - x.blocksCount ||
      Number(x.title.includes("任意")) - Number(y.title.includes("任意")) ||
      x.n - y.n,
  );
}

// oc:no-pr の再着手までの間隔 (ms)。prio:critical は半分にして、臨界経路の再投入を早める。
export function noPrCooldownMs(prio: Prio, cooldownH: number): number {
  const ms = cooldownH * 3_600_000;
  return prio === "critical" ? ms / 2 : ms;
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
// held は着手待ち (ready) で今回は選ばれなかった issue と理由。low-cap = LOW_CAP で落ちた / room・batch = 枠 (TARGET − active)・BATCH で落ちた。
export function planLaunch(input: LaunchInput): { room: number; picks: number[]; held: { n: number; why: "low-cap" | "room" | "batch" }[] } {
  const target = input.target ?? DEFAULT_TARGET;
  const batch = input.batch ?? DEFAULT_BATCH;
  const room = Math.max(0, target - input.active);
  let left = input.low ? lowAllowance(input.low) : Infinity;
  const lowDropped = new Set<number>();
  const admit = (n: number): boolean => {
    if (!input.low?.isLow(n)) return true;
    if (left <= 0) {
      lowDropped.add(n);
      return false;
    }
    left--;
    return true;
  };
  const relaunch = input.relaunch.filter(admit);
  const readyOrder = sortReady(input.ready).map((r) => r.n);
  const ready = readyOrder.filter(admit);
  const frame = Math.min(room, batch, relaunch.length + ready.length);
  const picks = [...relaunch, ...ready].slice(0, Math.max(frame, relaunch.length));
  const picked = new Set(picks);
  const held = readyOrder.filter((n) => !picked.has(n)).map((n) => ({ n, why: lowDropped.has(n) ? ("low-cap" as const) : room < batch ? ("room" as const) : ("batch" as const) }));
  return { room, picks, held };
}
