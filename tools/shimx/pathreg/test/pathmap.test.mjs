// pathmap.mjs 単体テスト (JS ミラー)。C 参照実装との一致は e2e.mjs のクロスチェックで検査する。
// 実行: node --test test/pathmap.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeWinPath, createMapper, defaultMounts, DEFAULT_PATHS, FLAG_RO, FLAG_PERSIST, FLAG_TMP } from '../js/pathmap.mjs';

test('normalize: 区切り / ドライブ / プレフィクス / 畳み込み', () => {
  const cases = [
    ['C:\\foo\\bar', 'C:\\foo\\bar'],
    ['c:\\foo\\bar', 'C:\\foo\\bar'],
    ['C:/foo/bar', 'C:\\foo\\bar'],
    ['C:\\\\foo\\\\\\\\bar\\', 'C:\\foo\\bar'],
    ['C:\\foo\\.\\baz\\..\\qux', 'C:\\foo\\qux'],
    ['C:\\foo\\..\\bar', 'C:\\bar'],
    ['C:\\', 'C:\\'],
    ['C:', 'C:\\'],
    ['\\\\?\\C:\\x\\y', 'C:\\x\\y'],
    ['\\\\.\\C:\\x', 'C:\\x'],
    ['\\\\?\\UNC\\srv\\share\\f.txt', '\\\\srv\\share\\f.txt'],
    ['\\\\srv\\share\\x', '\\\\srv\\share\\x'],
    ['\\foo\\bar', '\\foo\\bar'],
    ['foo\\bar', 'foo\\bar'],
    ['C:\\foo\\..\\..\\bar', 'C:\\bar'],
    ['C:\\Foo\\BAR', 'C:\\Foo\\BAR'],
  ];
  for (const [input, want] of cases) assert.equal(normalizeWinPath(input), want, input);
  assert.equal(normalizeWinPath(''), null);
  assert.equal(normalizeWinPath(null), null);
});

test('mapper: 既定表の写像 (stub_plan §4 / nfo 配置 / seed paths 整合)', () => {
  const m = createMapper();
  assert.equal(m.map('C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp'), '/fl/Data/System/Empty.flp');
  assert.equal(
    m.map('c:/PROGRAM FILES/image-line/fl studio 2026/Plugins/Fruity/Generators/Fruity Wrapper/Fruity Wrapper_x64.dll'),
    '/fl/Plugins/Fruity/Generators/Fruity Wrapper/Fruity Wrapper_x64.dll',
  );
  assert.equal(
    m.map('C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml'),
    '/c/home/Documents/Image-Line/FL Studio/Settings/Manifest.xml',
  );
  // nfo REPORT §3 の Plugin database 配置 (Shared data 配下)
  assert.equal(
    m.map('C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Generators\\VST3\\Serum2.vst3.nfo'),
    '/c/home/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/Generators/VST3/Serum2.vst3.nfo',
  );
  // vreg seed の Shared data 値 (webstudio profile) も同じ実体へ
  assert.equal(
    m.map('C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Effects\\VST\\OTT.nfo'),
    '/c/home/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/Effects/VST/OTT.nfo',
  );
  // Temp は Local より長い接頭辞で勝つ
  assert.equal(m.map('C:\\Users\\user\\AppData\\Local\\Temp\\Image-Line\\123-1\\pack.zip'), '/c/tmp/123-1/pack.zip');
  assert.equal(m.map('C:\\Users\\user\\AppData\\Local\\Image-Line\\cache.dat'), '/c/home/AppData/Local/Image-Line/cache.dat');
  // %APPDATA% 直接
  assert.equal(m.map('C:\\Users\\user\\AppData\\Roaming\\Image-Line\\config.xml'), '/c/home/AppData/Roaming/Image-Line/config.xml');
  // 残余ドライブ C
  assert.equal(m.map('C:\\Windows\\notepad.exe'), '/c/Windows/notepad.exe');
  // 非対応 → null (shimx 既定写像に委譲)
  assert.equal(m.map('D:\\foo\\bar'), null);
  assert.equal(m.map('/posix/abs'), null);
  assert.equal(m.map('relative.txt'), null);
  assert.equal(m.map(''), null);
});

test('mapper: 追加マウント (最長一致・大小無視) と逆写像', () => {
  const m = createMapper({ extraMounts: [{ win: 'E:\\SampleLib', target: '/libs/sample', flags: FLAG_RO }] });
  assert.equal(m.map('e:\\samplelib\\x\\y.dll'), '/libs/sample/x/y.dll');
  assert.equal(m.map('E:\\SampleLib2\\x'), null);   // 別セグメント (SampleLib2) は不一致 → shimx 既定 (E: → /e/...) へ委譲
  assert.equal(m.unmap('/libs/sample/x/y.dll'), 'E:\\SampleLib\\x\\y.dll');
  assert.equal(m.unmap('/fl/Data/System/Empty.flp'), 'C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp');
  assert.equal(m.unmap('/elsewhere/x'), null);
});

test('既定表の構造 (flags / 2 プロファイル / C:) ', () => {
  const mounts = defaultMounts();
  const byWin = new Map(mounts.map((m) => [m.win, m]));
  assert.equal(byWin.get('C:\\Program Files\\Image-Line\\FL Studio 2026').flags, FLAG_RO);
  assert.equal(byWin.get('C:\\Users\\user\\Documents\\Image-Line').flags, FLAG_PERSIST);
  assert.equal(byWin.get('C:\\Users\\user\\AppData\\Local\\Temp\\Image-Line').flags, FLAG_TMP);
  assert.ok(byWin.has('C:\\Users\\webstudio\\Documents\\Image-Line'));   // vreg seed 由来の予備 profile
  assert.ok(byWin.has('C:\\'));                                          // 残余ドライブ C ("C:" は "C:\" に正準化)
  // 共有データ先の上書き (CAB-101 が実配置を確定した場合)
  const custom = defaultMounts({ ...DEFAULT_PATHS, sharedDataDir: 'D:\\FLData' });
  assert.ok(custom.some((m) => m.win === 'D:\\FLData' && m.target === '/c/home/Documents/Image-Line'));
});
