# LB 依存 trap 7 件の wasm offset → IR 命令の特定 (#5667・親 #3389・M11-N255)

測定主体: 本 PR の作業 runner (2026-10-16 UTC)。素材は `fl-win64` (`extracted/block00031_PE.bin` 22,227,016 B のみ展開)・`work-m11` (`tools/m11/work/` に展開・233 件)・`toolchain-emsdk` (`/opt/emsdk` emsdk 6.0.12、既存)。
測定 commit: `f195a93a9` (main。コードは変更していない)。`git diff f195a93a9 HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` の出力は空。

## 1. 結論

- **trap の wasm offset → 関数 → faulting 命令は、LB=0 / LB=0x10000 の両 build で特定できた** (§2〜§3)。
- **「address 0 を読むか」は未確定。** 受入条件の後半は、実行時の値が要る。今回は値を観測していない。
- wasm では address 0 は有効なメモリなので、**trap を起こした access が address 0 であることは無い**。address 0 の読みは trap にならず、trap の信号では検出できない (§4)。
- 今回の run では、291・296・304 の trap スタック行が出なかった (§5)。

## 2. LB=0 (本 run の build。wasm 指紋 `017043e6`)

計測: `M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=291,296,304,555,745 bash tools/m11/m11_lb_tolerant_repro.sh 0 work/lb0`。rc=0、寛容起動 wall 8,697 ms (スクリプト計測)、`time` 実測 1 分 10 秒。

| unit | trap の wasm 関数 (offset) | 関数名 | faulting 命令 (逆アセンブル) | IR 対応 |
|---|---|---|---|---|
| 555 | `[14890]:0x353a06` | `function_535c11` | `i64.load 0` (直前 `i64.sub` + `i32.wrap_i64`) | `189437 %7 = add %5,-8` → `189439 load i64 [%8]` (`work/lb0/boot_final.ll`) |
| 745 | `[1877]:0x13d5e1` | `function_407e20__lifted` | `i64.load 0` (直前 `local.get 3; i32.wrap_i64`) | 未対応 (IR 行の特定は未実施) |

- unit 555 の呼出し鎖: `function_535c11` ← `function_4fad10` ← `function_4fb910` ← `m11_icall` (0x353a06 の先頭 5 フレーム)。
- unit 745 の呼出し鎖: `function_407e20__lifted` ← `function_407e20` (probe wrapper) ← `function_409440__lifted` ← `function_409440` ← `function_666bb0` ← `function_7745a0` ← `function_ebb3b0`。
- `function_535c11` (LB=0 IR) の load 連鎖: `%2 = [arg1+8]`・`%5 = [%2+8]`・`%9 = [%5-8]` (trap)。

## 3. LB=0x10000 (wasm 指紋 `017049e2`)

計測: `M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=40,153,158 bash tools/m11/m11_lb_tolerant_repro.sh 0x10000 work/lb10000`。rc=0、wall 11,416 ms、`time` 実測 1 分 14 秒。

| unit | trap の wasm 関数 (offset) | 関数名 | faulting 命令 | IR 対応 (`work/lb10000/boot_final.ll`) |
|---|---|---|---|---|
| 153 | `[77]:0x6b70b` | `function_412e40` | `i32.load 0` (直前 `local.get 6; i64.const -8; i64.add; i32.wrap_i64`) | `115690 %4 = add %1,-8` → `115692 load i32 [%5]`。**一致 (高)** |
| 158 | `[2057]:0x14cba9` | `function_412c20` | `i32.store16 0` (直前 `local.get 14; local.get 5; i64.add; i32.wrap_i64; i32.const 0`) | 候補: `115472 store i16 0, ptr %25` 付近。**未確定** |
| 40 | (halt0) | `function_412770` C 版 | `m11_throw_dllmain_done` | `REPORT_N3325.md` §2・§8 と同じ (今回は再測定していない) |

- unit 153 の呼出し鎖: `function_412e40` ← `function_664fd0` ← `function_665b90` ← `m11_icall`。
- unit 158 の呼出し鎖: `function_412c20` ← `function_4136a0` ← `function_413760` ← `function_414bb0` ← `function_653660`。

## 4. address 0 の判定 (受入 2 の後半)

- **trap の access は address 0 ではない。** wasm の linear memory は 0 から始まるため、address 0 の読みは trap しない。trap になった access は、実効アドレスが memory の外にあったものに限られる。
- **address 0 の読みは trap に出ない。** 例: `function_412e40` は `[rsi]` を読む (`115682`)。`rsi = 0` なら address 0 を読むが、trap しないので、今回の trap の信号では検出できない。`[rsi] != 0` の分岐に入る前の読みは、観測が要る。
- **unit 555 (推定・未検証):** `%5 = [%2+8]` が 0 なら、`[%5-8]` の実効アドレスは -8 (u32 で 0xFFFFFFF8) になり OOB する。つまり「null 基底 (`%5 = 0`) の読み」と整合する。ただし `%5` の大きい値でも OOB するため、値を観測するまで確定しない。
- **unit 153 (推定・未検証):** 分岐 (`icmp eq %1, 0`) を通るので `%1 != 0`。`%1 - 8` の OOB は、`%1` が小さすぎる (1〜7 → 負の wrap) か大きすぎることを示す。address 0 (`%1 = 8`) では無い。

## 5. 未確認 (今回の run)

| 項目 | 状態 |
|---|---|
| unit 291・296・304 の trap スタック | 今回の run の出力に stack 行が出なかった (LB=0 は 555・745 のみ)。REPORT_N3325 §4 の記録と突き合わせていない |
| unit 745 の IR 行 (`function_407e20` の load) | 未対応 |
| unit 158 の IR 行 (`store16`) | 候補のみ |
| 555 の `%5` の実行時の値 | 未観測 |
| 153 の `%1` の実行時の値 | 未観測 |
| address 0 の読み (trap にならない読み) の有無 | 未観測。観測には load の実効アドレスを記録する計測が要る |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 555 の `%5`・153 の `%1` の実行時の値 (null 基底か) | 受入「address 0 を読むか」の判定 | #5667 (本 issue。計測の実装は次の run) |
| address 0 の読み (trap にならない読み) の観測 | 「address 0 を読むか」の残り。trap の信号では分からない | #5667 |
| 745 の IR 行 (`function_407e20` の `i64.load`)・158 の `store16` の IR 行の確定 | 命令の対応が候補止まり | #5667 |
| 291・296・304 の trap 再現 (今回の run では stack 行なし) | 受入の対象 7 件のうち 3 件が今回未確認 | #5667 |

## 7. 再現

```
export FL_WIN64_DIR=$HOME/analysis/win64
M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=291,296,304,555,745 bash tools/m11/m11_lb_tolerant_repro.sh 0 work/lb0
M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=40,153,158 bash tools/m11/m11_lb_tolerant_repro.sh 0x10000 work/lb10000
python3 tools/m11/m11_wasmnames.py tools/m11/work/m11_boot.cjs.wasm <idx>   # 関数名
/opt/emsdk/upstream/bin/llvm-objdump -d --start-address=<off-48> --stop-address=<off+8> <wasm>   # 逆アセンブル
```

- wasm と IR は build ごとに変わる。`work/lb0/`・`work/lb10000/` に退避した `boot_final.ll`・`m11_boot.cjs.wasm` を使う (`work/boot_final.ll` は後の run で上書きされる)。
