#!/usr/bin/env node
// FLP ブラウザ E2E (issue #112 / L-8)。tools/flp/web (parseFlp / writeFlp / dumpText / summarize を
// ブラウザで実行するハーネス) を build して静的配信し、ファイル入力 (file picker 相当の upload と
// drag&drop 相当の drop イベント) 経由で FL 同梱ファイルを渡して、ブラウザ側の結果を Node 側の
// 独立実行 (同じ src/ だが別ランタイム) と manifest (corpus/manifest.json) の両方と突合する。
//   node suite/flp.mjs [--driver agent-browser|puppeteer|both]
// 入力: E2E_FLP_WIN_DIR (fl-win64.tar.zst の extracted/) または FL_ROOT。無ければ SKIP (E2E_REQUIRE_FLP=1 で FAIL)。
// 出力: work/results/flp-<driver>.json, work/shots/flp-<driver>-*.png
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, mkdirSync, statSync, writeFileSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { dumpText } from "../../flp/src/format.ts";
import { parseFlp, writeFlp } from "../../flp/src/flp.ts";
import { summarize } from "../../flp/src/summary.ts";
import { resolveFixtures } from "./flp-fixtures.mjs";
import { E2E_DIR, REPO_ROOT } from "./servers.mjs";

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};
const driverOpt = opt("driver", process.env.E2E_DRIVER ?? "agent-browser");
const drivers = driverOpt === "both" ? ["agent-browser", "puppeteer"] : [driverOpt];
const chrome = process.env.E2E_CHROME ?? "/usr/bin/google-chrome";
const requireFlp = process.env.E2E_REQUIRE_FLP === "1";

const DIST = path.join(E2E_DIR, "work/flp-dist");
const shotsDir = path.join(E2E_DIR, "work/shots");
const resultsDir = path.join(E2E_DIR, "work/results");
mkdirSync(shotsDir, { recursive: true });
mkdirSync(resultsDir, { recursive: true });

const sha = (b) => createHash("sha256").update(b).digest("hex");
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css" };

function build() {
  const r = spawnSync(
    path.join(REPO_ROOT, "node_modules/.bin/vite"),
    ["build", path.join(REPO_ROOT, "tools/flp/web"), "--outDir", DIST, "--emptyOutDir", "--base", "./"],
    { cwd: REPO_ROOT, encoding: "utf8" },
  );
  if (r.status !== 0) throw new Error(`vite build 失敗:\n${r.stdout}${r.stderr}`);
}

function serve() {
  const server = http.createServer((req, res) => {
    const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = path.join(DIST, p === "/" ? "index.html" : p);
    let ok = file.startsWith(DIST + path.sep);
    try {
      ok &&= statSync(file).isFile();
    } catch {
      ok = false;
    }
    if (!ok) {
      res.writeHead(404).end("not found");
      return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
    createReadStream(file).pipe(res);
  });
  return new Promise((resolve) =>
    server.listen(0, "127.0.0.1", () =>
      resolve({
        url: `http://127.0.0.1:${server.address().port}`,
        stop: () => {
          server.closeAllConnections();
          server.close();
        },
      }),
    ),
  );
}

// Node 側の期待値 (ブラウザとは別プロセスで src/ を実行)
function expectedOf(fx) {
  const f = parseFlp(fx.buf);
  const out = writeFlp(f);
  const s = summarize(f);
  const dump = dumpText(f);
  return {
    inSha: sha(fx.buf),
    outSha: sha(out),
    events: f.events.length,
    version: s.version,
    tempo: s.tempo,
    channels: s.channels,
    patterns: s.patterns,
    notes: s.notes,
    dumpLen: dump.length,
    dumpSha: sha(Buffer.from(dump, "utf8")),
  };
}

const assert = (c, m) => {
  if (!c) throw new Error(m);
};

/** ブラウザ結果 got を Node 期待値 exp と manifest m に突合。不一致の説明配列を返す (空 = 一致) */
export function compare(got, exp, m) {
  const bad = [];
  const eq = (k, a, b) => a !== b && bad.push(`${k}: browser=${JSON.stringify(a)} expected=${JSON.stringify(b)}`);
  if (got.error) return [`parse error: ${got.error}`];
  eq("roundtrip", got.roundtrip, true);
  eq("inSha", got.inSha, exp.inSha);
  eq("outSha(=inSha)", got.outSha, exp.inSha);
  eq("outSha(node)", got.outSha, exp.outSha);
  for (const k of ["events", "version", "tempo", "channels", "patterns", "notes", "dumpLen", "dumpSha"]) eq(k, got[k], exp[k]);
  eq("warnings", got.warnings, 0);
  // manifest (別経路で生成済みの派生メタデータ) とも突合
  eq("manifest.events", got.events, m.events);
  eq("manifest.version", got.version, m.version);
  if (m.tempo !== undefined) eq("manifest.tempo", got.tempo, m.tempo);
  eq("manifest.channels", got.channels, m.channels);
  return bad;
}

const waitDone = (ctx, n, timeoutMs = 120000) =>
  ctx.drv.waitFn(`window.__flp && window.__flp.done && window.__flp.results.length === ${n}`, timeoutMs);

function makeChecks(fixtures) {
  const expected = fixtures.files.map(expectedOf);
  const checkAll = (results, files) => {
    assert(results.length === files.length, `結果件数 ${results.length} != ${files.length}`);
    const lines = [];
    results.forEach((got, i) => {
      const bad = compare(got, expected[i], files[i].manifest);
      assert(bad.length === 0, `${files[i].name}: ${bad.join("; ")}`);
      lines.push(`${got.name}(${got.size}B ${got.events}ev ${got.ms}ms)`);
    });
    return lines.join(" ");
  };
  return [
    {
      id: "flp-page-load",
      async run(ctx) {
        await ctx.drv.open(ctx.url + "/");
        assert(await ctx.drv.waitFn(`document.readyState==='complete' && !!window.__flp`), "ハーネスが起動しない (window.__flp 無し)");
        const t = await ctx.drv.eval("document.title");
        assert(t === "flp harness", `title=${t}`);
        const isolated = await ctx.drv.eval("typeof process === 'undefined' && typeof require === 'undefined'");
        assert(isolated, "ブラウザに node グローバルが存在する (node 依存ゼロの前提が崩れている)");
        return `title="${t}" (node グローバル無し)`;
      },
    },
    {
      id: "flp-file-input",
      async run(ctx) {
        const files = fixtures.files;
        await ctx.drv.upload("#flp-file", files.map((f) => f.abs));
        assert(await waitDone(ctx, files.length), "処理が完了しない (file input)");
        const got = JSON.parse(await ctx.drv.eval("JSON.stringify(window.__flp)"));
        assert(got.source === "input", `source=${got.source}`);
        const detail = checkAll(got.results, files);
        await ctx.shot("flp-input");
        return detail;
      },
    },
    {
      id: "flp-dump-view",
      async run(ctx) {
        const first = fixtures.files[0];
        const dump = dumpText(parseFlp(first.buf)).split("\n").slice(0, 200).join("\n");
        const shown = await ctx.drv.eval("document.getElementById('dump').textContent");
        assert(shown === dump, `画面のダンプが Node の dumpText と一致しない (先頭 ${first.name}, 画面 ${shown.length}B / 期待 ${dump.length}B)`);
        const status = await ctx.drv.eval("document.getElementById('status').textContent");
        assert(/異常 0 件/.test(status), `status=${status}`);
        const rows = await ctx.drv.eval("document.querySelectorAll('#summary tr').length");
        assert(rows === fixtures.files.length + 1, `summary 行数 ${rows}`);
        return `dump 先頭 ${first.name} ${dump.length}B 一致 / status="${status}" / 表 ${rows - 1} 行`;
      },
    },
    {
      id: "flp-drop",
      async run(ctx) {
        // 小さいファイルだけ drop 経由 (base64 を eval に載せるため)。DataTransfer で drop イベントを合成
        const files = fixtures.files.filter((f) => f.buf.length <= 400_000);
        assert(files.length >= 3, `drop 対象 ${files.length} 件`);
        const payload = files.map((f) => ({ name: f.name, b64: f.buf.toString("base64") }));
        await ctx.drv.eval(`(() => {
          const dt = new DataTransfer();
          for (const f of ${JSON.stringify(payload)}) {
            const bin = atob(f.b64); const u = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
            dt.items.add(new File([u], f.name));
          }
          document.getElementById('drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
          return true;
        })()`);
        assert(await waitDone(ctx, files.length), "処理が完了しない (drop)");
        const got = JSON.parse(await ctx.drv.eval("JSON.stringify(window.__flp)"));
        assert(got.source === "drop", `source=${got.source}`);
        const idx = files.map((f) => fixtures.files.indexOf(f));
        const results = got.results;
        assert(results.length === files.length, "drop 結果件数");
        const lines = results.map((r, i) => {
          const bad = compare(r, expected[idx[i]], files[i].manifest);
          assert(bad.length === 0, `${files[i].name}: ${bad.join("; ")}`);
          return `${r.name}(${r.size}B)`;
        });
        return lines.join(" ");
      },
    },
    {
      id: "flp-bad-input",
      async run(ctx) {
        // FLhd でないファイルは例外を握りつぶさず error として報告し、ページは落ちない
        await ctx.drv.eval(`(() => {
          const dt = new DataTransfer();
          dt.items.add(new File([new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16])], 'garbage.flp'));
          document.getElementById('drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
          return true;
        })()`);
        assert(await waitDone(ctx, 1), "処理が完了しない (bad input)");
        const r = JSON.parse(await ctx.drv.eval("JSON.stringify(window.__flp.results[0])"));
        assert(typeof r.error === "string" && /not an FLhd file/.test(r.error), `error=${r.error}`);
        return `error="${r.error}"`;
      },
    },
    {
      id: "flp-console-clean",
      async run(ctx) {
        const errs = await ctx.drv.pageErrors();
        assert(errs.length === 0, `pageerror: ${errs.join(" | ")}`);
        const bad = (await ctx.drv.consoleMessages()).filter(
          (m) => (m.type === "error" || m.type === "warning" || m.type === "warn") && !/\/favicon\.ico$/.test(m.url ?? ""),
        );
        assert(bad.length === 0, `想定外 console: ${bad.map((m) => `[${m.type}] ${m.text}`).join(" | ")}`);
        return "pageerror=0, console error/warning=0";
      },
    },
    {
      // ネガティブコントロール: ?sabotage で書込結果を 1 byte 壊したページを読み、検出器 (compare) が FAIL を返すこと
      id: "flp-negative-control",
      async run(ctx) {
        await ctx.drv.open(ctx.url + "/?sabotage");
        assert(await ctx.drv.waitFn(`!!window.__flp`), "sabotage ページが起動しない");
        const f = fixtures.files[0];
        await ctx.drv.upload("#flp-file", [f.abs]);
        assert(await waitDone(ctx, 1), "処理が完了しない (negative)");
        const got = JSON.parse(await ctx.drv.eval("JSON.stringify(window.__flp.results[0])"));
        const bad = compare(got, expectedOf(f), f.manifest);
        assert(bad.length > 0, "壊した出力が検出されない (検出器が無効)");
        assert(bad.some((b) => b.startsWith("roundtrip") || b.startsWith("outSha")), `期待した不一致種別なし: ${bad.join("; ")}`);
        return `${f.name} 1 byte 破壊 -> 検出 ${bad.length} 項目 (${bad[0]})`;
      },
    },
  ];
}

async function runDriver(driverName, fixtures, url) {
  const mod = await import(`./drivers/${driverName}.mjs`);
  const drv = await mod.createDriver({ chrome, session: `webstudio-flp-${process.pid}-${driverName}` });
  const tag = `flp-${driverName}`;
  const ctx = {
    url,
    drv,
    async shot(name) {
      await drv.screenshot(path.join(shotsDir, `${tag}-${name}.png`));
    },
  };
  console.log(`\n=== flp driver=${drv.name} (${drv.version}) url=${url} fixtures=${fixtures.files.length} (${fixtures.source})`);
  const results = [];
  let failed = 0;
  try {
    for (const c of makeChecks(fixtures)) {
      const t0 = Date.now();
      let status = "PASS";
      let detail = "";
      try {
        detail = (await c.run(ctx)) ?? "";
      } catch (e) {
        status = "FAIL";
        detail = e?.message ?? String(e);
        failed++;
      }
      const ms = Date.now() - t0;
      results.push({ id: c.id, status, detail, ms });
      console.log(`${status.padEnd(4)} ${c.id.padEnd(22)} ${String(ms).padStart(6)}ms  ${detail}`);
    }
  } finally {
    await drv.close();
  }
  writeFileSync(path.join(resultsDir, `${tag}.json`), JSON.stringify({ driver: drv.name, driverVersion: drv.version, results }, null, 2));
  return { failed, pass: results.filter((r) => r.status === "PASS").length };
}

const fixtures = resolveFixtures();
if (!fixtures) {
  const msg = "FLP フィクスチャ無し (E2E_FLP_WIN_DIR=<fl-win64 の extracted/> または FL_ROOT を指定)";
  console.log(`${requireFlp ? "FAIL" : "SKIP"} ${msg}`);
  process.exit(requireFlp ? 1 : 0);
}

const t0 = Date.now();
build();
console.log(`vite build tools/flp/web -> ${path.relative(REPO_ROOT, DIST)} (${Date.now() - t0}ms)`);
const server = await serve();
let failed = 0;
let pass = 0;
try {
  for (const d of drivers) {
    try {
      const r = await runDriver(d, fixtures, server.url);
      failed += r.failed;
      pass += r.pass;
    } catch (e) {
      failed++;
      console.log(`FAIL runner driver=${d}: ${e.stack ?? e}`);
    }
  }
} finally {
  server.stop();
}
console.log(`\nSUMMARY: PASS=${pass} FAIL=${failed} (suite=flp drivers=${drivers.join(",")} fixtures=${fixtures.files.length} source=${fixtures.source})`);
process.exit(failed ? 1 : 0);
