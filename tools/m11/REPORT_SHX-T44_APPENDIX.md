# SHX-T44 付録: mov 渡し 301 site の機械語突合 (site 単位)

生成: `FL_WIN64_DIR=<展開先> python3 frame_share/site_check.py --sites work/frame_share.json --out work/site_check.json` と `base_check.py` の出力 (`work/base_check.json`) を突合。判定列は線型走査の粗い分類で、真の D23 の確定ではない。

| call | 親 | callee | access_class | callee 読み先 | IR 突合 | IR alloca 幅 |
|---|---|---|---|---|---|---|
| 0x408c0b | function_408b60 | function_408970 | arg_home_only | 0x1004f:1:store | ir_truncated | 72 |
| 0x40b8eb | function_40b620 | function_40b290 | write_local | 0x30:8:load, 0x30:8:store, 0x38:8:load, 0x40:8:load, 0x48:8:load, 0x88:8:load, 0x90:8:load | unmatched | - |
| 0x40b938 | function_40b620 | function_40b290 | write_local | 0x30:8:load, 0x30:8:store, 0x38:8:load, 0x40:8:load, 0x48:8:load, 0x88:8:load, 0x90:8:load | unmatched | - |
| 0x40b963 | function_40b620 | function_40b290 | write_local | 0x30:8:load, 0x30:8:store, 0x38:8:load, 0x40:8:load, 0x48:8:load, 0x88:8:load, 0x90:8:load | unmatched | - |
| 0x40f412 | function_40f210 | function_40f160 | write_local | 0x30:8:load, 0x30:8:rmw, 0x30:8:store, 0x3c:4:load, 0x3c:4:rmw, 0x6c:8:load, 0x6c:8:store | ir_truncated | 88 |
| 0x43aec4 | function_43ae60 | function_43adf0 | read_local | 0x50:8:load | ir_truncated | 40 |
| 0x43aef7 | function_43ae60 | function_43adf0 | read_local | 0x50:8:load | ir_truncated | 40 |
| 0x43f913 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43f928 | function_43f800 | function_43f490 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43f9b5 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43f9f1 | function_43f800 | function_43f550 | write_local | 0x50:4:load, 0x50:4:rmw | unmatched | - |
| 0x43f9fd | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fa2e | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fa38 | function_43f800 | function_43f550 | write_local | 0x50:4:load, 0x50:4:rmw | unmatched | - |
| 0x43fa44 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fa78 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fa9d | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fab6 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43facb | function_43f800 | function_43f550 | write_local | 0x50:4:load, 0x50:4:rmw | unmatched | - |
| 0x43fad7 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fb01 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fb09 | function_43f800 | function_43f550 | write_local | 0x50:4:load, 0x50:4:rmw | unmatched | - |
| 0x43fb15 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fb2c | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fb3b | function_43f800 | function_43f550 | write_local | 0x50:4:load, 0x50:4:rmw | unmatched | - |
| 0x43fb47 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fb7a | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fb82 | function_43f800 | function_43f580 | write_local | 0x48:4:load, 0x48:4:rmw, 0x48:4:store, 0x4c:4:load, 0x4c:4:rmw, 0x4c:4:store, 0x54:2:load, 0xb0:1:load, 0xc0:4:load, 0xc8:8:load | ir_truncated | 64 |
| 0x43fc7e | function_43f800 | function_43f490 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x43fc88 | function_43f800 | function_43f580 | write_local | 0x48:4:load, 0x48:4:rmw, 0x48:4:store, 0x4c:4:load, 0x4c:4:rmw, 0x4c:4:store, 0x54:2:load, 0xb0:1:load, 0xc0:4:load, 0xc8:8:load | ir_truncated | 64 |
| 0x43fc94 | function_43f800 | function_43f440 | write_local | 0x6c:4:rmw, 0x90:8:load, 0x90:8:rmw, 0x98:1:load | unmatched | - |
| 0x4413a2 | function_441380 | function_440d30 | write_local | 0x30:8:load, 0x48:4:load, 0x50:4:rmw | unmatched | - |
| 0x441758 | function_441730 | function_441500 | write_local | 0x6e:2:store, 0x80:8:load, 0x80:8:rmw | unmatched | - |
| 0x44177b | function_441730 | function_441530 | read_local | 0x6e:2:load | ir_truncated | 72 |
| 0x44179d | function_441730 | function_441560 | read_local | 0x6e:2:load | unmatched | - |
| 0x4417c0 | function_441730 | function_4415a0 | read_local | 0x6e:2:load | ir_truncated | 72 |
| 0x4417e7 | function_441730 | function_441500 | write_local | 0x6e:2:store, 0x80:8:load, 0x80:8:rmw | unmatched | - |
| 0x4417f3 | function_441730 | function_4415a0 | read_local | 0x6e:2:load | ir_truncated | 72 |
| 0x44181e | function_441730 | function_441500 | write_local | 0x6e:2:store, 0x80:8:load, 0x80:8:rmw | unmatched | - |
| 0x441831 | function_441730 | function_4416a0 | read_local | 0x6e:2:load | ir_truncated | 72 |
| 0x441858 | function_441730 | function_441530 | read_local | 0x6e:2:load | ir_truncated | 72 |
| 0x441b92 | function_441b20 | function_441900 | arg_home_only | 0x8c:4:load, 0x8c:4:rmw, 0xb0:8:load | ir_truncated | 64 |
| 0x441bb3 | function_441b20 | function_441930 | arg_home_only | 0x8c:4:load, 0x8c:4:rmw, 0xb0:8:load, 0x118:4:rmw | unmatched | - |
| 0x441c58 | function_441b20 | function_441a90 | arg_home_only | 0x8c:4:load, 0x8c:4:rmw, 0xb0:8:load | ir_truncated | 64 |
| 0x441c77 | function_441b20 | function_441900 | arg_home_only | 0x8c:4:load, 0x8c:4:rmw, 0xb0:8:load | ir_truncated | 64 |
| 0x4436af | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x4436b7 | function_443490 | function_443080 | write_local | 0x3b:1:load, 0x3b:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443719 | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443721 | function_443490 | function_443080 | write_local | 0x3b:1:load, 0x3b:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x44374e | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443756 | function_443490 | function_443080 | write_local | 0x3b:1:load, 0x3b:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443783 | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x44378b | function_443490 | function_443080 | write_local | 0x3b:1:load, 0x3b:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443815 | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443846 | function_443490 | function_443080 | write_local | 0x3b:1:load, 0x3b:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x44392b | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443933 | function_443490 | function_4430c0 | write_local | 0x3a:1:load, 0x3a:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443a53 | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443a5b | function_443490 | function_4430c0 | write_local | 0x3a:1:load, 0x3a:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443a89 | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443a91 | function_443490 | function_4430c0 | write_local | 0x3a:1:load, 0x3a:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443abf | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443b13 | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443b1b | function_443490 | function_4430c0 | write_local | 0x3a:1:load, 0x3a:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443b49 | function_443490 | function_4430c0 | write_local | 0x3a:1:load, 0x3a:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443c75 | function_443490 | function_443080 | write_local | 0x3b:1:load, 0x3b:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443cdd | function_443490 | function_443080 | write_local | 0x3b:1:load, 0x3b:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x443d47 | function_443490 | function_443030 | write_local | 0x3c:4:store, 0x40:2:load, 0x88:8:load, 0x88:8:rmw | ir_truncated | 32 |
| 0x443d6d | function_443490 | function_4430c0 | write_local | 0x3a:1:load, 0x3a:1:store, 0x80:8:load | ir_truncated | 32 |
| 0x44528b | function_444dd0 | function_444d20 | write_local | 0x57:1:load, 0x57:1:rmw, 0x158:4:load | ir_truncated | 64 |
| 0x4454e1 | function_444dd0 | function_444d20 | write_local | 0x57:1:load, 0x57:1:rmw, 0x158:4:load | ir_truncated | 64 |
| 0x445548 | function_444dd0 | function_444c90 | arg_home_only | 0x15c:4:load, 0x15c:4:rmw, 0x15c:4:store | ir_truncated | 64 |
| 0x44808f | function_447f40 | function_447ee0 | arg_home_only | 0x98:2:load | ir_truncated | 64 |
| 0x44824a | function_447f40 | function_447ee0 | arg_home_only | 0x98:2:load | ir_truncated | 64 |
| 0x448588 | function_448490 | function_4483f0 | write_local | 0x48:4:rmw, 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x4485c6 | function_448490 | function_4483f0 | write_local | 0x48:4:rmw, 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x44864a | function_448490 | function_448430 | write_local | 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x44865b | function_448490 | function_448430 | write_local | 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x448692 | function_448490 | function_4483f0 | write_local | 0x48:4:rmw, 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x4486ca | function_448490 | function_4483f0 | write_local | 0x48:4:rmw, 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x4486e0 | function_448490 | function_4483f0 | write_local | 0x48:4:rmw, 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x448708 | function_448490 | function_4483f0 | write_local | 0x48:4:rmw, 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x448720 | function_448490 | function_4483f0 | write_local | 0x48:4:rmw, 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x44872c | function_448490 | function_4483f0 | write_local | 0x48:4:rmw, 0x4c:4:load, 0x4c:4:rmw, 0x70:8:load | ir_truncated | 48 |
| 0x457c99 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457cb6 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457cd3 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457cf0 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457d0d | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457d2a | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457d47 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457d64 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457d81 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457d9e | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457dbb | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457dd8 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457df5 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457e12 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457e2f | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457e4c | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457e69 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457e86 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457ea3 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457ec0 | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457edd | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x457efa | function_457c70 | function_457c40 | read_local | 0x28:8:load | ir_covers | 56 |
| 0x497f07 | function_497e60 | function_497e40 | read_local | 0x58:8:load | ir_truncated | 72 |
| 0x517cc5 | function_517b50 | function_517ac0 | arg_home_only | 0x70:8:load, 0x78:8:load | no_prologue | - |
| 0x517ce9 | function_517b50 | function_517a40 | arg_home_only | 0x70:8:load, 0x78:8:load | no_prologue | - |
| 0x517d18 | function_517b50 | function_517ac0 | arg_home_only | 0x70:8:load, 0x78:8:load | no_prologue | - |
| 0x5c5743 | function_5c5500 | function_5c53e0 | arg_home_only | 0x168:8:load | ir_truncated | 128 |
| 0x612b2e | function_612aa0 | function_6129d0 | write_local | 0x30:8:store, 0x38:8:load, 0x38:8:store, 0x68:8:load, 0x70:1:load | ir_truncated | 88 |
| 0x612b72 | function_612aa0 | function_6129d0 | write_local | 0x30:8:store, 0x38:8:load, 0x38:8:store, 0x68:8:load, 0x70:1:load | ir_truncated | 88 |
| 0x6906ec | function_6905f0 | function_690580 | read_local | 0x67:1:load, 0x68:8:load, 0x70:8:load, 0x78:8:load, 0xa8:8:load | unmatched | - |
| 0x69073b | function_6905f0 | function_690580 | read_local | 0x67:1:load, 0x68:8:load, 0x70:8:load, 0x78:8:load, 0xa8:8:load | unmatched | - |
| 0x690804 | function_6905f0 | function_690580 | read_local | 0x67:1:load, 0x68:8:load, 0x70:8:load, 0x78:8:load, 0xa8:8:load | unmatched | - |
| 0x6908b3 | function_6905f0 | function_690580 | read_local | 0x67:1:load, 0x68:8:load, 0x70:8:load, 0x78:8:load, 0xa8:8:load | unmatched | - |
| 0x6909d4 | function_6905f0 | function_690580 | read_local | 0x67:1:load, 0x68:8:load, 0x70:8:load, 0x78:8:load, 0xa8:8:load | unmatched | - |
| 0x6a0a22 | function_6a09b0 | function_6a0760 | read_local | 0x2c:4:load, 0x68:8:load, 0x68:8:other | ir_truncated | 88 |
| 0x6a0a39 | function_6a09b0 | function_6a0760 | read_local | 0x2c:4:load, 0x68:8:load, 0x68:8:other | ir_truncated | 88 |
| 0x6a25ed | function_6a25b0 | function_6a23d0 | write_local | 0x2c:4:store, 0x30:4:load, 0x30:4:store, 0x34:4:store, 0x3c:4:load, 0x60:8:load, 0x78:1:load | unmatched | - |
| 0x6a2653 | function_6a25b0 | function_6a23d0 | write_local | 0x2c:4:store, 0x30:4:load, 0x30:4:store, 0x34:4:store, 0x3c:4:load, 0x60:8:load, 0x78:1:load | unmatched | - |
| 0x6a2856 | function_6a2820 | function_6a26e0 | write_local | 0x30:4:store, 0x34:4:load, 0x34:4:store, 0x38:4:store, 0x3c:4:load, 0x60:8:load, 0x78:1:load | unmatched | - |
| 0x6a28a3 | function_6a2820 | function_6a26e0 | write_local | 0x30:4:store, 0x34:4:load, 0x34:4:store, 0x38:4:store, 0x3c:4:load, 0x60:8:load, 0x78:1:load | unmatched | - |
| 0x6b987e | function_6b97e0 | function_6b94b0 | read_local | 0x60:8:load, 0x68:8:load | ir_truncated | 88 |
| 0x6b9888 | function_6b97e0 | function_6b9690 | read_local | 0x60:8:load | ir_truncated | 88 |
| 0x6cdfff | function_6cdee0 | function_6cd900 | arg_home_only | 0x70:8:load | ir_truncated | 104 |
| 0x6ce01a | function_6cdee0 | function_6cd900 | arg_home_only | 0x70:8:load | ir_truncated | 104 |
| 0x6ce0fd | function_6cdee0 | function_6cd900 | arg_home_only | 0x70:8:load | ir_truncated | 104 |
| 0x6ce118 | function_6cdee0 | function_6cd900 | arg_home_only | 0x70:8:load | ir_truncated | 104 |
| 0x6eda65 | function_6ed9e0 | function_6ed7f0 | read_local | 0x2b:1:load, 0x2c:4:load, 0x40:8:load | ir_truncated | 56 |
| 0x6eda78 | function_6ed9e0 | function_6ed7f0 | read_local | 0x2b:1:load, 0x2c:4:load, 0x40:8:load | ir_truncated | 56 |
| 0x6eda8b | function_6ed9e0 | function_6ed7f0 | read_local | 0x2b:1:load, 0x2c:4:load, 0x40:8:load | ir_truncated | 56 |
| 0x72e004 | function_72df20 | function_72de70 | arg_home_only | 0x70:8:load, 0x78:8:load | ir_truncated | 56 |
| 0x8675cf | function_8675c0 | function_867540 | read_local | 0x30:8:load | ir_truncated | 40 |
| 0x8675e5 | function_8675c0 | function_867540 | read_local | 0x30:8:load | ir_truncated | 40 |
| 0x977fcd | function_977f50 | function_977e40 | write_local | 0x48:8:store, 0x68:1:load, 0x70:8:load, 0x80:1:load, 0x88:8:load, 0x98:8:load, 0xa0:1:load | ir_truncated | 88 |
| 0x977fed | function_977f50 | function_977870 | read_local | 0x60:8:load, 0x98:8:load | unmatched | - |
| 0x978018 | function_977f50 | function_977870 | read_local | 0x60:8:load, 0x98:8:load | unmatched | - |
| 0x9cea43 | function_9ce9e0 | function_9ce950 | read_local | 0x28:8:other | ir_covers | 104 |
| 0x9cea51 | function_9ce9e0 | function_9ce950 | read_local | 0x28:8:other | ir_covers | 104 |
| 0x9cea8e | function_9ce9e0 | function_9ce950 | read_local | 0x28:8:other | ir_covers | 104 |
| 0x9cea9c | function_9ce9e0 | function_9ce950 | read_local | 0x28:8:other | ir_covers | 104 |
| 0x9ceac4 | function_9ce9e0 | function_9ce950 | read_local | 0x28:8:other | ir_covers | 104 |
| 0x9ceb4f | function_9ce9e0 | function_9ce950 | read_local | 0x28:8:other | ir_covers | 104 |
| 0x9ceb5d | function_9ce9e0 | function_9ce950 | read_local | 0x28:8:other | ir_covers | 104 |
| 0x9ceb85 | function_9ce9e0 | function_9ce950 | read_local | 0x28:8:other | ir_covers | 104 |
| 0xa96e50 | function_a96df0 | function_a96d40 | read_local | 0x50:8:load | ir_truncated | 72 |
| 0xa9e863 | function_a9e7a0 | function_a9e430 | read_local | 0x2c:1:load, 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0xa9e86d | function_a9e7a0 | function_a9e4d0 | read_local | 0x2c:2:load, 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0xa9e877 | function_a9e7a0 | function_a9e570 | read_local | 0x2c:4:load, 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0xa9e881 | function_a9e7a0 | function_a9e610 | read_local | 0x2c:1:load, 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0xa9e894 | function_a9e7a0 | function_a9e430 | read_local | 0x2c:1:load, 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0xa9e8a5 | function_a9e7a0 | function_a9e4d0 | read_local | 0x2c:2:load, 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0xa9e8b6 | function_a9e7a0 | function_a9e570 | read_local | 0x2c:4:load, 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0xa9e8c7 | function_a9e7a0 | function_a9e610 | read_local | 0x2c:1:load, 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0xc5613e | function_c55dc0 | function_c55d60 | arg_home_only | 0x13f:1:load, 0x13f:1:store, 0x178:8:load | ir_truncated | 80 |
| 0xc56457 | function_c55dc0 | function_c55d60 | arg_home_only | 0x13f:1:load, 0x13f:1:store, 0x178:8:load | ir_truncated | 80 |
| 0xcb9f5e | function_cb9eb0 | function_cb9e00 | read_local | 0x28:8:load, 0x30:4:load, 0x34:4:load, 0x34:4:other, 0x38:4:load, 0x38:4:other, 0x3c:4:load, 0x3c:4:other, 0x60:8:load | ir_truncated | 88 |
| 0xcb9f72 | function_cb9eb0 | function_cb9e00 | read_local | 0x28:8:load, 0x30:4:load, 0x34:4:load, 0x34:4:other, 0x38:4:load, 0x38:4:other, 0x3c:4:load, 0x3c:4:other, 0x60:8:load | ir_truncated | 88 |
| 0xcb9f92 | function_cb9eb0 | function_cb9e00 | read_local | 0x28:8:load, 0x30:4:load, 0x34:4:load, 0x34:4:other, 0x38:4:load, 0x38:4:other, 0x3c:4:load, 0x3c:4:other, 0x60:8:load | ir_truncated | 88 |
| 0xcc7d06 | function_cc7c50 | function_cc7c00 | write_local | 0x2c:4:load, 0x2c:4:rmw | ir_covers | 72 |
| 0xcc7d15 | function_cc7c50 | function_cc7c00 | write_local | 0x2c:4:load, 0x2c:4:rmw | ir_covers | 72 |
| 0xcc7d24 | function_cc7c50 | function_cc7c00 | write_local | 0x2c:4:load, 0x2c:4:rmw | ir_covers | 72 |
| 0xcc7d33 | function_cc7c50 | function_cc7c00 | write_local | 0x2c:4:load, 0x2c:4:rmw | ir_covers | 72 |
| 0xcc7d42 | function_cc7c50 | function_cc7c00 | write_local | 0x2c:4:load, 0x2c:4:rmw | ir_covers | 72 |
| 0xcc7d51 | function_cc7c50 | function_cc7c00 | write_local | 0x2c:4:load, 0x2c:4:rmw | ir_covers | 72 |
| 0xcc7d60 | function_cc7c50 | function_cc7c00 | write_local | 0x2c:4:load, 0x2c:4:rmw | ir_covers | 72 |
| 0xcc7d6f | function_cc7c50 | function_cc7c00 | write_local | 0x2c:4:load, 0x2c:4:rmw | ir_covers | 72 |
| 0xd23c8f | function_d23c00 | function_d23b80 | read_local | 0x40:8:load | ir_truncated | 56 |
| 0xd23d01 | function_d23c00 | function_d23b80 | read_local | 0x40:8:load | ir_truncated | 56 |
| 0xd264bb | function_d26460 | function_d26430 | read_local | 0x2c:4:other | unmatched | - |
| 0xd264d4 | function_d26460 | function_d26430 | read_local | 0x2c:4:other | unmatched | - |
| 0xd264eb | function_d26460 | function_d26430 | read_local | 0x2c:4:other | unmatched | - |
| 0xd26504 | function_d26460 | function_d26430 | read_local | 0x2c:4:other | unmatched | - |
| 0xd2651d | function_d26460 | function_d26430 | read_local | 0x2c:4:other | unmatched | - |
| 0xdc223e | function_dc2130 | function_dc20d0 | read_local | 0x48:8:load | ir_truncated | 40 |
| 0xdc2304 | function_dc2130 | function_dc20d0 | read_local | 0x48:8:load | ir_truncated | 40 |
| 0xdd846f | function_dd8380 | function_dd8230 | write_local | 0x2c:4:load, 0x2c:4:store, 0x3b:1:store, 0x40:4:store, 0x44:4:load, 0x44:4:other, 0x44:4:rmw, 0x44:4:store, 0x48:4:store, 0x80:4:load, 0x80:4:store, 0x88:4:store, 0x8c:4:store, 0xa0:8:load, 0xa8:8:load | ir_truncated | 32 |
| 0xddd2e2 | function_ddd1f0 | function_ddd1a0 | arg_home_only | 0x80:8:load | ir_truncated | 120 |
| 0xddd3db | function_ddd1f0 | function_ddd1a0 | arg_home_only | 0x80:8:load | ir_truncated | 120 |
| 0xdded02 | function_ddeca0 | function_ddea70 | arg_home_only | 0xc0:8:load | ir_truncated | 80 |
| 0xdded1e | function_ddeca0 | function_dde9f0 | arg_home_only | 0xc0:8:load | ir_truncated | 80 |
| 0xdded58 | function_ddeca0 | function_dde9f0 | arg_home_only | 0xc0:8:load | ir_truncated | 80 |
| 0xdded6f | function_ddeca0 | function_dde970 | arg_home_only | 0xc0:8:load | ir_truncated | 80 |
| 0xdded9e | function_ddeca0 | function_dde970 | arg_home_only | 0xc0:8:load | ir_truncated | 80 |
| 0xddedb4 | function_ddeca0 | function_dde970 | arg_home_only | 0xc0:8:load | ir_truncated | 80 |
| 0xddf49e | function_ddeca0 | function_dde970 | arg_home_only | 0xc0:8:load | ir_truncated | 80 |
| 0xde135d | function_de10c0 | function_de0fc0 | arg_home_only | 0xf0:8:load, 0x128:8:load | ir_truncated | 136 |
| 0xde455d | function_de43b0 | function_de4120 | write_local | 0x54:4:load, 0x54:4:store, 0x58:4:load, 0x5c:4:load, 0x90:8:load, 0xa8:4:rmw | unmatched | - |
| 0xe253d5 | function_e25380 | function_e25310 | read_local | 0x60:8:load | ir_truncated | 88 |
| 0xe2a0d9 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a0e8 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a0f7 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a106 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a115 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a124 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a133 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a142 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a151 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a160 | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a16f | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a17e | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a18d | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a19c | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe2a1ab | function_e2a0c0 | function_e2a080 | read_local | 0x48:1:load | ir_truncated | 56 |
| 0xe3f1e4 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f1f7 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f228 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f23b | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f24e | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f264 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f277 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f28a | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f29d | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f2b0 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f2c3 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f2d6 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f2e9 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f2fc | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f30f | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe3f322 | function_e3ef60 | function_e3eef0 | write_local | 0x44:4:rmw, 0x48:4:load, 0x4c:4:load, 0x4c:4:rmw | ir_truncated | 48 |
| 0xe4f335 | function_e4f310 | function_e4f2d0 | read_local | 0x30:8:load | unmatched | - |
| 0xe4f359 | function_e4f310 | function_e4f2d0 | read_local | 0x30:8:load | unmatched | - |
| 0xe4f373 | function_e4f310 | function_e4f2d0 | read_local | 0x30:8:load | unmatched | - |
| 0xf43d74 | function_f40840 | function_f3d5e0 | arg_home_only | 0x4640:8:load | unmatched | - |
| 0xfed8f0 | function_fed8c0 | function_fed830 | read_local | 0x40:8:load | ir_truncated | 56 |
| 0x1006f21 | function_1006ec0 | function_1006ce0 | read_local | 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0x1006ff5 | function_1006ec0 | function_1006dd0 | read_local | 0x40:8:load, 0x48:8:load | ir_truncated | 48 |
| 0x103496b | function_10348b0 | function_1034780 | arg_home_only | 0x70:8:load | ir_truncated | 40 |
| 0x1034a84 | function_10348b0 | function_1034780 | arg_home_only | 0x70:8:load | ir_truncated | 40 |
| 0x1042eaa | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x1043223 | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x1043346 | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x10433ac | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x104340b | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x104358a | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x1043658 | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x1043840 | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x104398b | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x1043c08 | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x1043cf4 | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x1043e91 | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
| 0x1043fab | function_1042d20 | function_1042d00 | arg_home_only | 0xf8:4:load | ir_truncated | 160 |
