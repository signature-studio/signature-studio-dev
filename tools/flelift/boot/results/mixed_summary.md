関数数 8364: 一致 4942 / 不一致 777 / 実行不能 2645

不一致の類型 (主因 = 優先順位最上位の1つ / 該当数 = 複数タグ重複あり):
  unlifted_callee          主因   379   該当   392
  x-route_diff             主因   143   該当   143
  callee_divergence        主因   119   該当   224
  callsite_arg_drop        主因    66   該当    66
  ret_only                 主因    23   該当    23
  memory_semantics         主因    13   該当    13
  import_arg_diff          主因     8   該当    15
  zero_init_drop           主因     7   該当    13
  arg_drop                 主因     6   該当     8
  xmm_arg_drop             主因     6   該当    12
  wasm_trap                主因     6   該当   361
  x-boot_chain             主因     1   該当     1

不一致のうち callee を一切呼ばずに差分が出た (= その関数自身の欠陥と確定) : 19 / wasm trap を含む : 362

実行不能の内訳:
  native_fault_all_patterns           1158
  native_null_deref_all_patterns       691
  no_wasm_definition                   389
  hang                                 357
  unsupported_sig                       50

## verdict 混在採算 (boot unit 級 + liftdiff 関数級)

| target | 行数 | match | mismatch | unexec |
|---|---:|---:|---:|---:|
| flelift | 7421 | 4143 | 633 | 2645 |
| flelift-boot | 943 | 799 | 144 | 0 |
| **合計** | **8364** | **4942** | **777** | **2645** |

### unit 級 (target=flelift-boot) の寄与

| 分類 | unit 数 | 説明 |
|---|---:|---|
| match (x64c = RetDec baseline) | 799 | 両 route で同じ結果 |
| **x-route_diff** | 143 | survey unit 単位の差分。うち **native_fault (native 側 fault / x64c ok = x64c 優位) = 89** |
| x-boot_chain | 1 | boot 連鎖全体 (sequential init) の比較行 |

### 関数級 (target=flelift) の mismatch タグ上位

- unlifted_callee: 392
- wasm_trap: 361
- callee_divergence: 224
- callsite_arg_drop: 66
- ret_only: 23
- import_call_seq: 20
- import_arg_diff: 15
- memory_semantics: 13
- zero_init_drop: 13
- xmm_arg_drop: 12

`liftdiff.py summary` は両 target を同じ PE VA 空間 (恒等写像) で集計するため、
unit 級 row と関数級 row を 1 ファイルに混在させても `function.va` で衝突しない。

