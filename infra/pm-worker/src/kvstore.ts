// 永続化の最小インタフェース。本番は Durable Object の SQLite (pm-do.ts)、テストはメモリ。
export type Bucket =
  | "issues"
  | "prs"
  | "runs"
  | "botLast"
  | "pmArt"
  | "blockedBy"
  | "launchedAt"
  | "sig"
  | "relaunch"
  | "launchObs"
  | "meta";

export interface Store {
  get<T = unknown>(bucket: Bucket, key: string): T | undefined;
  put(bucket: Bucket, key: string, value: unknown): void;
  del(bucket: Bucket, key: string): void;
  all<T = unknown>(bucket: Bucket): Array<[string, T]>;
}

export class MemoryStore implements Store {
  writes = 0;
  readonly data = new Map<string, Map<string, string>>();

  private b(bucket: Bucket): Map<string, string> {
    let m = this.data.get(bucket);
    if (!m) {
      m = new Map();
      this.data.set(bucket, m);
    }
    return m;
  }
  get<T = unknown>(bucket: Bucket, key: string): T | undefined {
    const v = this.b(bucket).get(key);
    return v === undefined ? undefined : (JSON.parse(v) as T);
  }
  put(bucket: Bucket, key: string, value: unknown): void {
    this.writes++;
    this.b(bucket).set(key, JSON.stringify(value));
  }
  del(bucket: Bucket, key: string): void {
    this.writes++;
    this.b(bucket).delete(key);
  }
  all<T = unknown>(bucket: Bucket): Array<[string, T]> {
    return [...this.b(bucket)].map(([k, v]) => [k, JSON.parse(v) as T]);
  }
}
