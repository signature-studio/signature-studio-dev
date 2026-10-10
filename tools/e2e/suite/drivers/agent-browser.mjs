// agent-browser (vercel-labs/agent-browser) CLI を子プロセスで叩くドライバ。
// 1 実行 = 1 名前付きセッション (他 agent と共有しない)。--json で機械可読出力。
// spawnSync は使わない: edge-sim が同一 node プロセス内で動くため、同期待ちすると
// サーバのイベントループが止まり Chrome のリクエストが全滅する (実際にハングした)。
import { execFileSync, spawn } from "node:child_process";
import path from "node:path";
import { wait } from "../util.mjs";

const BIN = path.resolve(
  import.meta.dirname,
  "../../node_modules/.bin/agent-browser",
);

export async function createDriver({
  chrome = "/usr/bin/google-chrome",
  session,
  headers,
}) {
  const env = { ...process.env, AGENT_BROWSER_SESSION: session };
  const launchFlags = [
    "--executable-path",
    chrome,
    "--args",
    "--no-sandbox,--autoplay-policy=no-user-gesture-required",
  ];

  function ab(args, { input, timeoutMs = 60000 } = {}) {
    return new Promise((resolve, reject) => {
      const child = spawn(BIN, ["--json", ...args], { env });
      let out = "";
      let err = "";
      const timer = setTimeout(() => {
        child.kill("SIGKILL");
        reject(new Error(`agent-browser ${args[0]}: ${timeoutMs}ms でタイムアウト`));
      }, timeoutMs);
      child.stdout.on("data", (d) => (out += d));
      child.stderr.on("data", (d) => (err += d));
      child.on("error", reject);
      child.on("close", (rc) => {
        clearTimeout(timer);
        let j;
        try {
          j = JSON.parse(out);
        } catch {
          return reject(
            new Error(`agent-browser ${args[0]}: 非 JSON 出力 (rc=${rc}): ${out}${err}`),
          );
        }
        if (!j.success) return reject(new Error(`agent-browser ${args[0]}: ${j.error}`));
        resolve(j.data);
      });
      child.stdin.end(input ?? "");
    });
  }

  const drv = {
    name: "agent-browser",
    version: execFileSync(BIN, ["--version"], { encoding: "utf8" }).trim(),
    async open(url) {
      const extra = headers ? ["--headers", JSON.stringify(headers)] : [];
      return ab([...launchFlags, ...extra, "open", url]);
    },
    async eval(expr) {
      return (await ab(["eval", "--stdin"], { input: expr })).result;
    },
    async click(selector) {
      await ab(["click", selector]);
    },
    // expr が truthy になるまで 100ms polling。タイムアウトなら false
    async waitFn(expr, timeoutMs = 15000) {
      const deadline = Date.now() + timeoutMs;
      for (;;) {
        if (await drv.eval(`Boolean(${expr})`)) return true;
        if (Date.now() > deadline) return false;
        await wait(100);
      }
    },
    async screenshot(file) {
      await ab(["screenshot", file]);
    },
    async consoleMessages() {
      return (await ab(["console"])).messages.map((m) => ({ type: m.type, text: m.text }));
    },
    async pageErrors() {
      return (await ab(["errors"])).errors.map((e) => e.text);
    },
    async close() {
      try {
        await ab(["close"]);
      } catch {
        /* セッション未起動 */
      }
    },
  };
  return drv;
}
