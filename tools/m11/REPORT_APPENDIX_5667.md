# #5667 付録: LB trap の wasm 逆アセンブル生出力・build 指紋・IR 突合 (M11-N255)

`tools/m11/REPORT_5667.md` の付録。REPORT の本文は結論と表だけを持ち、ここに生の証拠を置く。

測定 commit: `739b46e2d`。本付録の追加はコードを変えない (`git diff 739b46e2d HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` は空)。
測定主体: 作業 runner (2026-10-16 UTC)。素材は `fl-win64` (`extracted/block00031_PE.bin`)・`work-m11`・`toolchain-emsdk` (`[EMSDK]`)。
展開先は detached worktree (`$RUNNER_TEMP`) で、repo の `tools/m11/work/` には触れていない。

## 1. build の指紋

wasm は `m11_lb_tolerant_repro.sh` を LB ごとに実行して生成した (再生成する。LB を切り替えると wasm が変わる)。

| LB | wasm sha256 (先頭 8 桁) | 備考 |
|---|---|---|
| 0 | `d6274222` | 再生成。`tolerant.out` に `[tolerant][stack]` 555・745 を出力 |
| 0x10000 | `cb141c7f` | 再生成。`tolerant.out` に `[tolerant][stack]` 153・158・291・296・304 を出力 |
| (参考) | `6fe40c2e` | `work-m11` 展開直後の `tools/m11/work/m11_boot.cjs.wasm` (どの LB か不明)。上の 2 つのどちらとも一致しない |

`REPORT_5667.md` 旧版の指紋 `d0aa354c`・`528af80d` は、算出方法が無く再現できなかったため取り下げた。

## 2. 逆アセンブル (`llvm-objdump -d`・生出力)

いずれも `--start-address=<off-40> --stop-address=<off+8>` の出力。

### 2.1 LB=0x10000 (`cb141c7f`) の `0x353b81` = unit 291・296・304

```
  353b59: 29 03 00     	i64.load	0
  353b5c: 42 08        	i64.const	8
  353b5e: 7c           	i64.add 
  353b5f: a7           	i32.wrap_i64
  353b60: 29 03 00     	i64.load	0
  353b63: 37 03 08     	i64.store	8
  353b66: 02 40        	block   	
  353b68: 02 40        	block   	
  353b6a: 20 01        	local.get	1
  353b6c: 29 03 08     	i64.load	8
  353b6f: 42 00        	i64.const	0
  353b71: 52           	i64.ne  
  353b72: 41 01        	i32.const	1
  353b74: 71           	i32.and 
  353b75: 45           	i32.eqz
  353b76: 0d 00        	br_if   	0                       # 0: down to label1
  353b78: 20 01        	local.get	1
  353b7a: 29 03 08     	i64.load	8
  353b7d: 42 08        	i64.const	8
  353b7f: 7d           	i64.sub 
  353b80: a7           	i32.wrap_i64
  353b81: 29 03 00     	i64.load	0
  353b84: 21 02        	local.set	2
  353b86: 0c 01        	br      	1                       # 1: down to label0
  353b88: 0b           	end
```

### 2.2 LB=0 (`d6274222`) の `0x353a06` = unit 555

```
  3539de: 29 03 00     	i64.load	0
  3539e1: 42 08        	i64.const	8
  3539e3: 7c           	i64.add 
  3539e4: a7           	i32.wrap_i64
  3539e5: 29 03 00     	i64.load	0
  3539e8: 37 03 08     	i64.store	8
  3539eb: 02 40        	block   	
  3539ed: 02 40        	block   	
  3539ef: 20 01        	local.get	1
  3539f1: 29 03 08     	i64.load	8
  3539f4: 42 00        	i64.const	0
  3539f6: 52           	i64.ne  
  3539f7: 41 01        	i32.const	1
  3539f9: 71           	i32.and 
  3539fa: 45           	i32.eqz
  3539fb: 0d 00        	br_if   	0                       # 0: down to label1
  3539fd: 20 01        	local.get	1
  3539ff: 29 03 08     	i64.load	8
  353a02: 42 08        	i64.const	8
  353a04: 7d           	i64.sub 
  353a05: a7           	i32.wrap_i64
  353a06: 29 03 00     	i64.load	0
  353a09: 21 02        	local.set	2
  353a0b: 0c 01        	br      	1                       # 1: down to label0
  353a0d: 0b           	end
```

### 2.3 LB=0x10000 (`cb141c7f`) の 153・158

`0x6b70b` (unit 153・`function_412e40`):

```
   6b6fe: 7c           	i64.add 
   6b6ff: 21 08        	local.set	8
   6b701: 20 06        	local.get	6
   6b703: 42 78        	i64.const	-8
   6b705: 7c           	i64.add 
   6b706: a7           	i32.wrap_i64
   6b707: 21 09        	local.set	9
   6b709: 20 09        	local.get	9
   6b70b: 28 02 00     	i32.load	0
   6b70e: 21 0a        	local.set	10
   6b710: 20 0a        	local.get	10
   6b712: 41 01        	i32.const	1
```

`0x14cba9` (unit 158・`function_412c20`):

```
  14cb9b: a7           	i32.wrap_i64
  14cb9c: 20 0f        	local.get	15
  14cb9e: 3b 01 00     	i32.store16	0
  14cba1: 20 0e        	local.get	14
  14cba3: 20 05        	local.get	5
  14cba5: 7c           	i64.add 
  14cba6: a7           	i32.wrap_i64
  14cba7: 41 00        	i32.const	0
  14cba9: 3b 01 00     	i32.store16	0
  14cbac: 20 01        	local.get	1
  14cbae: 20 0e        	local.get	14
  14cbb0: 37 03 00     	i64.store	0
```

## 3. stack 実測 (`M11_TOLERANT_STACK` の出力・生行)

```
[tolerant][stack] unit 555 va=0x7f2500: RuntimeError: memory access out of bounds
    at wasm://wasm/017043e6:wasm-function[14890]:0x353a06
[tolerant][stack] unit 745 va=0xabb3b0: RuntimeError: memory access out of bounds
    at wasm://wasm/017043e6:wasm-function[1877]:0x13d5e1
```

```
[tolerant][stack] unit 153 va=0x275b90: RuntimeError: memory access out of bounds
    at wasm://wasm/017049e2:wasm-function[77]:0x6b70b
[tolerant][stack] unit 158 va=0x27d1a0: RuntimeError: memory access out of bounds
    at wasm://wasm/017049e2:wasm-function[2057]:0x14cba9
[tolerant][stack] unit 291 va=0x442660: RuntimeError: memory access out of bounds
    at wasm://wasm/017049e2:wasm-function[14890]:0x353b81
[tolerant][stack] unit 296 va=0x456130: RuntimeError: memory access out of bounds
    at wasm://wasm/017049e2:wasm-function[14890]:0x353b81
[tolerant][stack] unit 304 va=0x493140: RuntimeError: memory access out of bounds
    at wasm://wasm/017049e2:wasm-function[14890]:0x353b81
```

関数名: `function_535c11` は wasm func index 14890 (`m11_wasmnames.py` の出力)。`function_407e20__lifted` は 1877。

## 4. IR 突合

- `function_535c11`: `work/lb0/boot_final.ll` と `work/lb10000/boot_final.ll` の本体 (`define i64 @function_535c11` から `}` まで・1,261 バイト) を取り出して比較。**差分 0 行**。
- 対応 (wasm ↔ IR): wasm `local.get 1; i64.load 8` = IR `%5 = load [%2+8]`。wasm の `i64.load 8; i64.const 8; i64.sub; i32.wrap_i64; i64.load 0` = IR `%7 = add %5,-8`・`%8 = inttoptr`・`%9 = load i64 [%8]`。faulting 命令は `%9` の load。
- 分岐: LB=0 と LB=0x10000 の分岐の並び (`i64.ne 0; i32.and 1; i32.eqz; br_if`) は同じで、アドレスだけが違う。

## 5. 再現

```
export FL_WIN64_DIR=<fl-win64 の展開先 (extracted/block00031_PE.bin を含む)>
M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=291,296,304,555,745 bash tools/m11/m11_lb_tolerant_repro.sh 0 work/lb0
M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=40,153,158,291,296,304 bash tools/m11/m11_lb_tolerant_repro.sh 0x10000 work/lb10000
sha256sum work/m11_boot.cjs.wasm
<EMSDK>/upstream/bin/llvm-objdump -d --start-address=<off-40> --stop-address=<off+8> work/m11_boot.cjs.wasm
```

- 生ログ (`tolerant.out`・`tolerant_units.json`) は `work/lb0/`・`work/lb10000/` に出る (gitignore)。repo には commit しない (`tolerant_units.json` 48 KB × 2・ログは `work/` 配下でのみ再現可能)。
- `m11_lb_tolerant_repro.sh` は `work/` 直下の wasm と IR を上書きする。LB を切り替える前に退避する。

## 6. 745 の IR 突合 (`function_407e20__lifted`・LB=0・指紋 `d6274222`)

逆アセンブルは `llvm-objdump -d work/lb0/m11_boot.cjs.wasm` の関数本体 (`0x13d52c` から)。faulting は `0x13d5e1`。

```
  13d598: 21 03        	local.set	3
  13d59a: 20 03        	local.get	3
  13d59c: 42 07        	i64.const	7
  13d59e: 83           	i64.and
  13d5a1: 51           	i64.eq
  13d5de: 20 03        	local.get	3
  13d5e0: a7           	i32.wrap_i64
  13d5e1: 29 03 00     	i64.load	0
```

- `local 3` (`0x13d598` の `local.set 3`) = IR `%2 = load i64 [arg1-8]` (`boot_final.ll:104752` 付近)。
- `0x13d5de`〜`0x13d5e1` の `local.get 3; i32.wrap_i64; i64.load 0` = IR `%8 = inttoptr %2`・`%9 = load i64 [%8]` (`boot_final.ll:104775`)。
- `%2` の実行時の値 (address 0 か) は未観測。
