// FL 内蔵 MCP (TMCPServer) 相当の JSON-RPC 2.0 面: tools/list, tools/call を wasm Python 上の MCPTools(__main__) に橋渡しする。
// 応答の形は FLEngine rodata の固定テンプレート {"jsonrpc":"2.0","id":..,"result":{"content":[{"type":"text","text":..}],"isError":..}} に合わせる。
// 外部 LLM ゲートウェイ (Gopher 側) は含まない: ここは「JSON-RPC 文字列 → Python tool」のローカル部分のみ。
export class McpBridge {
  constructor(py) { this.py = py; }
  async handle(req) {
    const { id, method, params = {} } = typeof req === "string" ? JSON.parse(req) : req;
    const ok = (result) => ({ jsonrpc: "2.0", id, result });
    const err = (code, message) => ({ jsonrpc: "2.0", id, error: { code, message } });
    if (method === "initialize") {
      return ok({ protocolVersion: "2024-11-05", capabilities: { tools: {} }, serverInfo: { name: "flpy-mcp-bridge", version: "0.1" } });
    }
    if (method === "tools/list") {
      const r = await this.py.call("__main__:get_mcp_tools_json", {});
      return ok({ tools: JSON.parse(r.ok) });
    }
    if (method === "tools/call") {
      const r = await this.py.call(`__main__:${params.name}`, params.arguments || {});
      const isError = r.err !== undefined;
      return ok({ content: [{ type: "text", text: isError ? r.err : String(r.ok) }], isError });
    }
    return err(-32601, `Method not found: ${method}`);
  }
}
