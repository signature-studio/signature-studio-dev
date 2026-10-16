# SHX-T44 付録 (続き)

| call | 親 | callee | access_class | callee 読み先 | IR 突合 | IR alloca 幅 |
|---|---|---|---|---|---|---|
| 0x104400a | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x104403b | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x104404a | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x10440ec | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x11ca5a9 | function_11ca4e0 | function_11ca410 | read_local | 0x40:4:load | ir_truncated | 56 |
| 0x11e754c | function_11e7430 | function_11e6c00 | read_local | 0x54:4:load | unmatched | - |
| 0x11e755f | function_11e7430 | function_11e7310 | arg_home_only | 0x90:4:load | ir_truncated | 72 |
| 0x125da38 | function_125d9b0 | function_125d960 | read_local | 0x50:8:load | ir_truncated | 40 |
| 0x127d66e | function_127d420 | function_127d120 | arg_home_only | 0xec:4:other, 0xf0:4:other, 0xf4:4:other, 0xf8:4:other, 0xfc:4:load, 0x130:8:load | ir_truncated | 152 |
| 0x127dc1a | function_127d420 | function_127d120 | arg_home_only | 0xec:4:other, 0xf0:4:other, 0xf4:4:other, 0xf8:4:other, 0xfc:4:load, 0x130:8:load | ir_truncated | 152 |
| 0x1281aaf | function_1280530 | function_1280250 | arg_home_only | 0x290:8:load | ir_truncated | 208 |
| 0x1281c58 | function_1280530 | function_1280250 | arg_home_only | 0x290:8:load | ir_truncated | 208 |
| 0x1281ebd | function_1280530 | function_1280250 | arg_home_only | 0x290:8:load | ir_truncated | 208 |
| 0x12820fb | function_1280530 | function_1280250 | arg_home_only | 0x290:8:load | ir_truncated | 208 |
| 0x12825a2 | function_1280530 | function_1280380 | arg_home_only | 0x21c:4:load | ir_truncated | 208 |
| 0x12829d7 | function_1280530 | function_1280250 | arg_home_only | 0x290:8:load | ir_truncated | 208 |
| 0x1282ced | function_1280530 | function_1280250 | arg_home_only | 0x290:8:load | ir_truncated | 208 |
| 0x1283a77 | function_1280530 | function_1280170 | arg_home_only | 0x220:8:load, 0x228:4:load, 0x290:8:load | unmatched | - |
| 0x12844d7 | function_1280530 | function_1280380 | arg_home_only | 0x21c:4:load | ir_truncated | 208 |
| 0x1284d8b | function_1280530 | function_1280170 | arg_home_only | 0x220:8:load, 0x228:4:load, 0x290:8:load | unmatched | - |
| 0x12a4558 | function_12a4450 | function_12a4390 | write_local | 0x3c:4:store, 0x40:8:load, 0x4c:4:rmw, 0x90:4:rmw | ir_truncated | 136 |
| 0x12a4576 | function_12a4450 | function_12a4390 | write_local | 0x3c:4:store, 0x40:8:load, 0x4c:4:rmw, 0x90:4:rmw | ir_truncated | 136 |
| 0x12a9532 | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a9545 | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a9558 | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a956b | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a95b7 | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a95ca | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a95dd | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a95f0 | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a9603 | function_12a93b0 | function_12a9350 | write_local | 0x52:1:load, 0x58:4:rmw, 0x5c:4:load | ir_truncated | 64 |
| 0x12a96a2 | function_12a93b0 | function_12a92d0 | read_local | 0x53:1:load, 0x54:4:load, 0x58:4:load, 0x5c:4:load | ir_truncated | 64 |
| 0x12a96b5 | function_12a93b0 | function_12a92d0 | read_local | 0x53:1:load, 0x54:4:load, 0x58:4:load, 0x5c:4:load | ir_truncated | 64 |
| 0x12a96c8 | function_12a93b0 | function_12a92d0 | read_local | 0x53:1:load, 0x54:4:load, 0x58:4:load, 0x5c:4:load | ir_truncated | 64 |
| 0x12c66bf | function_12c6630 | function_12c6570 | arg_home_only | 0x90:4:load | ir_truncated | 72 |
| 0x12cac09 | function_12cab20 | function_12ca640 | arg_home_only | 0x88:4:load, 0x88:4:store, 0x8c:4:rmw | ir_truncated | 96 |
| 0x12cace0 | function_12cab20 | function_12ca640 | arg_home_only | 0x88:4:load, 0x88:4:store, 0x8c:4:rmw | ir_truncated | 96 |
| 0x12cb6d0 | function_12cb680 | function_12cb4c0 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12cb6df | function_12cb680 | function_12cb4c0 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12cb6ee | function_12cb680 | function_12cb4c0 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12cb6fd | function_12cb680 | function_12cb4c0 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12cb72c | function_12cb680 | function_12cb4c0 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12cb738 | function_12cb680 | function_12cb4c0 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12cb744 | function_12cb680 | function_12cb4f0 | write_local | 0x34:4:load, 0x34:4:store, 0x38:4:store, 0x70:8:other, 0x78:8:load | ir_truncated | 104 |
| 0x12cb781 | function_12cb680 | function_12cb4c0 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12cb7bd | function_12cb680 | function_12cb570 | write_local | 0x38:4:load, 0x38:4:store, 0x70:8:other, 0x78:8:load | ir_truncated | 104 |
| 0x12cb7dd | function_12cb680 | function_12cb570 | write_local | 0x38:4:load, 0x38:4:store, 0x70:8:other, 0x78:8:load | ir_truncated | 104 |
| 0x12cbb8a | function_12cb680 | function_12cb4f0 | write_local | 0x34:4:load, 0x34:4:store, 0x38:4:store, 0x70:8:other, 0x78:8:load | ir_truncated | 104 |
| 0x12cbbda | function_12cb680 | function_12cb5e0 | write_local | 0x34:4:load, 0x34:4:store, 0x38:4:store, 0x70:8:other, 0x78:8:load | ir_truncated | 104 |
| 0x12cbc11 | function_12cb680 | function_12cb5e0 | write_local | 0x34:4:load, 0x34:4:store, 0x38:4:store, 0x70:8:other, 0x78:8:load | ir_truncated | 104 |
| 0x12cbcab | function_12cb680 | function_12cb4c0 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12d44e5 | function_12d4480 | function_12d42f0 | write_local | 0x20:4:load, 0x24:1:rmw, 0x24:4:load, 0x28:4:load, 0x2c:4:load, 0x30:4:load, 0x30:4:rmw, 0x30:4:store, 0x34:4:store, 0x38:4:store, 0x3c:4:store, 0x4c:4:load, 0x4c:4:rmw, 0x4c:4:store, 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12d453a | function_12d4480 | function_12d42f0 | write_local | 0x20:4:load, 0x24:1:rmw, 0x24:4:load, 0x28:4:load, 0x2c:4:load, 0x30:4:load, 0x30:4:rmw, 0x30:4:store, 0x34:4:store, 0x38:4:store, 0x3c:4:store, 0x4c:4:load, 0x4c:4:rmw, 0x4c:4:store, 0x70:8:load, 0x78:8:load | ir_truncated | 104 |
| 0x12e610d | function_12e60b0 | function_12e5ef0 | read_local | 0x60:8:load, 0x68:4:load | ir_truncated | 56 |
| 0x12e6115 | function_12e60b0 | function_12e5fd0 | read_local | 0x60:8:load, 0x68:4:load | ir_truncated | 56 |
| 0x131096a | function_13105d0 | function_13104e0 | write_local | 0x4c:4:load, 0x4c:4:rmw, 0x4c:4:store, 0x80:8:load | unmatched | - |
| 0x131098b | function_13105d0 | function_1310550 | arg_home_only | 0x80:8:load | ir_truncated | 48 |
