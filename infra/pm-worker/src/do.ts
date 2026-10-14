// Durable Object (SQLite)。状態・App の鍵 (封印済み)・alarm を持つ。Cloudflare ランタイムでだけ動く薄い層で、
// ロジックは app.ts / engine.ts にあり、そちらを Node のテストで検証する。
import { PmApp } from "./app.ts";
import { loadConfig, type Env } from "./config.ts";
import type { Bucket, Store } from "./kvstore.ts";

class SqlStore implements Store {
  private readonly sql: any;
  constructor(sql: any) {
    this.sql = sql;
    sql.exec("CREATE TABLE IF NOT EXISTS kv (bucket TEXT NOT NULL, k TEXT NOT NULL, v TEXT NOT NULL, PRIMARY KEY (bucket, k))");
  }
  get<T = unknown>(bucket: Bucket, key: string): T | undefined {
    const rows = [...this.sql.exec("SELECT v FROM kv WHERE bucket = ? AND k = ?", bucket, key)];
    return rows.length ? (JSON.parse(rows[0].v) as T) : undefined;
  }
  put(bucket: Bucket, key: string, value: unknown): void {
    this.sql.exec("INSERT INTO kv (bucket, k, v) VALUES (?, ?, ?) ON CONFLICT (bucket, k) DO UPDATE SET v = excluded.v", bucket, key, JSON.stringify(value));
  }
  del(bucket: Bucket, key: string): void {
    this.sql.exec("DELETE FROM kv WHERE bucket = ? AND k = ?", bucket, key);
  }
  all<T = unknown>(bucket: Bucket): Array<[string, T]> {
    return [...this.sql.exec("SELECT k, v FROM kv WHERE bucket = ?", bucket)].map((r: any) => [r.k, JSON.parse(r.v) as T]);
  }
}

export class PmDO {
  private readonly ctx: any;
  private readonly app: PmApp;

  constructor(ctx: any, env: Env) {
    this.ctx = ctx;
    const cfg = loadConfig(env);
    this.app = new PmApp({
      store: new SqlStore(ctx.storage.sql),
      cfg,
      storeKey: env.STORE_KEY,
      now: () => Date.now(),
      fetch: (i, init) => fetch(i, init),
      scheduleSoon: () => this.schedule(2000),
    });
  }

  private async schedule(ms: number, onlyIfSooner = true): Promise<void> {
    const want = Date.now() + ms;
    const cur = await this.ctx.storage.getAlarm();
    if (onlyIfSooner && cur && cur <= want) return;
    await this.ctx.storage.setAlarm(want);
  }

  async fetch(req: Request): Promise<Response> {
    const res = await this.app.handle(req);
    // cron からの /tick と /setup 後の初回で alarm を張る (alarm が途切れても 1 分以内に戻る)。
    if (new URL(req.url).pathname === "/tick") await this.schedule(this.app.engine.nextDelayMs());
    return res;
  }

  async alarm(): Promise<void> {
    try {
      await this.app.engine.tick();
    } finally {
      await this.schedule(this.app.engine.nextDelayMs(), false);
    }
  }
}
