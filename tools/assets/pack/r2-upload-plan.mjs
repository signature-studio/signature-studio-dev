// R2 アップロード計画の表示のみ (実アップロードは行わない)。
//   node pack/r2-upload-plan.mjs <pkgdir> <bucket> [--tool wrangler|aws] [--endpoint https://<acct>.r2.cloudflarestorage.com]
// 出力: 1 オブジェクト 1 行のコマンド (stdout)。 head -n で確認し、実行は人手/CI で行う。
import fs from 'node:fs';
import path from 'node:path';
const [dir, bucket] = process.argv.slice(2, 4);
const flag = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const tool = flag('--tool', 'wrangler');
const endpoint = flag('--endpoint', 'https://<ACCOUNT_ID>.r2.cloudflarestorage.com');
if (!dir || !bucket) throw new Error('usage: r2-upload-plan.mjs <pkgdir> <bucket>');
const plan = JSON.parse(fs.readFileSync(path.join(dir, 'upload-plan.json'), 'utf8'));
// latest.json は最後 (manifest と chunk が揃ってから pointer を切り替える)
plan.sort((a, b) => (a.key === 'latest.json') - (b.key === 'latest.json'));
let bytes = 0;
for (const o of plan) {
  bytes += o.size;
  const f = path.join(dir, o.key);
  if (tool === 'wrangler')
    console.log(`wrangler r2 object put "${bucket}/${o.key}" --file "${f}" --content-type "${o.contentType}" --cache-control "${o.cacheControl}"${o.contentEncoding ? ` --content-encoding ${o.contentEncoding}` : ''} --remote`);
  else
    console.log(`aws s3api put-object --endpoint-url ${endpoint} --bucket ${bucket} --key "${o.key}" --body "${f}" --content-type "${o.contentType}" --cache-control "${o.cacheControl}"${o.contentEncoding ? ` --content-encoding ${o.contentEncoding}` : ''}`);
}
console.error(`# ${plan.length} objects, ${(bytes / 1e6).toFixed(1)} MB (dry-run: nothing executed)`);
