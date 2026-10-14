// undo_probe_check.mjs — PY-123 (#3028) の正の対照: image 敷設 (_fle_data_install) 直後と
// _fle_init 直後に、undo 管理 global (0x15e1c78) と安全判定 global (0x15e4790) が PE の値を持つことを確かめる。
//   FLE_BOOT_VARIANT=plain node tools/flelift/boot/undo_probe_check.mjs work/boot/fleboot_plain.cjs
const cjs = process.argv[2];
const mod = await import(cjs);
const m = await (mod.default ? mod.default() : mod());
const rd = (a) => new DataView(m.HEAPU8.buffer).getBigUint64(a, true).toString(16);
const snap = (tag) => console.log(tag.padEnd(18), 'slot_0x15e1c78=0x' + rd(0x15e1c78), 'slot_0x15e4790=0x' + rd(0x15e4790));
snap('before_install');
m._fle_data_install(); snap('after_data_install');
m._fle_init(); snap('after_fle_init');
