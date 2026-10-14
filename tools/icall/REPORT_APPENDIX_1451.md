# 付録: icall #1451 (ICALL-28) — Fresh Air SlateCore の wasm route と native xmm0 比較

> 親: #1299 (ICALL-25)。本付録は ICALL-28 の部分達成を記録する。CRT 初期化の native 再現 (受入条件 2) は未了で、子 issue に残す。

## 1. 結論

- Fresh Air SlateCore closure (131 関数) の wasm route を作成できた (`diff/fa_route` 相当: `tools/icall/fa_route_build.sh`)。RetDec 再実行は無し (素材 `work-icall` の `rt_freshair-core/after.0.restored.ll` を使用)。
- native (`ott_native` + `ott_load`) と wasm の xmm0 bit 比較を全 131 関数に実施。**40 関数が 8/8 入力で bit 一致**、**91 関数は未一致** (内訳は §3)。
- 未了: CRT 初期化 (DllMain・グローバル初期化) の native 再現。これが無いため native 側で 66 関数が SIGSEGV する。

## 2. 測定

測定 commit: `db761b69` (scripts 3 本を追加した commit)。`main` 取り込みは未実施 (`git diff db761b69 HEAD -- tools/icall` の差分は 0)。

| 項目 | 値 |
|---|---|
| 素材 | `fl-win64`・`plugins-freshair`・`toolchain-retdec`・`toolchain-emsdk`・`work-icall`・`work-liftlib` を `$HOME/artifacts` で確認 (実在) |
| `fa_route_build.sh` | OK、8 s、load 0.22 → 0.83 |
| `fa_sweep.sh 8 60` | 131 関数、74 s。bit 一致 40 / 他 91 |
| 単体 `fa_cmp.py 1803b3d10 --n 8` | 8/8 bit 一致、native_err 0、wasm_err 0 |

### 2.1 wasm route の作り方 (ott_route.sh との差)

1. `ir_flatten.py --limit 0x10000000`: 既定の `--limit 0x4800000` では SlateCore の BLK (`0x186319000`) が shift されず、wasm が `memory access out of bounds` で trap した。画像全域を shift する。
2. emcc に `-DICALL_BLK=0x36319000` (= map.json の blk を shift した値) と `0x3c000000` のメモリを渡す。
3. `data_gen.py` で `.rdata` / `.data` / `_RDATA` (DIR64 補正 6,147 件) を敷設。空の `ott_data_install` のままでは global 参照が壊れる。

## 3. 内訳 (`work/fa_route/sweep.jsonl`、131 関数)

| 区分 | 件数 | 説明 |
|---|---|---|
| bit 一致 | 40 | native と wasm が 8/8 一致 |
| native crash / timeout | 66 | native が SIGSEGV (CRT 未初期化の global 参照。例: `1803b3fc0` rip 外・`1803de310` addr=0x60100000)。native 基準が取れないため判定不能 |
| wasm のみ err | 15 | closure 外の関数を呼ぶ。例: `1803b5500` → `function_1803b5546` が未生成 (`Aborted(missing function)`) |
| 値の不一致 | 10 | 例: `1803de190` は native 非ゼロ、wasm 0。`1803de190` は `__asm_movsd` 等の stub を含み、`m11_simd2.py` の未実装 helper (silent 0 返却経路) の疑い。未切り分け |

- `m11_simd2.py` の未実装 declare は 39 件 (implemented 56 / 98)。`simd_merge.json` で残る stub は `__asm_int` `__asm_int3` `__asm_movntps` `__asm_vucomisd` `__asm_vucomiss` の 5 種。これらが値不一致の候補。

## 4. 未解決 (子 issue)

- **CRT 初期化の native 再現** (受入条件 2): DllMain / グローバル初期化を走らせない限り、native 66 関数は SIGSEGV で基準が取れない。子 issue を起票する (§5)。
- **値不一致 10 関数**: 未実装 SIMD stub (5 種) の実装と再比較。
- **wasm のみ err 15 関数**: closure に無い callee (例 `function_1803b5546`)。closure 拡張 (`roots` への追加) で解消するか検討。
- **`REPORT_APPENDIX_*.md` の判定**: 本付録は 1 回の sweep (N=8・seed 3) の結果。N の増加と入力分布の見直しは未実施。

## 5. 再現

```
bash tools/icall/fa_route_build.sh          # wasm route 作成 (素材 work-icall / plugins-freshair が必要)
bash tools/icall/diff/fa_sweep.sh 8 60      # 全 131 関数の native/wasm 比較 (1 関数 1 プロセス)
python3 tools/icall/diff/fa_cmp.py 1803b3d10 --n 8   # 単体
```
