if (process.env.FLE_IPP === '0') globalThis.__ippoff = 1;
const mod = await import(process.argv[2]); const m = await (mod.default ? mod.default() : mod());
const U=m.HEAPU8; const rd=(a)=>{let v=0n;for(let i=7;i>=0;i--)v=(v<<8n)|BigInt(U[a+i]);return v;};
if (globalThis.__ippoff) m._fle_boot_set_ipp(0);
try { m._fle_boot_enter(0); } catch(e) { console.log('threw', e.fle_kind, e.fle_a && e.fle_a.toString(16)); }
const h=(v)=>'0x'+v.toString(16);
console.log('units_run', Number(m._fle_units_run()));
for (const a of [0x15F40E8,0x15F33C0,0x15F34A0,0x15E0A48,0x15F4B80]) console.log(h(BigInt(a)), h(rd(a)));
console.log('ipp names', m._fle_ipp_names(), 'calls', m._fle_ipp_total());
for (let i=0;i<m._fle_ipp_names();i++){ const c=m._fle_ipp_count(i); if(c) console.log('  called', m.UTF8ToString(m._fle_ipp_name(i)), c); }
