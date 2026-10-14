import { configuredApp, send, T0 } from "./helpers.ts";
import { REPO } from "./helpers.ts";

export const REVIEWER = "oc-reviewer-for-signature-studio[bot]";
export const IMPL = "opencode-for-signature-studio[bot]";
export type Ctx = Awaited<ReturnType<typeof configuredApp>>;

export interface Author {
  login: string;
  type: string;
  assoc: string;
}
export const HUMAN: Author = { login: "pycabbage", type: "User", assoc: "OWNER" };
export const OUTSIDER: Author = { login: "stranger", type: "User", assoc: "NONE" };
export const IMPL_BOT: Author = { login: IMPL, type: "Bot", assoc: "NONE" };
export const EVIL_BOT: Author = { login: "evil-app[bot]", type: "Bot", assoc: "NONE" };

export const iso = (ms: number): string => new Date(ms).toISOString();

export const issueEv = (
  n: number,
  o: { labels?: string[]; author?: Author; at?: string; action?: string; label?: string; title?: string; body?: string; state?: string } = {},
) => {
  const a = o.author ?? HUMAN;
  return {
    action: o.action ?? "opened",
    repository: REPO,
    ...(o.label ? { label: { name: o.label } } : {}),
    issue: {
      number: n,
      title: o.title ?? `[CI-${n}] t`,
      body: o.body ?? "",
      state: o.state ?? "open",
      updated_at: o.at ?? "2026-10-14T11:00:00Z",
      labels: (o.labels ?? []).map((name) => ({ name })),
      user: { login: a.login, type: a.type },
      author_association: a.assoc,
      issue_dependencies_summary: { total_blocked_by: 0 },
    },
  };
};

export const prEv = (n: number, o: { labels?: string[]; author?: Author; at?: string; title?: string; body?: string } = {}) => {
  const a = o.author ?? IMPL_BOT;
  return {
    action: "opened",
    repository: REPO,
    pull_request: {
      number: n,
      state: "open",
      merged_at: null,
      draft: false,
      head: { ref: `${n}-x` },
      title: o.title ?? `pr ${n}`,
      body: o.body ?? "",
      updated_at: o.at ?? "2026-10-14T11:00:00Z",
      labels: (o.labels ?? []).map((name) => ({ name })),
      user: { login: a.login, type: a.type },
      author_association: a.assoc,
    },
  };
};

export const commentEv = (n: number, who: { login: string; type?: string }, body: string, at: string, isPr = false) => ({
  action: "created",
  repository: REPO,
  issue: isPr ? { number: n, pull_request: {} } : { number: n },
  comment: { user: { login: who.login, type: who.type ?? (who.login.endsWith("[bot]") ? "Bot" : "User") }, body, created_at: at },
});

export const reviewEv = (n: number, body: string, at: string, o: { state?: string; login?: string; action?: string } = {}) => ({
  action: o.action ?? "submitted",
  repository: REPO,
  pull_request: { ...prEv(n).pull_request, updated_at: at },
  review: { user: { login: o.login ?? REVIEWER }, state: o.state ?? "changes_requested", body, submitted_at: at },
});

export const stopBody = (pr: number, reason = "repeat") =>
  `reviewer の差し戻しが 5 件に達したため、自動修正を止めます。<!-- oc-fix-limit --> <!-- oc-pm-intent: stuck pr=${pr} reason=${reason} -->`;
export const outcomeBody = (reason: string, run = 100) => `[run-outcome] ...\n<!-- oc-run-outcome: no-pr reason=${reason} run=${run} -->`;

export const T_BASE = Date.parse("2026-10-14T10:00:00Z");
export const at = (min: number): string => iso(T_BASE + min * 60_000);

export { send, T0 };
