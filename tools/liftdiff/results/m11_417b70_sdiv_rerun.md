<!-- 自動生成: python3 tools/liftdiff/tests/trace_417b70_sdiv_rerun.py (LD-62, #1767) -->
| stride | count | native | udiv wasm | sdiv wasm | udiv 食い違い | sdiv 食い違い |
|---:|---:|---|---|---|:---:|:---:|
| 16 | 1 | segv | trap | trap | both_fault | both_fault |
| -16 | 1 | segv | trap | trap | both_fault | both_fault |
| 16 | 2 | segv | trap | trap | both_fault | both_fault |
| -16 | 2 | segv | trap | trap | both_fault | both_fault |
| -16 | 3 | segv | trap | trap | both_fault | both_fault |
| 16 | 1152921504606846976 | segv | trap | trap | both_fault | both_fault |
| -16 | 1152921504606846976 | segv | trap | trap | both_fault | both_fault |
| 2147483647 | 3 | segv | trap | trap | both_fault | both_fault |

wasm 側 trace 先頭 (sdiv 版):
- stride 16 count 1: ['0x417b70', '0x409410', '0x407a50', '0x407770', '0x409730', '0x4096d0', '0x41d110', '0x4096b0']
- stride -16 count 1: ['0x417b70', '0x409730', '0x4096d0', '0x41d110', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0']
- stride 16 count 2: ['0x417b70', '0x409410', '0x407a50', '0x407770', '0x409730', '0x4096d0', '0x41d110', '0x4096b0']
- stride -16 count 2: ['0x417b70', '0x409730', '0x4096d0', '0x41d110', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0']
- stride -16 count 3: ['0x417b70', '0x409730', '0x4096d0', '0x41d110', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0']
- stride 16 count 1152921504606846976: ['0x417b70', '0x409410', '0x407a50', '0x407770', '0x409730', '0x4096d0', '0x41d110', '0x4096b0']
- stride -16 count 1152921504606846976: ['0x417b70', '0x409730', '0x4096d0', '0x41d110', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0']
- stride 2147483647 count 3: ['0x417b70', '0x409730', '0x4096d0', '0x41d110', '0x4096b0', '0x412a40', '0x4128b0', '0x4125e0']
