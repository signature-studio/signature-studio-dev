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

export function validateArtLine(line: string): boolean {
  if (!line.startsWith(ART_PREFIX)) return false;
  if (line.slice(ART_PREFIX.length).trim() === "none") return true;
  const names = line.slice(ART_PREFIX.length).trim().split(/\s+/).filter(Boolean);
  return names.length > 0 && names.every((a) => ALLOW_ARTS.includes(a));
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
  "1. issue 本文と該当 REPORT・過去コメントを読み、**未達の受入条件を特定**してください。",
  "   - 全て達成済みなら、根拠 (PR・commit・実測) をコメントして issue を close してください。",
  "   - 未達があれば、`N-<slug>` ブランチで実装し、PR (--base main) を作成してください。受入条件を全て満たしたときだけ `Closes #N`、部分達成なら `Refs #N` とし、未解決は起票先付きで書いてください。",
  "2. 着手から 10 分以内と、完了・停止時に、必ず `gh issue comment` で結果を投稿してください。60 分で終わらない場合は、その時点の成果を ready の PR にして区切ってください。",
  "   - **1 run (60 分) に収まらないと判断したら、停止せずに分割してください**: 受入条件の一部として最小で完結する単位を選んで実装し、ready の PR で区切る。残りは、重複を `gh api -X GET search/issues` で確認したうえで、子 issue として**自分で起票**する (題名は `[AREA-n]` 形式、本文に `親: #N`・受入条件・必要な `oc_artifacts:` 行を書く)。起票した番号を最終回答と issue コメントに書く。「PM に分割を依頼する」で止まらない。",
  "3. 素材が足りない場合は、必要な `oc_artifacts` 名を報告して停止してください。他の issue に依存することが分かった場合も、その issue 番号を報告して停止してください (PM が blocked_by を設定します)。",
];

// 固定テンプレート。可変なのは素材行だけで、allowlist を通ったものしか入らない。
export function buildLaunchBody(artLine: string): string {
  if (!validateArtLine(artLine)) throw new Error(`invalid artifacts line: ${artLine}`);
  return BODY_LINES.map((l) => (l === "{art}" ? artLine : l)).join("\n") + "\n";
}

export interface ReadyIssue {
  n: number;
  title: string;
  blocksCount: number;
}

// launch_issues.py の並び順: (-被ブロック数, 『任意』を含む, 番号)
export function sortReady(ready: ReadyIssue[]): ReadyIssue[] {
  return [...ready].sort(
    (x, y) =>
      y.blocksCount - x.blocksCount ||
      Number(x.title.includes("任意")) - Number(y.title.includes("任意")) ||
      x.n - y.n,
  );
}

export interface LaunchInput {
  ready: ReadyIssue[];
  relaunch: number[];
  active: number;
  target?: number;
  batch?: number;
}

// 1 tick の枠: room = TARGET - active、枠 = min(room, BATCH, relaunch + ready)。relaunch も枠に入り、残りを ready が使う。
// relaunch は枠 (room・BATCH) を超えても全件出す。枠を ready の件数で頭打ちにする launch_issues.py の式とは、
// relaunch がある tick で最大 relaunch 件だけ差が出る。
// picks = (relaunch + ready)[: max(枠, len(relaunch))]
export function planLaunch(input: LaunchInput): { room: number; picks: number[] } {
  const target = input.target ?? DEFAULT_TARGET;
  const batch = input.batch ?? DEFAULT_BATCH;
  const room = Math.max(0, target - input.active);
  const relaunch = input.relaunch.length;
  const frame = Math.min(room, batch, relaunch + input.ready.length);
  const order = [...input.relaunch, ...sortReady(input.ready).map((r) => r.n)];
  return { room, picks: order.slice(0, Math.max(frame, relaunch)) };
}
