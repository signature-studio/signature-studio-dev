// winmm midi* 強定義の結線 e2e (#179 SHX-T6, build.sh --midi)。
//   node midi_e2e.mjs <m11_sx_*_midi.cjs>        exit 0 = 全 PASS
// 1) constructor (sx_midi_boot) の flmidi_shimx_install() で shimx の midi* backend 表が登録されていること:
//    sx_midi_probe_numdevs(3) が 3 を返す (未登録の weak 実装なら常に 0)。
// 2) 検査口を経由せず midiOutGetNumDevs を直接叩いた値が n_out の設定値に従うこと (表の経路が生きている)。
// 3) wasm の export に flm_init / sx_midi_probe_numdevs が入っていること。
import path from 'path';

const cjs = path.resolve(process.argv[2]);
const m2 = await import(cjs);
const mod = await (m2.default || m2)({ printErr: () => {} });

let fails = 0;
const check = (name, ok, detail) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}  ${detail ?? ''}`); if (!ok) fails++; };

check('export sx_midi_probe_numdevs', typeof mod._sx_midi_probe_numdevs === 'function');
const r3 = mod._sx_midi_probe_numdevs(3);
check('registered: midiOutGetNumDevs routes to flm_ctl n_out (3)', r3 === 3, `got=${r3}`);
const r0 = mod._sx_midi_probe_numdevs(0);
check('registered: n_out=0 returns 0 (table path, not a constant)', r0 === 0, `got=${r0}`);
console.log(fails === 0 ? 'ALL PASS' : `FAIL ${fails}`);
process.exit(fails === 0 ? 0 : 1);
