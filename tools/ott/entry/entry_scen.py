#!/usr/bin/env python3
"""entry_scen.py — VST 入口比較 matrix の scenario 定義 (native / wasm 両ランナの唯一のソース)。

各 scenario は「VSTPluginMain + 連続する guest 呼出」の列。runner (entry_nat.py / entry_wasm.mjs) は
各 call の (rax, xmm0, buf) と終端状態 (obj / alog / am_counts) を同一 schema の JSON で吐く。

buffer 配置 (harness 固定アドレス — guest 側両 runner で同一):
  STR   0x30320000  0x201 B   文字列受信 (Fruity Wrapper の buffer サイズに合わせる)
  OUT_F 0x30321000  4 B       補助 4B (getParameter 出力確認 / beginLoadBank の 8B 書き先の一方)
  CKPT  0x30322000  8 B       effGetChunk の void** 受信 / 補助 8B
  CHUNK 0x30323000  4096 B    effSetChunk の data
  IN_A  0x30330000 / OU_A 0x30331000 / BUF 0x30340000  processReplacing 用 (tools/ott/diff と同型)

実測注記:
  - OTT の getParameter (vtbl+0x58) は float* (r8) に書かず **xmm0 で返す** (31 path 全部実測)。
  - effGetParamDisplay の float→文字列 path は DLL 内 CRT (未初期化) で native が SIGSEGV →
    比較対象は整数系 formatter のみ (DISP_OK)。float 系は到達確認 (coverage) のみ。
"""
import json

STR, OUT_F, CKPT, CHUNK = 0x30320000, 0x30321000, 0x30322000, 0x30323000
IN_A, OU_A, BUF = 0x30330000, 0x30331000, 0x30340000
N = 128

RVA = dict(vstmain=0x128ba0, dispatcher=0x126c00, setp=0x127520, getp=0x1271a0,
           procr=0x127450, procd=0x127440, process=0x127430,
           setp_ovr=0x125bd0, getp_ovr=0x11e5a0, sr=0x120ed0, bs=0x120ac0,
           getprog=0x11eae0, setprog=0x120d10, getpname=0x11eaf0, setpname=0x120e90,
           plabel=0x11e7b0, pdisplay=0x11e770, pname=0x11e820,
           gname_i=0x11eb70, aeffect=0x11c9f0, res2=0x120ee0, bsetprog=0x11ebc0)

# effGetParamDisplay の native 実測 OK set (ctor 既定値 + 0.5 preset の両方で
# 整数系 formatter を通る param)。float %f formatter 経路は CRT 未初期化で native crash。
DISP_OK = [4, 11, 12, 13, 14, 15, 19]
DISP_CRASH = [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 16, 17, 18]


def scen_list():
    S = []

    def base(name, calls):
        S.append((name, [{'c': 'vstmain'}] + calls))

    # --- dispatcher op 網羅 (native 実測 OK の 76 op + editor NULL 経路の GUI op) ---
    for op, val, buf in [(0, 0, 0), (3, 0, 0), (4, 0, 1), (5, 0, 1), (6, 0, 1), (8, 0, 1),
                         (9, 0, 0), (11, 64, 0), (12, 1, 0), (12, 0, 0), (22, 0, 0),
                         (25, 0, 1), (26, 3, 0), (27, 3, 1), (28, 0, 0), (29, 0, 1),
                         (31, 0, 0), (32, 0, 0), (33, 0, 1), (35, 0, 0), (36, 0, 0),
                         (37, 0, 0), (38, 0, 0), (39, 0, 0), (40, 0, 0), (41, 0, 0),
                         (42, 0, 1), (43, 0, 0), (44, 0, 0), (45, 0, 1), (46, 0, 0),
                         (47, 0, 1), (48, 0, 1), (49, 0, 0), (50, 0x1000, 1), (51, 0, 1),
                         (52, 0, 0), (53, 0, 0), (54, 0, 0), (55, 0, 0), (56, 0, 1),
                         (57, 0, 0), (58, 0, 0), (59, 128, 0), (61, 3, 0), (62, 0, 1),
                         (63, 0, 1), (64, 0, 1), (65, 0, 0), (66, 0, 0), (67, 0, 0),
                         (68, 0, 0), (69, CKPT, 1), (70, 0, 1), (71, 0, 1), (72, 0, 1),
                         (73, 0, 0), (74, 0, 0), (75, 0, 0), (76, 0, 0), (77, 0, 0),
                         (78, 0, 0), (79, 0, 0)]:
        base('op%d' % op, [{'c': 'disp', 'op': op, 'idx': 0, 'val': val, 'buf': buf}])
    base('op30', [{'c': 'disp', 'op': 30, 'idx': 0, 'val': 0, 'buf': 0},
                  {'c': 'disp', 'op': 30, 'idx': 0, 'val': 0, 'buf': 0, 'opt': 48000.0}])
    base('op60', [{'c': 'disp', 'op': 60, 'idx': 0, 'val': 0, 'buf': 0},
                  {'c': 'proc', 'n': N}])
    # --- getParameter / setParameter 往復 (AEffect 関数ポインタ経路) ---
    for i in (0, 1, 3, 7, 19):
        base('getp%d' % i, [{'c': 'setp', 'idx': i, 'fv': 0.75}, {'c': 'getp', 'idx': i}])
    base('getp_range', [{'c': 'getp', 'idx': i} for i in range(20)])  # 20..30 は未定義 path (stack 巻き読み) 非比較
    base('setp_all', [{'c': 'setp', 'idx': i, 'fv': v} for i, v in
                      [(0, 0.9), (1, 0.1), (4, 0.0), (4, 1.0), (19, 1.0), (19, 0.0)]])
    # --- 直接 virtual 呼出 (obj->method; 引数は MS x64 の位置 = rdx/r8/r9 + xmm) ---
    base('virt_sr', [{'c': 'virt', 'rva': RVA['sr'], 'xmm': {1: 96000.0}},
                     {'c': 'virt', 'rva': RVA['sr'], 'xmm': {1: 44100.0}}])
    base('virt_bs', [{'c': 'virt', 'rva': RVA['bs'], 'rdx': 512}, {'c': 'virt', 'rva': RVA['bs'], 'rdx': 128}])
    base('virt_prog', [{'c': 'virt', 'rva': RVA['setprog'], 'rdx': 0}, {'c': 'virt', 'rva': RVA['getprog']},
                       {'c': 'virt', 'rva': RVA['getpname'], 'rdx': STR, 'buf': 1},
                       {'c': 'virt', 'rva': RVA['setpname'], 'rdx': STR, 'buf': 1},
                       {'c': 'virt', 'rva': RVA['getprog']}])
    base('virt_plabel', [{'c': 'virt', 'rva': RVA['plabel'], 'rdx': i, 'r8': STR, 'buf': 1} for i in range(20)])
    base('virt_pname', [{'c': 'virt', 'rva': RVA['pname'], 'rdx': i, 'r8': STR, 'buf': 1} for i in range(21)])
    base('virt_pdisplay', [{'c': 'virt', 'rva': RVA['pdisplay'], 'rdx': i, 'r8': STR, 'buf': 1} for i in DISP_OK])
    base('virt_setp_ovr', [{'c': 'virt', 'rva': RVA['setp_ovr'], 'rdx': 2, 'xmm': {2: 0.3}},
                           {'c': 'getp', 'idx': 2}])
    base('virt_aeffect', [{'c': 'virt', 'rva': RVA['aeffect']}])
    base('virt_misc', [{'c': 'virt', 'rva': RVA['res2']},
                       {'c': 'virt', 'rva': RVA['bsetprog'], 'rdx': OUT_F, 'r8': CKPT,
                        'reads': ['out_f', 'ckpt']},
                       {'c': 'virt', 'rva': RVA['gname_i'], 'rdx': 0, 'r8': 0, 'r9': STR, 'buf': 1}])
    # --- chunk round-trip (op 23/24): OTT は ProgramChunks 非搭載 (base 既定 = 0) ---
    base('chunk_rt', [{'c': 'setchunk', 'is_preset': 1},
                      {'c': 'getchunk', 'is_preset': 1},
                      {'c': 'setchunk', 'is_preset': 0},
                      {'c': 'getchunk', 'is_preset': 0}])
    # --- GUI (editor NULL surrogate 経路): 到達確認 + 戻り 0 の突合 ---
    base('gui_ops', [{'c': 'disp', 'op': 13, 'idx': 0, 'val': 0, 'buf': 1},
                     {'c': 'disp', 'op': 14, 'idx': 0, 'val': 0, 'buf': 1},
                     {'c': 'disp', 'op': 15, 'idx': 0, 'val': 0, 'buf': 0},
                     {'c': 'disp', 'op': 19, 'idx': 0, 'val': 0, 'buf': 0}])
    # --- effOpen 後の実処理: param → resume (effMainsChanged) → processReplacing (thunk 経由) ---
    # param は 0..18 (DSP matrix の std と同配置; p19>0 は bypass [0x326]=1 で process 早期 return)
    base('full_cycle', [{'c': 'disp', 'op': 0, 'idx': 0, 'val': 0, 'buf': 0}] +
        [{'c': 'setp', 'idx': i, 'fv': 0.5} for i in range(19)] +
        [{'c': 'disp', 'op': 12, 'idx': 0, 'val': 1, 'buf': 0},
         {'c': 'proc', 'n': N},
         {'c': 'disp', 'op': 12, 'idx': 0, 'val': 0, 'buf': 0}])
    # --- effClose (dtor + operator delete): obj を破壊するので専用 scenario ---
    base('close', [{'c': 'disp', 'op': 0, 'idx': 0, 'val': 0, 'buf': 0},
                   {'c': 'disp', 'op': 1, 'idx': 0, 'val': 0, 'buf': 0}])
    # --- editor ctor (0x180120ff0) 直呼び: editor=NULL surrogate の到達確認 ---
    base('editor_null', [{'c': 'editorctor'}])
    return S


if __name__ == '__main__':
    import sys
    json.dump([{'name': n, 'steps': s} for n, s in scen_list()], open(sys.argv[1], 'w'))
    print('[entry_scen] scenarios', len(scen_list()))
