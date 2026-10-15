// tools/startup/vreg の取込入口 (license_import.mjs・store.mjs・build/vreg_wasm.mjs) の型。実装の正本は tools/startup/vreg/js/*.mjs。
declare module "*/vreg/build/vreg_wasm.mjs" {
  const createVregModule: () => Promise<unknown>;
  export default createVregModule;
}

declare module "*/vreg/data/seed.json" {
  const seed: object;
  export default seed;
}

declare module "*/vreg/js/store.mjs" {
  export class IdbStore {
    load(profile: string): Promise<unknown>;
    save(profile: string, record: unknown): Promise<void>;
    delete(profile: string): Promise<void>;
  }
}

declare module "*/vreg/js/license_import.mjs" {
  export interface LicenseStatus {
    restored: boolean;
    licenseMode: string;
    registered: boolean;
    userReg: { name: string; savedAt: number } | null;
    machineGuid: string;
  }
  export class LicenseImport {
    static open(o: {
      createModule: () => Promise<unknown>;
      store: { load(p: string): Promise<unknown>; save(p: string, r: unknown): Promise<void>; delete(p: string): Promise<void> };
      seed: object;
      profile?: string;
    }): Promise<LicenseImport>;
    importUserReg(bytes: Uint8Array, name?: string): Promise<{ values: number }>;
    revertUserReg(): Promise<boolean>;
    setMachineGuid(guid: string): Promise<void>;
    status(): LicenseStatus;
    readonly vreg: unknown;
  }
}
