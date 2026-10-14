# REPORT_DISPATCHER 付録 (#2782)

本付録は `REPORT_DISPATCHER.md` §10 の詳細表。測定 commit `48f2ced9` (`hs_disp_emu.py` に `HS_DISP_RET_SPEC` の `one` (戻り値 1) を追加した commit)。既定の出力 (0 埋め・経路・応答) は `0bb93345` と同一 (§D の基準 run の数値が一致)。表は `base.json` (既定)・`one_all.json` (基準で呼ばれた 82 VA を全て `one`)・`one_40fe90.json` (`0x40fe90` のみ `one`)・`fill.json` (`HS_DISP_STACK_FILL=0xa5`) と、機械語の逆アセンブルから生成した。

## A. 応答スロット `[rbp+0x11a0]` の格納箇所

### A-1. 機械語の全書き込み命令 (69 件)

数え方: 関数範囲 `[0x13173a0, 0x1330000)` を capstone で逆アセンブルし (12,834 命令)、宛先が `qword ptr [rbp + 0x11a0]` の `mov` (67 件) と `or` (2 件) を全件挙げた。`cmp qword ptr [rbp + 0x11a0], 0` (7 件) と読み出し `0x1328a38` は書き込みではないので除く。

- 「実行 ID 数」は 256 ID の各 run で、その命令が `[rbp+0x11a0]` へ書いた ID 数 (ストア命令のフックで数えた)。括弧内は ID (4 件以下のとき)。
- 「直前の分岐・call」はアドレス順で直前の `jcc`・`jmp`・`call` (機械語上の位置)。経路条件そのものではない。
- 基準 run で実行された書き込み VA は **30 件**、未実行は **39 件**。
- 全 callee=1 の run と `0x40fe90`=1 の run で新たに実行された VA は 4 件 (`0x1320f72`・`0x13210ae`・`0x13211a1`・`0x1321efb`。ID 0x32・0x33・0x34・0x4c)。詳細は B-2。
- 3 run のどの書き込みも、この 69 件のいずれかである (表に無い書き込みは観測されなかった)。


| 格納 VA | 命令 | 基準 run の実行 ID 数 | 全 callee=1 の実行 ID 数 | `0x40fe90`=1 の実行 ID 数 | アドレス順で直前の分岐・call |
|---|---|---|---|---|---|
| `0x131873f` | `mov qword ptr [rbp + 0x11a0], 0` | 256 | 256 | 256 | - |
| `0x1318e46` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x01) | 1 (0x01) | 1 (0x01) | 0x1318e3e `call 0x11ffde0` |
| `0x13192eb` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x07) | 1 (0x07) | 1 (0x07) | 0x13192da `call 0x41d110` |
| `0x1319561` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x0e) | 1 (0x0e) | 1 (0x0e) | 0x1319550 `call 0x41d110` |
| `0x1319f13` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1319f06 `je 0x1319f1f` |
| `0x1319f1f` | `mov qword ptr [rbp + 0x11a0], 0` | 0 | 0 | 0 | 0x1319f1a `jmp 0x13281af` |
| `0x1319f6e` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x13) | 1 (0x13) | 1 (0x13) | 0x1319f66 `call 0x9636a0` |
| `0x1319fd0` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x4e) | 1 (0x4e) | 1 (0x4e) | 0x1319fbf `call 0x41d110` |
| `0x131a268` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x18) | 1 (0x18) | 1 (0x18) | 0x131a25c `jmp 0x13281af` |
| `0x131b8d1` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x1c) | 1 (0x1c) | 1 (0x1c) | 0x131b8c0 `call 0x41d110` |
| `0x131bb50` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x1d) | 1 (0x1d) | 1 (0x1d) | 0x131bb3f `call 0x41d110` |
| `0x131bb66` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x56) | 1 (0x56) | 1 (0x56) | 0x131bb57 `jmp 0x13281af` |
| `0x131c415` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x26) | 1 (0x26) | 1 (0x26) | 0x131c40c `call 0xe4e970` |
| `0x1320de8` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x2e) | 1 (0x2e) | 1 (0x2e) | 0x1320de3 `call 0x86c900` |
| `0x1320e23` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1320e21 `call qword ptr [rax]` |
| `0x1320f72` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 1 (0x32) | 1 (0x32) | 0x1320f57 `je 0x1320f6b` |
| `0x1320fc4` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1320fa9 `je 0x1320fbd` |
| `0x1320fda` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x32) | 0 | 0 | 0x1320fd8 `jne 0x1320fea` |
| `0x1320ff9` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1320fe5 `jmp 0x13281af` |
| `0x13210ae` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 1 (0x33) | 1 (0x33) | 0x13210a6 `jmp 0x13210aa` |
| `0x13210e8` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x33) | 0 | 0 | 0x13210e3 `jmp 0x13281af` |
| `0x13211a1` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 1 (0x34) | 1 (0x34) | 0x1321199 `jmp 0x132119d` |
| `0x1321225` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x34) | 0 | 0 | 0x132121d `jmp 0x1321221` |
| `0x13213f3` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x13213ee `call qword ptr [rax]` |
| `0x1321780` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x3d) | 1 (0x3d) | 1 (0x3d) | 0x132176f `call 0x41d110` |
| `0x1321836` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x41) | 1 (0x41) | 1 (0x41) | 0x132182b `je 0x1321836` |
| `0x13218c1` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x13218b8 `call 0x1313220` |
| `0x1321966` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1321952 `call 0xf5b190` |
| `0x13219b0` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x13219a7 `call 0x1313220` |
| `0x1321a2f` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x41) | 1 (0x41) | 1 (0x41) | 0x1321a1b `call 0x11d06e0` |
| `0x1321b6c` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1321b5b `call 0x41d110` |
| `0x1321b89` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x45) | 1 (0x45) | 1 (0x45) | 0x1321b73 `jmp 0x13281af` |
| `0x1321bb0` | `mov qword ptr [rbp + 0x11a0], 1` | 0 | 0 | 0 | 0x1321bab `call 0x11f7b10` |
| `0x1321bf1` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x46) | 1 (0x46) | 1 (0x46) | 0x1321be8 `call 0xed6780` |
| `0x1321c10` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x47) | 1 (0x47) | 1 (0x47) | 0x1321c0b `call 0x75b3d0` |
| `0x1321df9` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x4c) | 1 (0x4c) | 1 (0x4c) | 0x1321df4 `jmp 0x13281af` |
| `0x1321efb` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 1 (0x4c) | 1 (0x4c) | 0x1321eea `call 0x41d110` |
| `0x1321f0e` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1321f02 `jmp 0x13281af` |
| `0x1321f34` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1321f15 `jmp 0x13281af` |
| `0x1321f6c` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1321f3b `jmp 0x13281af` |
| `0x1321fc2` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1321f73 `jmp 0x13281af` |
| `0x132206e` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1322031 `call 0x40ae70` |
| `0x13220b2` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1322075 `jmp 0x13281af` |
| `0x13220be` | `mov qword ptr [rbp + 0x11a0], 0` | 0 | 0 | 0 | 0x13220b9 `jmp 0x13281af` |
| `0x13220ef` | `or qword ptr [rbp + 0x11a0], 1` | 0 | 0 | 0 | 0x13220ed `jne 0x13220f7` |
| `0x132210a` | `or qword ptr [rbp + 0x11a0], 2` | 0 | 0 | 0 | 0x1322104 `je 0x13281af` |
| `0x13221be` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1322181 `call 0x40ae70` |
| `0x13221ca` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x4d) | 1 (0x4d) | 1 (0x4d) | 0x13221c5 `jmp 0x13281af` |
| `0x132257d` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x1322575 `call 0xfdd2c0` |
| `0x132266b` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x54) | 1 (0x54) | 1 (0x54) | 0x1322666 `jmp 0x13281af` |
| `0x132268e` | `mov qword ptr [rbp + 0x11a0], 0x10` | 0 | 0 | 0 | 0x132268c `jne 0x132269e` |
| `0x13226dd` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x54) | 1 (0x54) | 1 (0x54) | 0x13226c5 `je 0x13281af` |
| `0x1322971` | `mov qword ptr [rbp + 0x11a0], rax` | 0 | 0 | 0 | 0x132296f `call qword ptr [rax]` |
| `0x1322a07` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x64) | 1 (0x64) | 1 (0x64) | 0x13229ea `jmp 0x13281af` |
| `0x1322b47` | `mov qword ptr [rbp + 0x11a0], rax` | 1 (0x65) | 1 (0x65) | 1 (0x65) | 0x1322b1b `call qword ptr [rbx + 0x130]` |
| `0x1322c1c` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x6b) | 1 (0x6b) | 1 (0x6b) | 0x1322c17 `jmp 0x13281af` |
| `0x132415e` | `mov qword ptr [rbp + 0x11a0], 4` | 0 | 0 | 0 | 0x132415c `jne 0x132416e` |
| `0x132567c` | `mov qword ptr [rbp + 0x11a0], 3` | 0 | 0 | 0 | 0x132567a `jne 0x132568c` |
| `0x1326b9a` | `mov qword ptr [rbp + 0x11a0], 2` | 0 | 0 | 0 | 0x1326b98 `jne 0x1326baa` |
| `0x1328098` | `mov qword ptr [rbp + 0x11a0], 1` | 0 | 0 | 0 | 0x1328092 `jne 0x13281af` |
| `0x13280a8` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x6c) | 1 (0x6c) | 1 (0x6c) | 0x13280a3 `jmp 0x13281af` |
| `0x1328104` | `mov qword ptr [rbp + 0x11a0], 1` | 0 | 0 | 0 | 0x1328102 `jmp 0x1328131` |
| `0x1328114` | `mov qword ptr [rbp + 0x11a0], 2` | 0 | 0 | 0 | 0x132810f `jmp 0x13281af` |
| `0x1328124` | `mov qword ptr [rbp + 0x11a0], 3` | 0 | 0 | 0 | 0x132811f `jmp 0x13281af` |
| `0x1328131` | `mov qword ptr [rbp + 0x11a0], 4` | 0 | 0 | 0 | 0x132812f `jmp 0x13281af` |
| `0x132813e` | `mov qword ptr [rbp + 0x11a0], 0` | 1 (0x6d) | 1 (0x6d) | 1 (0x6d) | 0x132813c `jmp 0x13281af` |
| `0x132818a` | `mov qword ptr [rbp + 0x11a0], 1` | 0 | 0 | 0 | 0x1328188 `jmp 0x13281a4` |
| `0x1328197` | `mov qword ptr [rbp + 0x11a0], 2` | 0 | 0 | 0 | 0x1328195 `jmp 0x13281af` |
| `0x13281a4` | `mov qword ptr [rbp + 0x11a0], 3` | 0 | 0 | 0 | 0x13281a2 `jmp 0x13281af` |

### A-2. 最後の書き込み (ID ごとに最後に実行された格納・28 行)

数え方: 各 ID で、最後に `[rbp+0x11a0]` へ書いた VA の件数 (中間の書き込みは含まない)。最後の書き込みが初期化 `0x131873f` の ID は 229 件 (読み出し到達 202 + 読み出し前の出口 27)。残りの 27 ID は case 格納が最後になる。

中間の書き込み (最後より前に実行されたもの): 初期化 `0x131873f` が case 格納 27 ID で先に実行される。ID 0x41 は `0x1321836` (`mov ...,0`) が先、ID 0x54 は `0x132266b` (`mov ...,0`) が先。

| 格納 VA | 直前 2 命令と格納 | 値の出所 | 判定 | ID 件数 | ID (hex) |
|---|---|---|---|---|---|
| `0x131873f` | `mov qword ptr [rbp + 0x1880], rax → nop  → mov qword ptr [rbp + 0x11a0], 0` | 初期化 (全 ID の分岐木より前) | init 0 (機械語で確定) | 229 | 0x00 0x02 0x03 0x04 0x05 0x06 0x08 0x09 0x0a 0x0b 0x0c 0x0d 0x0f 0x10 0x11 0x12 0x14 0x15 0x16 0x17 0x19 0x1a 0x1b 0x1e 0x1f 0x20 0x21 0x22 0x23 0x24 0x25 0x27 0x28 0x29 0x2a 0x2b 0x2c 0x2d 0x2f 0x30 0x31 0x35 0x36 0x37 0x38 0x39 0x3a 0x3b 0x3c 0x3e 0x3f 0x40 0x42 0x43 0x44 0x48 0x49 0x4a 0x4b 0x4f 0x50 0x51 0x52 0x53 0x55 0x57 0x58 0x59 0x5a 0x5b 0x5c 0x5d 0x5e 0x5f 0x60 0x61 0x62 0x63 0x66 0x67 0x68 0x69 0x6a 0x6e 0x6f 0x70 0x71 0x72 0x73 0x74 0x75 0x76 0x77 0x78 0x79 0x7a 0x7b 0x7c 0x7d 0x7e 0x7f 0x80 0x81 0x82 0x83 0x84 0x85 0x86 0x87 0x88 0x89 0x8a 0x8b 0x8c 0x8d 0x8e 0x8f 0x90 0x91 0x92 0x93 0x94 0x95 0x96 0x97 0x98 0x99 0x9a 0x9b 0x9c 0x9d 0x9e 0x9f 0xa0 0xa1 0xa2 0xa3 0xa4 0xa5 0xa6 0xa7 0xa8 0xa9 0xaa 0xab 0xac 0xad 0xae 0xaf 0xb0 0xb1 0xb2 0xb3 0xb4 0xb5 0xb6 0xb7 0xb8 0xb9 0xba 0xbb 0xbc 0xbd 0xbe 0xbf 0xc0 0xc1 0xc2 0xc3 0xc4 0xc5 0xc6 0xc7 0xc8 0xc9 0xca 0xcb 0xcc 0xcd 0xce 0xcf 0xd0 0xd1 0xd2 0xd3 0xd4 0xd5 0xd6 0xd7 0xd8 0xd9 0xda 0xdb 0xdc 0xdd 0xde 0xdf 0xe0 0xe1 0xe2 0xe3 0xe4 0xe5 0xe6 0xe7 0xe8 0xe9 0xea 0xeb 0xec 0xed 0xee 0xef 0xf0 0xf1 0xf2 0xf3 0xf4 0xf5 0xf6 0xf7 0xf8 0xf9 0xfa 0xfb 0xfc 0xfd 0xfe 0xff |
| `0x1318e46` | `call 0x11ffde0 → movsxd rax, eax → mov qword ptr [rbp + 0x11a0], rax` | call 戻り値 | 未確定 | 1 | 0x01 |
| `0x13192eb` | `lea rcx, [0x2a8] → lea rax, [rax + rcx] → mov qword ptr [rbp + 0x11a0], rax` | [obj]+0x2a8 (オブジェクト内アドレス) | 未確定 | 1 | 0x07 |
| `0x1319561` | `lea rcx, [0x2a8] → lea rax, [rax + rcx] → mov qword ptr [rbp + 0x11a0], rax` | [obj]+0x2a8 | 未確定 | 1 | 0x0e |
| `0x1319f6e` | `call 0x9636a0 → movsxd rax, eax → mov qword ptr [rbp + 0x11a0], rax` | call 戻り値 | 未確定 | 1 | 0x13 |
| `0x1319fd0` | `lea rcx, [0x2a8] → lea rax, [rax + rcx] → mov qword ptr [rbp + 0x11a0], rax` | [obj]+0x2a8 | 未確定 | 1 | 0x4e |
| `0x131a268` | `jmp 0x13281af → mov rax, qword ptr [rip + 0x2d2030] → mov qword ptr [rbp + 0x11a0], rax` | グローバル変数の参照 ([rip]) | 未確定 | 1 | 0x18 |
| `0x131b8d1` | `lea rcx, [0x2a8] → lea rax, [rax + rcx] → mov qword ptr [rbp + 0x11a0], rax` | [obj]+0x2a8 | 未確定 | 1 | 0x1c |
| `0x131bb50` | `lea rcx, [0x2a8] → lea rax, [rax + rcx] → mov qword ptr [rbp + 0x11a0], rax` | [obj]+0x2a8 | 未確定 | 1 | 0x1d |
| `0x131bb66` | `mov rax, qword ptr [rip + 0x2c9005] → mov rax, qword ptr [rax] → mov qword ptr [rbp + 0x11a0], rax` | グローバル変数の参照 ([rip] の 2 段) | 未確定 | 1 | 0x56 |
| `0x131c415` | `call 0xe4e970 → movsx rax, al → mov qword ptr [rbp + 0x11a0], rax` | call 戻り値 (bool) | 未確定 | 1 | 0x26 |
| `0x1320de8` | `mov rcx, qword ptr [rax] → call 0x86c900 → mov qword ptr [rbp + 0x11a0], rax` | call 0x86c900 の戻り値 | 未確定 | 1 | 0x2e |
| `0x1320fda` | `cmp qword ptr [rbp + 0x1878], 0 → jne 0x1320fea → mov qword ptr [rbp + 0x11a0], 0` | 0 (分岐の fall-through) | 0 (経路上) | 1 | 0x32 |
| `0x13210e8` | `call 0x1317230 → jmp 0x13281af → mov qword ptr [rbp + 0x11a0], 0` | call 後に 0 | 0 (経路上) | 1 | 0x33 |
| `0x1321225` | `mov al, 1 → movsx rax, al → mov qword ptr [rbp + 0x11a0], rax` | 定数 1 | 1 (経路上) | 1 | 0x34 |
| `0x1321780` | `lea rcx, [0x2a8] → lea rax, [rax + rcx] → mov qword ptr [rbp + 0x11a0], rax` | [obj]+0x2a8 | 未確定 | 1 | 0x3d |
| `0x1321a2f` | `sete al → movsx rax, al → mov qword ptr [rbp + 0x11a0], rax` | sete (比較結果) | 未確定 | 1 | 0x41 |
| `0x1321b89` | `mov rax, qword ptr [rax] → movsxd rax, dword ptr [rax + 0x3518] → mov qword ptr [rbp + 0x11a0], rax` | オブジェクトフィールド [obj]+0x3518 (int) | 未確定 | 1 | 0x45 |
| `0x1321bf1` | `call 0xed6780 → movsx rax, al → mov qword ptr [rbp + 0x11a0], rax` | call 戻り値 (bool) | 未確定 | 1 | 0x46 |
| `0x1321c10` | `mov rcx, qword ptr [rax + 0x30] → call 0x75b3d0 → mov qword ptr [rbp + 0x11a0], rax` | call 戻り値 | 未確定 | 1 | 0x47 |
| `0x1321df9` | `call 0x132a5a0 → jmp 0x13281af → mov qword ptr [rbp + 0x11a0], 0` | call 後に 0 | 0 (経路上) | 1 | 0x4c |
| `0x13221ca` | `mov qword ptr [rbp + 0x11a0], rax → jmp 0x13281af → mov qword ptr [rbp + 0x11a0], 0` | 0 (別ブロック) | 0 (経路上) | 1 | 0x4d |
| `0x13226dd` | `mov rcx, qword ptr [rbp + 0x1880] → movsxd rax, dword ptr [rax + rcx*4] → mov qword ptr [rbp + 0x11a0], rax` | テーブル参照 [rax+rcx*4] (index は [rbp+0x1880]) | 未確定 | 1 | 0x54 |
| `0x1322a07` | `setg al → movsx rax, al → mov qword ptr [rbp + 0x11a0], rax` | setg (比較結果) | 未確定 | 1 | 0x64 |
| `0x1322b47` | `movss dword ptr [rbp + 0x109c], xmm0 → movsxd rax, dword ptr [rbp + 0x109c] → mov qword ptr [rbp + 0x11a0], rax` | float フィールド [obj]+0x2e4 のビット列 | 未確定 | 1 | 0x65 |
| `0x1322c1c` | `call 0x13545b0 → jmp 0x13281af → mov qword ptr [rbp + 0x11a0], 0` | call 後に 0 | 0 (経路上) | 1 | 0x6b |
| `0x13280a8` | `mov qword ptr [rbp + 0x11a0], 1 → jmp 0x13281af → mov qword ptr [rbp + 0x11a0], 0` | 0 (別ブロック) | 0 (経路上) | 1 | 0x6c |
| `0x132813e` | `mov qword ptr [rbp + 0x11a0], 4 → jmp 0x13281af → mov qword ptr [rbp + 0x11a0], 0` | 0 (別ブロック) | 0 (経路上) | 1 | 0x6d |

## B. 応答に格納が無い ID (202) と出口で終わる ID (27)

### B-1. 読み出し到達・格納が初期化のみの ID と、出口の ID

- 読み出し `0x1328a38` に到達し、格納が初期化 (`0x131873f`) のみの ID: **202 件**。応答は 0。ただし **callee 戻り値 0 を仮定した経路判定**であり、無条件には確定しない (B-2)。
- 読み出しに到達せず別の出口で終わる ID: **27 件**。出口の命令と ID (基準 run・callee 戻り値 0):


| 出口 VA | 命令 | ID (hex) | 判定 |
|---|---|---|---|
| `0x1318cf8` | `call qword ptr [rax + 0x20]` | 0x00 | 未確定 (仮想呼出し・未モデル) |
| `0x1318f4c` | `call qword ptr [rbx + 0x18]` | 0x04 | 未確定 (仮想呼出し・未モデル) |
| `0x13193eb` | `call qword ptr [rbx + 0xf0]` | 0x57 | 未確定 (仮想呼出し・未モデル) |
| `0x1319490` | `call qword ptr [rbx + 0x70]` | 0x0a | 未確定 (仮想呼出し・未モデル) |
| `0x1319ef4` | `call qword ptr [rax + 0x18]` | 0x12 | 未確定 (仮想呼出し・未モデル) |
| `0x131a4e1` | `call qword ptr [rax + 0x40]` | 0x1a | 未確定 (仮想呼出し・未モデル) |
| `0x131bba4` | `call qword ptr [rbx + 8]` | 0x1e | 未確定 (仮想呼出し・未モデル) |
| `0x131bd0f` | `call qword ptr [rbx + 0x80]` | 0x23 | 未確定 (仮想呼出し・未モデル) |
| `0x1320a96` | `call qword ptr [rax + 0x88]` | 0x2c | 未確定 (仮想呼出し・未モデル) |
| `0x1320e21` | `call qword ptr [rax]` | 0x2f | 未確定 (仮想呼出し・未モデル) |
| `0x1320e53` | `call qword ptr [rax + 0x48]` | 0x5b | 未確定 (仮想呼出し・未モデル) |
| `0x13213ee` | `call qword ptr [rax]` | 0x3a | 未確定 (仮想呼出し・未モデル) |
| `0x132158c` | `call qword ptr [rbx + 0x260]` | 0x3c | 未確定 (仮想呼出し・未モデル) |
| `0x1321b19` | `call qword ptr [rax]` | 0x44 | 未確定 (仮想呼出し・未モデル) |
| `0x1321dd2` | `call qword ptr [rbx + 0x58]` | 0x49 | 未確定 (仮想呼出し・未モデル) |
| `0x13227c5` | `call qword ptr [rbx + 0x38]` | 0x5c | 未確定 (仮想呼出し・未モデル) |
| `0x132282f` | `call qword ptr [rbx + 0x58]` | 0x5d | 未確定 (仮想呼出し・未モデル) |
| `0x1322893` | `call qword ptr [rbx + 0xc0]` | 0x5e | 未確定 (仮想呼出し・未モデル) |
| `0x13228cc` | `call qword ptr [rbx + 0x98]` | 0x5f | 未確定 (仮想呼出し・未モデル) |
| `0x13228eb` | `call qword ptr [rbx + 0xb8]` | 0x60 | 未確定 (仮想呼出し・未モデル) |
| `0x132296f` | `call qword ptr [rax]` | 0x62 | 未確定 (仮想呼出し・未モデル) |
| `0x1322b69` | `call qword ptr [rbx + 0xc0]` | 0x67 | 未確定 (仮想呼出し・未モデル) |
| `0x1322ba7` | `call qword ptr [rbx + 0x60]` | 0x69 | 未確定 (仮想呼出し・未モデル) |
| `0x1322be7` | `call rax` | 0x6a | 未確定 (仮想呼出し・未モデル) |
| `0x132a690` | `call qword ptr [rax]` | 0x4b | 未確定 (仮想呼出し・未モデル) |
| `0x132ceae` | `call qword ptr [rax + 0x20]` | 0x59 | 未確定 (仮想呼出し・未モデル) |
| `0x132fe2c` | `call qword ptr [rbx + 0x90]` | 0x09 | 未確定 (仮想呼出し・未モデル) |

### B-2. callee 戻り値への依存 (実測・測定 commit 48f2ced9)

基準 run は、Dispatcher 外へ呼び出された callee の戻り値をすべて 0 とする。`HS_DISP_RET_SPEC` で戻り値を 1 にした 2 run との差 (基準 run と比較した ID):

| 指定 | 202 から外れた ID | 202 に入った ID | 経路 (path_hash) が変わった ID | rax が変わった ID |
|---|---|---|---|---|
| `0x40fe90:one` (ID 0x17 の最初の外部呼出し) | 0x17 | 0x0a | 0x0a 0x11 0x14 0x15 0x17 0x32 0x33 0x34 0x38 0x4c 0x4d (11 件) | 0x0a 0x17 0x34 0x4c (4 件) |
| 基準 run で呼ばれた 82 VA を全て `one` | 0x17 | 0x0a | 0x0a 0x11 0x14 0x15 0x17 0x1a 0x32 0x33 0x34 0x38 0x4c 0x4d (12 件) | 0x01 0x07 0x0a 0x0e 0x13 0x17 0x1c 0x1d 0x26 0x2e 0x34 0x3d 0x46 0x47 0x49 0x4c 0x4e 0x5d 0x6a (19 件) |

- ID 0x17 は `0x40fe90` の戻り値 1 で出口 `0x131a259` へ分岐し、読み出し `0x1328a38` に届かない (格納は初期化のみ)。代わりに ID 0x0a が読み出しに届く。
- 202 件の集合は、callee 戻り値 0 の仮定の上でのみ成り立つ。`0x40fe90` は §8.2 の 3 callee にも、REPORT_DISPATCHER.md §5 の未解決の一覧にも含まれていなかった callee であり、未解決である。
- 基準 run で実行されなかった書き込み 39 件 (A-1) のうち 4 件は、戻り値 1 で実行される: `0x1320f72` (ID 0x32)・`0x13210ae` (ID 0x33)・`0x13211a1` (ID 0x34)・`0x1321efb` (ID 0x4c)。両指定で同じ ID が実行した。
- 残り 35 件は、基準・全 callee=1・`0x40fe90`=1 のいずれの run でも実行されなかった。分岐条件 (構造体フィールドや他 callee の戻り値) は未解析。
- 全 callee を HOST ポインタにする run は本 PR では再測していない。REPORT §8.2 の 3 callee A/B で 202 件が不変だったのは、その 3 callee の範囲に限る。


## C. 未収載 ID (受入 2) の個別結果

| ID (dec) | ID (hex) | rax | 読み出し到達 | 格納 (書き込み列) | 判定 |
|---|---|---|---|---|---|
| 25 | 0x19 | 0x0 | あり | 0x131873f=0x0 | 0 を確定 |
| 54 | 0x36 | 0x0 | あり | 0x131873f=0x0 | 0 を確定 |
| 64 | 0x40 | 0x0 | あり | 0x131873f=0x0 | 0 を確定 |
| 88 | 0x58 | 0x0 | あり | 0x131873f=0x0 | 0 を確定 |
| 96 | 0x60 | 0x0 | なし (出口 0x13228eb) | 0x131873f=0x0 | 未確定 |
| 101 | 0x65 | 0x0 | あり | 0x131873f=0x0, 0x1322b47=0x0 | 未確定 |
| 128 | 0x80 | 0x0 | あり | 0x131873f=0x0 | 0 を確定 |

## D. 感度試験 (スタック埋め) と実測

測定 commit `48f2ced9` (基準と 0xa5 埋めの 2 run)。0bb93345 の旧測定を参考行に残す。

| 指標 | 差分のあった ID 数 (256 中) |
|---|---|
| rax | 0 |
| path_hash | 0 |
| callouts | 0 |
| stop | 0 |
| steps | 0 |
| slot_writes | 0 |
| unmapped | 0 |

| 実行 | 指定 | wall | 開始 load | 終了 load | distinct (rax, path) | unmapped (ID / 件数) |
|---|---|---|---|---|---|---|
| base (48f2ced9) | 既定 (0 埋め) | 51.87 秒 | 未計測 | 未計測 | 109 | 61 / 5,340 |
| fill (48f2ced9) | `HS_DISP_STACK_FILL=0xa5` | 55.58 秒 | 未計測 | 未計測 | 109 | 61 / 5,340 |
| head_base0 (0bb93345・参考) | 既定 (0 埋め) | 72.44 秒 | 0.06 | 0.74 | 109 | 61 / 5,340 |
| head_fill (0bb93345・参考) | `HS_DISP_STACK_FILL=0xa5` | 73.64 秒 | 0.68 | 0.91 | 109 | 61 / 5,340 |

応答スロットの `rbp` 検証は 48f2ced9 でも一致 (読み出し到達 229 ID で一致 229・不一致 0・未到達 27)。


## E. 再現手順

```
FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<unicorn 2.1.4・pefile 入り lib> \
  HS_DISP_OUT=<base.json> python3 tools/plugins/framework/hostshim/hs_disp_emu.py
FL_WIN64_DIR=... PYTHONPATH=... HS_DISP_STACK_FILL=0xa5 HS_DISP_OUT=<fill.json> python3 tools/plugins/framework/hostshim/hs_disp_emu.py
FL_WIN64_DIR=... PYTHONPATH=... HS_DISP_RET_SPEC=0x40fe90:one HS_DISP_OUT=<one_40fe90.json> python3 tools/plugins/framework/hostshim/hs_disp_emu.py
FL_WIN64_DIR=... PYTHONPATH=... HS_DISP_RET_SPEC=<base.json の callouts 全 VA を "VA:one" で , 区切り> HS_DISP_OUT=<one_all.json> python3 tools/plugins/framework/hostshim/hs_disp_emu.py
```

- A-1 の表: `extracted/block00031_PE.bin` を capstone (x86-64) で `[0x13173a0, 0x1330000)` 逆アセンブルし、宛先 `qword ptr [rbp + 0x11a0]` の `mov`・`or` を抽出 (69 件)。実行数は JSON の `slot_writes` (`<命令 VA>=<値>`) を VA ごとに数えた。
- A-2 の表: 各 ID の `slot_writes` の最後の要素の VA を数えた。
- B-2 の表: 各 run の `path_hash`・`rax` と基準 run の差、`stop`・`trail` から 202 集合 (`reached` かつ `slot_writes` が初期化のみ) を比較した。
