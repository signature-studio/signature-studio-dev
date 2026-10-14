// PmState の SQLite 永続化。増分保存: 前後の state を内容 (JSON) で比べ、変わった entity だけを upsert する。
// 参照では比べない (同じ配送の再適用でも新しいオブジェクトになるため)。
import type { PmState } from "./webhook.ts";

export interface SqlCursor {
  toArray(): Record<string, unknown>[];
}
export interface SqlLike {
  exec(query: string, ...bindings: unknown[]): SqlCursor;
}
// Durable Object の ctx.storage に対応する最小形 (sql と transactionSync のみ使う)。
export interface StorageLike {
  sql: SqlLike;
  transactionSync<T>(fn: () => T): T;
}

type Field = keyof PmState;
const KINDS: Array<{ kind: string; field: Field }> = [
  { kind: "issue", field: "issues" },
  { kind: "pr", field: "prs" },
  { kind: "run", field: "runs" },
  { kind: "bot_last", field: "botLast" },
  { kind: "pm_art", field: "pmArt" },
  { kind: "blocked_by", field: "blockedBy" },
  { kind: "launched_at", field: "launchedAt" },
];
const FIELD_OF: Record<string, Field> = Object.fromEntries(KINDS.map((k) => [k.kind, k.field]));

export function migrate(storage: StorageLike): void {
  storage.sql.exec(
    "CREATE TABLE IF NOT EXISTS pm_entities (kind TEXT NOT NULL, key TEXT NOT NULL, json TEXT NOT NULL, PRIMARY KEY (kind, key))",
  );
}

export function loadState(storage: StorageLike): PmState {
  const state: PmState = { issues: {}, prs: {}, runs: {}, botLast: {}, pmArt: {}, blockedBy: {}, launchedAt: {} };
  for (const row of storage.sql.exec("SELECT kind, key, json FROM pm_entities").toArray()) {
    const field = FIELD_OF[String(row.kind)];
    if (!field) continue;
    (state[field] as Record<string, unknown>)[String(row.key)] = JSON.parse(String(row.json));
  }
  return state;
}

// 戻り値は書き込んだ行数。変更が無ければ何も書かない。
export function saveChanges(storage: StorageLike, prev: PmState, next: PmState): number {
  const changes: Array<{ kind: string; key: string; value: unknown }> = [];
  for (const { kind, field } of KINDS) {
    const before = prev[field] as Record<string, unknown>;
    const after = next[field] as Record<string, unknown>;
    for (const key of Object.keys(after)) {
      const json = JSON.stringify(after[key]);
      if (before[key] === undefined || JSON.stringify(before[key]) !== json) {
        changes.push({ kind, key, value: after[key] });
      }
    }
  }
  if (changes.length === 0) return 0;
  storage.transactionSync(() => {
    for (const c of changes) {
      storage.sql.exec(
        "INSERT INTO pm_entities (kind, key, json) VALUES (?, ?, ?) ON CONFLICT (kind, key) DO UPDATE SET json = excluded.json",
        c.kind,
        c.key,
        JSON.stringify(c.value),
      );
    }
  });
  return changes.length;
}
