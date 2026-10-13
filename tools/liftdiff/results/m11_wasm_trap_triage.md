<!-- 自動生成: python3 tools/liftdiff/tests/triage_wasm_trap.py > tools/liftdiff/results/m11_wasm_trap_triage.md (既定入力 = tools/liftdiff/work/m11/batch_closure.jsonl, results/m11_closure_verdicts.tsv。cwd 非依存) -->
# m11 wasm_trap トリアージ (LD-5, #236)

対象 = verdicts.tsv の tags 列に `wasm_trap` を含む行 **578** (primary_tag が wasm_trap は 380)。
batch jsonl: 7421 行。

## 1. 種別内訳 (関数単位・最初の wasm_trap case 基準)

| 種別 | 関数数 |
|---|---:|
| oob | 222 |
| unreachable | 218 |
| hang | 39 |
| badjson | 25 |
| indirect_sig | 3 |
| arith | 2 |
| stack_overflow | 1 |
| other | 1 |
| (jsonl に wasm_trap case なし) | 67 |
| 合計 | 578 |

## 2. unreachable (218)

- trap した最上位 frame: `function_4128b0__lifted` × 218
- 上位 5 frame の連鎖 (trap 側 → 呼出元): `function_4128b0__lifted < function_4128b0 < function_412a40 < function_4096b0 < function_4096d0` × 143, `function_4128b0__lifted < function_4128b0 < function_412a40 < function_412a60 < function_411d20` × 74, `function_4128b0__lifted < function_4128b0 < function_412a40 < function_4096b0 < function_40c820` × 1
- frame 名に signature / thunk を含むもの: **0**
- `function_412a40` の呼出元 (frame [3]): `function_4096b0` × 144, `function_412a60` × 74
- wasm 側 import 呼出列に `ExitProcess` を含む: 218 / 218。native 側に含む: 0 / 218
- 先頭 2 import の (native → wasm) 上位:
  - [] → ['MessageBoxA', 'ExitProcess'] × 64
  - ['LoadStringW', 'RaiseException'] → ['LoadStringW', 'ExitProcess'] × 25
  - [] → ['VirtualAlloc', 'MessageBoxA'] × 19
  - [] → ['LoadStringW', 'VirtualAlloc'] × 18
  - ['GetACP', 'GetACP'] → ['GetACP', 'GetACP'] × 16

## 3. OOB (222)

- trap した最上位 frame の異なり数: 71。上位: `function_414ad0` × 68, `function_412e40` × 12, `__asm_rep_movsq_memcpy` × 12, `function_1062930` × 11, `function_8cbcb0` × 10, `function_4133f0` × 9, `function_409660` × 8, `function_410b10` × 6
- タグ組合せ上位: `wasm_trap` × 140, `icall_drop,wasm_trap` × 19, `callee_divergence,wasm_trap` × 9, `callsite_arg_drop,callee_divergence,wasm_trap` × 8, `simd_helper,wasm_trap` × 7
- OOB が出た case の pattern 内訳 (case 単位): p0=82, p01=143, p1=71, pall=121, pall2=99, q0=101, qall=147, s=54, z=60

## 4. hang (39) / その他

- hang のタグ組合せ: `wasm_trap` × 23, `icall_drop,wasm_trap` × 4, `simd_helper,wasm_trap` × 3, `ret_only,wasm_trap` × 2, `callee_divergence,wasm_trap` × 2
- badjson (25): `` × 24, `{"c",` × 1
- indirect_sig (3): `function signature mismatch @ ld_wasm.wa` × 3
- arith (2): `divide by zero @ ld_wasm.wasm.function_1` × 2
- stack_overflow (1): `Maximum call stack size exceeded @ ld_wa` × 1
- other (1): `remainder by zero @ ld_wasm.wasm.functio` × 1

## 5. verdicts.tsv と jsonl の差

- jsonl で wasm_trap タグを持つ関数: 582。TSV 側 578 との共通: 511 (TSV のみ 67 / jsonl のみ 71)。
- verdict が TSV と jsonl で食い違う関数: 98 / 7421 (batch 再走間の揺らぎ・§6.2 の負荷依存と整合)。

## 6. unreachable 由来の再現 (work/m11 のスナップショットを直接検査)

- 対象 = `work/m11/ld_wasm.wasm` / `ir_instr.ll` / `build.json` (mtime は batch jsonl と別。jsonl を作った build と同一かは未確認 → 下記は「現スナップショットでの観測」)。
- wasm バイナリ (name section 含む) 中の `signature_mismatch` 出現数: **0**
- wasm バイナリ (name section 含む) 中の `sig_mismatch` 出現数: **0**
- wasm バイナリ (name section 含む) 中の `thunk` 出現数: **0**
- `function_4128b0__lifted` の出現数 (name section 等): 2
- `build.json` の `sig_mismatch` (wasm-ld リンクログの `signature mismatch` 警告数 = 署名不一致 thunk が残っていれば >0): **0** (`undefined`: 1)
- IR `function_4128b0__lifted` (152 行) 内の `ExitProcess` 呼出の直後の命令: `unreachable` × 1
