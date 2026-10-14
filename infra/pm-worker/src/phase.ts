// Review-Only (指示 130) の数値規則。tools/pm/launch_issues.py の count_open_prs / phase_update と同じ規則にする
// (test/phase_crosscheck.py で固定 JSON を突き合わせる)。
export const PHASE_LOW = 10;
export const PHASE_HIGH = 80;
export const STUCK_LABEL = "oc:stuck";

export interface PhaseState {
  review_only: boolean;
  since?: string;
  open_prs?: number;
}

// open PR の (oc:stuck を除いた数, oc:stuck の数)。
export function countOpenPrs(prs: Array<{ state: string; labels: string[] }>): { openExclStuck: number; stuck: number } {
  let openExclStuck = 0;
  let stuck = 0;
  for (const p of prs) {
    if (p.state !== "open") continue;
    if (p.labels.includes(STUCK_LABEL)) stuck++;
    else openExclStuck++;
  }
  return { openExclStuck, stuck };
}

// 80 を超えたら Review-Only、10 を下回ったら解除、その間は直前の値。
export function nextReviewOnly(prev: boolean, openPrs: number): boolean {
  if (openPrs > PHASE_HIGH) return true;
  if (openPrs < PHASE_LOW) return false;
  return prev;
}
