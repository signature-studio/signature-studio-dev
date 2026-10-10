#!/usr/bin/env python3
"""report_tables.py — results/*.json から REPORT 用の表を生成 (手転記による数値ミスの防止)。 usage: report_tables.py > results/TABLES.md"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, 'results')


def load(n):
    p = os.path.join(R, n)
    return json.load(open(p)) if os.path.exists(p) else None


def pct(a, b):
    return '%.2f%%' % (100.0 * a / b) if b else '-'


def main():
    cen = load('census.json')
    if cen:
        print('### census (capstone の disp 位置/長さ vs dispfix 真値)\n')
        print('| サンプル | 命令数 | disp 有 | rip 相対 | rip 誤り (率) | disp32 非 rip 誤り | 誤り計 (nop 除く) | 関数 誤り有/全 |')
        print('|---|--:|--:|--:|--:|--:|--:|--:|')
        for k, v in cen.items():
            c = v['counts']
            print('| %s | %d | %d | %d | %d (%s) | %d | %d (%d) | %d/%d |' % (
                k, c.get('n_ins', 0), c.get('disp', 0), c.get('n_rip', 0), c.get('err_rip', 0), pct(c.get('err_rip', 0), c.get('n_rip', 0)),
                c.get('err_disp32', 0), c.get('err', 0), c.get('err_nonnop', 0), c.get('funcs_with_err', 0), c.get('n_funcs', 0)))
        S = lambda key: sum(v['counts'].get(key, 0) for v in cen.values())
        print('\n全 sample 合計: rip 相対 mem.disp 値の検証 %d 件中 不一致 %d / imm_offset 不整合 %d / 誤りの原因 = 66 prefix %d + VEX2.pp66 %d + その他 %d / 67 付き rip 相対 %d / phantom disp %d' % (
            S('rip_val_checked'), S('rip_val_mismatch'), S('imm_offset_mismatch'), S('cls_legacy66'), S('cls_vex2pp66'), S('cls_other'), S('n_addr32_rip'), S('phantom_disp')))
    imp = load('impact_hash.json')
    if cen and imp:
        g = lambda name, key: cen[name]['counts'].get(key, 0)
        DEL, FLE, BAL, MAC, OTT = ('Delphi plugin 133 DLL (全 .pdata)', 'FLEngine_x64.dll (全 .pdata)', 'Fruity Balance closure (67 関数)',
                                   'mac Fruity Mach-O x86_64 slice (LC_FUNCTION_STARTS)', 'OTT F (icall closure 282 関数)')
        a, b = imp['fw_overlap_convention'], imp['win_funcs_convention']
        print('\n### ツール別の影響 (対象命令 = そのツールが disp を見る命令)\n')
        print('| ツール | disp の使い方 | サンプル | 対象命令数 | capstone 誤り (率) | 関数 hash 変化 |')
        print('|---|---|---|--:|--:|--:|')
        n = g(DEL, 'n_rip') + g(DEL, 'n_disp32'); e = g(DEL, 'err_rip') + g(DEL, 'err_disp32')
        print('| inventory/fw_overlap.py, p0c/kernel_matrix.py | disp_size==4 の全 disp32 をゼロ化 | Delphi 133 DLL | %d | %d (%s) | %d/%d (%s) |' % (n, e, pct(e, n), a['funcs_hash_changed'], a['funcs'], pct(a['funcs_hash_changed'], a['funcs'])))
        print('| inventory/win_funcs.py | rip 相対 disp32 のみゼロ化 | Delphi 133 DLL (hash は 180 PE) | %d | %d (%s) | %d/%d (%s) |' % (g(DEL, 'n_rip'), g(DEL, 'err_rip'), pct(g(DEL, 'err_rip'), g(DEL, 'n_rip')), b['funcs_hash_changed'], b['funcs'], pct(b['funcs_hash_changed'], b['funcs'])))
        print('| framework/fw_prep.py (同規約・編集禁止) | 同上 | FLEngine 全 .pdata / Balance closure | %d / %d | %d (%s) / %d (%s) | win_funcs と同規約 |' % (
            g(FLE, 'n_rip'), g(BAL, 'n_rip'), g(FLE, 'err_rip'), pct(g(FLE, 'err_rip'), g(FLE, 'n_rip')), g(BAL, 'err_rip'), pct(g(BAL, 'err_rip'), g(BAL, 'n_rip'))))
        print('| inventory/mac_funcs.py | rip 相対のみ | mac Fruity x86_64 slice | %d | %d (%s) | SimSynth で 20/340 (全体未計測) |' % (g(MAC, 'n_rip'), g(MAC, 'err_rip'), pct(g(MAC, 'err_rip'), g(MAC, 'n_rip'))))
        print('| icall_rewrite.py (modrm 自前計算) | disp 位置を modrm から算出 | OTT F | %d | 影響 0 (e2e 89/89 bit 一致; modrm_tail_len == dispfix) | - |' % g(OTT, 'n_rip'))
        tv = sum(v['counts'].get('rip_val_checked', 0) for v in cen.values())
        print('| mem.disp 値のみ使用 (x64c.py, liftlib/mc.py, khmach.py, m11 ldmach.py, serum2/freshair scripts ほか 42 ファイル) | address+size+mem.disp | 全 sample の rip 相対 | %d | 値不一致 0 | - |' % tv)
    if imp:
        a, b = imp['fw_overlap_convention'], imp['win_funcs_convention']
        print('\n### 関数 fingerprint への影響 (Delphi plugin)\n')
        print('| 規約 (使用スクリプト) | 関数数 | hash が変わる関数 | distinct hash legacy→fixed | ≥13 DLL 共有 hash legacy→fixed | framework 判定関数 |')
        print('|---|--:|--:|--:|--:|--:|')
        print('| fw_overlap: md5, 全 disp32 (fw_overlap.py / kernel_matrix.py), 133 DLL | %d | %d (%s) | %d→%d | %d→%d | DLL 当たり中央値 %s→%s, fw_fraction 中央値 %s→%s |' % (
            a['funcs'], a['funcs_hash_changed'], pct(a['funcs_hash_changed'], a['funcs']), a['legacy']['distinct_hashes'], a['fixed']['distinct_hashes'],
            a['legacy']['distinct_hash_in_ge_13_dlls'], a['fixed']['distinct_hash_in_ge_13_dlls'],
            a['legacy']['fw_funcs_per_dll_median'], a['fixed']['fw_funcs_per_dll_median'], a['legacy']['fw_fraction_median'], a['fixed']['fw_fraction_median']))
        print('| win_funcs: sha1, rip 相対 disp32 (win_funcs.py / framework/fw_prep.py), %d PE | %d | %d (%s) | %d→%d | %d→%d | %d→%d (非fw→fw %d / fw→非fw %d) |' % (
            b['files'], b['funcs'], b['funcs_hash_changed'], pct(b['funcs_hash_changed'], b['funcs']), b['distinct_hash_legacy'], b['distinct_hash_fixed'],
            b['ge13_legacy'], b['ge13_fixed'], b['fw_funcs_legacy'], b['fw_funcs_fixed'], b['flip_nonfw_to_fw'], b['flip_fw_to_nonfw']))
        print('\nlegacy 再現性: fw_overlap 集計 == stored fw_overlap.json: %s / win_funcs hash == stored winfuncs/*.json: %d/%d PE' % (
            a['legacy_reproduces_stored'], b['legacy_reproduces_stored_pe'], b['files']))
    pm = load('prefix_matrix.json')
    if pm:
        print('\n### prefix matrix\n')
        print('| opsize 区分 | case 数 | capstone disp_size 誤り | disp_offset 誤り | imm 誤り | dispfix 不一致 |')
        print('|---|--:|--:|--:|--:|--:|')
        for k, c in sorted(pm['by_opsize'].items()):
            print('| %s | %d | %d | %d | %d | %d |' % (k, c['n'], c.get('cs_disp_size_err', 0), c.get('cs_disp_off_err', 0),
                                                    c.get('cs_imm_size_err', 0) + c.get('cs_imm_off_err', 0),
                                                    c.get('fx_span_err', 0) + c.get('fx_layout_err', 0) + c.get('fx_modrm_err', 0)))


if __name__ == '__main__':
    main()
