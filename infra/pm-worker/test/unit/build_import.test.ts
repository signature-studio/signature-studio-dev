import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { ALLOW_ARTS } from "../../src/launch.ts";
import { MAX_IMPORT_BYTES, parseVmState } from "../../src/vmstate.ts";
import * as script from "../../scripts/build_import.mjs";

// 取り込みの本文を作るスクリプト (#2799)。出力は Worker 自身の検証 (parseVmState) を通すことを確かめる。
const SCRIPT = join(import.meta.dirname, "..", "..", "scripts", "build_import.mjs");
const NOW = Date.parse("2026-10-14T12:00:00Z");
const phase = { review_only: false, open_prs: 4, since: "2026-10-14T10:00:00.123456+00:00" };
const launched = { "11": "2026-10-14T11:50:00.000000+00:00" };
const relaunch = {
  "11": { count: 1, art: "oc_artifacts: none fl-win64" }, // none と名前の混在 (launch_issues.py の cand の形)
  "14": { count: 0, art: "oc_artifacts: fetchsh (説明)" }, // 全部落ちる → art null
  "15": { count: 2, art: "oc_artifacts: fl-win64 plugins-ott（kilohearts の確認は後で）" }, // 全角の括弧書き
};
const state = {
  pm_art: {
    "12": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fl-win64 plugins-ott (解析用の素材。PM が指定)" },
    "13": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fetchsh" }, // 全部落ちる → 行ごと除く
    "16": { at: "2026-10-13T10:00:00Z", line: "`oc_artifacts: none`" },
  },
};

const tmp = mkdtempSync(join(tmpdir(), "build-import-"));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));

const runCli = (args: string[]) => spawnSync(process.execPath, [SCRIPT, ...args], { encoding: "utf8" });
const writeJson = (name: string, v: unknown) => {
  const p = join(tmp, name);
  writeFileSync(p, JSON.stringify(v, null, 2));
  return p;
};
const cliArgs = (
  v: { launched?: unknown; relaunch?: unknown; state?: unknown; phase?: unknown } = {},
  tag = "base",
): string[] => [
  "--launched", writeJson(`${tag}-l.json`, v.launched ?? launched),
  "--relaunch", writeJson(`${tag}-r.json`, v.relaunch ?? relaunch),
  "--state", writeJson(`${tag}-s.json`, v.state ?? state),
  "--export", writeJson(`${tag}-e.json`, { phase: v.phase === undefined ? phase : v.phase }),
];

describe("build_import: 定数の突き合わせ", () => {
  it("許可リストと上限は src/ と同じ (スクリプトの複製が食い違わない)", () => {
    expect(script.ALLOW_ARTS).toEqual([...ALLOW_ARTS]);
    expect(script.MAX_IMPORT_BYTES).toBe(MAX_IMPORT_BYTES);
    expect(MAX_IMPORT_BYTES).toBe(200 * 1024);
  });
});

describe("build_import: 素材行の正規化", () => {
  it.each([
    ["oc_artifacts: fl-win64 plugins-ott", "oc_artifacts: fl-win64 plugins-ott", []],
    ["oc_artifacts: fl-win64 plugins-ott (解析用の素材)", "oc_artifacts: fl-win64 plugins-ott", []],
    ["oc_artifacts: fl-win64 (plugins-ott は後で)", "oc_artifacts: fl-win64", []],
    ["oc_artifacts: fl-win64 plugins-ott（全角の括弧）", "oc_artifacts: fl-win64 plugins-ott", []],
    ["oc_artifacts: none fl-win64", "oc_artifacts: fl-win64", []],
    ["oc_artifacts: none", "oc_artifacts: none", []],
    ["oc_artifacts: none fetchsh", "oc_artifacts: none", ["fetchsh"]],
    ["`oc_artifacts: fl-win64, toolchain-emsdk`", "oc_artifacts: fl-win64 toolchain-emsdk", []],
    ["oc_artifacts: fl-win64 fl-win64 plugins-ott", "oc_artifacts: fl-win64 plugins-ott", []],
    ["oc_artifacts: fl-win64 fetchsh", "oc_artifacts: fl-win64", ["fetchsh"]],
    ["oc_artifacts: fetchsh (説明)", null, ["fetchsh"]],
    ["oc_artifacts: (説明だけ)", null, []],
    ["fl-win64", null, ["fl-win64"]],
  ])("%s", (raw, line, dropped) => {
    expect(script.normalizeArtLine(raw)).toEqual({ line, dropped });
  });
});

describe("build_import: 本文の組み立て", () => {
  const out = script.buildImport({ launched, relaunch, state, phase }) as any;

  it("正規化した値になる (relaunch.art の全落ちは null・count は残す / pm_art の全落ちは行ごと除く)", () => {
    expect(out).toEqual({
      launched,
      relaunch: {
        "11": { count: 1, art: "oc_artifacts: fl-win64" },
        "14": { count: 0, art: null },
        "15": { count: 2, art: "oc_artifacts: fl-win64 plugins-ott" },
      },
      phase,
      pm_art: {
        "12": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fl-win64 plugins-ott" },
        "16": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: none" },
      },
    });
  });

  it("出力は Worker の検証 (parseVmState = POST /admin/import と同じ関数) を通る", () => {
    const r = script.serialize(out);
    const parsed = parseVmState(JSON.parse(r), NOW);
    expect(parsed.ok).toBe(true);
    if (parsed.ok) expect(parsed.value.relaunch["14"]).toEqual({ count: 0, art: null });
  });

  it("落とした語は issue 番号と一緒に log に出る", () => {
    const lines: string[] = [];
    script.buildImport({ launched, relaunch, state, phase }, (m: string) => lines.push(m));
    expect(lines.join("\n")).toMatch(/issue #14 \(relaunch\).*fetchsh/);
    expect(lines.join("\n")).toMatch(/issue #13 \(pm_art\)/);
  });

  it("phase が null のときは失敗する (取り込みは最初の tick の後の値が要る)", () => {
    expect(() => script.buildImport({ launched, relaunch, state, phase: null })).toThrow(/phase/);
  });

  it("pm_art が無い issues_state.json は失敗する (黙って空にしない)", () => {
    expect(() => script.buildImport({ launched, relaunch, state: {}, phase })).toThrow(/pm_art/);
  });

  it("整形しない JSON で、整形出力より小さい", () => {
    const text = script.serialize(out);
    expect(text).not.toContain("\n");
    expect(JSON.parse(text)).toEqual(out);
    expect(text.length).toBeLessThan(JSON.stringify(out, null, 2).length);
  });

  it("200 KiB を超える本文は投げる (何も返さない)", () => {
    const big: Record<string, unknown> = {};
    for (let n = 1; n <= 2000; n++) big[String(n)] = { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fl-win64 plugins-ott analysis-ott-binaries work-liftlib-targets work-liftlib" };
    expect(() => script.serialize({ launched: {}, relaunch: {}, phase, pm_art: big })).toThrow(/200 KiB/);
  });
});

describe("build_import: コマンド", () => {
  it("正常系: 標準出力に本文だけを書き、落とした語は標準エラーに出る。終了 0", () => {
    const r = runCli(cliArgs({}, "ok"));
    expect(r.status, r.stderr).toBe(0);
    expect(JSON.parse(r.stdout)).toEqual(script.buildImport({ launched, relaunch, state, phase }));
    expect(r.stderr).toMatch(/#14 \(relaunch\)/);
  });

  it("上限を超えると終了 1・標準出力は空 (何も書かない)", () => {
    const big: Record<string, unknown> = {};
    for (let n = 1; n <= 2000; n++) big[String(n)] = { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fl-win64 plugins-ott analysis-ott-binaries work-liftlib-targets work-liftlib" };
    const r = runCli(cliArgs({ state: { pm_art: big } }, "big"));
    expect(r.status).toBe(1);
    expect(r.stdout).toBe("");
    expect(r.stderr).toMatch(/200 KiB/);
  });

  it("phase が null の export は終了 1", () => {
    const r = runCli(cliArgs({ phase: null }, "nophase"));
    expect(r.status).toBe(1);
    expect(r.stdout).toBe("");
  });

  it("引数が足りないときは終了 2 (使い方を出す)", () => {
    const r = runCli(["--launched", "x.json"]);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/usage/);
  });
});
