#!/usr/bin/env python3
"""SR-1d (#340) verifier. Checks (exit 1 on any FAIL) that nlohmann::json v3.12 binary_reader/binary_writer live at the
addresses claimed in host/REPORT.md §5-2, using 3 independent evidence classes, plus negative controls.
usage: sr1d_verify.py <pe> <index.npz>   (index from sr3_index.py)
 E1  error-message literals of binary_reader.hpp (v3.12) -> referencing functions
 E2  sax_parse jump table (0x180256dc0, input_format_t {json,cbor,msgpack,ubjson,bson,bjdata}) decoded from the PE
 E3  caller of sax_parse: `mov edx, <fmt>` immediately before `call 0x180256dc0` in 0x1801bfb00 / 0x1801bf5f0
 N*  negative controls: each is the same check run against a deliberately wrong expectation and must FAIL."""
import sys, struct, bisect
import numpy as np
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PATH, IDX = sys.argv[1:3]
pe = pefile.PE(PATH, fast_load=True)
IMG = pe.OPTIONAL_HEADER.ImageBase
data = open(PATH, 'rb').read()
mm = pe.get_memory_mapped_image()
z = np.load(IDX); funcs = z['funcs']; refs = z['refs']
fst = funcs[:, 0].tolist()
rip = refs[refs[:, 2] == 0]
o = np.argsort(rip[:, 1], kind='stable'); rt = rip[o, 1]; rs = rip[o, 0]
secs = [(s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]
text = next(s for s in pe.sections if s.Name.startswith(b'.text')); TB = text.get_data(); TVA = text.VirtualAddress


def fn_of(rva):
    i = bisect.bisect_right(fst, rva) - 1
    return int(funcs[i][0]) + IMG if i >= 0 and funcs[i][0] <= rva < funcs[i][1] else None


def refs_to_literal(lit):
    out = set(); p = 0
    while True:
        p = data.find(lit, p)
        if p < 0:
            break
        for va, po, ps in secs:
            if po <= p < po + ps:
                rva = va + p - po
                lo = np.searchsorted(rt, rva, 'left'); hi = np.searchsorted(rt, rva + len(lit), 'left')
                out |= {fn_of(int(s)) for s in rs[lo:hi]} - {None}
        p += 1
    return out


fails = []
def check(name, ok, detail=''):
    print(f"{'PASS' if ok else 'FAIL'}\t{name}\t{detail}")
    if not ok:
        fails.append(name)
def negctl(name, ok_wrong_expectation, detail=''):
    """a negative control passes only when the check, run on a wrong expectation, FAILS"""
    print(f"{'PASS' if not ok_wrong_expectation else 'FAIL'}\tNEGCTL {name}\t{detail}")
    if ok_wrong_expectation:
        fails.append('negctl:' + name)


# ---------- E1: literal -> function (binary_reader.hpp v3.12; per-function mapping verified against upstream source) ----------
E1 = {  # literal : (upstream function, expected referencing function)
    b'expected length specification (0x60-0x7B) or indefinite string type (0x7F); last byte: 0x': ('get_cbor_string', 0x18025bbd0),
    b'expected length specification (0x40-0x5B) or indefinite binary array type (0x5F); last byte: 0x': ('get_cbor_binary', 0x18025b510),
    b'expected length specification (0xA0-0xBF, 0xD9-0xDB); last byte: 0x': ('get_msgpack_string', 0x18025d200),
    b'expected length type specification (U, i, I, l, L) after \'#\'; last byte: 0x': ('get_ubjson_size_type', 0x180261c90),
    b'expected length type specification (U, i, I, l, L); last byte: 0x': ('get_ubjson_size_value', 0x18025fbb0),
    b"expected '#' after type information; last byte: 0x": ('get_ubjson_type', 0x180263d10),
    b'BJData object does not support ND-array size in optimized format': ('get_ubjson_object', 0x180261410),
    b'Unsupported BSON record type 0x': ('parse_bson_element_internal', 0x1802598d0),
    b'expected end of input; last byte: 0x': ('parse_cbor_internal/sax_parse tail', 0x180256dc0),
}
for lit, (up, want) in E1.items():
    got = refs_to_literal(lit)
    check(f'E1 {up}', want + 0 in got or (want in got), f'literal refs={sorted(hex(x) for x in got)} expect {want:#x}')
negctl('E1 literal with last char flipped has 0 hits',
       len(refs_to_literal(b'expected length specification (0x60-0x7B) or indefinite string type (0x7F); last byte: 0y')) > 0)
negctl('E1 wrong expectation (get_cbor_string != 0x18025b510)',
       0x18025b510 in refs_to_literal(b'expected length specification (0x60-0x7B) or indefinite string type (0x7F); last byte: 0x'))

# ---------- E2: sax_parse jump table ----------
SAX = 0x180256dc0
off = SAX - IMG
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
tbl = None
for ins in md.disasm(TB[off - TVA:off - TVA + 80], SAX):
    if ins.mnemonic == 'lea' and 'rip' in ins.op_str and tbl is None:
        tbl = ins.address + ins.size + ins.operands[1].mem.disp
        break
targets = {}
for i in range(5):
    d = struct.unpack_from('<i', mm, tbl - IMG + 4 * i)[0]
    targets[i + 1] = tbl + d       # `dec edx` before the switch: index = input_format_t - 1
check('E2 jump table is 5 entries (cbor,msgpack,ubjson,bson,bjdata)', tbl is not None and len(targets) == 5, f'table={tbl:#x}')


def callee_of_case(case_va):
    """first direct call in the case block = the parse_*_internal function"""
    for ins in md.disasm(TB[case_va - IMG - TVA:case_va - IMG - TVA + 128], case_va):
        if ins.mnemonic == 'call':
            return ins.operands[0].imm


expect = {1: ('cbor -> parse_cbor_internal', 0x1802571e0), 2: ('msgpack -> parse_msgpack_internal', 0x1802580d0),
          3: ('ubjson -> parse_ubjson_internal', 0x18025e340), 4: ('bson -> parse_bson_internal', 0x180257130),
          5: ('bjdata -> parse_ubjson_internal (shared with ubjson)', 0x18025e340)}
cb = {k: callee_of_case(v) for k, v in targets.items()}
for k, (nm, want) in expect.items():
    check(f'E2 fmt={k} {nm}', cb[k] == want, f'case={targets[k]:#x} callee={cb[k]:#x}')
# parse_cbor_internal must (transitively one hop) reference both cbor string/binary readers
def direct_callees(fva):
    i = bisect.bisect_right(fst, fva - IMG) - 1; b, e = int(funcs[i][0]), int(funcs[i][1]); out = set()
    for ins in md.disasm(TB[b - TVA:e - TVA], b + IMG):
        if ins.mnemonic in ('call', 'jmp') and ins.operands[0].type == 2:
            out.add(ins.operands[0].imm)
    return out
cc = direct_callees(0x1802571e0)
check('E2 parse_cbor_internal(0x1802571e0) calls get_cbor_string+get_cbor_binary', {0x18025bbd0, 0x18025b510} <= cc)
check('E2 parse_msgpack_internal(0x1802580d0) calls get_msgpack_string', 0x18025d200 in direct_callees(0x1802580d0))
negctl('E2 wrong: msgpack case calls get_cbor_string', 0x18025bbd0 in direct_callees(0x1802580d0))
negctl('E2 wrong: ubjson case == cbor callee', cb[3] == expect[1][1])

# ---------- E3: what format do reader entry points pass? ----------
def fmt_passed(fva):
    i = bisect.bisect_right(fst, fva - IMG) - 1; b, e = int(funcs[i][0]), int(funcs[i][1]); last = None
    for ins in md.disasm(TB[b - TVA:e - TVA], b + IMG):
        if ins.mnemonic == 'mov' and ins.op_str.startswith('edx, ') and ins.op_str[5:].isdigit():
            last = int(ins.op_str[5:])
        if ins.mnemonic == 'call' and ins.operands[0].imm == SAX:
            return last
fc, fu = fmt_passed(0x1801bfb00), fmt_passed(0x1801bf5f0)
check('E3 0x1801bfb00 passes format 1 (= cbor)', fc == 1, f'edx={fc}')
check('E3 0x1801bf5f0 passes format 3 (= ubjson)', fu == 3, f'edx={fu}')
negctl('E3 wrong: 0x1801bfb00 is ubjson', fc == 3)
negctl('E3 wrong: 0x1801bf5f0 is cbor', fu == 1)
# which of them does the version-2 branch of 0x1801bf1c0 call? (call order: bf480 zstd-ish then bfb00)
c1 = direct_callees(0x1801bf1c0)
check('E3 0x1801bf1c0 calls both 0x1801bfb00 and 0x1801bf5f0', {0x1801bfb00, 0x1801bf5f0} <= c1)

# E4: container version dispatch inside 0x1801bf1c0 (instruction order, not just callee set)
i = bisect.bisect_right(fst, 0x1801bf1c0 - IMG) - 1; b, e = int(funcs[i][0]), int(funcs[i][1])
ins_l = list(md.disasm(TB[b - TVA:e - TVA], b + IMG))
calls = [(x.address, x.operands[0].imm) for x in ins_l if x.mnemonic == 'call' and x.operands[0].type == 2]
order = [c for _, c in calls]
# version==2 path: `cmp eax, 2 ; je T` -> T's first call must be 0x1801bf480 (zstd-ish), followed by `cmp rax, -0x78` (ZSTD_isError) then 0x1801bfb00 (CBOR)
je_t = next(ins_l[k + 1].operands[0].imm for k, x in enumerate(ins_l[:-1]) if x.mnemonic == 'cmp' and x.op_str == 'eax, 2' and ins_l[k + 1].mnemonic == 'je')
first_call_at_T = next(x.operands[0].imm for x in ins_l if x.address >= je_t and x.mnemonic == 'call')
k480 = order.index(0x1801bf480)
cmp_after = next(x for x in ins_l if x.address > calls[k480][0] and x.mnemonic == 'cmp')
check('E4 version==2 branch (cmp eax,2; je) first calls 0x1801bf480', first_call_at_T == 0x1801bf480, f'je target={je_t:#x}')
check('E4 0x1801bf480 result checked with `cmp rax, -0x78` (= ZSTD_isError: ZSTD_error_maxCode 120)', cmp_after.op_str == 'rax, -0x78', cmp_after.op_str)
check('E4 order: 0x1801bf480 -> 0x1801bfb00 (version 2 = zstd + CBOR)', order.index(0x1801bf480) < order.index(0x1801bfb00))
check('E4 order: 0x180571dc0 -> 0x1801bf5f0 (version 0/1 = zlib-window + UBJSON)', order.index(0x180571dc0) < order.index(0x1801bf5f0))
negctl('E4 wrong: version 2 reaches 0x180571dc0 first', first_call_at_T == 0x180571dc0)
negctl('E4 wrong: 0x1801bf5f0 called before 0x180571dc0', order.index(0x1801bf5f0) < order.index(0x180571dc0))

# ---------- writer: 0x1801be2e0 -> 0x1801bea90 -> 0x180256250 emits CBOR initial bytes ----------
check('W1 writer 0x1801be2e0 calls 0x1801bea90', 0x1801bea90 in direct_callees(0x1801be2e0))
check('W2 0x1801bea90 calls write_cbor 0x180256250', 0x180256250 in direct_callees(0x1801bea90))
b = int(funcs[bisect.bisect_right(fst, 0x180256250 - IMG) - 1][0]); e = int(funcs[bisect.bisect_right(fst, 0x180256250 - IMG) - 1][1])
def imms(fva):
    i = bisect.bisect_right(fst, fva - IMG) - 1; b, e = int(funcs[i][0]), int(funcs[i][1])
    return [ins.op_str for ins in md.disasm(TB[b - TVA:e - TVA], b + IMG) if ins.mnemonic in ('mov', 'or', 'add')]
has = lambda L, s: any(s in x for x in L)
# upstream binary_writer.hpp v3.12 write_cbor: null 0xF6 (l.102), bool 0xF4|b (l.110), half-inf 0xF9 (l.213), 0xFC (l.221)
w = imms(0x180256250)
check('W3 write_cbor 0x180256250 emits 0xF6 null, 0xF4|b bool, 0xF9 half-float, 0xFC', has(w, 'dl, 0xf6') and has(w, 'dl, 0xf4') and has(w, 'dl, 0xf9') and has(w, 'edx, 0xfc'))
# upstream get_cbor_float_prefix 0xFA/0xFB (l.1303/1308) and its msgpack twin get_msgpack_float_prefix 0xCA/0xCB share one template pair
f = imms(0x180256c70)
check('W4 0x180256c70 holds cbor float prefixes 0xFA/0xFB (+ msgpack twins 0xCA/0xCB)', has(f, 'eax, 0xfa') and has(f, 'eax, 0xfb') and has(f, 'edx, 0xca') and has(f, 'edx, 0xcb'))
check('W5 write_cbor 0x180256250 calls 0x180256c70 (float prefix)', 0x180256c70 in direct_callees(0x180256250))
negctl('W3 wrong: msgpack null 0xc0 emitted by write_cbor 0x180256250', has(w, 'dl, 0xc0'))
negctl('W4 wrong: 0xfa also in neighbour helper 0x180256bb0', has(imms(0x180256bb0), 'eax, 0xfa'))

# L: ABI of the DOM seen by Xfer-side code. write_cbor reads basic_json inline: m_type byte @+0, m_value ptr @+8, array = begin/end pair of 16-byte
# elements (`sub rbx,[rax]; sar rbx,4`), object = std::map walked via node bytes (`cmp byte ptr [reg+0x19],0` = MSVC _Tree_node::_Isnil after 3 ptrs + _Color).
lay = [x for x in md.disasm(TB[0x180256250 - IMG - TVA:0x180256250 - IMG - TVA + 2172], 0x180256250)]
ops = [x.mnemonic + ' ' + x.op_str for x in lay]
check('L1 write_cbor reads basic_json type byte @+0 and value ptr @+8', 'movzx eax, byte ptr [rdx]' in ops and 'mov rax, qword ptr [rdi + 8]' in ops)
check('L2 write_cbor array size = (end-begin)>>4 (16-byte element, MSVC vector begin/end)', 'sar rbx, 4' in ops)
check('L3 write_cbor map walk tests byte [node+0x19] (MSVC std::map _Isnil)', any(o.startswith('cmp byte ptr [r') and o.endswith('+ 0x19], 0') for o in ops))
negctl('L3 wrong: _Isnil at +0x1a', any(o.startswith('cmp byte ptr [r') and o.endswith('+ 0x1a], 0') for o in ops))

print('\nRESULT', 'FAIL ' + ','.join(fails) if fails else 'ALL PASS')
sys.exit(1 if fails else 0)
