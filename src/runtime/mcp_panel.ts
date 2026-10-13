/**
 * mcp_panel.ts — MCP JSON-RPC (tools/python/host/mcp_rpc.mjs) をアプリ内 UI / devtools に公開する (PY-4 #77)。
 *   devtools:  await flMcp.start()  →  await flMcp.rpc({jsonrpc:"2.0",id:1,method:"tools/list"})
 *   UI:        /?mcp=1 で右下にパネル (MCPTools.pyc / midi.py / utils.py を選択 or ドロップ → tools/list / tools/call)
 * MCPTools.pyc 等は利用者の FL インストールから実行時に供給する (リポジトリ・配信物に非同梱)。
 * 外部 LLM / Gopher AI / FL Cloud には接続しない (ローカル完結)。
 * flapi の提供側は FLEngine 未完成の間 host/fl_mock.mjs (FLEngine 模擬) — 実エンジン結合後は engine を差し替える (BRIDGE.md §5)。
 */

type Json = unknown;
type McpResponse = { jsonrpc: "2.0"; id: unknown; result?: { tools?: { name: string }[]; content?: { type: string; text: string }[]; isError?: boolean }; error?: { code: number; message: string } };

export type FlMcp = {
  /** wasm Python を起動し MCPTools.pyc を __main__ として読み込む。files のキーはファイル名 (MCPTools.pyc / midi.py / utils.py)。省略時は UI で供給済みのもの */
  start(files?: Record<string, Uint8Array>): Promise<{ tools: number; python: string }>;
  /** JSON-RPC 2.0 (initialize / tools/list / tools/call)。文字列 / オブジェクトどちらも可 */
  rpc(req: string | object): Promise<McpResponse>;
  list(): Promise<{ name: string; description?: string }[]>;
  call(name: string, args?: Record<string, Json>): Promise<{ text: string; isError: boolean }>;
  stop(): Promise<void>;
  readonly started: boolean;
};

declare global {
  interface Window {
    flMcp?: FlMcp;
  }
}

const PY_BASE = "/py";
const REQUIRED = ["MCPTools.pyc", "midi.py", "utils.py"] as const;
const DEST: Record<string, string> = { "MCPTools.pyc": "/fl/Tools/MCPTools.pyc", "midi.py": "/fl/Lib/midi.py", "utils.py": "/fl/Lib/utils.py" };

// ビルド時に解決させない動的 import (tools/python は配信物に含まれず、実行時に /py/ から取得する)
const dynImport = (url: string): Promise<any> => import(/* @vite-ignore */ url);

export function installFlMcp(): FlMcp {
  if (window.flMcp) return window.flMcp;
  const supplied: Record<string, Uint8Array> = {};
  let py: any = null;
  let bridge: any = null;
  let starting: Promise<{ tools: number; python: string }> | null = null;
  const stdout: string[] = [];

  const start: FlMcp["start"] = (files) => {
    if (files) for (const [k, v] of Object.entries(files)) supplied[k.split("/").pop()!] = v;
    if (starting) return starting;
    starting = (async () => {
      if (!crossOriginIsolated) throw new Error("crossOriginIsolated=false: SAB が使えません (COOP/COEP を確認)");
      const missing = REQUIRED.filter((n) => !supplied[n]);
      if (missing.length) throw new Error(`利用者の FL インストールから供給が必要: ${missing.join(", ")}`);
      const origin = location.origin + PY_BASE;
      const [{ FlPython }, { createMockEngine }, { McpBridge }, ids] = await Promise.all([
        dynImport(`${origin}/host/flpython.mjs`),
        dynImport(`${origin}/host/fl_mock.mjs`),
        dynImport(`${origin}/host/mcp_rpc.mjs`),
        fetch(`${origin}/analysis/flapi/flapi_ids.json`).then((r) => {
          if (!r.ok) throw new Error(`flapi_ids.json: HTTP ${r.status}`);
          return r.json();
        }),
      ]);
      const files2: Record<string, Uint8Array> = {};
      for (const n of REQUIRED) files2[DEST[n]!] = supplied[n]!;
      py = await FlPython.create({
        flpyUrl: `${origin}/dist/flpy.js`,
        engine: createMockEngine(),
        ids,
        files: files2,
        onStdout: (t: string) => stdout.push(t),
        onStderr: (t: string) => stdout.push(`ERR ${t}`),
      });
      await py.run(`import fl_rt\nfl_rt.install_flapi()\nfl_rt.load_pyc("/fl/Tools/MCPTools.pyc", "__main__")`);
      bridge = new McpBridge(py);
      const lst = (await bridge.handle({ jsonrpc: "2.0", id: "start", method: "tools/list" })) as McpResponse;
      const ver = (await py.call("platform:python_version", []).catch(() => null)) as { ok?: string } | null;
      return { tools: lst.result?.tools?.length ?? 0, python: ver?.ok ?? "3.12" };
    })();
    starting.catch(() => { starting = null; });
    return starting;
  };

  const need = (): any => {
    if (!bridge) throw new Error("flMcp.start() が未実行です (MCPTools.pyc の供給が必要)");
    return bridge;
  };
  const api: FlMcp = {
    start,
    rpc: (req) => need().handle(req),
    async list() {
      const r = (await need().handle({ jsonrpc: "2.0", id: "list", method: "tools/list" })) as McpResponse;
      return (r.result?.tools ?? []) as { name: string; description?: string }[];
    },
    async call(name, args = {}) {
      const r = (await need().handle({ jsonrpc: "2.0", id: "call", method: "tools/call", params: { name, arguments: args } })) as McpResponse;
      return { text: r.result?.content?.[0]?.text ?? "", isError: r.result?.isError ?? true };
    },
    async stop() {
      if (py) await py.terminate();
      py = bridge = starting = null;
    },
    get started() { return bridge !== null; },
  };
  // 供給済みファイルを UI から渡すための内部口 (パネル用)
  (api as unknown as { _supply: (n: string, b: Uint8Array) => void })._supply = (n, b) => { supplied[n] = b; };
  window.flMcp = api;
  return api;
}

export function mountMcpPanel(): void {
  const api = installFlMcp() as FlMcp & { _supply(n: string, b: Uint8Array): void };
  const panel = document.createElement("div");
  panel.id = "mcp-panel";
  panel.style.cssText = "position:fixed;right:12px;bottom:12px;z-index:20;width:460px;max-height:70vh;overflow:auto;background:#000c;padding:10px;font:12px/1.4 monospace;color:#cfe;border:1px solid #345";
  panel.innerHTML = `
    <div><b>MCP JSON-RPC</b> (ローカル / 外部 LLM なし)</div>
    <div style="margin:6px 0">FL の <code>MCPTools.pyc</code> <code>midi.py</code> <code>utils.py</code> を選択/ドロップ:
      <input id="mcp-files" type="file" multiple></div>
    <div><button id="mcp-start" disabled>起動</button> <span id="mcp-state">ファイル未供給</span></div>
    <div style="margin-top:6px"><select id="mcp-tool" disabled style="max-width:300px"></select>
      <button id="mcp-call" disabled>tools/call</button></div>
    <div style="margin-top:4px"><input id="mcp-args" value="{}" style="width:98%" placeholder="arguments (JSON)"></div>
    <pre id="mcp-out" style="margin:6px 0 0;white-space:pre-wrap"></pre>`;
  document.body.appendChild(panel);
  const $ = <T extends HTMLElement>(id: string) => panel.querySelector<T>(`#${id}`)!;
  const state = $("mcp-state"), out = $("mcp-out"), startBtn = $<HTMLButtonElement>("mcp-start");
  const sel = $<HTMLSelectElement>("mcp-tool"), callBtn = $<HTMLButtonElement>("mcp-call"), args = $<HTMLInputElement>("mcp-args");
  const have = new Set<string>();
  const refresh = (text = true) => {
    const missing = REQUIRED.filter((n) => !have.has(n));
    startBtn.disabled = missing.length > 0 || api.started;
    if (text) state.textContent = missing.length ? `未供給: ${missing.join(", ")}` : "供給済み — 起動できます";
  };
  const ingest = async (list: FileList | File[]) => {
    for (const f of Array.from(list)) {
      if (!(REQUIRED as readonly string[]).includes(f.name)) continue;
      api._supply(f.name, new Uint8Array(await f.arrayBuffer()));
      have.add(f.name);
    }
    refresh();
  };
  $<HTMLInputElement>("mcp-files").addEventListener("change", (e) => void ingest((e.target as HTMLInputElement).files ?? []));
  panel.addEventListener("dragover", (e) => e.preventDefault());
  panel.addEventListener("drop", (e) => { e.preventDefault(); void ingest(e.dataTransfer?.files ?? []); });
  startBtn.addEventListener("click", async () => {
    state.textContent = "起動中…";
    try {
      const r = await api.start();
      sel.replaceChildren(...(await api.list()).map((t) => Object.assign(document.createElement("option"), { value: t.name, textContent: t.name })));
      sel.disabled = callBtn.disabled = false;
      state.textContent = `起動済み: tools/list = ${r.tools} (python ${r.python})`;
    } catch (e) {
      state.textContent = `失敗: ${String(e)}`;
    }
    refresh(false);
  });
  callBtn.addEventListener("click", async () => {
    try {
      const r = await api.call(sel.value, JSON.parse(args.value || "{}"));
      out.textContent = `${r.isError ? "isError" : "ok"}: ${r.text}`;
    } catch (e) {
      out.textContent = `error: ${String(e)}`;
    }
  });
  refresh();
}
