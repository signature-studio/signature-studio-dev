#!/usr/bin/env node
// E2E スイート実行本体 (run.sh から呼ばれる)。
//   node suite/run.mjs [--targets preview,edge-sim,dev] [--driver agent-browser|puppeteer|both]
//   リモート: E2E_URL=https://host/ node suite/run.mjs --targets url
//     (Cloudflare Access 保護時は E2E_ACCESS_CLIENT_ID / E2E_ACCESS_CLIENT_SECRET)
// 出力: work/results/<target>-<driver>.json, work/shots/<target>-<driver>-<name>.png
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { loadPolicy } from "../../../deploy/lib/policy.mjs";
import { Skip, checks } from "./checks.mjs";
import { E2E_DIR, startTarget } from "./servers.mjs";

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};
const targets = opt("targets", process.env.E2E_TARGETS ?? "preview,edge-sim").split(",");
const driverOpt = opt("driver", process.env.E2E_DRIVER ?? "agent-browser");
const drivers = driverOpt === "both" ? ["agent-browser", "puppeteer"] : [driverOpt];
const chrome = process.env.E2E_CHROME ?? "/usr/bin/google-chrome";

const shotsDir = path.join(E2E_DIR, "work/shots");
const resultsDir = path.join(E2E_DIR, "work/results");
mkdirSync(shotsDir, { recursive: true });
mkdirSync(resultsDir, { recursive: true });

const accessHeaders =
  process.env.E2E_ACCESS_CLIENT_ID && process.env.E2E_ACCESS_CLIENT_SECRET
    ? {
        "CF-Access-Client-Id": process.env.E2E_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": process.env.E2E_ACCESS_CLIENT_SECRET,
      }
    : undefined;

const policy = loadPolicy();
let failed = 0;
const summary = [];

async function runOne(targetName, driverName) {
  const strict = targetName === "edge-sim" || targetName === "url";
  let server;
  if (targetName === "url") {
    const u = process.env.E2E_URL;
    if (!u) throw new Error("target=url には E2E_URL が必要");
    server = { url: u.replace(/\/$/, ""), stop: async () => {} };
  } else {
    server = await startTarget(targetName);
  }
  const tag = `${targetName}-${driverName}`;
  const mod = await import(`./drivers/${driverName}.mjs`);
  const session = `webstudio-e2e-${process.pid}-${tag}`;
  const drv = await mod.createDriver({ chrome, session, headers: accessHeaders });
  const ctx = {
    url: server.url,
    drv,
    policy,
    headers: accessHeaders ?? {},
    target: { name: targetName, strict },
    async shot(name) {
      await drv.screenshot(path.join(shotsDir, `${tag}-${name}.png`));
    },
  };
  console.log(`\n=== target=${targetName} driver=${drv.name} (${drv.version}) url=${server.url}`);
  const results = [];
  try {
    for (const c of checks) {
      const t0 = Date.now();
      let status = "PASS";
      let detail = "";
      try {
        detail = (await c.run(ctx)) ?? "";
      } catch (e) {
        if (e instanceof Skip) {
          status = "SKIP";
          detail = e.message;
        } else {
          status = "FAIL";
          detail = e?.message ?? String(e);
          failed++;
        }
      }
      const ms = Date.now() - t0;
      results.push({ id: c.id, title: c.title, status, detail, ms });
      console.log(`${status.padEnd(4)} ${c.id.padEnd(22)} ${String(ms).padStart(5)}ms  ${detail}`);
    }
    try {
      await ctx.shot("final");
    } catch (e) {
      console.log(`WARN final screenshot: ${e.message}`);
    }
  } finally {
    await drv.close();
    await server.stop();
  }
  const out = { target: targetName, driver: drv.name, driverVersion: drv.version, url: server.url, results };
  writeFileSync(path.join(resultsDir, `${tag}.json`), JSON.stringify(out, null, 2));
  summary.push(out);
}

for (const t of targets) {
  for (const d of drivers) {
    try {
      await runOne(t, d);
    } catch (e) {
      failed++;
      console.log(`FAIL runner target=${t} driver=${d}: ${e.stack ?? e}`);
    }
  }
}

const count = (s) => summary.flatMap((x) => x.results).filter((r) => r.status === s).length;
console.log(`\nSUMMARY: PASS=${count("PASS")} FAIL=${failed} SKIP=${count("SKIP")} (targets=${targets.join(",")} drivers=${drivers.join(",")})`);
process.exit(failed ? 1 : 0);
