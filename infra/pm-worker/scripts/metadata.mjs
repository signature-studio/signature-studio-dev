// Workers Scripts upload (REST: PUT /accounts/{id}/workers/scripts/{name}) の metadata を wrangler.toml と同じ内容で作る。
// 使い方: node scripts/metadata.mjs [--keep-secret] > metadata.json
// STORE_KEY (secret_text) の値はここでは扱わない。デプロイ側 (README の手順) が Secrets API で別に設定する。
// `--keep-secret` は既存の secret を残す指定 (keep_bindings)。再デプロイ時に使う。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const toml = readFileSync(fileURLToPath(new URL("../wrangler.toml", import.meta.url)), "utf8");
const str = (k) => new RegExp(`^${k}\\s*=\\s*"([^"]*)"`, "m").exec(toml)?.[1];
const vars = {};
const vblock = /^\[vars\]\n([\s\S]*?)(?=^\[)/m.exec(toml)?.[1] ?? "";
for (const m of vblock.matchAll(/^(\w+)\s*=\s*"([^"]*)"/gm)) vars[m[1]] = m[2];

const keep = process.argv.includes("--keep-secret");
const meta = {
  main_module: "index.js",
  compatibility_date: str("compatibility_date"),
  compatibility_flags: ["nodejs_compat"],
  bindings: [
    ...Object.entries(vars).map(([name, text]) => ({ type: "plain_text", name, text })),
    { type: "durable_object_namespace", name: "PM", class_name: "PmDO" },
  ],
  migrations: { new_tag: "v1", new_sqlite_classes: ["PmDO"] },
  keep_bindings: keep ? ["secret_text"] : [],
  observability: { enabled: true },
};
process.stdout.write(JSON.stringify(meta, null, 2) + "\n");
