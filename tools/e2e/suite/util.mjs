import net from "node:net";

export const wait = (ms) => new Promise((r) => setTimeout(r, ms));

export function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.once("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

// 短 polling (100ms) で HTTP 応答を待つ。固定時間待機はしない
export async function waitHttp(url, { timeoutMs = 30000, headers = {} } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url, { headers, redirect: "manual" });
      if (r.status < 500) return r.status;
      last = `status ${r.status}`;
    } catch (e) {
      last = String(e?.cause?.code ?? e);
    }
    await wait(100);
  }
  throw new Error(`waitHttp timeout ${url} (${last})`);
}
