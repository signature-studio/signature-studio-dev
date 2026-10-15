// E2E チェック定義。ドライバ非依存 (drv は suite/drivers/* の共通 IF)。
//   throw Error      -> FAIL
//   throw new Skip() -> SKIP
//   return string    -> PASS の詳細
import {
  applyRequestRewrite,
  applyResponseHeaders,
  contentTypeFor,
} from "../../../deploy/lib/policy.mjs";

export class Skip extends Error {}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function assertEq(actual, expected, what) {
  assert(actual === expected, `${what}: 期待 ${JSON.stringify(expected)} / 実際 ${JSON.stringify(actual)}`);
}

async function http(ctx, p, init = {}) {
  const r = await fetch(new URL(p, ctx.url), {
    redirect: "manual",
    ...init,
    headers: { ...ctx.headers, ...(init.headers ?? {}) },
  });
  if (r.status >= 300 && r.status < 400) {
    throw new Error(
      `${p}: リダイレクト ${r.status} -> ${r.headers.get("location")} ` +
        "(Cloudflare Access ログインなら E2E_ACCESS_CLIENT_ID/SECRET を指定)",
    );
  }
  return r;
}

const STATUS_JS = `document.getElementById('status')?.textContent ?? ''`;

export const checks = [
  {
    id: "headers-isolation",
    title: "ドキュメントと worklet が COOP same-origin / COEP require-corp を返す",
    async run(ctx) {
      for (const p of ["/", "/worklets/fl-audio-worklet.js"]) {
        const r = await http(ctx, p);
        assertEq(r.status, 200, `${p} status`);
        assertEq(r.headers.get("cross-origin-opener-policy"), "same-origin", `${p} COOP`);
        assertEq(r.headers.get("cross-origin-embedder-policy"), "require-corp", `${p} COEP`);
      }
      return "COOP=same-origin COEP=require-corp (/, /worklets/fl-audio-worklet.js)";
    },
  },
  {
    id: "edge-policy",
    title: "配信ポリシー (CORP/Cache-Control/Content-Type/圧縮/index rewrite/R2 同様の 404) を満たす",
    async run(ctx) {
      if (!ctx.target.strict) throw new Skip("strict ターゲット (edge-sim / remote) のみ");
      const policy = ctx.policy;
      const html = await (await http(ctx, "/")).text();
      const jsPath = /src="(\/assets\/[^"]+\.js)"/.exec(html)?.[1];
      assert(jsPath, "index.html から /assets/*.js を取得できない");
      const probes = ["/", "/index.html", jsPath, "/worklets/fl-audio-worklet.js", "/__e2e__/add.wasm"];
      const notes = [];
      for (const p of probes) {
        const r = await http(ctx, p, { headers: { "Accept-Encoding": "br, zstd, gzip" } });
        if (p === "/__e2e__/add.wasm" && r.status === 404) {
          notes.push("add.wasm 未配置(skip)");
          continue;
        }
        assertEq(r.status, 200, `${p} status`);
        const eff = applyRequestRewrite(policy, p);
        const want = applyResponseHeaders(policy, { path: eff, status: 200 }, {});
        for (const [k, v] of Object.entries(want)) {
          assertEq(r.headers.get(k), v, `${p} ${k}`);
        }
        const wantCt = contentTypeFor(policy, eff);
        assertEq(r.headers.get("content-type"), wantCt, `${p} content-type`);
        await r.arrayBuffer();
      }
      // 圧縮: JS (1KB 超) は何らかの Content-Encoding が付く
      const rj = await http(ctx, jsPath, { headers: { "Accept-Encoding": "br" } });
      const enc = rj.headers.get("content-encoding");
      await rj.arrayBuffer();
      if (ctx.target.name === "edge-sim") assertEq(enc, "br", `${jsPath} content-encoding`);
      else notes.push(`content-encoding=${enc ?? "なし"}`);
      // R2 カスタムドメインは SPA fallback / 暗黙 index を持たない
      const r404 = await http(ctx, "/__no_such_object__");
      assertEq(r404.status, 404, "存在しないキーは 404");
      return `probes=${probes.length} br=${enc} ${notes.join(" ")}`.trim();
    },
  },
  {
    id: "page-load",
    title: "ページを開き、ハーネスが起動表示に至る",
    async run(ctx) {
      await ctx.drv.open(ctx.url);
      const ok = await ctx.drv.waitFn(
        `document.readyState === 'complete' && !(${STATUS_JS}).includes('確認中')`,
      );
      assert(ok, "ステータス表示が確認中のまま (index.ts が起動していない)");
      const title = await ctx.drv.eval("document.title");
      assertEq(title, "webstudio harness", "title");
      return `title="${title}"`;
    },
  },
  {
    id: "cross-origin-isolated",
    title: "crossOriginIsolated=true / SharedArrayBuffer が生成可能",
    async run(ctx) {
      const r = await ctx.drv.eval(`(() => {
        let canSab = false;
        try { new SharedArrayBuffer(16); canSab = true; } catch {}
        return { coi: crossOriginIsolated, sab: typeof SharedArrayBuffer,
                 canSab, secure: isSecureContext, atomicsWait: typeof Atomics.wait,
                 status: document.getElementById('status').textContent };
      })()`);
      assertEq(r.coi, true, "crossOriginIsolated");
      assertEq(r.sab, "function", "typeof SharedArrayBuffer");
      assert(r.canSab, "new SharedArrayBuffer() が失敗");
      assert(r.secure, "isSecureContext=false");
      assert(r.status.includes("有効"), `ステータス表示が有効でない: ${r.status}`);
      return `crossOriginIsolated=true, SAB OK, secure=${r.secure}`;
    },
  },
  {
    id: "wasm-load",
    title: "wasm ロード: アプリ内 smoke (add(40,2)=42) + instantiateStreaming (MIME application/wasm)",
    async run(ctx) {
      const find = `[...document.querySelectorAll('div')].map(d => d.textContent).find(t => t.startsWith('wasm smoke')) ?? ''`;
      const ok = await ctx.drv.waitFn(`(${find}).startsWith('wasm smoke: OK')`);
      const text = await ctx.drv.eval(find);
      assert(ok, `アプリ内 wasm smoke が OK にならない: "${text}"`);
      assert(text.includes("add(40,2)=42"), `smoke 結果不正: ${text}`);
      const s = await ctx.drv.eval(`(async () => {
        const r = await fetch('/__e2e__/add.wasm');
        const ct = r.headers.get('content-type');
        if (!r.ok || ct !== 'application/wasm') return { status: r.status, ct };
        const { instance } = await WebAssembly.instantiateStreaming(r);
        return { status: 200, ct, add: instance.exports.add(40, 2) };
      })()`);
      // dev / remote は fixture を持たない (dev は SPA fallback が text/html を返す)
      const hasFixture = ctx.target.name === "preview" || ctx.target.name === "edge-sim";
      if (!hasFixture && s.ct !== "application/wasm") {
        return `${text} / fixture 未配置 (status=${s.status} ct=${s.ct}) のため instantiateStreaming は skip`;
      }
      assertEq(s.status, 200, "/__e2e__/add.wasm status");
      assertEq(s.ct, "application/wasm", "wasm Content-Type");
      assertEq(s.add, 42, "add(40,2)");
      return `${text} / instantiateStreaming OK (ct=${s.ct})`;
    },
  },
  {
    id: "canvas-render",
    title: "Canvas 描画: 全画面 canvas に putImageData したフレームが読み戻せる",
    async run(ctx) {
      const r = await ctx.drv.eval(`(() => {
        const c = document.getElementById('screen');
        const g = c.getContext('2d');
        const d = g.getImageData(0, 0, c.width, c.height).data;
        const seen = new Set(); let lit = 0;
        for (let i = 0; i < d.length; i += 4) {
          if (d[i] > 0) lit++;
          if (seen.size < 8) seen.add((d[i] << 16) | (d[i+1] << 8) | d[i+2]);
        }
        return { w: c.width, h: c.height, lit, colors: seen.size };
      })()`);
      assert(r.w > 0 && r.h > 0, `canvas サイズ 0: ${r.w}x${r.h}`);
      assert(r.lit > 0, "putImageData したピクセルが読み戻せない (全面黒)");
      assert(r.colors >= 2, "色数 < 2");
      await ctx.shot("canvas");
      return `${r.w}x${r.h}, lit=${r.lit}px, colors>=${r.colors}`;
    },
  },
  {
    id: "audioworklet",
    title: "AudioWorklet 起動: クリックで worklet が走り samplePos が 128f 単位で進む",
    async run(ctx) {
      const disabled = await ctx.drv.eval(`document.getElementById('start-audio').disabled`);
      assertEq(disabled, false, "start-audio ボタンが有効 (isolated 時のみ有効化される)");
      await ctx.drv.click("#start-audio");
      const pos = `(() => { const m = /samplePos=(\\d+)/.exec(${STATUS_JS}); return m ? +m[1] : -1; })()`;
      assert(
        await ctx.drv.waitFn(`${pos} > 0`, 20000),
        `samplePos が進まない (worklet 未起動): ${await ctx.drv.eval(STATUS_JS)}`,
      );
      const t0 = Date.now();
      const p1 = await ctx.drv.eval(pos);
      assert(
        await ctx.drv.waitFn(`${pos} > ${p1} + 4800`, 20000),
        `samplePos が増加しない (p1=${p1})`,
      );
      const p2 = await ctx.drv.eval(pos);
      const dt = (Date.now() - t0) / 1000;
      assertEq(p1 % 128, 0, "samplePos#1 が 128f 倍数");
      assertEq(p2 % 128, 0, "samplePos#2 が 128f 倍数");
      const rate = Math.round((p2 - p1) / dt);
      assert(rate > 10000, `samplePos 進行が遅すぎる: ${rate}/s`);
      const st = await ctx.drv.eval(STATUS_JS);
      assert(st.includes("worklet 実行中"), `ステータス: ${st}`);
      await ctx.shot("audio");
      return `samplePos ${p1} -> ${p2} (${rate} frames/s, 128f 単位)`;
    },
  },
  {
    id: "console-clean",
    title: "uncaught エラー無し / 想定外の console error・warning 無し",
    async run(ctx) {
      const errs = await ctx.drv.pageErrors();
      assertEq(errs.length, 0, `pageerror: ${errs.join(" | ")}`);
      // index.ts の fail-fast フォワーダ疎通テストが意図的に出す 1 件のみ許容
      const allow = [/\[imports\] 未実装 import が呼ばれました: "shim_port\.not_implemented_yet"/];
      // ブラウザが自動要求する /favicon.ico の 404 (ハーネスは favicon を持たない) も許容
      const bad = (await ctx.drv.consoleMessages()).filter(
        (m) =>
          (m.type === "error" || m.type === "warning" || m.type === "warn") &&
          !allow.some((a) => a.test(m.text)) &&
          !/\/favicon\.ico$/.test(m.url ?? ""),
      );
      assert(bad.length === 0, `想定外 console: ${bad.map((m) => `[${m.type}] ${m.text} ${m.url ?? ""}`).join(" | ")}`);
      return "pageerror=0, 想定外 console error/warning=0";
    },
  },
  {
    id: "webstudio-contract",
    title: "window.__webstudio 契約の形状 ({state: booting|running|error, frames: number})",
    async run(ctx) {
      const st = await ctx.drv.eval(`JSON.stringify(window.__webstudio ?? null)`);
      const s = JSON.parse(st);
      assert(s !== null, "window.__webstudio が公開されていない");
      assert(["booting", "running", "error"].includes(s.state), `state が契約外: ${st}`);
      assertEq(typeof s.frames, "number", "frames の型");
      assert(s.frames >= 0, `frames < 0: ${st}`);
      if (s.state === "error") assertEq(typeof s.error, "string", "error の型 (state=error 時)");
      else assert(s.error === undefined, `state=${s.state} なのに error がある: ${st}`);
      // FL 未統合ハーネスは GUI フレームを転送しないので running にならない (running には frames>0 が必要)
      if (s.state === "running") assert(s.frames > 0, `running なのに frames=0: ${st}`);
      return st;
    },
  },
  {
    id: "fl-boot",
    title: "FL 起動 (契約: window.__webstudio.state==='running' && frames>0)",
    async run(ctx) {
      if (process.env.E2E_REQUIRE_FL !== "1") {
        throw new Skip("FL 未統合 (統合後 E2E_REQUIRE_FL=1。契約は REPORT.md §FL 起動契約)");
      }
      const ok = await ctx.drv.waitFn(
        `window.__webstudio?.state === 'running' || window.__webstudio?.state === 'error'`,
        180000,
      );
      const st = await ctx.drv.eval(`JSON.stringify(window.__webstudio ?? null)`);
      assert(ok, `FL が 180s 以内に running にならない: ${st}`);
      const s = JSON.parse(st);
      // D5: テストゲスト (guest: "test") では FL の起動として PASS させない
      assertEq(s.guest, "fl", `ゲスト種別 (テストゲストでは fl-boot を PASS させない: ${st})`);
      assertEq(s.state, "running", `state (${st})`);
      assert(typeof s.frames === "number" && s.frames > 0, `GUI フレーム 0: ${st}`);
      // 画素検査: 転送済みフレームが canvas に載っている (全面単色でない)。
      // OffscreenCanvas 移譲後の canvas は getContext 不可なので temp canvas へ drawImage して読む
      const px = await ctx.drv.eval(`(() => {
        const c = document.getElementById('screen');
        const t = document.createElement('canvas');
        t.width = c.width; t.height = c.height;
        const g = t.getContext('2d');
        g.drawImage(c, 0, 0);
        const d = g.getImageData(0, 0, t.width, t.height).data;
        const seen = new Set(); let lit = 0;
        for (let i = 0; i < d.length; i += 4) {
          if (d[i] | d[i+1] | d[i+2]) lit++;
          if (seen.size < 8) seen.add((d[i] << 16) | (d[i+1] << 8) | d[i+2]);
        }
        return { w: t.width, h: t.height, lit, colors: seen.size };
      })()`);
      assert(px.w > 0 && px.h > 0, `canvas サイズ 0: ${px.w}x${px.h}`);
      assert(px.lit > 0 && px.colors >= 2, `FL フレームが canvas に描画されていない: ${JSON.stringify(px)}`);
      await ctx.shot("fl");
      return `${st} canvas ${px.w}x${px.h} lit=${px.lit}px colors>=${px.colors}`;
    },
  },
  {
    id: "gui-guest-boot",
    title: "製品ページ gui=wasm: テストゲスト (chunked・FL 以外) が GuiHost 経由で GUI canvas に描画 (state==='running' && frames>0)",
    async run(ctx) {
      const q = "/?gui=wasm&glue=/__e2e__/gui-guest/app.js&app=/__e2e__/gui-guest/app.wasm.parts/index.json";
      await ctx.drv.open(new URL(q, ctx.url).href);
      const ok = await ctx.drv.waitFn(
        `window.__webstudio?.state === 'running' || window.__webstudio?.state === 'error'`,
        180000,
      );
      const st = await ctx.drv.eval(`JSON.stringify(window.__webstudio ?? null)`);
      assert(ok, `テストゲストが 180s 以内に running にならない: ${st}`);
      const s = JSON.parse(st);
      assertEq(s.state, "running", `state (${st})`);
      assertEq(s.guest, "test", `guest (${st})`);
      assert(typeof s.frames === "number" && s.frames > 0, `GUI フレーム 0: ${st}`);
      // 画素検査: GuiHost の readback (worker 側の canvas 内容) を読み、全面単色でないことを見る
      const px = await ctx.drv.eval(`(async () => {
        const r = await window.__guiGuest.readback();
        const seen = new Set(); let lit = 0;
        for (let i = 0; i < r.data.length; i += 4) {
          if (r.data[i] | r.data[i+1] | r.data[i+2]) lit++;
          if (seen.size < 8) seen.add((r.data[i] << 16) | (r.data[i+1] << 8) | r.data[i+2]);
        }
        return { w: r.width, h: r.height, lit, colors: seen.size };
      })()`);
      assert(px.w > 0 && px.h > 0, `canvas サイズ 0: ${px.w}x${px.h}`);
      assert(px.lit > 0 && px.colors >= 2, `テストゲストのフレームが描画されていない: ${JSON.stringify(px)}`);
      await ctx.shot("gui-guest");
      return `${st} canvas ${px.w}x${px.h} lit=${px.lit}px colors>=${px.colors}`;
    },
  },
  {
    id: "gui-guest-tamper",
    title: "ネガコン (gui=wasm): chunked の part 1 バイト改竄は sha256 検証で停止 (state=error・running にならない)",
    async run(ctx) {
      const q = "/?gui=wasm&glue=/__e2e__/gui-guest/app.js&app=/__e2e__/gui-guest/tampered/app.wasm.parts/index.json";
      await ctx.drv.open(new URL(q, ctx.url).href);
      const ok = await ctx.drv.waitFn(
        `window.__webstudio?.state === 'running' || window.__webstudio?.state === 'error'`,
        60000,
      );
      const st = await ctx.drv.eval(`JSON.stringify(window.__webstudio ?? null)`);
      assert(ok, `改竄ゲストの判定が 60s 以内に出ない: ${st}`);
      const s = JSON.parse(st);
      assertEq(s.state, "error", `改竄 part が error にならない: ${st}`);
      // Chrome は compileStreaming で stream の中身の例外 (sha256 不一致の ChunkIntegrityError) を包む。原因の文言は見えない。
      // 原因の同定は chunked.mjs 側の単体テスト (deploy/client/chunked.test.mjs) と同じ改竄 descriptor を node で読んだ結果 (REPORT)。
      assert(/WebAssembly compilation aborted/.test(s.error ?? ""), `error が compile 中断ではない: ${st}`);
      assertEq(s.frames, 0, `改竄ゲストで frames が進んだ: ${st}`);
      return st;
    },
  },
];
