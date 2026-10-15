// 着手を保留している issue の理由と解除見込み (#5110)。観測のみ (launch・dispatch・no-PR 再投入の判断には使わない)。
// 理由の語は classify.ts の rows の行名と engine.ts の再投入判断の note に対応させる。解除見込みは時間ベースの窓だけ。

import { BOT_COMMENT_WINDOW_H, RUN_WINDOW_H } from "./classify.ts";

const H = 3_600_000;

export interface HoldTimes {
  botAt?: number;
  launchedAt?: number;
  doneAt?: number;
  lastAct?: number;
  cooldownMs?: number;
}

export interface Hold {
  n: number;
  row: string;
  reason: string;
  // 時間で解除される見込み時刻 (ISO)。窓が時間で閉じないもの (他 issue・人・PM の判断待ち) は null。
  until: string | null;
}

// recent の行 (classify.ts の rows.recent と engine.ts の oc:no-pr cooldown) の理由と解除見込み。
export function recentHold(n: number, note: string, t: HoldTimes): Hold {
  const iso = (ms: number | null) => (ms === null ? null : new Date(ms).toISOString());
  const at = (base: number | undefined, h: number) => (base === undefined ? null : base + h * H);
  if (note.startsWith("bot comment")) return { n, row: "recent", reason: "bot-comment", until: iso(at(t.botAt, BOT_COMMENT_WINDOW_H)) };
  if (note.startsWith("launch not observed")) return { n, row: "recent", reason: "launch-not-observed", until: null };
  if (note.startsWith("run finished")) return { n, row: "recent", reason: "run-finished", until: iso(at(t.doneAt, RUN_WINDOW_H)) };
  if (note.startsWith("launched ")) return { n, row: "recent", reason: "launched", until: iso(at(t.launchedAt, RUN_WINDOW_H)) };
  if (note === "oc:no-pr cooldown") return { n, row: "recent", reason: "oc:no-pr cooldown", until: iso(t.lastAct === undefined || t.cooldownMs === undefined ? null : t.lastAct + t.cooldownMs) };
  return { n, row: "recent", reason: "recent", until: null };
}

// stopped の行の理由。本文の抜粋は出さない。既知の語以外は bot の報告による停止 (bot-report) とする。
export function stoppedHold(n: number, note: string): Hold {
  const reason = note.startsWith("oc:no-pr") ? "oc:no-pr"
    : note.startsWith("artifact:") ? "artifact"
    : note.startsWith("killed x") ? "killed"
    : note === "parent/stuck" ? "parent-or-stuck"
    : note === "launch-unobserved" ? "launch-unobserved"
    : note === "stop" || note === "split" ? note
    : "bot-report";
  return { n, row: "stopped", reason, until: null };
}
