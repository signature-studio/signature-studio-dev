// Event-stream diff of two FLP files with a "volatile" mask (ORACLE.md tier T1: load/save fidelity of the wasm engine).
import { type FlpFile } from './flp.ts';
import { hex } from './decode.ts';
import { eventName } from './events.ts';

/** ids whose payload legitimately changes on every save: FL version text, build, FL Studio version text, licensee, timestamp */
export const VOLATILE_IDS: ReadonlySet<number> = new Set([199, 159, 0xc0000101, 200, 237]);

export interface FlpDiff {
  identical: boolean;
  sameIdSequence: boolean;
  eventsA: number;
  eventsB: number;
  onlyA: Record<string, number>;
  onlyB: Record<string, number>;
  masked: number;
}

export function diffFlp(a: FlpFile, b: FlpFile, mask: ReadonlySet<number> = VOLATILE_IDS): FlpDiff {
  const key = (e: { id: number; data: Uint8Array }) => `${e.id}:${hex(e.data)}`;
  const ea = a.events.filter((e) => !mask.has(e.id));
  const eb = b.events.filter((e) => !mask.has(e.id));
  const cnt = new Map<string, number>();
  for (const e of ea) cnt.set(key(e), (cnt.get(key(e)) ?? 0) + 1);
  for (const e of eb) cnt.set(key(e), (cnt.get(key(e)) ?? 0) - 1);
  const onlyA: Record<string, number> = {};
  const onlyB: Record<string, number> = {};
  for (const [k, v] of cnt) {
    if (v === 0) continue;
    const id = parseInt(k.slice(0, k.indexOf(':')), 10);
    const name = `${eventName(id)}(${id})`;
    if (v > 0) onlyA[name] = (onlyA[name] ?? 0) + v;
    else onlyB[name] = (onlyB[name] ?? 0) - v;
  }
  const seqA = ea.map((e) => e.id).join(',');
  const seqB = eb.map((e) => e.id).join(',');
  const same = Object.keys(onlyA).length === 0 && Object.keys(onlyB).length === 0;
  return { identical: same && seqA === seqB, sameIdSequence: seqA === seqB, eventsA: a.events.length, eventsB: b.events.length, onlyA, onlyB, masked: a.events.length - ea.length };
}
