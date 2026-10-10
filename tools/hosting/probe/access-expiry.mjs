// access-expiry.mjs <url-origin> — Access 配下 (service token で 1 回認証) で CF_Authorization cookie を失効させた時、
// COEP ページ内の fetch() が何を見るかを確認する (E の lazy VFS が「ネットワーク断」と「セッション切れ」を区別するため)
import fs from 'node:fs';
import puppeteer from 'puppeteer-core';
const origin = process.argv[2];
const tk = JSON.parse(fs.readFileSync(process.env.CF_ACCESS_FILE, 'utf8'));
const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setExtraHTTPHeaders({ 'CF-Access-Client-Id': tk.client_id, 'CF-Access-Client-Secret': tk.client_secret });
await page.goto(origin + '/s/?data=/d/&big=part-24m.bin', { waitUntil: 'load' });
await page.waitForFunction(() => document.title === 'probe-done', { timeout: 120000 });
await page.setExtraHTTPHeaders({});
const out = {};
const run = (label) => page.evaluate(async (label) => {
  const r = {};
  const t = async (k, fn) => { try { const x = await fn(); r[k] = x; } catch (e) { r[k] = `${e?.name}: ${e?.message}`; } };
  await t('default', async () => { const x = await fetch('/d/x.raw', { cache: 'no-store' }); return `${x.status} redirected=${x.redirected} type=${x.type}`; });
  await t('manual', async () => { const x = await fetch('/d/x.raw', { cache: 'no-store', redirect: 'manual' }); return `${x.status} type=${x.type}`; });
  await t('xhrHeader', async () => { const x = await fetch('/d/x.raw', { cache: 'no-store', headers: { 'X-Requested-With': 'XMLHttpRequest' } }); return `${x.status} type=${x.type}`; });
  await t('inWorker', () => new Promise((res) => {
    const w = new Worker(URL.createObjectURL(new Blob([`self.onmessage=async()=>{try{const x=await fetch(location.origin+'/d/x.raw',{cache:'no-store'});postMessage(x.status+' '+x.type)}catch(e){postMessage(e.name+': '+e.message)}}`], { type: 'text/javascript' })));
    w.onmessage = (e) => res(e.data); w.postMessage(1); setTimeout(() => res('timeout'), 8000);
  }));
  return r;
}, label);
out.valid = await run('valid');
await page.deleteCookie({ name: 'CF_Authorization', url: origin });
out.expired = await run('expired');
console.log(JSON.stringify(out, null, 1));
await browser.close();
