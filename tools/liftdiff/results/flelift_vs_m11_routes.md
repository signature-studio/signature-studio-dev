# 自動生成: `liftdiff` batch (m11 経路比較)

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。

共通関数 7421 (flelift 7421, m11 7421)

| m11 \ flelift | match | mismatch | unexec |
|---|---|---|---|
| match | 1907 | 5 | 363 |
| mismatch | 2226 | 627 | 32 |
| unexec | 10 | 1 | 2250 |

- 両 route 一致 (match&match): 1907
- flelift のみ一致 (m11 mismatch → match): 2226
- flelift のみ不一致 (m11 match → mismatch): 5
- 両方不一致: 627
- 実行不能: m11 2261 / flelift 2645 (flelift は lift 集合外 2250 を含む)

## flelift のみ一致 (m11 mismatch → match) 上位 40
- `407520` function_407520: m11 主因 memory_semantics → flelift -
- `407720` function_407720: m11 主因 wasm_trap → flelift -
- `4078c0` function_4078c0: m11 主因 memory_semantics → flelift -
- `408040` function_408040: m11 主因 memory_semantics → flelift -
- `408540` function_408540: m11 主因 memory_semantics → flelift -
- `408580` function_408580: m11 主因 callee_divergence → flelift -
- `408600` function_408600: m11 主因 memory_semantics → flelift -
- `4087a0` function_4087a0: m11 主因 callee_divergence → flelift -
- `409230` function_409230: m11 主因 callee_divergence → flelift -
- `409350` function_409350: m11 主因 callee_divergence → flelift -
- `4093f0` function_4093f0: m11 主因 callsite_arg_drop → flelift -
- `409470` function_409470: m11 主因 icall_drop → flelift -
- `409c80` function_409c80: m11 主因 spill_slot_deref → flelift -
- `409ef0` function_409ef0: m11 主因 wasm_trap → flelift -
- `40a0d0` function_40a0d0: m11 主因 memory_semantics → flelift -
- `40a1c0` function_40a1c0: m11 主因 wasm_trap → flelift -
- `40a300` function_40a300: m11 主因 ret_only → flelift -
- `40a330` function_40a330: m11 主因 ret_only → flelift -
- `40a340` function_40a340: m11 主因 callee_divergence → flelift -
- `40a3b0` function_40a3b0: m11 主因 simd_helper → flelift -
- `40a3d0` function_40a3d0: m11 主因 ret_only → flelift -
- `40a410` function_40a410: m11 主因 memory_semantics → flelift -
- `40a550` function_40a550: m11 主因 ret_only → flelift -
- `40ae00` function_40ae00: m11 主因 xmm_arg_drop → flelift -
- `40ae30` function_40ae30: m11 主因 xmm_arg_drop → flelift -
- `40ae70` function_40ae70: m11 主因 xmm_arg_drop → flelift -
- `40b290` function_40b290: m11 主因 simd_helper → flelift -
- `40b620` function_40b620: m11 主因 xmm_arg_drop → flelift -
- `40bba0` function_40bba0: m11 主因 xmm_arg_drop → flelift -
- `40bc90` function_40bc90: m11 主因 xmm_arg_drop → flelift -
- `40bf40` function_40bf40: m11 主因 xmm_arg_drop → flelift -
- `40c1d0` function_40c1d0: m11 主因 xmm_arg_drop → flelift -
- `40c4a0` function_40c4a0: m11 主因 xmm_arg_drop → flelift -
- `40c540` function_40c540: m11 主因 xmm_arg_drop → flelift -
- `40c670` function_40c670: m11 主因 ret_only → flelift -
- `40c760` function_40c760: m11 主因 ret_only → flelift -
- `40d2ba` function_40d2ba: m11 主因 memory_semantics → flelift -
- `40d2c4` function_40d2c4: m11 主因 memory_semantics → flelift -
- `40d2cb` function_40d2cb: m11 主因 memory_semantics → flelift -
- `40ed10` function_40ed10: m11 主因 wasm_trap → flelift -

## flelift のみ不一致 (m11 match → mismatch) 上位 40
- `409070` function_409070: flelift memory_semantics[m]
- `4090e0` function_4090e0: flelift memory_semantics[m]
- `50cb00` function_50cb00: flelift unlifted_callee[h],wasm_trap[h]
- `6a1c30` function_6a1c30: flelift xmm_arg_drop[m],wasm_trap[h]
- `786c80` function_786c80: flelift callee_divergence[m]

## 両不一致の主因遷移 (m11 主因 → flelift 主因, 上位 30)
- wasm_trap → unlifted_callee: 169
- callee_divergence → unlifted_callee: 89
- callee_divergence → callee_divergence: 49
- import_arg_diff → unlifted_callee: 49
- callsite_arg_drop → callee_divergence: 38
- wasm_trap → callee_divergence: 33
- callsite_arg_drop → callsite_arg_drop: 28
- icall_drop → unlifted_callee: 20
- wasm_trap → callsite_arg_drop: 15
- icall_drop → callee_divergence: 14
- ret_only → ret_only: 13
- callee_divergence → callsite_arg_drop: 9
- ret_only → unlifted_callee: 8
- callsite_arg_drop → unlifted_callee: 7
- zero_init_drop → unlifted_callee: 6
- memory_semantics → callee_divergence: 5
- simd_helper → unlifted_callee: 5
- simd_helper → callsite_arg_drop: 5
- callee_divergence → memory_semantics: 4
- import_arg_diff → callee_divergence: 4
- arg_drop → arg_drop: 4
- wasm_trap → ret_only: 4
- xmm_arg_drop → xmm_arg_drop: 4
- callsite_arg_drop → import_arg_diff: 3
- callee_divergence → ret_only: 3
- memory_semantics → memory_semantics: 3
- callsite_arg_drop → xmm_arg_drop: 3
- rep_string_helper → wasm_trap: 3
- callsite_arg_drop → arg_drop: 3
- callsite_arg_drop → memory_semantics: 2
