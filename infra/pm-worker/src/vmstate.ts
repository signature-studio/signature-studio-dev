// VM の状態 (tools/pm の launched.json・relaunch.json・phase.json と issues_state.json の pm_art) の取り込み・書き出しの形式と値域 (#2343)。
// 純関数のみ。DO への書き込みは engine が行う。値は検証したままの文字列で保存するので、書き出して取り込み直しても同じ内容になる。
import { validateArtLine } from "./launch.ts";

export const MAX_IMPORT_BYTES = 200 * 1024;
export const VM_KEYS = ["launched", "relaunch", "phase", "pm_art"] as const;
// 取り込む時刻は「現在時刻 + 5 分」までにする (VM と Worker の時計のずれを許す)。これより先の時刻は 3 時間の窓や PM 投稿の新旧比較を止めるので 400。
export const FUTURE_SKEW_MS = 5 * 60_000;
const ISSUE_NO = /^[1-9]\d{0,6}$/;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})$/;
const MAX_COUNT = 3;
const MAX_PROBLEMS = 50;

export interface VmRelaunch {
  count: number;
  art: string | null;
}

export interface VmPhase {
  review_only: boolean;
  open_prs: number;
  since: string;
}

export interface VmPmArt {
  at: string;
  line: string;
}

export interface VmState {
  launched: Record<string, string>;
  relaunch: Record<string, VmRelaunch>;
  phase: VmPhase;
  pm_art: Record<string, VmPmArt>;
}

export type VmParse = { ok: true; value: VmState } | { ok: false; problems: string[] };

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

// タイムゾーン付きの ISO 8601 (VM の datetime.isoformat() と同じ形)。
export const isIso = (s: unknown): s is string => typeof s === "string" && ISO.test(s) && Number.isFinite(Date.parse(s));

// "oc_artifacts: none" (追加素材なし) か、ALLOW_ARTS の名前を 1 つ以上並べた行だけを通す。launch.ts の validateArtLine と同じ規則。
export function artLineOk(line: unknown): boolean {
  return typeof line === "string" && validateArtLine(line);
}

const keyText = (k: string): string => JSON.stringify(k.slice(0, 40));

// nowMs を渡したときは、時刻が nowMs + FUTURE_SKEW_MS より後のものを 400 にする。
export function parseVmState(v: unknown, nowMs?: number): VmParse {
  const problems: string[] = [];
  const bad = (msg: string): void => {
    if (problems.length < MAX_PROBLEMS) problems.push(msg);
  };
  const later = (at: string): boolean => nowMs !== undefined && Date.parse(at) > nowMs + FUTURE_SKEW_MS;
  if (!isObj(v)) return { ok: false, problems: ["body must be a JSON object"] };
  for (const k of VM_KEYS) if (!(k in v)) bad(`missing key: ${k}`);
  for (const k of Object.keys(v)) if (!(VM_KEYS as readonly string[]).includes(k)) bad(`unknown key: ${keyText(k)}`);

  const launched: Record<string, string> = {};
  if (!isObj(v.launched)) bad("launched must be an object");
  else
    for (const [k, at] of Object.entries(v.launched)) {
      if (!ISSUE_NO.test(k)) bad(`launched: ${keyText(k)} is not an issue number`);
      else if (!isIso(at)) bad(`launched.${k}: time must be ISO 8601 with a timezone`);
      else if (later(at)) bad(`launched.${k}: time is later than now + 5 min`);
      else launched[k] = at;
    }

  const relaunch: Record<string, VmRelaunch> = {};
  if (!isObj(v.relaunch)) bad("relaunch must be an object");
  else
    for (const [k, r] of Object.entries(v.relaunch)) {
      if (!ISSUE_NO.test(k)) bad(`relaunch: ${keyText(k)} is not an issue number`);
      else if (!isObj(r) || !Number.isInteger(r.count) || (r.count as number) < 0 || (r.count as number) > MAX_COUNT) bad(`relaunch.${k}.count must be an integer 0-${MAX_COUNT}`);
      else if (r.art !== null && !artLineOk(r.art)) bad(`relaunch.${k}.art must be null or an oc_artifacts line within the allowlist`);
      else relaunch[k] = { count: r.count as number, art: r.art as string | null };
    }

  const pm_art: Record<string, VmPmArt> = {};
  if (!isObj(v.pm_art)) bad("pm_art must be an object");
  else
    for (const [k, p] of Object.entries(v.pm_art)) {
      if (!ISSUE_NO.test(k)) bad(`pm_art: ${keyText(k)} is not an issue number`);
      else if (!isObj(p) || !isIso(p.at)) bad(`pm_art.${k}.at must be ISO 8601 with a timezone`);
      else if (later(p.at)) bad(`pm_art.${k}.at is later than now + 5 min`);
      else if (!artLineOk(p.line)) bad(`pm_art.${k}.line must be an oc_artifacts line within the allowlist`);
      else pm_art[k] = { at: p.at, line: p.line as string };
    }

  let phase: VmPhase = { review_only: true, open_prs: 0, since: "" };
  if (!isObj(v.phase) || typeof v.phase.review_only !== "boolean" || !Number.isInteger(v.phase.open_prs) || (v.phase.open_prs as number) < 0 || !isIso(v.phase.since)) {
    bad("phase must be {review_only: bool, open_prs: integer >= 0, since: ISO 8601 with a timezone}");
  } else {
    phase = { review_only: v.phase.review_only, open_prs: v.phase.open_prs as number, since: v.phase.since };
  }

  if (problems.length) return { ok: false, problems };
  return { ok: true, value: { launched, relaunch, phase, pm_art } };
}
