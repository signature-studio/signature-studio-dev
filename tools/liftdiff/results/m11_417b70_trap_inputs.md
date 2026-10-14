<!-- 自動生成: python3 tools/liftdiff/tests/trace_417b70_trap.py (LD-62, #1767) -->
| stride | count | 予測 site1 (0x417c62) | 予測 site2 (0x417c75) | native status | 0x409730 進入 | FN 直後が 0x409730 |
|---:|---:|:---:|:---:|---|:---:|:---:|
| 16 | 1 | False | False | segv | False | False |
| -16 | 1 | False | False | segv | False | False |
| 16 | 2 | False | False | segv | False | False |
| -16 | 2 | False | True | segv | True | True |
| -16 | 3 | False | True | segv | True | True |
| 16 | 1152921504606846976 | True | False | segv | True | True |
| -16 | 1152921504606846976 | True | False | segv | True | True |
| 2147483647 | 3 | False | False | segv | True | False |

生の trace 先頭 (t[0] は hex 文字列):
- stride 16 count 1: trace[0:8] = ['0x417b70', '0x409470', '0x407a50']
- stride -16 count 1: trace[0:8] = ['0x417b70', '0x409470']
- stride 16 count 2: trace[0:8] = ['0x417b70', '0x409470', '0x407a50']
- stride -16 count 2: trace[0:8] = ['0x417b70', '0x409730', '0x4096d0', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0', '0x4127d0']
- stride -16 count 3: trace[0:8] = ['0x417b70', '0x409730', '0x4096d0', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0', '0x4127d0']
- stride 16 count 1152921504606846976: trace[0:8] = ['0x417b70', '0x409730', '0x4096d0', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0', '0x4127d0']
- stride -16 count 1152921504606846976: trace[0:8] = ['0x417b70', '0x409730', '0x4096d0', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0', '0x4127d0']
- stride 2147483647 count 3: trace[0:8] = ['0x417b70', '0x409470', '0x407a50', '0x407770', '0x4073c0', '0x409730', '0x4096d0', '0x4096b0']
