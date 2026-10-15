"""LD-179 (#3862): m11_post の m11_tr_ 生成で %tagPOINT 引数を a0 から組む (x = 下位 32bit, y = 上位 32bit) ことと、
4256c0 の機械語入口型 (rcx の 8 バイト値) の単体テスト。失敗で非 0 終了。"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from ldlib import cases  # noqa: E402

POST = os.path.join(HERE, '..', '..', 'm11', 'm11_post.py')
IR = '''%tagPOINT = type { i32, i32 }

define i64 @function_4256c0(%tagPOINT %Point) local_unnamed_addr {
  ret i64 0
}

define i64 @function_1234(i64 %x) local_unnamed_addr {
  ret i64 %x
}
'''


def main():
    assert cases.MACHINE_ENTRY[0x4256c0] == ['i64']
    s = cases.machine_sig(0x4256c0, {'ret': 'i64', 'params': ['%tagPOINT'], 'defined': True})
    assert cases.supported_sig(s) and s['params'] == ['i64'] and s['ir_params'] == ['%tagPOINT'], s

    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 'in.ll')
        dst = os.path.join(d, 'out.ll')
        open(src, 'w').write(IR)
        subprocess.run([sys.executable, POST, src, dst], check=True, stdout=subprocess.DEVNULL)
        out = open(dst).read()
    body = out.split('define i64 @m11_tr_function_4256c0(', 1)[1].split('\n}', 1)[0]
    assert 'unsupported param' not in body, body
    for want in ['trunc i64 %a0 to i32', 'lshr i64 %a0, 32', 'insertvalue %tagPOINT undef, i32 %px0, 0',
                 'insertvalue %tagPOINT %u0, i32 %py0, 1', 'call i64 @function_4256c0(%tagPOINT %c0)']:
        assert want in body, (want, body)
    assert body.index('lshr') < body.index('insertvalue'), body
    tramp = out.split('define i64 @m11_tr_function_1234(', 1)[1].split('\n}', 1)[0]
    assert 'call i64 @function_1234(i64 %a0)' in tramp, tramp
    print('PASS test_ld179_tagpoint_tr')


if __name__ == '__main__':
    main()
