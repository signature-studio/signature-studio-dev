> **正本**: `tools/python/REPORT_PY41_3860.md` §9。本付録は §9 の 72 件の表 (書込み VA・書く値・必須分岐)。生成: `python3 analysis/py341_ret584_dominators.py work/py53/fn.txt work/py341` の `ret584_dominators.tsv` と `py65_ret584_reach.py` の出力を突き合わせて作成。

## PY-341 (#4574) 付録: 72 件の書込みの書く値と必須分岐

書く値は `mov dword ptr [rbp+0x5b8], *` の直前の命令。必須分岐は支配関係で確定したもの (辺を外すと入口から書込みへ届かない jcc の辺)。

| 書込み VA | 書く値 (直前の命令) | 必ず通る分岐の数 | 書込みに最も近い必須分岐 |
|---|---|---|---|
| 0x1046d6b | `0x1046d65 mov dword ptr [rbp + 0x5b0], ecx` | 0 | `（なし・関数入口の書込み）` |
| 0x1047719 | `0x1047714 call 0x10469f0` | 13 | `0x1047704 je(落ち) ← [0x10476ff test eax, 0x20` |
| 0x1047779 | `0x1047776 mov eax, dword ptr [rax + 4]` | 14 | `0x104776d je(落ち) ← [0x1047768 test eax, 2` |
| 0x1047969 | `0x1047964 call 0x10469f0` | 14 | `0x1047954 je(落ち) ← [0x104794f test eax, 0x20` |
| 0x10479c7 | `0x10479c5 mov eax, dword ptr [rax]` | 15 | `0x10479bc je(落ち) ← [0x10479b7 test eax, 2` |
| 0x1047c18 | `0x1047c16 add ecx, eax` | 13 | `0x1047bd0 je(落ち) ← [0x1047bcb test eax, 0x20` |
| 0x1047c92 | `0x1047c8e mov eax, dword ptr [rax + rcx*4 + 0xc]` | 14 | `0x1047c79 je(落ち) ← [0x1047c74 test eax, 2` |
| 0x1047d98 | `0x1047d93 call 0x10469f0` | 14 | `0x1047d80 je(落ち) ← [0x1047d7b test eax, 0x20` |
| 0x1047e09 | `0x1047e03 mov eax, dword ptr [rax + 0x174]` | 15 | `0x1047dfa je(落ち) ← [0x1047df5 test eax, 2` |
| 0x1047f42 | `0x1047f40 add ecx, eax` | 15 | `0x1047efa je(落ち) ← [0x1047ef5 test eax, 0x20` |
| 0x1047f9c | `0x1047f96 mov eax, dword ptr [rax + 0x180]` | 16 | `0x1047f8d je(落ち) ← [0x1047f88 test eax, 2` |
| 0x104802e | `0x104802c add ecx, eax` | 11 | `0x1047fe6 je(落ち) ← [0x1047fe1 test eax, 0x20` |
| 0x1048094 | `0x104808e mov eax, dword ptr [rax + 0x1f0]` | 12 | `0x1048085 je(落ち) ← [0x1048080 test eax, 2` |
| 0x1048152 | `0x104814e movzx rax, al` | 13 | `0x104813f je(落ち) ← [0x104813a test eax, 0x20` |
| 0x104821e | `0x1048216 movzx rax, byte ptr [rax + 0x32e]` | 14 | `0x104820d je(落ち) ← [0x1048208 test eax, 2` |
| 0x10483d3 | `0x10483ce call 0x40c660` | 14 | `0x10483bc je(落ち) ← [0x10483b7 test eax, 0x20` |
| 0x1048445 | `0x104843f mov eax, dword ptr [rbp + 0x348]` | 14 | `0x10483e4 je(落ち) ← [0x10483df test eax, 1` |
| 0x1048655 | `0x104864f mov eax, dword ptr [rax + 0x258]` | 15 | `0x1048646 je(落ち) ← [0x1048641 test eax, 2` |
| 0x1048894 | `0x1048892 add ecx, eax` | 12 | `0x104884c je(落ち) ← [0x1048847 test eax, 0x20` |
| 0x10488fa | `0x10488f4 mov eax, dword ptr [rax + 0x2c4]` | 13 | `0x10488eb je(落ち) ← [0x10488e6 test eax, 2` |
| 0x1048a7d | `0x1048a7b add ecx, eax` | 12 | `0x1048a35 je(落ち) ← [0x1048a30 test eax, 0x20` |
| 0x1048ae3 | `0x1048add mov eax, dword ptr [rax + 0x2d0]` | 13 | `0x1048ad4 je(落ち) ← [0x1048acf test eax, 2` |
| 0x1048b83 | `0x1048b81 add ecx, eax` | 13 | `0x1048b3b je(落ち) ← [0x1048b36 test eax, 0x20` |
| 0x1048be9 | `0x1048be3 mov eax, dword ptr [rax + 0x21c]` | 14 | `0x1048bda je(落ち) ← [0x1048bd5 test eax, 2` |
| 0x1048cea | `0x1048ce8 add ecx, eax` | 9 | `0x1048ca2 je(落ち) ← [0x1048c9d test eax, 0x20` |
| 0x1048d2c | `0x1048d26 mov eax, dword ptr [rax + 0x220]` | 10 | `0x1048d1d je(落ち) ← [0x1048d18 test eax, 2` |
| 0x1048e36 | `0x1048e34 add ecx, eax` | 12 | `0x1048dee je(落ち) ← [0x1048de9 test eax, 0x20` |
| 0x1048ed3 | `0x1048ece call 0x40c660` | 13 | `0x1048e9f je(落ち) ← [0x1048e9a test eax, 2` |
| 0x1048ffd | `0x1048ffb add ecx, eax` | 14 | `0x1048fb5 je(落ち) ← [0x1048fb0 test eax, 0x20` |
| 0x104906e | `0x1049069 call 0x40c660` | 15 | `0x1049057 je(落ち) ← [0x1049052 test eax, 2` |
| 0x1049178 | `0x1049176 add ecx, eax` | 11 | `0x1049130 je(落ち) ← [0x104912b test eax, 0x20` |
| 0x10491ed | `0x10491e8 call 0x40c660` | 12 | `0x10491cf je(落ち) ← [0x10491ca test eax, 2` |
| 0x10493bf | `0x10493bd add ecx, eax` | 11 | `0x1049377 je(落ち) ← [0x1049372 test eax, 0x20` |
| 0x1049469 | `0x1049466 mov eax, dword ptr [rax + rcx*4]` | 12 | `0x1049451 je(落ち) ← [0x104944c test eax, 2` |
| 0x104968b | `0x1049689 add ecx, eax` | 14 | `0x1049643 je(落ち) ← [0x104963e test eax, 0x20` |
| 0x1049719 | `0x1049715 mov eax, dword ptr [rax + rcx*4 + 8]` | 15 | `0x10496fe je(落ち) ← [0x10496f9 test eax, 2` |
| 0x10497e2 | `0x10497e0 add ecx, eax` | 12 | `0x104979a je(落ち) ← [0x1049795 test eax, 0x20` |
| 0x104985d | `0x1049856 mov eax, dword ptr [rax + rcx*4 + 0x200]` | 13 | `0x1049846 je(落ち) ← [0x1049841 test eax, 2` |
| 0x1049b31 | `0x1049b2c call 0x10469f0` | 13 | `0x1049b0f je(落ち) ← [0x1049b0d test al, al` |
| 0x1049b7f | `0x1049b7d add ecx, eax` | 13 | `0x1049b0f je(立ち) ← [0x1049b0d test al, al` |
| 0x1049cbe | `0x1049cb8 mov eax, dword ptr [rax + 0x2e0]` | 15 | `0x1049caf jne(落ち) ← [0x1049cad test eax, eax` |
| 0x1049cd6 | `0x1049cd3 add eax, 2` | 14 | `0x1049ca8 je(立ち) ← [0x1049ca6 test eax, eax` |
| 0x1049cf3 | `0x1049cec mov eax, dword ptr [rax + rcx*4 + 0x2ac]` | 15 | `0x1049caf jne(立ち) ← [0x1049cad test eax, eax` |
| 0x1049f24 | `0x1049f22 add ecx, eax` | 13 | `0x1049edc je(落ち) ← [0x1049ed7 test eax, 0x20` |
| 0x1049fb8 | `0x1049fb5 mov eax, dword ptr [rax + rcx*4]` | 14 | `0x1049f92 je(落ち) ← [0x1049f8d test eax, 2` |
| 0x104a13b | `0x104a139 add ecx, eax` | 12 | `0x104a0f3 je(落ち) ← [0x104a0ee test eax, 0x20` |
| 0x104a1de | `0x104a1db mov eax, dword ptr [rax + 0x30]` | 14 | `0x104a1d2 jne(落ち) ← [0x104a1cb cmp dword ptr [rbp + 0x570], 4` |
| 0x104a1fb | `0x104a1f4 mov eax, dword ptr [rax + rcx*4 + 0xd0]` | 14 | `0x104a1d2 jne(立ち) ← [0x104a1cb cmp dword ptr [rbp + 0x570], 4` |
| 0x104a494 | `0x104a48f call 0x10469f0` | 13 | `0x104a461 je(落ち) ← [0x104a45f test al, al` |
| 0x104a4e2 | `0x104a4e0 add ecx, eax` | 13 | `0x104a461 je(立ち) ← [0x104a45f test al, al` |
| 0x104a5b0 | `0x104a5ad mov eax, dword ptr [rax + rcx*4]` | 13 | `0x104a57f je(落ち) ← [0x104a57a test eax, 2` |
| 0x104a8a3 | `0x104a8a0 call qword ptr [rax + 0x30]` | 8 | `0x104a84f jne(落ち) ← [0x104a84c cmp eax, 0x20` |
| 0x104a95f | `0x104a95c call qword ptr [rax + 0x30]` | 9 | `0x104a932 jne(落ち) ← [0x104a930 test al, al` |
| 0x104a9c7 | `0x104a9c4 call qword ptr [rax + 0x30]` | 3 | `0x104a7d0 jge(落ち) ← [0x104a7cd cmp ecx, dword ptr [rax + 0x68` |
| 0x104aba9 | `0x104aba7 add ecx, eax` | 4 | `0x104ab61 je(落ち) ← [0x104ab5c test eax, 0x20` |
| 0x104ad2e | `0x104ad26 movzx rax, byte ptr [rax + 0x148]` | 5 | `0x104acfc je(落ち) ← [0x104acf7 test eax, 2` |
| 0x104af7f | `0x104af7d add ecx, eax` | 5 | `0x104af37 je(落ち) ← [0x104af32 test eax, 0x20` |
| 0x104b093 | `0x104b08d mov eax, dword ptr [rax + 0x138]` | 6 | `0x104b063 je(落ち) ← [0x104b05e test eax, 2` |
| 0x104b305 | `0x104b300 call 0x10469f0` | 6 | `0x104b2f0 je(落ち) ← [0x104b2eb test eax, 0x20` |
| 0x104b5aa | `0x104b5a3 mov eax, dword ptr [rax + rcx*8 + 0x394]` | 7 | `0x104b593 je(落ち) ← [0x104b58e test eax, 2` |
| 0x104b843 | `0x104b83e call 0x10469f0` | 6 | `0x104b7f7 je(落ち) ← [0x104b7f2 test eax, 0x20` |
| 0x104b94e | `0x104b94b mov eax, dword ptr [rax + rcx*4]` | 7 | `0x104b925 je(落ち) ← [0x104b920 test eax, 2` |
| 0x104bebf | `0x104bebd add ecx, eax` | 4 | `0x104be77 je(落ち) ← [0x104be72 test eax, 0x20` |
| 0x104bffa | `0x104bff7 mov eax, dword ptr [rax + rcx*4]` | 5 | `0x104bfbc je(落ち) ← [0x104bfb7 test eax, 2` |
| 0x104c311 | `0x104c30f add ecx, eax` | 7 | `0x104c2c9 je(落ち) ← [0x104c2c4 test eax, 0x20` |
| 0x104c3f0 | `0x104c3ee mov eax, dword ptr [rax]` | 8 | `0x104c3e5 je(落ち) ← [0x104c3e0 test eax, 2` |
| 0x104c51a | `0x104c518 add ecx, eax` | 4 | `0x104c4d2 je(落ち) ← [0x104c4cd test eax, 0x20` |
| 0x104c56d | `0x104c56b mov eax, dword ptr [rax]` | 5 | `0x104c562 je(落ち) ← [0x104c55d test eax, 2` |
| 0x104c6ba | `0x104c6b8 add ecx, eax` | 4 | `0x104c672 je(落ち) ← [0x104c66d test eax, 0x20` |
| 0x104c769 | `0x104c767 mov eax, dword ptr [rax]` | 5 | `0x104c75e je(落ち) ← [0x104c759 test eax, 2` |
| 0x104c984 | `0x104c982 add ecx, eax` | 5 | `0x104c924 je(落ち) ← [0x104c91f test eax, 0x20` |
| 0x104c9e6 | `0x104c9e4 mov eax, dword ptr [rax]` | 5 | `0x104c9db je(落ち) ← [0x104c9d6 test eax, 2` |
