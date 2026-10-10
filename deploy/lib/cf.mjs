// cf CLI (~/.bun/bin/cf) の薄いラッパ。出力は JSON。
// 認証は cf auth login (OAuth) か CLOUDFLARE_API_TOKEN。アカウントは CLOUDFLARE_ACCOUNT_ID。
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileP = promisify(execFile);
export const CF_BIN = process.env.CF_BIN ?? "cf";

export function requireEnv(...names) {
  const missing = names.filter((n) => !process.env[n]);
  if (missing.length) {
    throw new Error(`環境変数が未設定: ${missing.join(", ")} (deploy/env.example 参照)`);
  }
}

// 失敗時は stderr を含めて throw。404 を呼び出し側で扱えるよう err.notFound を付ける
export async function cf(args, { json = true } = {}) {
  try {
    const { stdout } = await execFileP(CF_BIN, args, {
      maxBuffer: 256 * 1024 * 1024,
      env: process.env,
    });
    if (!json) return stdout;
    return stdout.trim() ? JSON.parse(stdout) : null;
  } catch (e) {
    const msg = `${e.stderr ?? ""}${e.stdout ?? ""}` || String(e);
    const err = new Error(`cf ${args.join(" ")}\n${msg}`);
    err.notFound = /404|not find|not found/i.test(msg);
    throw err;
  }
}

export async function zoneId(zone) {
  if (/^[0-9a-f]{32}$/.test(zone)) return zone;
  const zs = await cf(["zones", "list", "--name", zone]).catch(() => null);
  const list = Array.isArray(zs) ? zs : zs?.result ?? [];
  const z = list.find((x) => x.name === zone);
  if (!z) throw new Error(`zone が見つからない/権限不足: ${zone}`);
  return z.id;
}

// 同時実行数を絞った Promise プール
export async function pool(items, n, fn) {
  const results = new Array(items.length);
  let i = 0;
  await Promise.all(
    Array.from({ length: Math.min(n, items.length) }, async () => {
      while (i < items.length) {
        const k = i++;
        results[k] = await fn(items[k], k);
      }
    }),
  );
  return results;
}
