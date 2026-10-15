// #2623 の再測定: merge 済み PR の本文に、旧判定 (統一前の指標の判定) と統一後の判定 (refsOnlyBody) を当てて件数を数える。
// 読み取りだけ (gh api GET)。数値の出所は tools/pm/REPORT_APPENDIX_2623.md §2。
// 旧判定は --old-ref (既定 7c85004e = 統一前の webhook.ts。889ec098 の親) の infra/pm-worker/src/webhook.ts から REFS_RE・CLOSE_RE の正規表現リテラルを読み出して評価する (手写しをしない)。
// 既定を origin/main にしないのは、統一後の main には REFS_RE が無く、merge 後にこのスクリプトが動かなくなるため。
// 窓は固定値 (--end・既定 2026-10-15T00:00:48Z)。現在時刻からの相対にしない。
// 母集団は REST の pulls 一覧 (updated 降順) を窓の始点まで読み切って取る (search の範囲指定は 1 回 1000 件までで、窓内の PR を取りこぼした)。
// 検算として gh search の範囲指定 (直近 24 時間) と件数・PR 番号の差を出す。
// 使い方: cd <repo> && node --experimental-strip-types --no-warnings tools/pm/refs_only_remeasure.ts [--end 2026-10-15T00:00:48Z] [--old-ref 7c85004e]
import { execFileSync } from "node:child_process";
import { refsOnlyBody } from "../../infra/pm-worker/src/webhook.ts";
import { refsOnlyNumbers } from "../../infra/pm-worker/src/refs.ts";

const R = "signature-studio/signature-studio-dev";
const H = 3_600_000;

const arg = (name: string, def: string): string => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? String(process.argv[i + 1]) : def;
};
const END = arg("end", "2026-10-15T00:00:48Z");
const OLD_REF = arg("old-ref", "7c85004e");
const iso = (ms: number): string => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const END_MS = Date.parse(END);
const START_24H = iso(END_MS - 24 * H);
const START_7D = iso(END_MS - 7 * 24 * H);

const git = (args: string[]): string => execFileSync("git", args, { encoding: "utf8", maxBuffer: 1 << 26 }).trim();
const oldSrc = git(["show", `${OLD_REF}:infra/pm-worker/src/webhook.ts`]);
const oldRegex = (name: string): RegExp => {
  const m = new RegExp(`^const ${name} = (/.*/[a-z]*);$`, "m").exec(oldSrc);
  if (!m) throw new Error(`${name} が ${OLD_REF}:infra/pm-worker/src/webhook.ts に無い`);
  const i = m[1].lastIndexOf("/");
  return new RegExp(m[1].slice(1, i), m[1].slice(i + 1));
};
const OLD_REFS_RE = oldRegex("REFS_RE");
const OLD_CLOSE_RE = oldRegex("CLOSE_RE");
const oldRefsOnly = (body: string): boolean => OLD_REFS_RE.test(body) && !OLD_CLOSE_RE.test(body);

type Pr = { number: number; body: string; mergedAt: string };

// REST の pulls 一覧を updated の降順に読む。窓内で merge された PR は updated_at が merged_at 以降なので、末尾の updated_at が窓の始点より前になった所で止める。
const mergedSince = (startIso: string): Pr[] => {
  const out: Pr[] = [];
  for (let page = 1; page <= 300; page++) {
    const items = JSON.parse(
      execFileSync("gh", ["api", "-X", "GET", `repos/${R}/pulls?state=closed&sort=updated&direction=desc&per_page=100&page=${page}`], { encoding: "utf8", maxBuffer: 1 << 28 }),
    ) as Array<{ number: number; body: string | null; merged_at: string | null; updated_at: string }>;
    if (!items.length) break;
    for (const it of items) {
      if (it.merged_at && it.merged_at > startIso && it.merged_at <= END) out.push({ number: it.number, body: it.body ?? "", mergedAt: it.merged_at });
    }
    if (items[items.length - 1].updated_at < startIso) break;
  }
  return out;
};

const SHAPES: Array<[string, RegExp]> = [
  ["Closes:#N", /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):#\d/i],
  ["Closes#N(空白なし)", /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)#\d/i],
  ["Closes owner/repo#N", /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+[\w.-]+\/[\w.-]+#\d/i],
  ["Refs:#N", /\bRefs:#\d/i],
  ["Refs#N(空白なし)", /\bRefs#\d/i],
  ["Refs owner/repo#N", /\bRefs:?\s+[\w.-]+\/[\w.-]+#\d/i],
  ["Refs 8 桁の番号", /\bRefs:?\s+#\d{8}/i],
  ["改行を挟んだ Refs", /\bRefs[ \t]*\n\s*:?\s*#\d/i],
];

const report = (label: string, prs: Pr[]): void => {
  const oldN = prs.filter((p) => oldRefsOnly(p.body)).length;
  const newN = prs.filter((p) => refsOnlyBody(p.body)).length;
  const changed = prs.filter((p) => oldRefsOnly(p.body) !== refsOnlyBody(p.body)).length;
  const mismatch = prs.filter((p) => refsOnlyBody(p.body) !== (refsOnlyNumbers(p.body).length > 0)).length;
  const shapes = SHAPES.map(([name, re]) => `${name}=${prs.filter((p) => re.test(p.body)).length}`).join(" ");
  console.log(`[${label}] merged=${prs.length} 旧 refs_only=${oldN} (${(oldN / prs.length).toFixed(4)}) 新 refs_only=${newN} (${(newN / prs.length).toFixed(4)}) 値が変わった PR=${changed} 新旧 refsOnlyNumbers 不一致=${mismatch}`);
  console.log(`  形式の出現 PR 数: ${shapes}`);
};

const week = mergedSince(START_7D);
const day = week.filter((p) => p.mergedAt > iso(END_MS - 24 * H));
console.log(`head=${git(["rev-parse", "--short", "HEAD"])} old-ref=${OLD_REF}(${git(["rev-parse", "--short", OLD_REF])}) end=${END}`);
report("直近 24 時間 (REST)", day);
report("直近 7 日 (REST)", week);

// 検算は補助。gh pr list は GraphQL を使うため、制限に掛かったら理由を出して REST の件数だけを使う。
const searchRange = `merged:${START_24H}..${END}`;
try {
  const searchDay = JSON.parse(
    execFileSync("gh", ["pr", "list", "--repo", R, "--state", "merged", "--search", searchRange, "--limit", "1000", "--json", "number,mergedAt"], { encoding: "utf8", maxBuffer: 1 << 28 }),
  ) as Array<{ number: number; mergedAt: string }>;
  const dayNums = new Set(day.map((p) => p.number));
  const searchNums = new Set(searchDay.map((p) => p.number));
  const onlyRest = [...dayNums].filter((n) => !searchNums.has(n));
  const onlySearch = [...searchNums].filter((n) => !dayNums.has(n));
  console.log(`検算 gh search "${searchRange}": ${searchDay.length} 件 / REST のみ ${onlyRest.length} 件 ${JSON.stringify(onlyRest)} / search のみ ${onlySearch.length} 件 ${JSON.stringify(onlySearch)} (search の取りこぼしを REST が補う)`);
} catch (e) {
  const why = String((e as { stderr?: unknown }).stderr ?? e).trim().split("\n")[0];
  console.log(`検算 gh search "${searchRange}": 取得できず (${why})。判定は REST の件数だけ`);
}
