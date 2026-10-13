/**
 * help_panel.ts — FL Help を sandbox iframe に表示するパネルと window.flHelp (ST-T8 #118)。純ロジックは help_viewer.ts。
 *   devtools:  flHelp.setFiles(...) → await flHelp.open("C:\\Program Files\\Image-Line\\FL Studio 2026\\Help\\index_offline.html")
 *   UI:        /?help=1 で左下にパネル (FL の Help フォルダを選択 or ドロップ)
 * Help の HTML は利用者の FL インストールから実行時に供給する (リポジトリ・配信物に非同梱)。外部通信なし・外部リンクは辿らない。
 * FL エンジンからの結線 (ShellExecuteW の shell hook → flHelp.shellExecute) は tools/startup/helpviewer/REPORT.md の未解決を参照。
 */
import {
  HELP_INDEX,
  buildNoticeSrcdoc,
  classifyShellExecute,
  classifyTarget,
  filesFromMap,
  prepareHelpPage,
  resolveLink,
  type HelpFiles,
  type HelpTarget,
  type NoticeKind,
  type ShellExecuteDecision,
} from "./help_viewer";

export type HelpEvent =
  | { type: "page"; path: string; title: string; inlined: number; missing: number; externalBlocked: number }
  | { type: "notice"; kind: NoticeKind; detail: string }
  | { type: "external-blocked"; url: string };

export type FlHelp = {
  /** 供給元を差し替える。Map は Help/ 相対パス (`html/FD/web/index.html`) → バイト列 */
  setFiles(files: HelpFiles | Map<string, Uint8Array>): void;
  /** FileList (`<input webkitdirectory>` / ドロップ) から供給する。`Help` 階層を自動検出 */
  setFileList(list: FileList | File[]): Promise<number>;
  /** 配信済みの Help を fetch で読む (404 = 無し)。base 例: "/fl/Help/" */
  useHttp(base: string): void;
  /** FL が渡す絶対ターゲット (Windows パス / file: / http(s)) を開く */
  open(target: string): Promise<HelpEvent>;
  /** ShellExecuteW(verb, file) の入口。Help 配下 / http(s) なら処理して ShellExecuteW の戻り値 (33) を返す。無関係なら null */
  shellExecute(verb: string | null, file: string): Promise<number | null>;
  back(): Promise<HelpEvent | null>;
  forward(): Promise<HelpEvent | null>;
  close(): void;
  /** パネルの `<iframe>` (mountHelpPanel 済みなら)。テスト用 */
  readonly frame: HTMLIFrameElement | null;
  readonly history: readonly string[];
  lang: "en" | "ja";
  /** 外部リンクをクリックされたときの通知口。既定は何もしない (外部通信なし)。 */
  onExternal: (url: string) => void;
  onEvent: (e: HelpEvent) => void;
};

declare global {
  interface Window {
    flHelp?: FlHelp;
  }
}

function httpFiles(base: string): HelpFiles {
  const b = base.endsWith("/") ? base : `${base}/`;
  return {
    async read(p) {
      const r = await fetch(b + p.split("/").map(encodeURIComponent).join("/"), { credentials: "same-origin" });
      if (!r.ok) return null;
      return new Uint8Array(await r.arrayBuffer());
    },
  };
}

/** `Help/` 階層を探して Help 相対パスの Map にする。`Help` 要素が無ければ選択フォルダ自体を Help とみなす */
async function mapFromFileList(list: FileList | File[]): Promise<Map<string, Uint8Array>> {
  const m = new Map<string, Uint8Array>();
  for (const f of Array.from(list)) {
    const rel = ((f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name).replace(/\\/g, "/").split("/");
    const i = rel.findIndex((s) => s.toLowerCase() === "help");
    const inner = i >= 0 ? rel.slice(i + 1) : rel.length > 1 ? rel.slice(1) : rel;
    if (inner.length) m.set(inner.join("/"), new Uint8Array(await f.arrayBuffer()));
  }
  return m;
}

export function installFlHelp(): FlHelp {
  if (window.flHelp) return window.flHelp;
  let files: HelpFiles | null = null;
  let frame: HTMLIFrameElement | null = null;
  let token = "";
  let current: string | null = null;
  const hist: string[] = [];
  let pos = -1;

  const showNotice = (kind: NoticeKind, detail = ""): HelpEvent => {
    token = "";
    if (frame) frame.srcdoc = buildNoticeSrcdoc(kind, api.lang, detail);
    const ev: HelpEvent = { type: "notice", kind, detail };
    api.onEvent(ev);
    return ev;
  };

  const showPage = async (path: string, fragment: string, depth = 0): Promise<HelpEvent> => {
    if (!files) return showNotice("no-files");
    const page = await prepareHelpPage(files, path, { fragment });
    if (!page) return showNotice("not-found", path);
    if (page.refresh && depth < 3) {
      const r = resolveLink(path, page.refresh);
      if (r.kind === "help" && r.path !== path) return showPage(r.path, r.fragment, depth + 1);
    }
    token = page.token;
    current = path;
    if (frame) {
      frame.srcdoc = page.srcdoc;
    }
    const ev: HelpEvent = {
      type: "page",
      path,
      title: page.title,
      inlined: page.stats.inlinedResources,
      missing: page.stats.missingResources.length,
      externalBlocked: page.stats.externalRefsBlocked,
    };
    api.onEvent(ev);
    return ev;
  };

  const go = async (t: HelpTarget, push: boolean): Promise<HelpEvent> => {
    switch (t.kind) {
      case "help": {
        const ev = await showPage(t.path, t.fragment);
        if (ev.type === "page" && push) {
          hist.splice(pos + 1);
          if (hist[hist.length - 1] !== ev.path) hist.push(ev.path);
          pos = hist.length - 1;
        }
        return ev;
      }
      case "offline-notice":
        return showNotice("offline");
      case "external": {
        const ev: HelpEvent = { type: "external-blocked", url: t.url };
        api.onExternal(t.url);
        api.onEvent(ev);
        return ev;
      }
      default:
        return showNotice("unsupported", t.reason);
    }
  };

  const onMessage = (e: MessageEvent): void => {
    const d = e.data as { flHelp?: string; href?: string } | null;
    if (!frame || e.source !== frame.contentWindow || !d || typeof d.href !== "string" || !token || d.flHelp !== token || current === null) return;
    void go(resolveLink(current, d.href), true);
  };
  window.addEventListener("message", onMessage);

  const api: FlHelp = {
    lang: /^ja/i.test(navigator.language) ? "ja" : "en",
    onExternal: () => {},
    onEvent: () => {},
    setFiles(f) {
      files = f instanceof Map ? filesFromMap(f) : f;
    },
    async setFileList(list) {
      const m = await mapFromFileList(list);
      files = filesFromMap(m);
      return m.size;
    },
    useHttp(base) {
      files = httpFiles(base);
    },
    open: (target) => go(classifyTarget(target), true),
    async shellExecute(verb, file) {
      const d: ShellExecuteDecision = classifyShellExecute(verb, file);
      if (d.action === "pass") return null;
      if (d.action === "help") await go(d.target, true);
      else api.onExternal(d.url);
      return d.result;
    },
    async back() {
      if (pos <= 0) return null;
      pos--;
      return showPage(hist[pos]!, "");
    },
    async forward() {
      if (pos >= hist.length - 1) return null;
      pos++;
      return showPage(hist[pos]!, "");
    },
    close() {
      frame?.closest<HTMLElement>("#help-panel")?.remove();
      frame = null;
    },
    get frame() {
      return frame;
    },
    get history() {
      return hist;
    },
  };
  (api as unknown as { _bind: (f: HTMLIFrameElement | null) => void })._bind = (f) => {
    frame = f;
  };
  window.flHelp = api;
  return api;
}

export function mountHelpPanel(): void {
  const api = installFlHelp() as FlHelp & { _bind(f: HTMLIFrameElement | null): void };
  const panel = document.createElement("div");
  panel.id = "help-panel";
  panel.style.cssText =
    "position:fixed;left:12px;bottom:12px;z-index:20;width:min(720px,70vw);height:min(560px,70vh);display:flex;flex-direction:column;background:#000c;padding:8px;font:12px/1.4 monospace;color:#cfe;border:1px solid #345";
  panel.innerHTML = `
    <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
      <b>FL Help</b> <span style="opacity:.7">(ローカル / 外部通信なし)</span>
      <button id="help-back">◀</button><button id="help-fwd">▶</button><button id="help-home">Help</button>
      <input id="help-files" type="file" webkitdirectory multiple style="max-width:260px">
      <span id="help-state" style="flex:1"></span><button id="help-close">✕</button>
    </div>
    <iframe id="help-frame" sandbox="allow-scripts" referrerpolicy="no-referrer" style="flex:1;border:0;background:#fff"></iframe>`;
  document.body.appendChild(panel);
  const $ = <T extends HTMLElement>(id: string) => panel.querySelector<T>(`#${id}`)!;
  const state = $("help-state");
  const frame = $<HTMLIFrameElement>("help-frame");
  api._bind(frame);
  frame.srcdoc = buildNoticeSrcdoc("no-files", api.lang);
  api.onEvent = (e) => {
    state.textContent =
      e.type === "page" ? `${e.path} — ${e.title || "(no title)"} / 埋込 ${e.inlined}・欠落 ${e.missing}・外部遮断 ${e.externalBlocked}` : e.type === "notice" ? `${e.kind} ${e.detail}` : `外部リンク遮断: ${e.url}`;
  };
  const ingest = async (list: FileList | File[]) => {
    const n = await api.setFileList(list);
    state.textContent = `${n} ファイル供給`;
    if (n) void api.open(`C:/Program Files/Image-Line/FL Studio 2026/Help/${HELP_INDEX}`);
  };
  $<HTMLInputElement>("help-files").addEventListener("change", (e) => void ingest((e.target as HTMLInputElement).files ?? []));
  panel.addEventListener("dragover", (e) => e.preventDefault());
  panel.addEventListener("drop", (e) => {
    e.preventDefault();
    void ingest(e.dataTransfer?.files ?? []);
  });
  $("help-back").addEventListener("click", () => void api.back());
  $("help-fwd").addEventListener("click", () => void api.forward());
  $("help-home").addEventListener("click", () => void api.open(`C:/Program Files/Image-Line/FL Studio 2026/Help/${HELP_INDEX}`));
  $("help-close").addEventListener("click", () => api.close());
}
