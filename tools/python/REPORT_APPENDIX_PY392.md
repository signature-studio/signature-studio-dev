# PY-392 (#4828): 0x104cc65 に届く 72 件の十分条件 (付録)

自動生成: `python3 analysis/py392_ret584_suffcond.py work/py53/fn.txt work/py392` → `python3 analysis/py392_summary.py work/py392/suffcond.tsv work/py341/ret584_dominators.tsv tools/python` (件数 72)。

列: 書込み VA・書く値の式 (`py53` の命令)・必須分岐数 (`py341`)・代表 cube の分岐数・BDD の排他 cube 数 (変数順序依存)。

| 書込み VA | 書く値の式 | 必須分岐 | 代表 cube の分岐数 | BDD の排他 cube 数 |
|---|---|---:|---:|---:|
| 0x1046d6b | `dword ptr [rbp + 0x5b8], edx` | 0 | 185 | 46176 |
| 0x1047719 | `dword ptr [rbp + 0x5b8], eax` | 13 | 36 | 5226 |
| 0x1047779 | `dword ptr [rbp + 0x5b8], eax` | 14 | 35 | 4857 |
| 0x1047969 | `dword ptr [rbp + 0x5b8], eax` | 14 | 37 | 5595 |
| 0x10479c7 | `dword ptr [rbp + 0x5b8], eax` | 15 | 36 | 5226 |
| 0x1047c18 | `dword ptr [rbp + 0x5b8], ecx` | 13 | 36 | 5226 |
| 0x1047c92 | `dword ptr [rbp + 0x5b8], eax` | 14 | 35 | 4857 |
| 0x1047d98 | `dword ptr [rbp + 0x5b8], eax` | 14 | 37 | 5595 |
| 0x1047e09 | `dword ptr [rbp + 0x5b8], eax` | 15 | 36 | 5226 |
| 0x1047f42 | `dword ptr [rbp + 0x5b8], ecx` | 15 | 38 | 5964 |
| 0x1047f9c | `dword ptr [rbp + 0x5b8], eax` | 16 | 37 | 5595 |
| 0x104802e | `dword ptr [rbp + 0x5b8], ecx` | 11 | 34 | 4488 |
| 0x1048094 | `dword ptr [rbp + 0x5b8], eax` | 12 | 33 | 4119 |
| 0x1048152 | `dword ptr [rbp + 0x5b8], eax` | 13 | 36 | 5226 |
| 0x104821e | `dword ptr [rbp + 0x5b8], eax` | 14 | 35 | 4857 |
| 0x10483d3 | `dword ptr [rbp + 0x5b8], eax` | 14 | 37 | 5226 |
| 0x1048445 | `dword ptr [rbp + 0x5b8], eax` | 14 | 42 | 7440 |
| 0x1048655 | `dword ptr [rbp + 0x5b8], eax` | 15 | 36 | 5226 |
| 0x1048894 | `dword ptr [rbp + 0x5b8], ecx` | 12 | 35 | 4857 |
| 0x10488fa | `dword ptr [rbp + 0x5b8], eax` | 13 | 34 | 4488 |
| 0x1048a7d | `dword ptr [rbp + 0x5b8], ecx` | 12 | 35 | 4857 |
| 0x1048ae3 | `dword ptr [rbp + 0x5b8], eax` | 13 | 34 | 4488 |
| 0x1048b83 | `dword ptr [rbp + 0x5b8], ecx` | 13 | 36 | 5226 |
| 0x1048be9 | `dword ptr [rbp + 0x5b8], eax` | 14 | 35 | 4857 |
| 0x1048cea | `dword ptr [rbp + 0x5b8], ecx` | 9 | 32 | 3750 |
| 0x1048d2c | `dword ptr [rbp + 0x5b8], eax` | 10 | 31 | 3381 |
| 0x1048e36 | `dword ptr [rbp + 0x5b8], ecx` | 12 | 35 | 4857 |
| 0x1048ed3 | `dword ptr [rbp + 0x5b8], eax` | 13 | 34 | 4488 |
| 0x1048ffd | `dword ptr [rbp + 0x5b8], ecx` | 14 | 37 | 5595 |
| 0x104906e | `dword ptr [rbp + 0x5b8], eax` | 15 | 36 | 5226 |
| 0x1049178 | `dword ptr [rbp + 0x5b8], ecx` | 11 | 34 | 4488 |
| 0x10491ed | `dword ptr [rbp + 0x5b8], eax` | 12 | 33 | 4119 |
| 0x10493bf | `dword ptr [rbp + 0x5b8], ecx` | 11 | 34 | 4488 |
| 0x1049469 | `dword ptr [rbp + 0x5b8], eax` | 12 | 33 | 4119 |
| 0x104968b | `dword ptr [rbp + 0x5b8], ecx` | 14 | 37 | 5595 |
| 0x1049719 | `dword ptr [rbp + 0x5b8], eax` | 15 | 36 | 5226 |
| 0x10497e2 | `dword ptr [rbp + 0x5b8], ecx` | 12 | 35 | 4857 |
| 0x104985d | `dword ptr [rbp + 0x5b8], eax` | 13 | 34 | 4488 |
| 0x1049b31 | `dword ptr [rbp + 0x5b8], eax` | 13 | 39 | 5964 |
| 0x1049b7f | `dword ptr [rbp + 0x5b8], ecx` | 13 | 39 | 5595 |
| 0x1049cbe | `dword ptr [rbp + 0x5b8], eax` | 15 | 36 | 5226 |
| 0x1049cd6 | `dword ptr [rbp + 0x5b8], eax` | 14 | 35 | 4857 |
| 0x1049cf3 | `dword ptr [rbp + 0x5b8], eax` | 15 | 36 | 5226 |
| 0x1049f24 | `dword ptr [rbp + 0x5b8], ecx` | 13 | 36 | 5226 |
| 0x1049fb8 | `dword ptr [rbp + 0x5b8], eax` | 14 | 35 | 4857 |
| 0x104a13b | `dword ptr [rbp + 0x5b8], ecx` | 12 | 35 | 4857 |
| 0x104a1de | `dword ptr [rbp + 0x5b8], eax` | 14 | 35 | 4857 |
| 0x104a1fb | `dword ptr [rbp + 0x5b8], eax` | 14 | 35 | 4857 |
| 0x104a494 | `dword ptr [rbp + 0x5b8], eax` | 13 | 36 | 5226 |
| 0x104a4e2 | `dword ptr [rbp + 0x5b8], ecx` | 13 | 36 | 4857 |
| 0x104a5b0 | `dword ptr [rbp + 0x5b8], eax` | 13 | 34 | 4488 |
| 0x104a8a3 | `dword ptr [rbp + 0x5b8], eax` | 8 | 49 | 17403 |
| 0x104a95f | `dword ptr [rbp + 0x5b8], eax` | 9 | 48 | 16296 |
| 0x104a9c7 | `dword ptr [rbp + 0x5b8], eax` | 3 | 46 | 14082 |
| 0x104aba9 | `dword ptr [rbp + 0x5b8], ecx` | 4 | 33 | 5595 |
| 0x104ad2e | `dword ptr [rbp + 0x5b8], eax` | 5 | 32 | 4857 |
| 0x104af7f | `dword ptr [rbp + 0x5b8], ecx` | 5 | 34 | 6333 |
| 0x104b093 | `dword ptr [rbp + 0x5b8], eax` | 6 | 33 | 5595 |
| 0x104b305 | `dword ptr [rbp + 0x5b8], eax` | 6 | 38 | 8547 |
| 0x104b5aa | `dword ptr [rbp + 0x5b8], eax` | 7 | 34 | 6333 |
| 0x104b843 | `dword ptr [rbp + 0x5b8], eax` | 6 | 35 | 7071 |
| 0x104b94e | `dword ptr [rbp + 0x5b8], eax` | 7 | 34 | 6333 |
| 0x104bebf | `dword ptr [rbp + 0x5b8], ecx` | 4 | 33 | 5595 |
| 0x104bffa | `dword ptr [rbp + 0x5b8], eax` | 5 | 32 | 4857 |
| 0x104c311 | `dword ptr [rbp + 0x5b8], ecx` | 7 | 30 | 3012 |
| 0x104c3f0 | `dword ptr [rbp + 0x5b8], eax` | 8 | 29 | 2643 |
| 0x104c51a | `dword ptr [rbp + 0x5b8], ecx` | 4 | 27 | 1905 |
| 0x104c56d | `dword ptr [rbp + 0x5b8], eax` | 5 | 26 | 1536 |
| 0x104c6ba | `dword ptr [rbp + 0x5b8], ecx` | 4 | 29 | 2274 |
| 0x104c769 | `dword ptr [rbp + 0x5b8], eax` | 5 | 26 | 1536 |
| 0x104c984 | `dword ptr [rbp + 0x5b8], ecx` | 5 | 29 | 2643 |
| 0x104c9e6 | `dword ptr [rbp + 0x5b8], eax` | 5 | 28 | 2274 |
