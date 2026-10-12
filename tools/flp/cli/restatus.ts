// Re-derive `name` / `status` in corpus/event_census.json and corpus/unknown_events.json from the current dictionary (src/events.ts)
// WITHOUT re-scanning the corpus (counts/sizes/firstSeen stay as measured by cli/corpus.ts). Use after relabelling ids.
// usage: node cli/restatus.ts [corpusDir]
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { defOf, docStatus } from '../src/events.ts';

const dir = process.argv[2] ?? join(import.meta.dirname, '..', 'corpus');
const J = (o: unknown): string => JSON.stringify(o, null, 1);

const cen = JSON.parse(readFileSync(join(dir, 'event_census.json'), 'utf8')) as { ids: { id: number; name: string | null; status: string }[] };
for (const c of cen.ids) {
  c.name = defOf(c.id)?.name ?? null;
  c.status = docStatus(c.id);
}
writeFileSync(join(dir, 'event_census.json'), J(cen));

const unk = JSON.parse(readFileSync(join(dir, 'unknown_events.json'), 'utf8')) as Record<string, any>;
const byId = new Map(cen.ids.map((c) => [c.id, c]));
for (const k of ['notInUpstream', 'newSinceFl21', 'newSince25_2']) {
  for (const e of unk[k]) {
    e.name = byId.get(e.id)?.name ?? e.name;
    e.status = byId.get(e.id)?.status ?? e.status;
  }
}
unk.undocumented = cen.ids.filter((c) => c.status === 'undocumented').map((c) => unk.notInUpstream.find((e: any) => e.id === c.id) ?? unk.undocumented.find((e: any) => e.id === c.id)).filter(Boolean);
unk.counts.undocumented = cen.ids.filter((c) => c.status === 'undocumented').length;
writeFileSync(join(dir, 'unknown_events.json'), J(unk));
console.log(JSON.stringify({ undocumented: unk.counts.undocumented, named: cen.ids.filter((c) => c.status !== 'undocumented').length, distinctIds: cen.ids.length }));
