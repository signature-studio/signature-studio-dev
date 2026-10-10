// edge-policy.json を解釈する共有ライブラリ。
// - Cloudflare Rulesets API ペイロード生成 (deploy/scripts/rulesets.mjs)
// - ローカル edge-sim (tools/e2e/suite/servers.mjs) の応答ヘッダ適用
// どちらも同じ match 定義を使うので「ルール JSON が本当に crossOriginIsolated を成立させるか」を
// Cloudflare 認証なしで E2E 検証できる。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

export const POLICY_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../config/edge-policy.json",
);

export function loadPolicy(file = process.env.EDGE_POLICY_FILE ?? POLICY_PATH) {
  return JSON.parse(readFileSync(file, "utf8"));
}

export function extOf(p) {
  const base = p.split("/").pop() ?? "";
  const i = base.lastIndexOf(".");
  return i > 0 ? base.slice(i + 1).toLowerCase() : "";
}

export function contentTypeFor(policy, p) {
  return policy.contentTypes[extOf(p)] ?? policy.defaultContentType;
}

// path/pathPrefix/ext は OR (どれか 1 つ。全部空なら全パス)。status は AND。
export function matches(match, { path: p, status }) {
  const sel = [];
  if (match.path) sel.push(match.path.includes(p));
  if (match.pathPrefix) sel.push(match.pathPrefix.some((x) => p.startsWith(x)));
  if (match.ext) sel.push(match.ext.includes(extOf(p)));
  if (match.pathSuffix) sel.push(p.endsWith(match.pathSuffix));
  const pathOk = sel.length === 0 ? true : sel.some(Boolean);
  const statusOk = match.status ? match.status.includes(status) : true;
  return pathOk && statusOk;
}

const q = (s) => JSON.stringify(s);
const setOf = (xs) => `{${xs.map(q).join(" ")}}`;

export function expression(match, host, { status = true } = {}) {
  const parts = [`http.host eq ${q(host)}`];
  const sel = [];
  if (match.path) sel.push(`http.request.uri.path in ${setOf(match.path)}`);
  if (match.pathPrefix) {
    for (const x of match.pathPrefix) {
      sel.push(`starts_with(http.request.uri.path, ${q(x)})`);
    }
  }
  if (match.ext) sel.push(`http.request.uri.path.extension in ${setOf(match.ext)}`);
  if (match.pathSuffix) sel.push(`ends_with(http.request.uri.path, ${q(match.pathSuffix)})`);
  if (sel.length) parts.push(sel.length === 1 ? sel[0] : `(${sel.join(" or ")})`);
  if (status && match.status) {
    parts.push(`http.response.code in {${match.status.join(" ")}}`);
  }
  return parts.map((x) => `(${x})`).join(" and ");
}

export const REF_PREFIX = "webstudio_";

// ルール ref はホスト単位で名前空間化 (同一ゾーンに staging/prod を置いても互いの rule を消さない)
export function refPrefix(host) {
  return `${REF_PREFIX}${host.toLowerCase().replace(/[^a-z0-9]+/g, "_")}_`;
}

export function buildTransformRules(policy, host) {
  return policy.responseHeaders.map((r) => ({
    ref: `${refPrefix(host)}hdr_${r.id.replace(/-/g, "_")}`,
    description: `webstudio: ${r.description}`,
    expression: expression(r.match, host),
    action: "rewrite",
    action_parameters: {
      headers: Object.fromEntries(
        Object.entries(r.set).map(([k, v]) => [k, { operation: "set", value: v }]),
      ),
    },
    enabled: true,
  }));
}

export function buildRewriteRules(policy, host) {
  return (policy.requestRewrite ?? []).map((r) => ({
    ref: `${refPrefix(host)}rewrite_${r.id.replace(/-/g, "_")}`,
    description: `webstudio: ${r.description}`,
    expression: expression(r.match, host, { status: false }),
    action: "rewrite",
    action_parameters: {
      uri: {
        path: {
          expression: `concat(http.request.uri.path, ${q(r.appendToPath)})`,
        },
      },
    },
    enabled: true,
  }));
}

// edge-sim 用: 末尾 / パスへの index 連結 (R2 カスタムドメインに Rewrite rule を当てた場合の挙動)
export function applyRequestRewrite(policy, p) {
  for (const r of policy.requestRewrite ?? []) {
    if (matches(r.match, { path: p, status: 200 })) p = p + r.appendToPath;
  }
  return p;
}

export function buildCacheRules(policy, host) {
  return policy.cache.map((r) => ({
    ref: `${refPrefix(host)}cache_${r.id.replace(/-/g, "_")}`,
    description: `webstudio: ${r.description}`,
    expression: expression(r.match, host, { status: false }),
    action: "set_cache_settings",
    action_parameters: {
      cache: r.cache,
      edge_ttl: r.edgeTtl,
      browser_ttl: r.browserTtl,
    },
    enabled: true,
  }));
}

export function buildCompressionRules(policy, host) {
  return policy.compression.map((r) => ({
    ref: `${refPrefix(host)}cmp_${r.id.replace(/-/g, "_")}`,
    description: `webstudio: ${r.description}`,
    expression: expression(r.match, host, { status: false }),
    action: "compress_response",
    action_parameters: { algorithms: r.algorithms.map((name) => ({ name })) },
    enabled: true,
  }));
}

// edge-sim 用: 応答ヘッダを policy 順に適用 (後勝ち)
export function applyResponseHeaders(policy, req, headers) {
  for (const r of policy.responseHeaders) {
    if (matches(r.match, req)) Object.assign(headers, r.set);
  }
  return headers;
}

export function compressionAlgorithms(policy, p) {
  let algos = null;
  for (const r of policy.compression) {
    if (matches(r.match, { path: p, status: 200 })) algos = r.algorithms;
  }
  return algos;
}
