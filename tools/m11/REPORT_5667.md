# LB 依存 trap 7 件の wasm offset → IR 命令の特定 (#5667・親 #3389・M11-N255)

測定主体: 作業 runner (2026-10-16 UTC)。素材は `fl-win64` (`extracted/block00031_PE.bin` 22,227,016 B のみ展開)・`work-m11` (`tools/m11/work/` に展開・233 件)・`toolchain-emsdk` (`[EMSDK]` emsdk 6.0.12)。
測定 commit: `739b46e2d` (origin/main。本 PR はコードを変えない。`git diff 739b46e2d HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` は空)。

## 1. 結論

- **trap 7 件すべて再現した。** LB=0: unit 555・745。LB=0x10000: unit 153・158・291・296・304 (+40 halt0)。
- **291・296・304 は 555 と同じ関数・同じ IR 命令で落ちる。** LB=0x10000 の build で `function_535c11` の `[14890]:0x353b81` (`i64.load 0`)。LB=0 の 555 の faulting 命令 (`[14890]:0x353a06`、`i64.load 0`) と同じ IR 命令 `load i64 [%8]` (`%8 = %5-8`) に当たる。両 build の `boot_final.ll` で `function_535c11` の本体は同一 (差分 0 行・付録 §4)。逆アセンブルの生出力と build 指紋は付録 `REPORT_APPENDIX_5667.md`。
- **153 は前回どおり IR 行一致 (高)。158 は候補のまま。745 は IR 行が未確定。**
- **「address 0 を読むか」は未確定。** 実行時の値は未観測。wasm では address 0 の読みは trap しないため、trap の信号では検出できない (§4)。

## 2. LB=0 (wasm 指紋 `d6274222`)

計測: `M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=291,296,304,555,745 bash tools/m11/m11_lb_tolerant_repro.sh 0 work/lb0`。rc=0・寛容起動 wall 12,197 ms (#5667 の再測定 2026-10-16・worktree の再生成)。
trap 行: unit 555 (`va=0x7f2500`)・unit 745 (`va=0xabb3b0`)。291・296・304 は trap しなかった。指紋・逆アセンブルの生出力は付録 §1・§2.2。

| unit | trap の wasm 関数 (offset) | 関数名 | faulting 命令 | IR 対応 (`work/lb0/boot_final.ll`) |
|---|---|---|---|---|
| 555 | `[14890]:0x353a06` | `function_535c11` | `i64.load 0` (直前 `i64.load 8; i64.const 8; i64.sub; i32.wrap_i64`。その前に `local.get 1; i64.load 8; i64.const 0; i64.ne; i32.and 1` の分岐) | `%5 = load [%2+8]`・`icmp eq %5, 0` → `%7 = add %5,-8` → `%9 = load i64 [%8]`。**一致 (高)** |
| 745 | `[1877]:0x13d5e1` | `function_407e20__lifted` | `i64.load 0` (直前 `local.get 3; i32.wrap_i64`) | 未確定。`boot_final.ll` に `__lifted` 本体は無い (`m11_post.py` が改名)。IR 本体 `function_407e20` (`boot_final.ll:104752`) の load 連鎖は未突合 |

- unit 555 の呼出し鎖: `function_535c11` ← `function_4fad10` ← `function_4fb910` ← `m11_icall`。
- unit 745 の呼出し鎖: `function_407e20__lifted` ← `function_407e20` ← `function_409440__lifted` ← `function_409440` ← `function_666bb0` ← `function_7745a0` ← `function_ebb3b0`。

## 3. LB=0x10000 (wasm 指紋 `cb141c7f`・`m11_boot.cjs.wasm`)

計測: `M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=40,153,158,291,296,304 bash tools/m11/m11_lb_tolerant_repro.sh 0x10000 work/lb10000`。rc=0・寛容起動 wall 15,842 ms・`time` 実測 1 分 29 秒 (2026-10-16 再測定)。指紋・逆アセンブルは付録 §1・§2.1・§2.3。

| unit | trap の wasm 関数 (offset) | 関数名 | faulting 命令 | IR 対応 (`work/lb10000/boot_final.ll`) |
|---|---|---|---|---|
| 153 | `[77]:0x6b70b` | `function_412e40` | `i32.load 0` (直前 `local.get 6; i64.const -8; i64.add; i32.wrap_i64`) | `115690 %4 = add %1,-8` → `115692 load i32 [%5]`。**一致 (高)** |
| 158 | `[2057]:0x14cba9` | `function_412c20` | `i32.store16 0` (直前 `local.get 14; local.get 5; i64.add; i32.wrap_i64; i32.const 0`) | 候補: `115472 store i16 0, ptr %25` 付近。**未確定** |
| 291 | `[14890]:0x353b81` | `function_535c11` | `i64.load 0` (直前 `i64.load 8; i64.const 8; i64.sub; i32.wrap_i64`) | `function_535c11` の `load i64 [%8]` (§2 と同じ)。**一致 (高)** |
| 296 | `[14890]:0x353b81` | `function_535c11` | 291 と同じ | 291 と同じ |
| 304 | `[14890]:0x353b81` | `function_535c11` | 291 と同じ | 291 と同じ |
| 40 | (halt0) | `m11_throw_dllmain_done` ← `function_412770` (C 版) | `m11_throw_dllmain_done` | `REPORT_N3325.md` §2・§8 と同じ |

- 291 の呼出し鎖: `function_535c11` ← `function_4fad10` ← `function_4fb910` ← `function_832660` ← `m11_icall`。296 は `function_846130` ← `function_4fb910`、304 は `function_883140` ← `function_4fb910` 経由。いずれも `function_535c11` の同じ faulting 命令で落ちる。
- unit 153 の呼出し鎖: `function_412e40` ← `function_664fd0` ← `function_665b90` ← `m11_icall`。
- unit 158 の呼出し鎖: `function_412c20` ← `function_4136a0` ← `function_413760` ← `function_414bb0` ← `function_653660`。

注意: LB=0 と LB=0x10000 の `function_535c11` は、分岐の並び (`i64.ne 0; i32.and 1; i32.eqz; br_if`) もアドレス以外は同じ。wasm の offset だけが違う (`0x3539fb`・`0x353b76` の分岐。付録 §2)。

## 4. address 0 の判定 (受入 2 の後半)

- **trap の access は address 0 ではない。** wasm の linear memory は 0 から始まるため、address 0 の読みは trap しない。
- **address 0 の読みは trap に出ない。** 例: `function_412e40` は `[rsi]` を読む。`rsi = 0` なら address 0 を読むが、trap しないので今回の信号では検出できない。
- **unit 555・291・296・304 (推定・未検証):** `%5 = [%2+8]` が 0 なら `[%5-8]` は -8 (u32 で 0xFFFFFFF8) になり OOB する。`icmp eq %5, 0` の分岐で `%5 == 0` は除かれるので、null 基底ではなく `%5` が 1〜7 のとき (wrap で負になる) か、大きすぎるときに OOB する。値を観測するまで確定しない。
- **unit 153 (推定・未検証):** 分岐 (`icmp eq %1, 0`) を通るので `%1 != 0`。address 0 (`%1 = 8`) では無い。

## 5. 未確認

| 項目 | 状態 |
|---|---|
| 555・291・296・304 の `%5` の実行時の値 | 未観測 |
| 153 の `%1` の実行時の値 | 未観測 |
| address 0 の読み (trap にならない読み) の有無 | 未観測。観測には load の実効アドレスを記録する計測が要る |
| 745 の IR 行 (`function_407e20` の `i64.load`) | 未確定 (`__lifted` 改名後の IR との突合が未実施) |
| 158 の `store16` の IR 行 | 候補のみ |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 555・291・296・304 の `%5`・153 の `%1` の実行時の値 (null 基底か) | 受入「address 0 を読むか」の判定 | #5667 (次の run。計測の実装が要る) |
| address 0 の読み (trap にならない読み) の観測 | 「address 0 を読むか」の残り。trap の信号では分からない | #5667 |
| 745 の IR 行 (`function_407e20` の `i64.load`)・158 の `store16` の IR 行の確定 | 命令の対応が候補止まり | #5667 |

## 7. 再現

```
export FL_WIN64_DIR=<fl-win64 の展開先 (extracted/block00031_PE.bin を含む)>
M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=291,296,304,555,745 bash tools/m11/m11_lb_tolerant_repro.sh 0 work/lb0
M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=40,153,158,291,296,304 bash tools/m11/m11_lb_tolerant_repro.sh 0x10000 work/lb10000
python3 tools/m11/m11_wasmnames.py <wasm> <idx>                                      # 関数名
<EMSDK>/upstream/bin/llvm-objdump -d --start-address=<off-40> --stop-address=<off+6> <wasm>  # 逆アセンブル
```

- wasm と IR は build ごとに変わる。`work/lb0/`・`work/lb10000/` に退避した `boot_final.ll`・`m11_boot.cjs.wasm` を使う (`work/boot_final.ll` は後の run で上書きされる)。
- 指紋 `6fe40c2e` の snapshot (`work-m11` 展開直後の `tools/m11/work/m11_boot.cjs.wasm`) は、上の 2 build のどちらとも一致しない。逆アセンブルは build ごとの wasm で行う (付録 §5)。
- 注意: `m11_lb_tolerant_repro.sh` は work 直下の wasm を上書きする。LB を切り替える前に退避する。
