# tools/plugins/p0c REPORT 付録 D (§12〜§13)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本ファイルは本体から**無変更で分割移動**した節の全文 (#378, `docs/DOC_MAP.md` §1)。節番号・見出しは移動前のまま。

## 12. P0c-5 追記 (#269): 0x5dfdb0 / 0x5de710 の残差は ext 精度ではなくハーネス/e2e 側の欠陥だった

作成: 2026-10-12 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD: `3ae2d0d` / 検証 HEAD: `970164f`
既知類型との関係 (DEFECTS.md): 該当なし (新類型 D19 候補を §12.4 に行案)。素材: `fl-win64.tar.zst` の
`block18983_PE.bin` のみ。`work/k80.lift.ll` は RetDec v5.0 (公開 release) で `lift_ranges.sh` から再生成した。

### 12.1 結論 (先出し)

1. **0x5dfdb0 の buf_diff は ext IR で 970,284 → 0 (bit-exact)**。dd 演算系列に bug は無かった。
   原因は `k80_diff.py` が table ポインタ (rcx/r9 相当) に buffer 先頭を渡していたこと。0x5dfdb0 は
   添字を `[-1, bound]` にクランプして `tbl[-1]` を読むため、native と IR で別 static 配列の直前 byte を
   読み、差分になっていた。buffer 先頭から 64 byte 内側を渡す (`bufpad`) と 0 になる。
2. **0x5de710 の buf_diff は 1,295,105 → 0**。さらに同じ原因の 0x5deb10 / 0x5decb0 / 0x5df270 /
   0x5df4d0 / 0x5df750 / 0x5df860 も 0 になった。原因は `p0c4_abi_e2e.py` が `lift_ranges.sh` の
   `fix_asm_stores.py` (movlps/movsd 等の 64bit 部分 store 復元) を通さずに `k80.lift.ll` を使っていたこと
   (IR 側で端数 (count&7) の store が欠落していた)。
3. issue の推定「dd 連鎖形の `_ext_round64` / `_ext_arith` の bug」は**否定**。ext_core_test.c
   (3M case 相当の既存モード + chain) は変更なしで全数一致 (§12.2)。

### 12.2 実測 (2000 case/kernel, fork 隔離, 検証 HEAD `970164f`)

数え方・buf_diff の定義は §11.3 と同じ。

| kernel | 起点 (3ae2d0d) | 修正後 | 備考 |
|---|---:|---:|---|
| 0x5dfdb0 (ext IR, p0c4_e2e.py) | 970,284 | **0** | 修正 1 |
| 0x5dfd30 (ext IR) | 0 | **0** | 維持 |
| 0x5de710 (x87fix IR, abi e2e) | 1,295,105 | **0** | 修正 2 |
| 0x5df610 | 2,493,284 | 2,404,917 | 残 (§12.3) |
| 0x5e0d80 | 910,694 | 910,077 | 残 (§12.3) |

- `p0c4_e2e.py 2000`: 判定 **bit-exact 7/14** (起点は 6/14)。回帰 7 kernel (0x5de820/0x5dedf0/0x5dfb60/
  0x5df210/0x5df240/0x5e0760/0x5e0b70/0x5e0bb0/0x5e1590/0x5e1780 を含む 14 kernel 表) は buf_diff=0 維持。
  所要 109.9 s (1 回実測, load average 0.87, 並列 1)。
- `p0c4_abi_e2e.py 2000`: rc=0, 所要 23.4 s (load average 0.87)。冪等性 / llvm-as OK、
  status センサス run=61 ok=54 sig11=7 (起点と同一)。
- `ext_core_test` (`cc -O2 -ffp-contract=off`): N=300000 で fails=0 (0.6 s)。

負論対照 (修正を外すと数値が戻る):

| 対照 | 外した修正 | 観測 |
|---|---|---|
| NC1 `K80_NO_BUFPAD=1` | bufpad (修正 1) | 0x5dfdb0 ext IR 0 → 970,284 (0x5dfbe0 / 0x5dfc90 は 0 のまま) |
| NC2 `K80_NO_ASMSTORES=1` | fix_asm_stores (修正 2) | 0x5de710 0 → 1,295,106 / 0x5deb10 0 → 1,295,104 / 0x5df4d0 0 → 1,305,143 / 0x5df750 0 → 649,070 / 0x5df860 0 → 644,332 |

(bufpad 適用前後で 0x5dfdb0 の x87fix IR 値も 979,240 → 13,901 に下がるが、x87fix IR は ext 精度差が
残るため 0 にはならない。ext IR で 0。)

### 12.3 残差 (推定ラベル付き・未検証)

- **0x5e0d80 (910,077) の原因候補**: lift IR の `ucomiss` 結果が捨てられている (`call void @__asm_ucomiss`
  の戻りが未使用)。機械語は `ucomiss; jbe` で `r14d = ±1` (符号) を選ぶが、IR は初回 `phitmp` と以降
  `store i64 -1` の定数になっている。符号が常に -1 になる**推定** (IR を読んだだけで、修復・差分での確認はしていない)。
  ext 精度ではない可能性が高い。
- **0x5df610 (2,404,917)**: 未調査 (§11.4 の「ext 精度」推定は、0x5de710 が精度と無関係に 0 になったため根拠が弱い)。

### 12.4 DEFECTS.md 行案・未解決・起票先

- **D19 (新, 候補) 差分ハーネスの境界 read 不一致**: 症状 = native/IR で buffer 先頭の直前 byte を読み
  diff が出る。根本原因 = クランプ添字 `-1` が buffer 先頭を指す。検出信号 = IR が buffer を使わず同じ入力で
  ret/buf が揺れる。修復 = buffer 先頭から内側にずらしたポインタを渡す。
- **D20 (新, 候補) e2e が lift 後段 pass を通していない**: `k80.lift.ll` は `lift_ranges.sh` 途中出力で、
  `fix_asm_stores` 等の後段を通らない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~0x5e0d80 の ucomiss 符号 lift 欠落 (§12.3)~~ → §13 で buf_diff 0、現状も 0 (§14.3)。#331 の対象は 0x5de3e0 / 0x5dee90 / 0x5df040 / 0x5e02b0 / 0x5e12b0 (§14.4) | (解消) | — |
| ~~0x5df610 の残差 (§12.3)~~ → §13 で buf_diff 0 | (解消) | — |
| wasm32 バックエンド検証・framework 統合 (fw_f80.py → f80_lower --ext) | #269 作業案 4 は未実施 → §16 (#311) で実施 (受入 3 のみ未検証) | #311 |
| 環境: `/opt/retdec`・`/home/ubuntu/work/{analysis,webstudio}` への絶対パス依存 (k80_diff.py 等) | CI 上では symlink で代替 | #197 に提案 (スクリプトの REPO 相対化) |

### 12.5 再現

```sh
export TMPDIR=$PWD/tools/plugins/p0c/work/tmp
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000   # 0x5de710=0 ほか
python3 tools/plugins/p0c/p0c4_e2e.py 2000        # 0x5dfdb0=0 (bit-exact 7/14)
K80_NO_BUFPAD=1 python3 tools/plugins/p0c/k80_diff.py --ir tools/plugins/p0c/work/ext/k80.ext.ll --only 0x5dfdb0 --cases 2000   # NC1
K80_NO_ASMSTORES=1 python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000                                                                # NC2
```

## 13. P0c-7 追記 (#310): 0x5df610 / 0x5e0d80 は bit-exact (buf_diff 0) になった

作成: 2026-10-13 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD: `400d546` / 検証 HEAD: `2c38a22` (コミット済み・`git status --porcelain` 空)
既知類型との関係 (DEFECTS.md): 該当なし (D21・D22 候補を §13.4 に行案)。素材: `fl-win64.tar.zst` の `block18983_PE.bin` のみ。
`work/k80.lift.ll` は `lift_ranges.sh` (RetDec v5.0) で再生成 (4.1 s)。`work/f80_classes.json` / `kernel_table.json` は
`f80_assess.py` / `inventory/kernel_table.py` で再生成。

### 13.1 結論 (先出し)

1. **0x5e0d80 (910,077 → 0)**: §12.3 の推定 (ucomiss 結果が捨てられ符号が定数) を**実測で確認**した。機械語は
   `ucomiss xmm0,xmm6; jbe` で `r14d = (0.0 > src) ? -1 : +1`。lift IR は `@__asm_ucomiss` の戻りを使わず、符号 alloca
   (`%cf.0.reg2mem`) が初回 `select(count==0, 1, -1)`・以降 `store -1` の定数だった。`k80_ucomi_sign.py` (新規) が
   ucomiss 直後に `select (fcmp ogt A.lane0, B.lane0), -1, 1` を作り `%cf.N.reload` の use を置換する。ext 精度ではなかった。
2. **0x5df610 (2,404,917 → 0)**: ext 精度でも lane 模型でもなく **k80_argfix.py [A] の xmm slot 割当の誤り**。
   `movdqa [rbp+0x10],xmm7` / `movdqa [rbp],xmm6` (非 volatile xmm6/7 の spill) の placeholder (`xor i128 0,0`) を [A] が
   「`__asm_movdqa` のみ使用 → 引数」と見て `%in.xmm3.bits` を先に割り当て、実際に xmm3 を読む `movss xmm7,xmm3` の
   placeholder は未接続のまま (0 扱い) だった。scale (xmm3) が 0 になり出力が全面不一致。修正 = `__asm_movdqa` のみの
   placeholder は引数にしない (`SKIP_SPILLFIX`)。`movaps xmm6,xmm3` 形 (0x5de5a0 / 0x5e07b0 / 0x5e0830) は幅 32 bit で接続する。
3. 副次: **同原因の 0x5de5a0 (1,260,951) / 0x5e07b0 (1,260,951) / 0x5e0830 (631,030) / 0x5de8e0 (2,365,445) も 0**。
   0x5df340 は 1,291,379 → 1,283,847 (残。未調査)。

### 13.2 実測 (2000 case/kernel, fork 隔離, 検証 HEAD `2c38a22`, 数え方は §11.3)

| kernel | 起点 (400d546) | 修正後 buf_diff | ret_diff (修正後) |
|---|---:|---:|---:|
| 0x5df610 | 2,404,917 | **0** | 2000 (native が rax を放置。判定対象外 §11.3) |
| 0x5e0d80 | 910,077 | **0** | 0 |
| 0x5de5a0 / 0x5e07b0 / 0x5e0830 / 0x5de8e0 | 1,260,951 / 1,260,951 / 631,030 / 2,365,445 | **0** | — |
| 0x5df340 | 1,291,379 | 1,283,847 | — (残) |

- 回帰: `p0c4_abi_e2e.py 2000` で起点 buf_diff=0 だった 29 kernel (status ok のみ) はすべて 0 のまま (29/29)。
  「status ok かつ buf_diff==0」の kernel 数は status ok 54 kernel 中 29 → 35 (sig11 7 kernel は buf_diff 列が 0 でも
  未実行なので数えない)。status センサス run=61 ok=54 sig11=7 (起点と同一)。冪等性・llvm-as OK、受入基準 ①-④ OK。
  所要 24.9 s (load average 0.59→0.97, 並列 1)。起点の同スクリプト実測は 27.7 s。
- `p0c4_e2e.py 2000` (ext IR): bit-exact 7/14 で起点と同一 (0x5dfbe0/0x5dfc90/0x5dfd30/0x5dfdb0/0x5e0b70/0x5e1590/0x5e1780)。
  所要 117.0 s (load average 0.97, 並列 1)。

### 13.3 負論対照 (修正を外すと数値が戻る, 2000 case)

| 対照 | 外した修正 | 観測 |
|---|---|---|
| NC1 `K80_NO_UCOMISIGN=1` | ucomiss 符号修復 | 0x5e0d80 0 → **910,077** (0x5df610 は 0 のまま) |
| NC2 `K80_NO_SPILLFIX=1` | spill placeholder 除外 | 0x5df610 0 → **2,404,917** / 0x5de5a0 0 → 1,260,951 / 0x5e07b0 0 → 1,260,951 / 0x5e0830 0 → 631,030 / 0x5de8e0 0 → 2,365,445 (0x5e0d80 は 0 のまま) |

NC は互いに独立 (NC1 は 0x5df610 に、NC2 は 0x5e0d80 に影響しない)。「status ok かつ buf_diff==0」の kernel 数 (status ok 54 kernel 中): 起点 29 / 修正後 35 / NC1 34 / NC2 30。

### 13.4 DEFECTS.md 行案・未解決・起票先

- **D21 (新, 候補) 比較フラグの結果を捨てた lift**: 症状 = `call void @__asm_ucomiss` の戻り未使用で、`jbe` 由来の分岐/選択値が
  定数化。検出信号 = IR に void の `__asm_*comis*` call があり、同 block の後続が `%cf.N.reload` を使う。修復 = fcmp で SSA 化。
- **D22 (新, 候補) callee-save spill の placeholder を引数と誤認**: 症状 = `movdqa [mem],xmm6/7` の `xor i128 0,0` に引数 xmm slot
  を割当て、本当の引数 read が未接続 (0)。検出信号 = `__asm_movdqa` のみ使用の placeholder に `%in.xmmN.bits` が付く。
  修復 = 除外し、movaps 全 reg コピー形は幅付きで接続。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x5df340 buf_diff 1,283,847 (未調査) | 80 kernel bit-exact の残 | 子 issue を起票 (本 PR 後・#197 親) |
| `k80_ucomi_sign.py` は `--func function_5e0d80` の opt-in (jbe→±1 を機械語で確認済みの 1 site のみ) | 他 kernel の同形は未走査 | #197 にコメント |
| sig11 7 kernel / abi-mismatch 7 kernel (§11.7) | 数値差分の対象外 | 子 #277 |
| `/opt/retdec`・`/home/ubuntu/work/*` 絶対パス依存 (runner では symlink で代替) | CI 再現性 | #294 |

### 13.5 再現

```sh
sudo ln -sfn <fl-win64 extracted> /home/ubuntu/work/analysis/win64/extracted ; sudo ln -sfn $PWD /home/ubuntu/work/webstudio   # #294 回避 (PR #301 と同方法)
bash tools/plugins/lift/lift_ranges.sh <PE> tools/plugins/lift/kernel_ranges_balance.txt tools/plugins/p0c/work k80
mkdir -p tools/plugins/work && python3 tools/plugins/inventory/kernel_table.py && python3 tools/plugins/p0c/f80_assess.py
export TMPDIR=$PWD/tools/plugins/p0c/work/tmp
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000                          # 0x5df610=0 / 0x5e0d80=0
K80_NO_UCOMISIGN=1 python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000       # NC1
K80_NO_SPILLFIX=1  python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000       # NC2
python3 tools/plugins/p0c/p0c4_e2e.py 2000                              # 回帰 (bit-exact 7/14)
```

