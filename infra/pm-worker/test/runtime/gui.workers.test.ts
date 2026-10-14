import { describe, it, expect } from "vitest";
import { SELF } from "cloudflare:test";

// 実 workerd (SELF.fetch) で GET / の GUI の応答を確かめる。ヘッダと nonce の検査は test/gui.test.ts でも行うが、ここでは Worker の入口 (index.ts) を通す。
const NONCE_RE = /nonce-([A-Za-z0-9_-]+)/;

describe("GET / の GUI (実 workerd)", () => {
  it("GET / は HTML と既定のヘッダを返し、nonce は応答ごとに変わる", async () => {
    const a = await SELF.fetch("https://pm.test/");
    const b = await SELF.fetch("https://pm.test/");
    expect(a.status).toBe(200);
    expect(a.headers.get("content-type")).toBe("text/html; charset=utf-8");
    expect(a.headers.get("x-content-type-options")).toBe("nosniff");
    expect(a.headers.get("referrer-policy")).toBe("no-referrer");
    expect(a.headers.get("cache-control")).toBe("no-store");
    const na = NONCE_RE.exec(a.headers.get("content-security-policy") ?? "")?.[1] ?? "";
    const nb = NONCE_RE.exec(b.headers.get("content-security-policy") ?? "")?.[1] ?? "";
    expect(na.length).toBeGreaterThanOrEqual(16);
    expect(nb).not.toBe(na);
    expect(a.headers.get("content-security-policy")).toContain("default-src 'none'; script-src 'nonce-");
    const body = await a.text();
    expect(body).toContain(`<script nonce="${na}">`);
    expect(body).not.toContain("__NONCE__");
    await b.text();
  });

  it("HEAD / は本文なしで同じヘッダ、POST / は 405 と Allow", async () => {
    const g = await SELF.fetch("https://pm.test/");
    const h = await SELF.fetch("https://pm.test/", { method: "HEAD" });
    expect(h.status).toBe(200);
    expect(h.headers.get("content-type")).toBe(g.headers.get("content-type"));
    expect(await h.text()).toBe("");
    await g.text();
    const p = await SELF.fetch("https://pm.test/", { method: "POST", body: "x" });
    expect(p.status).toBe(405);
    expect(p.headers.get("allow")).toBe("GET, HEAD");
    await p.text();
  });

  it("GET /status は従来どおり JSON を返す (GUI の追加で経路が変わっていない)", async () => {
    const r = await SELF.fetch("https://pm.test/status");
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toContain("application/json");
    const j = (await r.json()) as Record<string, unknown>;
    expect(j).toHaveProperty("configured");
    expect(j).toHaveProperty("mode");
  });
});
