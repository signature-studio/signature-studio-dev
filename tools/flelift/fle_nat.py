"""fle_nat.py — libflenative.so の ctypes ラッパ (FLEngine native 参照実行)。
原型 = tools/ott/native/ottnat.py。ASLR を切って VA 敷設を保証する。"""
import ctypes, os, struct, sys

_libc = ctypes.CDLL(None)
if (_libc.personality(0xffffffff) & 0x0040000) == 0 and os.environ.get('FLE_NOASLR') != '1':
    os.environ['FLE_NOASLR'] = '1'
    os.execvp('setarch', ['setarch', 'x86_64', '-R', sys.executable] + sys.argv)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'shared'))
from paths import FL_WIN64_DIR
DLL = os.environ.get('FLE_PE') or os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
_lib = ctypes.CDLL(os.path.join(HERE, 'work', 'libflenative.so'))
_lib.fle_call.restype = ctypes.c_uint64
_lib.fle_call.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
_lib.fle_load.argtypes = [ctypes.c_char_p]
_lib.fle_load.restype = ctypes.c_int
_lib.fle_diff_blocks.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_long]
_lib.fle_diff_blocks.restype = ctypes.c_long
_lib.fle_img.restype = ctypes.c_void_p
_lib.fle_read.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_long]
_lib.fle_read.restype = ctypes.c_long
_lib.fle_write.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_long]
_lib.fle_write.restype = ctypes.c_long

_loaded = False


def load(path=DLL):
    global _loaded
    _lib.fle_install_segv()
    r = _lib.fle_load(path.encode())
    if r != 0:
        raise RuntimeError('fle_load failed %d' % r)
    _loaded = True


def reset():
    _lib.fle_reset()


def call(fn, gpr=(), xmm=(), stk=()):
    """gpr: rcx,rdx,r8,r9 / xmm: xmm0-3 raw 64bit / stk: stack args。戻り (rax, xmm0 raw)"""
    g = (ctypes.c_uint64 * 4)(*(list(gpr) + [0] * (4 - len(gpr))))
    x = (ctypes.c_uint64 * 4)(*(list(xmm) + [0] * (4 - len(xmm))))
    s = (ctypes.c_uint64 * max(1, len(stk)))(*stk)
    o = (ctypes.c_uint64 * 2)()
    _lib.fle_call(fn, g, x, s, len(stk), o)
    return o[0], o[1]


def diff(va, n, maxb=512):
    out = (ctypes.c_uint64 * (maxb * 3))()
    k = _lib.fle_diff_blocks(va, n, out, maxb)
    return [(out[i * 3], out[i * 3 + 1], out[i * 3 + 2]) for i in range(k)]


def rd(addr, n):
    buf = (ctypes.c_ubyte * n)()
    if _lib.fle_read(ctypes.c_uint64(addr), buf, n) < 0:
        raise RuntimeError('fle_read oob %#x' % addr)
    return bytes(buf)


def wr(addr, b):
    if _lib.fle_write(ctypes.c_uint64(addr), (ctypes.c_ubyte * len(b)).from_buffer_copy(b), len(b)) < 0:
        raise RuntimeError('fle_write oob %#x' % addr)
