// POST /webhook の結線。署名を先に検証し、不正なら storage に一切触れず 401 を返す。
import { verifySignature } from "./hmac.ts";
import { handleWebhook, EMPTY_STATE, type WebhookResult } from "./webhook.ts";
import { loadState, migrate, saveChanges, type StorageLike } from "./store.ts";

export interface WebhookEnv {
  webhookSecret: string;
  botLogin: string;
}

export function receiveWebhook(storage: StorageLike, env: WebhookEnv, headers: Headers, body: string): WebhookResult {
  const signature = headers.get("X-Hub-Signature-256");
  if (!verifySignature(env.webhookSecret, body, signature)) {
    return { status: 401, state: EMPTY_STATE, reason: "bad signature" };
  }
  migrate(storage);
  const prev = loadState(storage);
  const result = handleWebhook(prev, {
    secret: env.webhookSecret,
    event: headers.get("X-GitHub-Event"),
    signature,
    body,
    botLogin: env.botLogin,
  });
  saveChanges(storage, prev, result.state);
  return result;
}
