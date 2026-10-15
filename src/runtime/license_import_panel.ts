// 製品ページの .reg 取込入口 (#2793 / vreg #116)。index.ts が ?license=import のときだけ動的 import する。
// 取込・MachineGuid・取消しの操作は tools/startup/vreg/ui/import.html と同じ (既定の起動経路には載らない)。
import createVregModule from "../../tools/startup/vreg/build/vreg_wasm.mjs";
import seed from "../../tools/startup/vreg/data/seed.json";
import { IdbStore } from "../../tools/startup/vreg/js/store.mjs";
import { LicenseImport } from "../../tools/startup/vreg/js/license_import.mjs";

const PANEL_HTML = `
  <div style="font-weight:bold;margin-bottom:6px">.reg 取込 (正規ライセンスをお持ちの方)</div>
  <p style="margin:0 0 8px;opacity:.8">ご自身で書き出した .reg を、生成・改変せずそのまま保存して起動時に適用します。</p>
  <input type="file" id="license-file" accept=".reg">
  <div style="margin:8px 0">
    <input id="license-guid" size="30" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx">
    <button id="license-guid-apply" type="button">MachineGuid 設定</button>
  </div>
  <button id="license-revert" type="button">取込を取り消す</button>
  <pre id="license-status" style="background:#111;padding:6px;overflow:auto;max-height:200px">読込中…</pre>
  <p id="license-msg" role="alert" style="margin:4px 0 0"></p>`;

const errText = (e: unknown): string => (e instanceof Error ? e.message : String(e));

export async function mountLicenseImport(): Promise<void> {
  const box = document.createElement("div");
  box.id = "license-import";
  box.style.cssText =
    "position:fixed;left:12px;top:56px;z-index:20;width:340px;padding:10px;background:#1c1c1c;border:1px solid #444;font:12px sans-serif;color:#eee;";
  box.innerHTML = PANEL_HTML;
  document.body.appendChild(box);
  const q = <T extends Element>(sel: string): T => box.querySelector(sel) as T;
  const fileIn = q<HTMLInputElement>("#license-file");
  const guidIn = q<HTMLInputElement>("#license-guid");
  const statusEl = q<HTMLElement>("#license-status");
  const msgEl = q<HTMLElement>("#license-msg");

  let lic: LicenseImport;
  try {
    lic = await LicenseImport.open({ createModule: createVregModule, store: new IdbStore(), seed });
  } catch (e) {
    statusEl.textContent = `vreg 初期化失敗: ${errText(e)}`;
    return;
  }
  const w = window as unknown as { licenseImport: LicenseImport; licenseImportReady: boolean };
  w.licenseImport = lic;
  const report = (text: string): void => {
    msgEl.textContent = text;
    statusEl.textContent = JSON.stringify(lic.status(), null, 2);
  };
  report("");

  fileIn.addEventListener("change", async () => {
    const f = fileIn.files?.[0];
    if (!f) return;
    try {
      const info = await lic.importUserReg(new Uint8Array(await f.arrayBuffer()), f.name);
      report(`取り込みました: ${f.name} (値 ${info.values} 件)`);
    } catch (e) {
      report(`取り込み失敗: ${errText(e)}`);
    }
    fileIn.value = "";
  });
  q<HTMLButtonElement>("#license-revert").addEventListener("click", async () => {
    try {
      const done = await lic.revertUserReg();
      report(done ? "取込を取り消しました (既定の登録済みに戻しました)" : "取り消す取込はありません");
    } catch (e) {
      report(`取消し失敗: ${errText(e)}`);
    }
  });
  q<HTMLButtonElement>("#license-guid-apply").addEventListener("click", async () => {
    try {
      await lic.setMachineGuid(guidIn.value.trim());
      report("MachineGuid を設定しました");
    } catch (e) {
      report(`MachineGuid 設定失敗: ${errText(e)}`);
    }
  });
  w.licenseImportReady = true;
}
