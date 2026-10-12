// L-6: every corpus id is labelled with a non-low confidence, and each such id is backed by an FlpLoad case (corpus/load_switch.json).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { defOf, docStatus } from '../src/events.ts';

const rd = (n: string) => JSON.parse(readFileSync(new URL(`../corpus/${n}`, import.meta.url), 'utf8'));
const census = rd('event_census.json') as { ids: { id: number; status: string; engineWritten: boolean }[] };
const sw = rd('load_switch.json') as { handlers: Record<string, string>; defaultArmIds: number[] };

test('no corpus id is left undocumented', () => {
  const bad = census.ids.filter((c) => docStatus(c.id) === 'undocumented').map((c) => c.id);
  assert.deepEqual(bad, []);
  assert.equal(rd('unknown_events.json').counts.undocumented, 0);
});

test('every non-upstream observed label with conf != low is explained by the FlpLoad switch (case handler or documented default arm)', () => {
  for (const c of census.ids) {
    const d = defOf(c.id);
    assert.ok(d, `id ${c.id} has no def`);
    if (d.src !== 'observed' || d.conf === 'low' || c.id > 0x100) continue;
    const handled = String(c.id) in sw.handlers;
    const dflt = sw.defaultArmIds.includes(c.id);
    assert.ok(handled || dflt, `id ${c.id} (${d.name}) is neither a FlpLoad case nor a default-arm id`);
  }
});

test('load switch recovered 176 case ids and id 37 is a default-arm (ignored) id', () => {
  assert.equal(Object.keys(sw.handlers).length, 176);
  assert.ok(sw.defaultArmIds.includes(37));
});
