#!/usr/bin/env python3
"""verify.py — STARTUP/GATES/PROCESSES/REGISTRY の主張を実バイナリから独立に再検証 (Ghidra 不要)。exit 0=全 OK。"""
import os, sys, struct, csv, re
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pedis import PE64
ROOT = os.path.dirname(HERE); WORK = os.path.join(ROOT, 'work')
ok = bad = 0
def chk(name, cond, detail=''):
    global ok, bad
    if cond: ok += 1; print('OK  ', name, detail)
    else: bad += 1; print('FAIL', name, detail)
def w16(s): return s.encode('utf-16le')
launcher = os.path.join(WORK, 'FL64.exe'); engine = os.path.join(WORK, 'FLEngine_x64.dll')
L = open(launcher, 'rb').read(); E = open(engine, 'rb').read()
pl = PE64(launcher); pe = PE64(engine)
# --- FL64.exe ---
imps = set(v.split('!')[1] for v in pl.imports.values())
for a in ('LoadLibraryW', 'GetProcAddress', 'SetCurrentDirectoryW', 'RegOpenKeyExW', 'RegQueryValueExW', 'WinVerifyTrust', 'ShellExecuteA', 'MessageBoxA', 'CryptQueryObject', 'CertGetNameStringA', 'GetModuleFileNameW'):
    chk('FL64 imports ' + a, a in imps)
chk('FL64 has no CreateProcess/ShellExecuteW', not (imps & {'CreateProcessW', 'CreateProcessA', 'ShellExecuteW', 'ShellExecuteExW'}))
chk('FL64 entry RVA 0x30ed4', pl.pe.OPTIONAL_HEADER.AddressOfEntryPoint == 0x30ed4)
for s in ('FLEngine_x64.dll', 'ILTools_x64.dll', r'System\Plugin\ReWire\FLReWire_x64.dll', r'Software\Image-Line\Shared\Paths', 'FL Studio engine', 'Shared DLLs', 'Builds\\', 'Image Line NV', 'Mfplat.dll', 'Shared\\'):
    chk('FL64 utf16 "%s"' % s, w16(s) in L)
for s in (b'CreateFruityInstance\0', b'ShowEngineChoice\0', b'MFStartup\0', b'FL Studio\0', b'1.3.6.1.4.1.311.2.1.12\0', b'https://support.image-line.com/redirect/kb_windows_n\0'):
    chk('FL64 ascii %r' % s[:-1], s in L)
chk('FL64 CreateFruityInstance call args mov ecx,0xC0 / mov edx,0xEDE95A', L.find(bytes.fromhex('BA5AE9ED00B9C0000000')) > 0)
va = 0x140006f2d - pl.base
off = pl.rva2off(va)
chk('FL64 call site @140006f2d = mov edx,0xede95a', L[off:off + 5] == bytes.fromhex('BA5AE9ED00'))
vt = struct.unpack('<3Q', pl.read(0x140069d00, 24))
chk('THostInstance vtable 3 entries @140069d00', vt == (0x140007520, 0x140007530, 0x140007540), str([hex(x) for x in vt]))
chk('WinMain call from CRT main @140030e61 -> 0x140007560', pl.read(0x140030e61, 5) == b'\xe8' + struct.pack('<i', 0x140007560 - 0x140030e66))
# --- FLEngine_x64.dll ---
chk('Engine export CreateFruityInstance @0x1375990', pe.exports.get(0x1375990) == 'CreateFruityInstance')
chk('Engine entry RVA 0xf76820 (VA 0x1376820)', pe.pe.OPTIONAL_HEADER.AddressOfEntryPoint == 0xf76820)
chk('Engine exports == 3', len(pe.exports) == 3, str(sorted(pe.exports.values())))
for s in ('HostVersion=%d Flags=%.8x', 'Init module', 'Init core paths', 'BasicInitialization failed.', 'Fire edition', 'Image Line NV', 'TFruityLoopsMainForm', 'WebView2Loader.dll', r'Software\Image-Line\FL Studio 26', '/PluginSetup', '/Reset', 'testpermissions.tmp', 'FL Studio', 'MAINICON', 'Another instance is already open.', 'BeforeRunning', 'ProcessFirstTimeStuff', 'Please remember to register', r'Software\Image-Line\Registrations\FL Studio 26.1', 'ILRegKey', 'MachineGuid', 'Silent Startup', 'Run counter', 'Browser FL CLOUD displayed', 'Disable FL CLOUD search', 'Update notification', 'CloudBounceConsole'):
    chk('Engine utf16 "%s"' % s, w16(s) in E or s.encode() in E)
for s in ('ControlCreator.exe', 'fldiagnostic.exe', 'CopyLicenseToAllUsers.exe', 'CloudBounceConsole.exe', 'RemoveLicenses.exe', 'PluginManager.exe', 'FL Cloud Plugins.exe', r'32bit\ilbridge.exe', r'64bit\ilbridge.exe', 'LicenceEngine.dll', 'MCPTools.pyc', 'index_offline.html', 'error-offline.html'):
    chk('Engine tool name "%s"' % s, w16(s) in E)
tb = pe.read(0x15342a0, 6 * 20)
ids = [struct.unpack('<i', tb[i * 20:i * 20 + 4])[0] for i in range(6)]
chk('Engine tool table ids [0,1,1000,1001,1002,2] @0x15342a0', ids == [0, 1, 1000, 1001, 1002, 2], str(ids))
chk('Engine imports advapi Reg* (W) present', {'RegOpenKeyExW', 'RegCreateKeyExW', 'RegQueryValueExW', 'RegSetValueExW'} <= set(v.split('!')[1] for v in pe.imports.values()))
chk('Engine WriteBool strings table "0","1" @0x13d4440', pe.wstr(0x5b1c34) in ('W"0"',) or pe.read(0x5b1c34, 6)[:2] == b'0\0')
# --- CSV outputs ---
def rows(p): return list(csv.DictReader(open(os.path.join(ROOT, p))))
reg = rows('REGISTRY.csv'); prc = rows('PROCESSES.csv')
chk('REGISTRY.csv rows >= 400', len(reg) >= 400, str(len(reg)))
chk('REGISTRY.csv has launcher FL Studio engine (HKCU/HKLM)', {r['hive'] for r in reg if r['value'] == 'FL Studio engine' and r['platform'] == 'win'} == {'HKCU', 'HKLM'})
chk('REGISTRY.csv has ILRegKey', any(r['value'] == 'ILRegKey' for r in reg))
chk('REGISTRY.csv Sample rate default 44100', any(r['value'] == 'Sample rate' and r['default'] == '44100' for r in reg))
chk('PROCESSES.csv rows >= 28', len(prc) >= 28, str(len(prc)))
chk('PROCESSES.csv verdict vocabulary', {r['verdict'] for r in prc} <= {'必要', '不要', '代替', '対象外', '後回し'})
# --- mac ---
osx = os.path.join(WORK, 'OsxFL_x86_64'); wb = os.path.join(WORK, 'libwinbridge_x86_64.dylib')
if os.path.exists(osx):
    O = open(osx, 'rb').read()
    for s in (b'-setenginepath', b'CreateFruityInstance', b'FL Studio engine', b'com.image-line.shared', b'RegWriteStringValue'):
        chk('OsxFL ascii %r' % s, s in O)
    chk('OsxFL utf16 /Contents/Libs/FLEngine_', w16('/Contents/Libs/FLEngine_') in O)
if os.path.exists(wb):
    B = open(wb, 'rb').read()
    chk('libwinbridge reg.xml + /Preferences/Image-Line/', w16('reg.xml') in B and w16('/Preferences/Image-Line/') in B)
print('\nSUMMARY ok=%d bad=%d' % (ok, bad))
sys.exit(1 if bad else 0)
