// PM 状態を保持する Durable Object と、POST /webhook の入口。
// 型は Workers ランタイムの必要最小限だけを局所に定義する (依存パッケージを増やさないため)。
import { receiveWebhook, type WebhookEnv } from "./route.ts";
import type { StorageLike } from "./store.ts";

export interface PmEnv extends WebhookEnv {
  PM_STATE: {
    idFromName(name: string): unknown;
    get(id: unknown): { fetch(req: Request): Promise<Response> };
  };
}

interface DurableObjectStateLike {
  storage: StorageLike;
}

export class PmStateObject {
  constructor(
    private readonly state: DurableObjectStateLike,
    private readonly env: WebhookEnv,
  ) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/webhook") {
      return new Response("not found", { status: 404 });
    }
    const body = await request.text();
    const result = receiveWebhook(this.state.storage, this.env, request.headers, body);
    return new Response(result.reason, { status: result.status });
  }
}

export default {
  async fetch(request: Request, env: PmEnv): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/webhook") {
      return new Response("not found", { status: 404 });
    }
    return env.PM_STATE.get(env.PM_STATE.idFromName("pm")).fetch(request);
  },
};
