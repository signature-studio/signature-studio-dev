// seed.mjs — data/seed.json を registry ツリーモデルへ展開する。
//   - entries[].apply=true のみ書く (applyCatalog=true で key が分かっている catalog 値も書く)
//   - skipGroups: 指定 group (例 settings,shared = コード既定値の書込) を書かない = 「値が無い」状態を保つ
//   - license group: licenseFlagBit0=0 (registered) の時だけ書く。1 (trial) では削除対象にする。external では書かない
//   - ${MACHINE_GUID} をプロファイル毎の GUID に置換
import { emptyModel, setValue } from './regfile.mjs';

export function resolveSeed(seed, { licenseFlagBit0, licenseMode, machineGuid, applyCatalog = false, skipGroups = [] } = {}) {
  const bit0 = licenseFlagBit0 ?? seed.license?.flag_bit0 ?? 0;
  const mode = licenseMode ?? (bit0 ? 'trial' : 'registered');
  const licGroups = new Set(seed.license?.groups ?? ['license']);
  const model = emptyModel();
  const pinned = [];          // 永続済みの値より seed を優先して再設定する値
  const licenseNames = [];    // license group の全 (hive,key,name)。trial / external で削除対象
  let applied = 0, catalogSkipped = 0;
  for (const e of seed.entries) {
    const isLic = licGroups.has(e.group);
    if (isLic) licenseNames.push({ hive: e.hive, key: e.key, name: e.name });
    if (!e.key || skipGroups.includes(e.group)) { catalogSkipped++; continue; }
    if (isLic && mode !== 'registered') continue;
    if (!(e.apply || applyCatalog)) { catalogSkipped++; continue; }
    if (isLic && !e.apply) { catalogSkipped++; continue; }   // Token 等は registered でも書かない
    const v = typeof e.value === 'string' ? e.value.replace('${MACHINE_GUID}', machineGuid) : e.value;
    setValue(model, e.hive, e.key, e.name, e.type, v);
    applied++;
    if (e.pinned || e.name === 'MachineGuid') pinned.push({ hive: e.hive, key: e.key, name: e.name, t: e.type, v });
  }
  return { model, mode, flagBit0: mode === 'registered' ? 0 : mode === 'trial' ? 1 : null, pinned, licenseNames, applied, catalogSkipped };
}

/** ライセンス状態の期待値 (CAB-106 の観察用): byte[0x14f84a8] bit0。external は不明 (null) */
export function expectedLicenseFlag(seed, mode) {
  const f = seed.license?.engine_flag ?? {};
  return { va: f.va ?? '0x14f84a8', bit: f.bit ?? 0, expectedBit0: mode === 'registered' ? 0 : mode === 'trial' ? 1 : null,
    semantic: f.semantic ?? '', confidence: f.confidence ?? '推定', mode };
}
