// FL 内部 module `ilmcp` の 9 関数 (PY-3 / #82)。引数規約は MCPTools.pyc の逆アセンブル実測 (tools/python/REPORT.md §7c):
//   getBrowserNames(name:str, recursive:int)   addChannel(plugin:str)       removeChannel(idx:int, 0 起点)
//   addEffect(plugin:str, track:int, slot:int) ※ plugin="" でスロット消去 (remove_effect / reset_mixer_tracks)
//   storePRScript(name, source)   runPRScript(source)   getHighlightNames()
//   showHighlight(item, name, caption, whenDone, flag:bool)   forwardTutorialEvent(...) ※ MCPTools 未使用・arity 不明
// 実エンジン (FLEngine) の戻り値・例外は実機未検証 → REPORT §7c の「仮定」欄。
import catalogJson from "../analysis/ilmcp/plugin_catalog.json" with { type: "json" };
import highlightJson from "../analysis/ilmcp/highlight_names.json" with { type: "json" };

export const catalog = () => catalogJson.entries;
export const highlightNames = () => highlightJson.names;

const ROOT = "Plugin database";
const norm = (p) => String(p ?? "").replace(/\\/g, "/").split("/").map((s) => s.trim()).filter(Boolean);

/** カタログから木を作る。native は Effects|Generators/<cat>/<name>、installed は Installed/<kind>/<fmt>/<name>。 */
function buildTree(entries) {
  const root = { dirs: new Map(), items: [] };
  for (const e of entries) {
    let n = root;
    for (const d of e.path) {
      if (!n.dirs.has(d)) n.dirs.set(d, { dirs: new Map(), items: [] });
      n = n.dirs.get(d);
    }
    n.items.push(e);
  }
  return root;
}

function walk(node, prefix, recursive, out) {
  for (const [d, sub] of [...node.dirs].sort((a, b) => a[0].localeCompare(b[0]))) {
    out.push(`${prefix}${d}/`);
    if (recursive) walk(sub, `${prefix}${d}/`, true, out);
  }
  for (const e of [...node.items].sort((a, b) => a.name.localeCompare(b.name))) out.push(`${prefix}${e.name}`);
}

export function createIlmcp(st, { RANGE, INVALID, makeChannel, nMixer, nSlots = 10 }) {
  const entries = catalog();
  const tree = buildTree(entries);
  const hl = highlightNames();
  const find = (name, kind) => entries.find((e) => e.name === name && e.kind === kind);
  st.prScripts ??= {};
  st.highlight ??= null;
  st.ilmcpLog ??= [];

  return {
    // 戻り: 指定パス直下 (recursive=0) / 全子孫 (1) のエントリ文字列 list。フォルダは末尾 "/"。パスは "Plugin database" 起点の相対表記。
    "ilmcp.getBrowserNames": (name, recursive) => {
      const parts = norm(name);
      if (parts[0] !== ROOT) throw INVALID(`Unknown browser path: ${name}`);
      let n = tree;
      for (const d of parts.slice(1)) {
        n = n.dirs.get(d);
        if (!n) throw INVALID(`Unknown browser path: ${name}`);
      }
      const out = [];
      walk(n, "", !!recursive, out);
      return out;
    },
    "ilmcp.getHighlightNames": () => hl.slice(),
    "ilmcp.showHighlight": (item, name, caption, whenDone, flag) => {
      st.highlight = { item, name, caption, cb: whenDone, flag };
      return true;
    },
    "ilmcp.forwardTutorialEvent": (...args) => { st.ilmcpLog.push(["forwardTutorialEvent", args.length]); return null; },
    // generator のみ受理 (get_browser_names の 'Plugin database' から得た名前)。戻り = 追加された 0 起点 index。
    "ilmcp.addChannel": (plugin) => {
      if (!find(plugin, "generator")) throw INVALID(`Unknown generator plugin: ${plugin}`);
      st.channels.push(makeChannel(plugin));
      return st.channels.length - 1;
    },
    "ilmcp.removeChannel": (i) => {
      if (!Number.isInteger(i) || i < 0 || i >= st.channels.length) throw RANGE();
      st.channels.splice(i, 1);
      return null;
    },
    "ilmcp.addEffect": (plugin, track, slot) => {
      if (!Number.isInteger(track) || track < 0 || track >= nMixer) throw RANGE();
      if (!Number.isInteger(slot) || slot < 0 || slot >= nSlots) throw RANGE();
      if (plugin !== "" && !find(plugin, "effect")) throw INVALID(`Unknown effect plugin: ${plugin}`);
      st.mixer[track].slots[slot] = plugin;
      st.mixer[track].spv[slot] = st.params.map((p) => p.v);
      return true;
    },
    "ilmcp.storePRScript": (name, source) => {
      if (typeof name !== "string" || !name || /[\\/:]/.test(name)) throw INVALID(`Invalid script name: ${name}`);
      st.prScripts[name] = source;
      return true;
    },
    // PY-5 (flpianoroll) が未実装のため実行はせず、受領ソースを保持して runner (PY-5 で登録) があれば委譲する。
    "ilmcp.runPRScript": (source) => {
      st.lastPRSource = source;
      if (typeof st.prRunner === "function") st.prRunner(source);
      st.ilmcpLog.push(["runPRScript", source.length]);
      return true;
    },
  };
}
