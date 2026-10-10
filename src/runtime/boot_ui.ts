/**
 * ブートパネル (進捗 UI + e2e フック)。
 *   /?runtime=<id|all>[&cache=http|cacheapi|none][&compile=streaming|bytes][&pump=1]
 * 結果は window.__runtime に格納 (headless Chrome e2e が polling する)。
 */

import { bootProgram, loadManifest, runPumpSelfTest, type ResultMsg } from "./boot";
import type { BootOptions, ManifestEntry, Phase, PumpSelfTestResult } from "./worker_protocol";

export type RuntimeRun = {
  id: string;
  ok: boolean;
  checks: ResultMsg["result"]["checks"];
  data: Record<string, unknown>;
  timings: ResultMsg["timings"];
  resource: ResultMsg["resource"];
  memory: ResultMsg["memory"];
  wasmBytes: number;
  error?: string;
};

export type RuntimeReport = {
  state: "running" | "done" | "error";
  crossOriginIsolated: boolean;
  runs: RuntimeRun[];
  pump?: PumpSelfTestResult;
  error?: string;
};

declare global {
  interface Window {
    __runtime?: RuntimeReport;
  }
}

const mb = (n: number) => (n / 1048576).toFixed(2);

export async function mountRuntimePanel(params: URLSearchParams): Promise<void> {
  const want = params.get("runtime") ?? "all";
  const opts: Partial<BootOptions> = {};
  const cache = params.get("cache");
  if (cache === "http" || cache === "cacheapi" || cache === "none") opts.cacheMode = cache;
  const compile = params.get("compile");
  if (compile === "streaming" || compile === "bytes") opts.compile = compile;

  const panel = document.createElement("div");
  panel.style.cssText =
    "position:fixed;right:12px;top:12px;z-index:20;width:520px;max-height:80vh;overflow:auto;background:#000c;padding:10px;font:12px/1.4 monospace;color:#cfe;border:1px solid #345";
  const bar = document.createElement("progress");
  bar.style.width = "100%";
  bar.max = 1;
  bar.value = 0;
  const pre = document.createElement("pre");
  pre.style.cssText = "margin:6px 0 0;white-space:pre-wrap";
  panel.append(bar, pre);
  document.body.appendChild(panel);
  const line = (s: string) => { pre.textContent += s + "\n"; };

  const report: RuntimeReport = { state: "running", crossOriginIsolated, runs: [] };
  window.__runtime = report;
  try {
    const { manifest, baseUrl } = await loadManifest();
    const entries: ManifestEntry[] = want === "all" ? manifest.entries : manifest.entries.filter((e) => e.id === want);
    line(`manifest: ${manifest.entries.length} entries, selected ${entries.length}, crossOriginIsolated=${crossOriginIsolated}`);
    for (const entry of entries) {
      line(`▶ ${entry.id} (${mb(entry.bytes)} MiB)`);
      const phaseName: Record<Phase, string> = { fetch: "取得", compile: "コンパイル", instantiate: "初期化", run: "実行" };
      try {
        const { result } = await bootProgram(baseUrl, entry, opts, {
          onProgress: (phase, loaded, total) => {
            bar.max = total || 1;
            bar.value = loaded;
            bar.title = `${phaseName[phase]} ${loaded}/${total}`;
          },
          onLog: (s, t) => line(`  [${s}] ${t}`),
        });
        const run: RuntimeRun = {
          id: entry.id,
          ok: result.result.ok,
          checks: result.result.checks,
          data: result.result.data,
          timings: result.timings,
          resource: result.resource,
          memory: result.memory,
          wasmBytes: entry.bytes,
        };
        report.runs.push(run);
        line(`  ${run.ok ? "OK " : "NG "} total ${run.timings.totalMs}ms (fetch+compile ${run.timings.fetchCompileMs}ms, run ${run.timings.runMs}ms)`);
      } catch (e) {
        report.runs.push({ id: entry.id, ok: false, checks: [], data: {}, timings: { fetchCompileMs: 0, instantiateMs: 0, initMs: 0, runMs: 0, totalMs: 0 }, resource: { transferSize: null, decodedBodySize: null, deliveryType: null, fromCacheApi: false }, memory: { model: "?", shared: false, bytes: 0 }, wasmBytes: entry.bytes, error: String(e) });
        line(`  ERROR ${String(e)}`);
      }
    }
    if (params.get("pump") === "1") {
      line("▶ pump self-test (Atomics.wait ブロッキング GetMessage)");
      report.pump = await runPumpSelfTest(Number(params.get("pumpN") ?? 2000), 10);
      line(`  received=${report.pump.received} timers=${report.pump.timers} p50=${report.pump.latency.p50}ms p99=${report.pump.latency.p99}ms`);
    }
    report.state = "done";
  } catch (e) {
    report.state = "error";
    report.error = String(e);
    line(`ERROR ${String(e)}`);
  }
  window.__runtime = { ...report };
}
