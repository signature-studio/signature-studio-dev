"""ottnat.py — OTT_vst2_win64.dll の実機械語を Linux プロセス内で直接実行する参照 (ctypes ラッパ)。"""
import ctypes, os, struct, sys
# brk/mmap が wasm linear 相当の固定アドレス (0x108xxxxx / 0x303xxxxx) と衝突しないよう ASLR を切って再 exec
_libc = ctypes.CDLL(None)
if (_libc.personality(0xffffffff) & 0x0040000) == 0 and os.environ.get('OTT_NOASLR') != '1':
    os.environ['OTT_NOASLR'] = '1'
    os.execvp('setarch', ['setarch', 'x86_64', '-R', sys.executable] + sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import PLUGINS_DIR
DLL = os.path.join(PLUGINS_DIR, 'ott', 'binaries', 'OTT_vst2_win64.dll')
_lib = ctypes.CDLL(os.path.join(HERE, '..', 'work', 'libottnative.so'))
_lib.ott_call.restype = ctypes.c_uint64
_lib.ott_call.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
_lib.ott_heap_alloc.restype = ctypes.c_uint64
_lib.ott_heap_alloc.argtypes = [ctypes.c_uint64]
_lib.ott_load.argtypes = [ctypes.c_char_p]

def f32b(v): return struct.unpack('<I', struct.pack('<f', v))[0]
def f64b(v): return struct.unpack('<Q', struct.pack('<d', v))[0]

def load(path=DLL):
    _lib.ott_install_segv()
    r = _lib.ott_load(path.encode())
    if r != 0: raise RuntimeError('ott_load failed %d' % r)

_lib.ott_enc_slots.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
def enc_slots(cookie_va, slot_vas):
    """encoded slot を enc(NULL)=cookie に初期化する (CRT 初期化相当の一部)。"""
    arr = (ctypes.c_uint64 * len(slot_vas))(*slot_vas)
    _lib.ott_enc_slots(cookie_va, arr, len(slot_vas))

def call(fn, gpr=(), xmm=(), stk=()):
    """gpr: 最大 4 個の整数引数 (位置 0..3 = rcx,rdx,r8,r9), xmm: 位置 0..3 の raw 64bit (f32 は f32b() を 32bit で, f64 は f64b())。
       戻り: (rax, xmm0_raw64)"""
    g = (ctypes.c_uint64 * 4)(*(list(gpr) + [0] * (4 - len(gpr))))
    x = (ctypes.c_uint64 * 4)(*(list(xmm) + [0] * (4 - len(xmm))))
    s = (ctypes.c_uint64 * max(1, len(stk)))(*stk)
    o = (ctypes.c_uint64 * 2)()
    _lib.ott_call(fn, g, x, s, len(stk), o)
    return o[0], o[1]

def alloc(n): return _lib.ott_heap_alloc(n)
def rd(addr, n): return ctypes.string_at(addr, n)
def wr(addr, b): ctypes.memmove(addr, b, len(b))
def u32(addr): return struct.unpack('<I', rd(addr, 4))[0]
def u64(addr): return struct.unpack('<Q', rd(addr, 8))[0]
def f32(addr): return struct.unpack('<f', rd(addr, 4))[0]
def f64(addr): return struct.unpack('<d', rd(addr, 8))[0]

_lib.ott_call_cov.restype = ctypes.c_uint64
_lib.ott_call_cov.argtypes = _lib.ott_call.argtypes
def call_cov(fn, gpr=(), xmm=(), stk=()):
    g = (ctypes.c_uint64 * 4)(*(list(gpr) + [0] * (4 - len(gpr))))
    x = (ctypes.c_uint64 * 4)(*(list(xmm) + [0] * (4 - len(xmm))))
    s = (ctypes.c_uint64 * max(1, len(stk)))(*stk)
    o = (ctypes.c_uint64 * 2)()
    _lib.ott_call_cov(fn, g, x, s, len(stk), o)
    return o[0], o[1]
def cov_bytes():
    _lib.ott_cov_buf.restype = ctypes.c_void_p
    return ctypes.string_at(_lib.ott_cov_buf(), 0x308000)

def cov_ct_bytes():
    _lib.ott_cov_ct_buf.restype = ctypes.c_void_p
    return ctypes.string_at(_lib.ott_cov_ct_buf(), 0x308000)
def cov_reset():
    b = ctypes.c_char_p; 
