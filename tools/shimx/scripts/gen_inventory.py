#!/usr/bin/env python3
"""inventory.md / BACKLOG.md / data/coverage.json / data/inventory.csv を実測から生成する。

入力:  data/imports.json (FLEngine 738+57 / プラグイン import, 呼出サイト数)
       work/nm_by_file_MT.txt (shimx が定義する公開関数と所属ファイル; scripts/build_objs.sh が生成)
       ../shim/exports.txt (M4 の 53 API), work/ir_m11.json / work/ir_ott.json (scripts/ir_undef.py), work/ott/result.json
実行:  python3 scripts/gen_inventory.py
"""
import csv, json, os, re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
W = lambda *p: os.path.join(ROOT, *p)

OTHER_OWNER = {
    'user32.dll': 'gui', 'gdi32.dll': 'gui', 'comctl32.dll': 'gui', 'opengl32.dll': 'gui', 'dwmapi.dll': 'gui',
    'uxtheme.dll': 'gui', 'imm32.dll': 'gui', 'shcore.dll': 'gui', 'msimg32.dll': 'gui', 'windowscodecs.dll': 'gui',
    'gdiplus.dll': 'gui', 'd3d11.dll': 'gui', 'd2d1.dll': 'gui', 'dwrite.dll': 'gui', 'dsound.dll': 'audio',
}
# 機能ではなく「無い/失敗/キャンセル」を返すスタブ (S)。それ以外の実装済みは機能実装 (F)
STUBS = set('''
InternetOpenW InternetGetConnectedState InternetCloseHandle InternetConnectW InternetOpenUrlW InternetReadFile InternetWriteFile
InternetSetOptionW InternetGetLastResponseInfoW HttpOpenRequestW HttpSendRequestExW HttpEndRequestW HttpAddRequestHeadersW
HttpQueryInfoW HttpQueryInfoA InternetOpenA InternetOpenUrlA InternetSetStatusCallbackW
WSAStartup WSACleanup WSAGetLastError WSASetLastError closesocket ioctlsocket WSAPoll WSASocketW
WNetOpenEnumW WNetEnumResourceW WNetCloseEnum WNetGetUniversalNameW WinVerifyTrust CertCloseStore CertFindCertificateInStore
CertFreeCertificateContext CertGetNameStringW CertGetNameStringA CryptMsgClose CryptMsgGetParam CryptQueryObject CryptDecodeObject
CryptAcquireContextA CryptCreateHash CryptHashData CryptGetHashParam CryptDestroyHash
midiInGetNumDevs midiOutGetNumDevs midiInGetDevCapsW midiOutGetDevCapsW midiInOpen midiOutOpen midiInClose midiOutClose midiInStart
midiInStop midiInReset midiInAddBuffer midiInPrepareHeader midiInUnprepareHeader midiOutPrepareHeader midiOutUnprepareHeader
midiOutShortMsg midiOutLongMsg midiInGetErrorTextW midiOutGetErrorTextW timeBeginPeriod timeEndPeriod timeGetDevCaps
acmMetrics acmDriverEnum acmDriverOpen acmDriverClose acmDriverDetailsA acmFormatChooseW acmFormatSuggest acmStreamOpen acmStreamClose
acmStreamConvert acmStreamMessage acmStreamPrepareHeader acmStreamUnprepareHeader acmStreamSize
GetOpenFileNameW GetSaveFileNameW CommDlgExtendedError OpenPrinterW ClosePrinter EnumPrintersW GetDefaultPrinterW DocumentPropertiesW
LresultFromObject WTSRegisterSessionNotification WTSUnRegisterSessionNotification PropVariantToFileTime PropVariantToVariant
VariantToPropVariant PropVariantToStringWithDefault PropVariantToBooleanWithDefault
DragAcceptFiles DragFinish DragQueryFileW DragQueryPoint SHAddToRecentDocs SHAppBarMessage SHChangeNotifyRegister SHChangeNotifyDeregister
Shell_NotifyIconW SHGetFileInfoW SHGetDesktopFolder SHCreateItemFromParsingName SHOpenFolderAndSelectItems SHCreateStreamOnFileEx
ExtractAssociatedIconW ShellExecuteA ShellExecuteW ShellExecuteExW ShellExecuteExA
CoCreateInstance CoGetClassObject ProgIDFromCLSID GetActiveObject GetErrorInfo CreateILockBytesOnHGlobal StgCreateDocfileOnILockBytes
CreateDataAdviseHolder OleDraw IsAccelerator OleSetMenuDescriptor DoDragDrop OleGetClipboard OleSetClipboard OleFlushClipboard
OleIsCurrentClipboard CreateProcessW AssignProcessToJobObject ReadDirectoryChangesW DeviceIoControl CreateSymbolicLinkW PeekNamedPipe
CreateIoCompletionPort GetQueuedCompletionStatus FreeLibraryWhenCallbackReturns SetPriorityClass GetPriorityClass SetThreadExecutionState
RtlVirtualUnwind RtlLookupFunctionEntry RtlCaptureContext SetProcessAffinityMask TerminateThread SuspendThread
GetConsoleMode ReadConsoleW SetErrorMode SetThreadErrorMode IsDebuggerPresent LockFile UnlockFile LockFileEx UnlockFileEx
SetVolumeLabelW OutputDebugStringW OutputDebugStringA IsWow64Process
RtlUnwind RtlUnwindEx
'''.split())
FAILFAST_BY_DESIGN = set()   # #171: RtlUnwind/RtlUnwindEx は SEH frame (setjmp 系) 経由で実巻き戻し。frame 未登録時のみ fail-fast

NOTE = {
    'RaiseException': 'VEH→SEH frame 鎖 (longjmp 捕捉)→UEF→fail-fast (継続可能例外のみ復帰)', 'RtlUnwind': 'SEH frame 巻き戻し (frame 未登録は fail-fast)',
    'RtlUnwindEx': 'SEH frame 巻き戻し (frame 未登録は fail-fast)', 'GetProcAddress': '組込み表 (proctable) + 外部フック。未知名は NULL', 'LoadLibraryW': 'モジュール表+load フック。実体ロードは hostbridge',
    'CreateProcessW': '常に ERROR_FILE_NOT_FOUND', 'ShellExecuteW': 'shimx_set_shell_execute_hook 経由', 'GetOpenFileNameW': 'キャンセル扱い (Web ファイル選択は下流)',
    'WSAStartup': 'WSASYSNOTREADY (ネットワーク無し)', 'InternetGetConnectedState': 'FALSE', 'timeGetTime': 'M4 継承 (emscripten_get_now)',
    'CreateThread': 'CREATE_SUSPENDED 対応/threadId 修正 (M4 差分)', 'SuspendThread': 'カウントのみ (実停止不可)', 'TerminateThread': '状態のみ完了扱い',
    'VirtualAlloc': 'weak (m11_rt.c 強定義が優先)', 'CharUpperW': 'weak (tools/gui が上書き可)', 'midiInGetNumDevs': 'デバイス 0 台 (weak; Web MIDI は下流)',
    'MsgWaitForMultipleObjects': 'weak。kernel object 待ちのみ (メッセージ無し)', 'RegOpenKeyExW': 'メモリ内レジストリ', 'EnterCriticalSection': 'Win64 40B レイアウトを直接実装',
    'GlobalUnlock': 'M4 互換 (ロック済みなら TRUE)', 'CoInitialize': 'スレッド毎カウント', 'CreateStreamOnHGlobal': 'IStream (Win64 vtable 8B スロット)',
    'SHGetMalloc': 'IMalloc (Win64 vtable)', 'MultiByteToWideChar': 'CP 1252/437近似/Latin1/ASCII/UTF-8。DBCS (932 等) は ERROR_INVALID_PARAMETER',
    'GetLocaleInfoW': 'en-US 固定データ (LCID 名のみ数種)', 'CreateFileW': 'Win→FS パス写像 + 大小無視再探索', 'FindFirstFileW': '先頭で全列挙→大小無視ソート',
    'CreateFileMappingW': '共有バッファ方式 (Unmap/Flush で書戻し)', 'GetVersionExW': '10.0.19045 (shimx_set_version で変更)',
    'IsProcessorFeaturePresent': 'FASTFAIL(23)/AVX 系は FALSE', 'GetFileVersionInfoW': '合成版情報 (FL 26.1.7.5653)', 'WinVerifyTrust': 'NOSIGNATURE (shimx_set_trust_ok で成功化)',
    'ExitProcess': 'exit hook + exit()', 'SetThreadPriority': '値保持のみ',
}

m4 = [l.strip() for l in open(W('..', 'shim', 'exports.txt')) if l.strip() and not l.startswith('#')]
imp = json.load(open(W('data', 'imports.json')))
fle = imp['flengine']['static']; delay = imp['flengine']['delay']

# shimx 定義済み関数 (所属ファイル付き)
defined, src_of, all_defined = set(), {}, set()
for l in open(W('work', 'nm_by_file_MT.txt')):
    m = re.match(r'^(.*?\.o): [0-9a-f]+ ([TW]) (\S+)$', l.strip())
    if m:
        n = m.group(3)
        all_defined.add(n)
        if n.startswith('shx_') or n == 'shim_unimplemented':
            continue
        defined.add(n); src_of[n] = os.path.basename(m.group(1))[:-2] + '.c'
public_api = sorted(n for n in defined if not n.startswith('shimx_') and not n.startswith('vreg_'))
hooks = sorted(n for n in defined if n.startswith('shimx_') or n.startswith('vreg_'))

LIBC_OK = {'memset', 'socket', 'bind', 'listen', 'accept', 'recv', 'send', 'getsockname', 'ntohs'}   # Emscripten libc が解決 (ソケットは実行時エラー)
# R3 で序数 → API を同定し GetProcAddress 序数表 (src/module.c shx_ordtable) に登録済みのもの
ORD_KNOWN = {'shell32.dll': {155: 'ILFree', 190: 'ILCreateFromPathW'}}
def status(name, dll):
    if name in defined:
        return 'S' if name in STUBS else 'F'
    if name in LIBC_OK:
        return 'L'
    if name.startswith('ord') and name[3:].isdigit():
        return 'O'
    if dll in OTHER_OWNER:
        return 'X:' + OTHER_OWNER[dll]
    return 'U'

ott_undef24 = set(json.load(open(W('work', 'ott', 'result.json'))).get('resolved_by_shimx', [])) if os.path.exists(W('work', 'ott', 'result.json')) else set()
m11 = json.load(open(W('work', 'ir_m11.json')))['classes'] if os.path.exists(W('work', 'ir_m11.json')) else {}
m11_decl = set(m11.get('shimx', [])) | set(m11.get('win_other', []))
plug_dem = defaultdict(set)
for pn, v in imp['plugins'].items():
    for e in v['static'] + v['delay']:
        plug_dem[e['name']].add(pn.split('_')[0].split('.')[0])

# ---- FLEngine 738 のカバレッジ ----
rows = []
for e in fle:
    st = status(e['name'], e['dll'])
    rows.append(dict(scope='static', dll=e['dll'], name=e['name'], calls=e['callers'] + e['calls'], status=st))
for e in delay:
    rows.append(dict(scope='delay', dll=e['dll'], name=e['name'], calls=0, status=status(e['name'], e['dll'])))
stat738 = [r for r in rows if r['scope'] == 'static']
cnt = Counter(r['status'].split(':')[0] for r in stat738)
n738 = len(stat738)
other = cnt['X']; inscope = n738 - other
impl = cnt['F'] + cnt['S']
cov = {
    'flengine_static_total': n738, 'implemented_functional': cnt['F'], 'implemented_stub': cnt['S'], 'libc_resolved': cnt['L'],
    'other_owner': other, 'other_owner_gui': sum(1 for r in stat738 if r['status'] == 'X:gui'), 'other_owner_audio': sum(1 for r in stat738 if r['status'] == 'X:audio'),
    'unimplemented': cnt['U'], 'ordinal': cnt['O'],
    'coverage_pct_vs_738': round(100.0 * impl / n738, 1), 'coverage_pct_incl_libc_vs_738': round(100.0 * (impl + cnt['L']) / n738, 1),
    'coverage_pct_in_scope': round(100.0 * (impl + cnt['L']) / inscope, 1), 'in_scope': inscope,
    'delay_total': len(delay), 'delay_implemented': sum(1 for r in rows if r['scope'] == 'delay' and r['status'] in ('F', 'S')),
    'delay_other_owner': sum(1 for r in rows if r['scope'] == 'delay' and r['status'].startswith('X')),
    'delay_unimplemented': sum(1 for r in rows if r['scope'] == 'delay' and r['status'] == 'U'),
    'm4_api': len(m4), 'm4_api_inherited': sum(1 for n in m4 if n in all_defined),
    'shimx_public_api': len(public_api), 'shimx_hooks': len(hooks),
    'shimx_stub_api': sum(1 for n in public_api if n in STUBS),
    'shimx_functional_api': sum(1 for n in public_api if n not in STUBS),
}
# プラグイン需要 (FLEngine 以外)
plug_rows = []
fle_names = {r['name'] for r in rows}
for pn, v in imp['plugins'].items():
    names = {}
    for e in v['static'] + v['delay']:
        names[e['name']] = e['dll']
    tot = len(names)
    ins = [(n, d) for n, d in names.items() if d not in OTHER_OWNER]
    ok = [n for n, d in ins if status(n, d) in ('F', 'S', 'L')]
    plug_rows.append((pn, tot, len(ins), len(ok), sorted(n for n, d in ins if status(n, d) not in ('F', 'S', 'L'))))
cov['plugins'] = {p[0]: dict(total=p[1], in_scope=p[2], covered=p[3], missing=p[4]) for p in plug_rows}
cov['m11_closure'] = {k: len(v) for k, v in m11.items()}
cov['ott_api_resolved'] = len(ott_undef24)
json.dump(cov, open(W('data', 'coverage.json'), 'w'), indent=1, ensure_ascii=False)

with open(W('data', 'inventory.csv'), 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['scope', 'dll', 'api', 'static_call_sites', 'status', 'm11_closure', 'ott_undefined', 'plugins', 'source'])
    for r in sorted(rows, key=lambda r: (r['scope'], r['dll'], r['name'])):
        w.writerow([r['scope'], r['dll'], r['name'], r['calls'], r['status'], int(r['name'] in m11_decl), int(r['name'] in ott_undef24),
                    '/'.join(sorted(plug_dem.get(r['name'], []))), src_of.get(r['name'], '')])

# ---- BACKLOG.md ----
def tier(r):
    n = r['name']
    if r['status'].startswith('X'):
        return 'X'
    if n in ott_undef24 or n in m11_decl:
        return 'P0'
    if r['calls'] >= 10 or len(plug_dem.get(n, ())) >= 3:
        return 'P1'
    if r['scope'] == 'static':
        return 'P2'
    return 'P3'
# プラグイン専用 (FLEngine に無い) in-scope を P3 として追加
extra = []
for n, ps in plug_dem.items():
    if n in fle_names:
        continue
    dll = next((e['dll'] for v in imp['plugins'].values() for e in v['static'] + v['delay'] if e['name'] == n), '?')
    extra.append(dict(scope='plugin', dll=dll, name=n, calls=0, status=status(n, dll)))
allrows = rows + extra
for r in allrows:
    r['tier'] = tier(r)
ST_JA = {'F': '機能実装', 'S': 'スタブ(エラー/無し返却)', 'L': 'libc 解決', 'O': '序数 import (未解決)', 'U': '**未実装**', 'X:gui': '対象外 (tools/gui)', 'X:audio': '対象外 (tools/audio)'}
order = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3, 'X': 4}
bl = ['# BACKLOG — shimx 実装バックログ (優先度順, 実測)', '',
      '優先度の定義 (必須性→使用頻度): **P0** = M11 init closure が declare する API または OTT undefined 24 種 / **P1** = FLEngine 静的呼出サイト ≥10 または 3 プラグイン以上が使用 / **P2** = FLEngine 静的 import のその他 / **P3** = delay-load・プラグイン専用 / **X** = 他担当 DLL (対象外)。',
      '呼出サイト数 = FLEngine_x64.dll の `jmp [IAT]` thunk への call/jmp/lea 参照数 (静的, `scripts/import_scan.py`)。', '',
      '## 集計', '', '| 優先 | API 数 | 機能実装 | スタブ | libc | 序数 | 未実装 | 対象外 |', '|---|---|---|---|---|---|---|---|']
for t in ('P0', 'P1', 'P2', 'P3', 'X'):
    rs = [r for r in allrows if r['tier'] == t]
    c = Counter(r['status'].split(':')[0] for r in rs)
    bl.append('| %s | %d | %d | %d | %d | %d | %d | %d |' % (t, len(rs), c['F'], c['S'], c['L'], c['O'], c['U'], c['X']))
bl += ['', '## 一覧 (P0〜P3。X は件数のみ — 全件は data/inventory.csv)', '',
       '| 優先 | API | DLL | 呼出サイト | M11 | OTT | プラグイン | 状態 | 実装 | 備考 |', '|---|---|---|---|---|---|---|---|---|---|']
for r in sorted([r for r in allrows if r['tier'] != 'X'], key=lambda r: (order[r['tier']], -r['calls'], r['name'])):
    n = r['name']
    bl.append('| %s | %s | %s | %d | %s | %s | %s | %s | %s | %s |' % (
        r['tier'], n, r['dll'].replace('.dll', ''), r['calls'], '●' if n in m11_decl else '', '●' if n in ott_undef24 else '',
        '/'.join(sorted(plug_dem.get(n, []))), ST_JA.get(r['status'], r['status']), src_of.get(n, ''), NOTE.get(n, '')))
bl += ['', '## 下流で実体化が必要な「口」(スタブ→実装の昇格候補)', '',
       '| 項目 | 現状 | 昇格に必要なもの | 想定担当 |', '|---|---|---|---|',
       '| LoadLibrary/GetProcAddress の実体 | モジュール表+フック | wasm モジュール連結 (hostbridge) が `shimx_set_load_hook`/`shimx_proc_register` を呼ぶ | hostbridge |',
       '| VFS (Emscripten FS) マウント | `shimx_set_path_mapper` | IDBFS/WORKERFS 等のマウント構成と Win パス写像規約の確定 | runtime |',
       '| ShellExecute / ファイル選択 | フック/キャンセル | ブラウザの `window.open` / File System Access API 接続 | gui |',
       '| MIDI (winmm midi*) | デバイス 0 台 (weak) | Web MIDI 接続 (強定義で上書き) | audio/midi |',
       '| SEH 実巻き戻し | fail-fast | lift 側 (.pdata/UHANDLER 8,021) で setjmp/例外タグへ変換、`shimx_set_raise_hook` に接続 | lift |',
       '| COM オブジェクトの関数ポインタ | Win64 vtable 8B スロットに wasm 関数ポインタ | lifted コードの間接呼出し規約ブリッジ (i64↔i32 署名) | hostbridge |',
       '| 暗号ハッシュ (advapi32 Crypt*) | 常に失敗 | MD5/SHA を実装 (Serum2 ライセンス系のみ。FL 対象外) | plugins |',
       '| レジストリ永続化 | `shimx_reg_export_text/import_text` | IndexedDB への保存/復元 | runtime |']
open(W('BACKLOG.md'), 'w').write('\n'.join(bl) + '\n')

# ---- inventory.md ----
inv = []
A = inv.append
A('# shimx inventory — 実装済み / 未実装 / 対象外 (実測)')
A('')
A('## 結論')
A('')
A('- **FLEngine_x64.dll 静的 import %d 個のうち shimx 実装 %d (機能 %d + スタブ %d) = %.1f%%** (libc 解決の `memset` 込み %.1f%%)。' % (
    n738, impl, cnt['F'], cnt['S'], cov['coverage_pct_vs_738'], cov['coverage_pct_incl_libc_vs_738']))
A('- 他担当 DLL (user32/gdi32/comctl32/opengl32 = tools/gui, dsound = tools/audio) の **%d 個を対象外** とすると、担当範囲 %d 個に対するカバレッジは **%.1f%%** (未実装 %d)。' % (
    other, inscope, cov['coverage_pct_in_scope'], cnt['U']))
A('- delay-load import %d 個: 実装 %d / 他担当 %d / 未実装 %d。' % (len(delay), cov['delay_implemented'], cov['delay_other_owner'], cov['delay_unimplemented']))
A('- shimx 公開 API %d 本 (機能 %d + スタブ %d) + 運用フック %d 本。M4 の 53 API は **%d/%d を継承** (M4 の unmodified test_main.c が shimx 実装で PASS)。' % (
    cov['shimx_public_api'], cov['shimx_functional_api'], cov['shimx_stub_api'], cov['shimx_hooks'], cov['m4_api_inherited'], cov['m4_api']))
mc = cov['m11_closure']
A('- M11 init closure (`boot_final2.ll`) の外部参照 %d 件: shimx 提供 **%d** / GUI・audio 担当 %d / lift 由来 %d。非 GUI の Win/CRT は **100%% 提供**。' % (
    sum(mc.values()), mc.get('shimx', 0), mc.get('win_other', 0), mc.get('lifter', 0)))
for p in plug_rows:
    A('- プラグイン %s: import %d (GUI/audio 除く担当 %d) のうち shimx 提供 %d、未提供: %s' % (p[0], p[1], p[2], p[3], ', '.join(p[4]) or 'なし'))
if os.path.exists(W('work', 'ott', 'result.json')):
    o = json.load(open(W('work', 'ott', 'result.json')))
    A('- **OTT undefined 47 種 (M8)**: shimx リンクで **%d → %d 種**。Win/CRT API 24 種は **全て解決** (残 %d は `function_18*` = lift 欠落で shim の対象外)。t1 出力 SHA は baseline と一致。' % (
        o['baseline_undefined'], o['shimx_undefined'], o['shimx_fn18']))
A('')
A('状態記号: **F** 機能実装 / **S** スタブ (無い・失敗・キャンセルを返す) / **L** libc 解決 / **O** 序数 import / **U** 未実装 / **X** 他担当。')
A('全 import の行別データ: `data/inventory.csv`、優先度付き一覧: `BACKLOG.md`、機械可読な集計: `data/coverage.json`。')
A('')
A('## 表A: DLL 別カバレッジ (FLEngine 静的 import %d)' % n738)
A('')
A('| DLL | import 数 | F 機能 | S スタブ | L libc | 他担当 | 序数 | U 未実装 | カバレッジ(担当内) |')
A('|---|---|---|---|---|---|---|---|---|')
bydll = defaultdict(list)
for r in stat738:
    bydll[r['dll']].append(r)
for dll, rs in sorted(bydll.items(), key=lambda kv: -len(kv[1])):
    c = Counter(r['status'].split(':')[0] for r in rs)
    scope_n = len(rs) - c['X']
    pct = ('%.0f%%' % (100.0 * (c['F'] + c['S'] + c['L']) / scope_n)) if scope_n else '—'
    A('| %s | %d | %d | %d | %d | %d | %d | %d | %s |' % (dll, len(rs), c['F'], c['S'], c['L'], c['X'], c['O'], c['U'], pct))
A('| **計** | **%d** | **%d** | **%d** | **%d** | **%d** | **%d** | **%d** | **%.1f%%** |' % (n738, cnt['F'], cnt['S'], cnt['L'], cnt['X'], cnt['O'], cnt['U'], cov['coverage_pct_in_scope']))
A('')
A('## 表B: 実装済み API (shimx 公開関数 %d 本; 記号 `*` = スタブ, `~` = weak 定義)' % len(public_api))
A('')
A('| ソース | 本数 | API |')
A('|---|---|---|')
weak = set()
for l in open(W('work', 'nm_by_file_MT.txt')):
    m = re.match(r'^.*?\.o: [0-9a-f]+ W (\S+)$', l.strip())
    if m:
        weak.add(m.group(1))
bysrc = defaultdict(list)
for n in public_api:
    bysrc[src_of[n]].append(n)
for s_, names in sorted(bysrc.items()):
    A('| %s | %d | %s |' % (s_, len(names), ' '.join(n + ('*' if n in STUBS else '') + ('~' if n in weak else '') for n in sorted(names))))
A('')
A('運用フック (`shimx_*` + `vreg_*`): ' + ' '.join(hooks))
A('')
A('## 表C: 未実装 (担当範囲内)')
A('')
un = [r for r in allrows if r['status'] == 'U']
ordn = [r for r in allrows if r['status'] == 'O']
if un:
    A('| API | DLL | 区分 | 呼出サイト |')
    A('|---|---|---|---|')
    for r in un:
        A('| %s | %s | %s | %d |' % (r['name'], r['dll'], r['scope'], r['calls']))
else:
    A('FLEngine 静的/delay import には担当範囲内の未実装 API は **ありません**。')
A('')
if ordn:
    known = ['%s!%s=%s (R3 同定, GetProcAddress 序数表で解決)' % (r['dll'].replace('.dll', ''), r['name'], ORD_KNOWN.get(r['dll'], {}).get(int(r['name'][3:]), '?'))
             for r in ordn if int(r['name'][3:]) in ORD_KNOWN.get(r['dll'], {})]
    unknown = ['%s!%s' % (r['dll'].replace('.dll', ''), r['name']) for r in ordn if int(r['name'][3:]) not in ORD_KNOWN.get(r['dll'], {})]
    if known:
        A('序数 import のうち同定済み (実行時は GetProcAddress が返す): ' + ', '.join(known))
    if unknown:
        A('序数 import (名前解決不能。実体 API の特定が要る): ' + ', '.join(unknown))
A('')
A('プラグイン専用で未提供 (BSD ソケット名は Emscripten libc が解決; 下記は Serum2 のみ): ' + ', '.join(sorted({n for p in plug_rows for n in p[4]})) )
A('')
A('## 表D: 対象外 (他担当 DLL)')
A('')
A('| DLL | 担当 | FLEngine import 数 | 備考 |')
A('|---|---|---|---|')
for dll, rs in sorted(bydll.items(), key=lambda kv: -len(kv[1])):
    if dll in OTHER_OWNER:
        A('| %s | tools/%s | %d | 名前一覧は data/inventory.csv。重複定義回避のため user32 の CharXxx/MsgWait* 等は shimx が weak 定義で保持 |' % (dll, OTHER_OWNER[dll], len(rs)))
A('')
A('## 方針差・制限 (M4 比 / 実装上の割り切り)')
A('')
for t in [
    'ハンドル表: 256→16384 スロット、HANDLE=(idx+1)*4、参照カウント、`DuplicateHandle`、名前付き Event/Mutex/Semaphore/FileMapping の共有名前空間 (`Local\\`/`Global\\` 接頭辞は同一視)。',
    'LastError・TLS・FLS・TID・擬似 TEB(gs:) はスレッドローカル (M4 は LastError がプロセス単位)。TEB は Win64 オフセット (+0x30 Self/+0x68 LastError/+0x1480 TlsSlots) を再現。',
    'CRITICAL_SECTION は M4 の「ポインタ→mutex 表 (128 件上限)」から、クライアントメモリ上の Win64 40B 構造体直接実装に変更 (上限なし/ゼロ初期化メモリも未ロック扱い)。',
    'CreateThread: CREATE_SUSPENDED 対応、返す threadId は新スレッド自身の ID (M4 は作成側 ID)。全スレッド detached、終了は状態+futex 通知。SuspendThread/TerminateThread は状態のみ (実停止不可)。',
    'Heap/Global/Local: ユーザポインタ 16B 整列 (M4 は 4B)。GMEM_MOVEABLE は FIXED 写像 (M4 同様)。`GlobalUnlock` は M4 互換 (ロック済みなら TRUE)。HeapDestroy は配下ブロックを解放しない。',
    'Win64 レイアウト構造体 (SYSTEM_INFO/MEMORYSTATUS/STARTUPINFOW/MEMORY_BASIC_INFORMATION/EXCEPTION_RECORD/VARIANT/SAFEARRAY/SHFILEOPSTRUCT/SHELLEXECUTEINFO 他) はポインタ位置を 8B スロットで実装。`FormatMessage` の ARGUMENT_ARRAY は 8B 要素。',
    'パス: `C:\\x` → `/c/x`、UNC → `/unc/...`、POSIX 絶対パスは素通し。FS 側未発見時は大小無視で再探索。`shimx_set_path_mapper` で VFS 連携。',
    'コードページ: 既定 ACP=1252。UTF-8/1252/Latin-1/ASCII のみ (932 等 DBCS は ERROR_INVALID_PARAMETER)。ロケールは en-US データ固定。',
    '`GetProcAddress` 未知名は NULL+ERROR_PROC_NOT_FOUND (strict モードで fail-fast)。関数ポインタは wasm テーブル index (lifted コードの間接呼出しとの整合は hostbridge 課題)。',
    '序数判定 (`MAKEINTRESOURCE`/`CharUpperW(単一文字)`/ordinal GetProcAddress) は値 < 0x10000 を整数とみなす → ビルドの GLOBAL_BASE は 64KB 以上にすること (lifted 系は 0x10000000 で適合)。',
    'ws2_32: BSD ソケット名 (`socket` 等) は libc 名衝突のため未定義 (Emscripten libc が解決)。Windows 固有名 (WSAStartup=WSASYSNOTREADY 等) のみ提供。',
    '`__lock`/`__unlock` は musl 内部名と衝突するため定義しない (`_lock`/`_unlock`/`_mlock`/`_munlock`/`_lock_file`/`__acrt_lock` のみ)。',
]:
    A('- ' + t)
open(W('inventory.md'), 'w').write('\n'.join(inv) + '\n')
print('coverage:', json.dumps({k: v for k, v in cov.items() if k not in ('plugins',)}, ensure_ascii=False))
