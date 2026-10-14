# 付録: icall #1606 (ICALL-34) — Fresh Air SlateCore の CRT 初期化・未一致の切り分け (部分達成)

> 親: #1451 (ICALL-28)。本付録は #1606 の 1 run 分の測定と切り分けを記録する。
> 受入条件 1 (CRT 初期化) は子 #1814 (ICALL-40) へ、2・3 は既存の #1632・#1633 へ移した。本 PR で満たすのは 4 (sweep 件数の更新) のみ。

## 1. 結論

- 受入条件 1 (native CRT 初期化で SIGSEGV 66 関数を解消): **子 #1814 へ移管**。CRT 初期化は `ott_native.c` に未実装。
  `addr=0x60100000` の読み出しを確認 (§3)。どの global を誰が設定するかは未特定。
- 受入条件 2 (値不一致 10 関数の SIMD stub 切り分け): **#1632 へ移管**。`1803de190` の wasm 0 返却は確認したが、SIMD stub 起因かは未検証 (§4)。
- 受入条件 3 (closure 外 missing function 15 関数の方針): **#1633 へ移管**。方針は未決 (§5)。
- 受入条件 4 (`fa_sweep.sh 8 60` の件数更新): **達成**。今回の実測は 40 / 66 / 15 / 10 (§2)。REPORT_APPENDIX_1451 の 41 / 9 とは 1 関数ずれる (§2.2)。

## 2. 測定

測定 commit: `2f685180` (`origin/main`。作業ブランチ `1606-fa-crt-init` の起点)。HEAD (`821f9383`) で同じ sweep を再実行し、同値を確認した (§2.2)。

### 2.1 鮮度の確認

```
$ git diff --stat 2f685180 HEAD -- tools/icall/diff tools/icall/*.sh tools/icall/*.py tools/icall/rt tools/ott/lift tools/ott/native tools/m2 tools/m5 tools/m11
(出力なし: コード範囲の差分 0 件)
```

(参考) 前回 `7e665077` からの差分には `tools/m11/m11_build.sh`・`tools/m11/trap_triage/` が含まれるが、
`tools/icall` の fa route・sweep からは参照されない (`grep` で 0 件) ため、測定値には影響しない。

### 2.2 sweep (`bash tools/icall/diff/fa_sweep.sh 8 60`)

| 項目 | 値 |
|---|---|
| 関数数 | 131 (`work/rt_freshair-core/map.json` の func_map) |
| 所要 | 73.6 s (real)。開始時 load 0.52・終了時 1.11 (4 vCPU) |
| 素材 | `work-icall` を repo 直下に展開 (`tools/icall/work/`)。`plugins-freshair` を `fetch.sh` で `tools/targets/freshair/work/win/` に展開 |
| wasm route | `bash tools/icall/fa_route_build.sh` OK (9.5 s)。ただし `ICALL_OVR` の 4 関数は closure 外で `missing` (既知) |
| 集計 | **bit一致 40 / native crash・timeout 66 / wasm のみ err 15 / 値の不一致 10** (合計 131) |

REPORT_APPENDIX_1451 の記録 (41 / 66 / 15 / 9) とは bit 一致が 1 関数少なく、不一致が 1 関数多い。
同じ `fa_sweep.sh` 末尾の判定で数えた値。差の 1 関数の原因は未特定 (本 run では 1451 の sweep 出力と突き合わせていない)。
本付録は今回の実測値を正とする。

### 2.3 ネガティブ・検算の扱い

sweep の判定は 1 関数 1 プロセスの JSON 1 行 (`status` / `native_err` / `wasm_err` / `mismatch`) で決まる。
区分の定義は `fa_sweep.sh` の集計部が正本。独立の検算スクリプトは本 run では未追加 (受入条件に含まれない)。

## 3. native SIGSEGV の確認 (受入条件 1 の切り分け)

| VA | 観測 | 解釈 |
|---|---|---|
| `1803de310` | `SIGSEGV rip=0x1803de3a5 (rva 0x3de3a5) addr=0x60100000 rcx=0x600ff810 rdx=0x600ff790` | `0x60100000` は `ott_native.c` の thunk 領域 (`0x60000000`・1 MiB) の直後。global ポインタが CRT 未初期化で不正値のまま参照されている疑い |
| `1803b3fc0` | `SIGSEGV rip=0x7ffff7002918 addr=(nil)` | rip が画像外 (libc 側)。関数ポインタ由来の間接 call の疑い |

- SlateCore の entry point は RVA `0x100be34` (VA `0x18100be34`)。`ott_native.c` の `ott_load` は entry を呼ばない
  (冒頭コメントの「CRT 初期化 (DllMain) は走らせない」が設計上の前提)。
- DllMain を走らせるには、現在 `missing_import` で即 exit する import の多くを実装する必要がある。本 run では未着手。

## 4. 値の不一致 (受入条件 2 の切り分け)

- 代表 `1803de190`: native `c000c5300342457c` / `3fd6a5368858d8d0` (先頭 2 入力)、wasm `0000000000000000` (両入力)。
- wasm 側が 0 を返す経路は `__asm_*` stub のいずれか。REPORT_APPENDIX_1451 §3 の 5 種 (`__asm_int` `__asm_int3` `__asm_movntps` `__asm_vucomisd` `__asm_vucomiss`) が候補。
- **未検証**: どの stub が 0 を返すかは、stub 呼び出しのトレースを取っていないため未特定。
  stub 実装の追加は本 run の範囲外。

## 5. closure 外 callee (受入条件 3)

- 代表 `1803b5500` → `function_1803b5546`: wasm 側で `Aborted(missing function)`。closure 外の関数を呼ぶ。
- 方針案 (未決): (a) closure の roots に追加して生成対象を広げる、(b) 呼び出し先を stub で固定値返却にする。
  どちらも判断材料 (呼び出し先の数・依存範囲) が不足しているため、本 run では決めない。

## 6. 再現

```
cd <repo root>
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60          # 末尾に 4 区分の件数
python3 tools/icall/diff/fa_cmp.py 1803de310 --n 2   # SIGSEGV 確認
python3 tools/icall/diff/fa_cmp.py 1803de190 --n 2   # 値不一致の確認
```

素材: `work-icall` (repo 直下に展開。tarball は `tools/icall/work/...` の相対パスを持つ)・
`plugins-freshair` (`FA_DL=<展開先> bash tools/targets/freshair/fetch.sh`)・`toolchain-emsdk` (`/opt/emsdk`)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| CRT 初期化 (DllMain・グローバル初期化) の native 再現・SIGSEGV 66 関数 | 66 関数の基準が取れない | #1814 (ICALL-40) |
| 値不一致 10 関数の SIMD stub 切り分け | 10 関数の bit 一致が不明 | #1632 (ICALL-36) |
| closure 外 missing function 15 関数の方針 | 15 関数が wasm で err | #1633 (ICALL-37) |
| 1451 (41/9) と 1606 (40/10) の 1 関数差 | 集計の再現性 | 本 issue のコメントで追跡 |
