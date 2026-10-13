#!/usr/bin/env python3
"""emu_reg.Emu で FLEngine の登録パーサ 0x10c7cd0 を入力ごとに実行し、観測値を results/cases.{json,md} に出す。
入力の license 群は vreg の seed (tools/startup/vreg/data/seed.json) の apply=true エントリをそのまま使う。
再現: python3 tools/startup/license_obs/run_cases.py   (要 FL_WIN64_DIR, uv pip install pefile capstone unicorn)
"""
import json, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu_reg import Emu, Reg, FLAG, ENTRY  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, '..', 'vreg', 'data', 'seed.json')
BTN = 0x15e0488
GUID_A = '12345678-aaaa-bbbb-cccc-1234567890ab'


def seed_license(reg, guid=GUID_A, il_override=None, drop_il=False, drop_guid=False):
    d = json.load(open(SEED))
    for e in d['entries']:
        if e.get('group') == 'license' and e.get('apply'):
            if drop_il and e['name'] == 'ILRegKey':
                continue
            v = e['value']
            if il_override is not None and e['name'] == 'ILRegKey':
                v = il_override
            reg.put(e['hive'], e['key'], e['name'], v)
    if not drop_guid:
        reg.put('HKLM', 'SOFTWARE\\Microsoft\\Cryptography', 'MachineGuid', guid)


def observe(name, reg, cl=0, comp='PC1', appdata='C:\\Users\\u\\AppData\\Roaming', patches=()):
    e = Emu(reg, comp=comp, appdata=appdata)
    e.setup_globals()
    for va, b in patches:
        e.uc.mem_write(va, b)
    t = time.time()
    st = e.run(cl=cl)
    reads = []
    for ev in reg.log:
        if ev[0] == 'read':
            reads.append(f'{ev[1]}\\{ev[2]} :: {ev[3]}')
    opens = sorted({f'{ev[1]}\\{ev[2]}' for ev in reg.log if ev[0] == 'open'})
    return {
        'case': name, 'cl': cl, 'status': st if st == 'ok' else st[:160],
        'flag_hex': e.rd(FLAG, 1).hex(), 'gradeChar_hex': e.rd(e.grade_ptr, 1).hex(),
        'button_id': struct.unpack('<I', e.rd(struct.unpack('<Q', e.rd(BTN, 8))[0], 4))[0],
        'unknown_apis': sorted(getattr(e, 'unknown', set())),
        'api_calls': len(e.api_log), 'registry_values_read': sorted(set(reads)),
        'registry_keys_opened': opens, 'elapsed_s': round(time.time() - t, 2),
    }


def main():
    out = []
    # --- 入力パターン (A: ILRegKey 無し / D: 空 / B,C: 非空 = VM 復号経路) ---
    def seeded(**kw):
        r = Reg()
        seed_license(r, **kw)
        return r
    out.append(observe('A1 ILRegKey 無し (cl=0)', seeded(drop_il=True)))
    out.append(observe('A2 ILRegKey 無し (cl=1 Fire check)', seeded(drop_il=True), cl=1))
    out.append(observe('A3 ILRegKey 無し + 別 MachineGuid / ComputerName / AppData', seeded(drop_il=True, guid='ffffffff-0000-1111-2222-333344445555'),
                       comp='OTHER-PC', appdata='D:\\x\\Roaming'))
    out.append(observe('A4 ILRegKey 無し + MachineGuid 取得失敗', seeded(drop_il=True, drop_guid=True)))
    out.append(observe('D2 空文字列の ILRegKey', seeded(il_override='')))
    out.append(observe('B1 vreg seed のプレースホルダ (cl=0)', seeded()))
    out.append(observe('B2 vreg seed のプレースホルダ (cl=1)', seeded(), cl=1))
    out.append(observe('D1 16 進 128 文字の非正規 ILRegKey', seeded(il_override='0123456789ABCDEF' * 8)))
    # --- ネガティブコントロール (A1 の入力): 実行された機械語の書込を観測できていることの確認 ---
    out.append(observe('N1 gradeChar 初期値 imm 0x40→0x42 に改変 (0x10ca56f)', seeded(drop_il=True), patches=[(0x10ca56f, b'\x42')]))
    out.append(observe('N2 bit0 を立てる or の直前の jle を nop 化 (0x10cf4e4)', seeded(drop_il=True), patches=[(0x10cf4e4, b'\x90\x90')]))
    out.append(observe('N3 FLAG の初期化値 imm 改変: store 元 0x10d08d8 を 0x04 に (.data)', seeded(drop_il=True), patches=[(0x10d08d8, b'\x04')]))
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, 'results', 'cases.json'), 'w'), indent=1, ensure_ascii=False)
    md = ['<!-- 自動生成: python3 tools/startup/license_obs/run_cases.py (人手編集禁止) -->', '',
          '# 0x10c7cd0 の実機械語実行結果 (unicorn)', '',
          '| case | 終了 | flag byte[0x14f84a8] | gradeChar | button ID | 未実装 API | 値読取 (distinct) | 所要 s |', '|---|---|---|---|---|---|---|---|']
    for o in out:
        okc = o['status'] == 'ok'
        fl, gr, bt = (f"0x{o['flag_hex']}", f"0x{o['gradeChar_hex']}", o['button_id']) if okc else ('—', '—', '—')
        md.append(f"| {o['case']} | {o['status'][:48]} | {fl} | {gr} | {bt} | "
                  f"{','.join(o['unknown_apis']) or '-'} | {len(o['registry_values_read'])} | {o['elapsed_s']} |")
    md += ['', '## 値読取の内訳 (case A1 / A4 / B1)', '']
    for o in out:
        if o['case'][:2] in ('A1', 'A4', 'B1'):
            md.append(f"### {o['case']}")
            md += [f'- `{x}`' for x in o['registry_values_read']]
            md.append('')
    open(os.path.join(HERE, 'results', 'CASES.md'), 'w').write('\n'.join(md) + '\n')
    for o in out:
        print(o['case'], '|', o['status'][:70], '| flag', o['flag_hex'], 'grade', o['gradeChar_hex'], 'btn', o['button_id'], '| unk', o['unknown_apis'], '| reads', len(o['registry_values_read']))


if __name__ == '__main__':
    main()
