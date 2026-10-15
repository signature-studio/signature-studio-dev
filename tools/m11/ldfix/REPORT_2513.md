# #2513 (LD-116): function_666a60 の entry の回数 0 早期脱出 (機械語 666ae0〜666ae4 の再現)

親: #2447 (LD-115、PR #2543 で merge 済み)。前段: #2447 の `REPORT_2447.md` §2.4 (回数 0 の分岐が IR に無い)。

**判定: 達成** (受入条件 3 件すべて)。修復は `fix_ld116.py` の検証用単独パッチで、本番の IR 生成経路 (`m11_gen_ir2.sh`) には未配線 (§8)。

測定 commit: `db08da04` (コードを変えた最後の commit)。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| entry に機械語の回数 0 早期脱出を IR で再現 (SSA を保つ形)。`fix_ld115.py` と同じ単独パッチ方式で、既存 2 箇所の修復を変えない | **達成**。§2・§3。IR diff は entry の分岐 (4 行) と exit の phi (3 行) だけ。fix_ld115 の 2 箇所は差分に出ない |
| `dyn_ld115.mjs` を拡張し、`arg2=0` で trap せず `ret=0`、`arg2=3` の結果が #2447 と変わらないことを wasm 直接呼びで実測 | **達成**。§4。`DYN_SUMMARY ld116_fail=0/2` |
| survey 942 unit を修復前後で突合し、ok 退行 0 | **達成**。§5。ok 871 → 871、ok 退行 0、kind 以外の差分 0 |

## 2. 機械語と IR の対応 (受入 1)

機械語 (`block00031_PE.bin` を `ldmach.py` の `Machine.disasm_fn` で逆アセンブル)。

```
666ada  mov edx, dword [r14]   ; edx = N.count (666a9e で書いた arg2)
666add  sub  edx, 1            ; edx = count - 1
666ae0  mov  eax, ecx          ; eax = 0 (ecx は 666ad8 の xor)
666ae2  cmp  eax, edx
666ae4  jg   0x666b29          ; 0 > count-1 (符号付き) = count ≤ 0 なら exit
666b29  ... pop/ret            ; eax = 0 のまま返す
```

修復前 IR (`pre.ll`) の entry 末尾は `store i64 0, ptr %rdx.0.reg2mem` の後の無条件 `br label %dec_label_pc_666aeb`。exit `dec_label_pc_666b29` は `ret i64 %40` だけで、preds は loop 本体のみ。このため回数 0 では loop が `rdx-1 = 0xFFFFFFFF` から回り続け、wasm では範囲外の store で trap する (`REPORT_2447.md` §4 の BASE)。

## 3. 修復 (受入 1)

`tools/m11/ldfix/fix_ld116.py` (標準ライブラリのみ、`fix_ld115.py` と同じ単独パッチ方式。想定と違う IR は assert で止める)。2 点を直す。

- entry 末尾の `br` を、機械語 `666ada`〜`666ae4` と同じ判定の条件分岐に置き換える。`%15` (N) から `load i32` で `N.count` を読み直し、`sub 1` の結果が符号付きで負なら exit、そうでなければ loop へ。count = INT_MIN の wrap も機械語どおり (`sub` は i32)。
- exit `dec_label_pc_666b29` の ret を phi で受ける。早期脱出の edge は 0 (機械語の `eax = 0`)、loop の edge は従来どおり `%40`。exit は単一のまま残す。

IR diff (`post115.ll` → `post116.ll`、`ld116_e2e.sh` の出力 `ir_116.diff`、14 行):

```
225182c225182,225185
<   br label %dec_label_pc_666aeb
---
>   %ldfx116c = load i32, ptr %15, align 4
>   %ldfx116d = sub i32 %ldfx116c, 1
>   %ldfx116e = icmp slt i32 %ldfx116d, 0
>   br i1 %ldfx116e, label %dec_label_pc_666b29, label %dec_label_pc_666aeb
225216,225217c225219,225221
< dec_label_pc_666b29:                              ; preds = %dec_label_pc_666aeb
<   ret i64 %40
---
> dec_label_pc_666b29:                              ; preds = %dec_label_pc_666aeb, %dec_label_pc_666a60
>   %ldfx116r = phi i64 [ %40, %dec_label_pc_666aeb ], [ 0, %dec_label_pc_666a60 ]
>   ret i64 %ldfx116r
```

`post115` は `REPORT_2447.md` の修復後 IR (`fix_ld115.py` の 2 箇所) そのもの。

## 4. 動的確認 (受入 2)

`tools/m11/ldfix/dyn_ld115.mjs` を拡張した (5 番目の引数 `AFTER116.cjs` を与えたときだけ、arg2=3 の同一性と arg2=0 の判定を追加する。既存の 3 版判定の出力は不変)。

| 版 | arg2=3 (count=3) | arg2=0 |
|---|---|---|
| pre (ldfix + fix_ld108) | TRAP `memory access out of bounds` | 対象外 |
| mid (+ 回数初期値のみ) | FAIL(slot0.f16) (`slot.+16` が slot のアドレス。#2447 の陰性対照と同じ) | 対象外 |
| post115 (#2447 修復後 = NEW) | PASS (N=0x10be8cf0, ret=0x3, count=0x3, slot0〜2.f16 = N) | **TRAP** `memory access out of bounds` (既知の欠陥。陰性対照) |
| post116 (#2513 修復後) | **PASS**、post115 と ret・count・tag・slot 4 欄が同一 (`NEW と同一: true`) | **PASS**: ret=0x0 count=0x0 tag=0x2 (trap せず 0 を返す) |

判定: `DYN_SUMMARY after_fail=0/1` (既存の 3 版判定)、`DYN_SUMMARY ld116_fail=0/2` (追加の判定)。

## 5. survey 942 unit (受入 3)

`ld116_e2e.sh` の 4/5・5/5。修復前 = post115、修復後 = post116 (同じ build 条件)。

| 項目 | 修復前 (post115) | 修復後 (post116) |
|---|--:|--:|
| ok | 871 | 871 |
| miss / other / halt0 / oob / noproc | 47 / 1 / 8 / 14 / 1 | 47 / 1 / 8 / 14 / 1 |
| ok 退行 unit | — | **0** |
| kind 以外も含めた差分 unit (frames は深さのみ) | — | **0** |
| icall sites・targets の [ok, miss] 差 | — | 0 件・0 件 |

限界 (2 点):

- `REPORT_2447.md` §5 の値 (ok 869 / oob 16) とは一致しない。測定起点が違う (2447 は `3dbb35e0`、本件は `573a4697`)。差の原因は未切り分け (§8)。本件の判定は同一 build 条件の修復前後比較で行った。
- 666a60 は survey の 942 unit で実行されない (`REPORT_509.md` §4.3)。このため ok 退行 0 は、関数が実行されないことによる。修復の波及は survey では測れない。

## 6. DEFECTS.md

D19 (件数 0 のループ本体が実行される類型) の例に、3 例目として `666a60` を 1 文で追記した (測定値は本 REPORT だけに置く)。D19 の根本原因は未切り分けのまま。

## 7. 検証 (WORKFLOW §6)

- 検証起点: `origin/main` = `573a4697`。
- 測定 commit: `db08da04` (コードを変えた最後の commit: `fix_ld116.py`・`ld116_e2e.sh` の追加と `dyn_ld115.mjs` の拡張)。
- 差分 0 の証跡: `git diff db08da04 HEAD -- tools/m11/ldfix/fix_ld116.py tools/m11/ldfix/dyn_ld115.mjs tools/m11/ldfix/ld116_e2e.sh` の出力は空 (本文執筆時点の HEAD で実行)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/ldfix/ld116_e2e.sh` (前提: `tools/m11/work` に work-m11 の展開、`[EMSDK]`、`capstone`・`pefile`)。
- 所要: **107 s** (`db08da04` での実行、rc=0、wall clock)。load average (1 分値) は 0.31 → 0.89。同じ検証を作業ツリー段階 (コード未コミット) で実行した時は 109.4 s で、DYN 行と survey の数値は両方で同一だった。
- 出力: DYN 行 (§4) と survey 2 本 (§5) は `db08da04` の実行で上記の値と一致。
- 20 MiB 超の blob: `find tools/m11/ldfix -type f -size +20M -not -path '*/work/*'` は空。
- 検証範囲: `work-m11` の snapshot (`boot_final.prealloca.ll`) から現行 ldfix で作った IR (2447 と同じ)。本番の `m11_gen_ir2.sh` 全体は未実施。
- 検証範囲外: 本番配線 (§8)、呼び出し元の arg2 分布 (§8)。

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `fix_ld116.py` の本番配線 (`m11_gen_ir2.sh` で `fix_ld115.py` の直後に掛け、`ir_conditions` に記録し、`m11_build.sh` で要求する) | 通常 build の wasm では 666a60 の回数 0 が未修復 (trap が残る) | #2527 (LD-117、`fix_ld115` の配線) の範囲に追記 (issue コメント) |
| 666a60 の 4 箇所の呼び出し元の arg2 分布 (回数 0 になる経路が実際にあるか) | 修復の実利の大きさが未確定 | 本 PR の未解決表で追跡 (測定のみのため起票しない) |
| 回数 0 の早期脱出の欠落の根本原因 (RetDec のどの段で `cmp; jg` が落ちるか) | 修復は後追いの単独パッチ。同型 (D19) の別関数は未探索 | DEFECTS D19 の未切り分け (既存行) |
| 2447 §5 の ok 869 との差 (測定起点の違い、原因未切り分け) | survey の絶対値は 2447 と比べられない | 本 PR の未解決表で追跡 (再測定のみのため起票しない) |
| 666a60 が survey で実行されない (`REPORT_509.md` §4.3) | ok 退行 0 は関数が実行されないことによる | 本 PR の未解決表で追跡 (`REPORT_2447.md` §8 から継続) |
