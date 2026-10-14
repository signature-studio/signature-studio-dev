# PY-163 REPORT (#3135): PY-88 の VCALL 3 件の呼出し先・引数・戻り値式

親: #2788 (PY-88)。前段: `REPORT_PY41_APPENDIX.md` の PY-88 節・`REPORT_PY159.md` §5・`REPORT_PY99_APPENDIX.md`。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。

## 1. 結論

- 受入 1 (呼出し先 vtbl[+0x30] の関数 VA): **確定できない** (不足情報は §4)。3 件は同じ `O2 = [rbp+0x410]` の vtbl[+0x30] を呼ぶ (O2 の到達定義は 3 件とも 0x104a7ab の 1 件)。O2 は `O1` の vtbl[+0x20] の戻り値で、O1 は関数 0x1331340 が `[rbp+0x118]` へ書く値。O1 の型は `.data` の実行時の配列要素で決まるため、機械語からは VA が出ない。
- 受入 2 (引数の式・VA つき): **達成**。§3 の表。edx は 2 経路の式、r8d は入口 edx (`d`) とその rint・呼出し A の戻り値・0xc61250 の out の集合、r9d は定数 `0x20`・`2`・入口 r8d (`r8_in`)。
- 受入 3 (戻り値式と突合): **達成**。戻り値式は §3 の 3 行。手計算との突合 **n=12・mismatch=0** (ネガティブコントロール mismatch=1・exit 1)。別算法 (命令単位 BFS の到達定義) の突合も n=12・mismatch=0。
- 訂正 (PY-88 節): py88 の `ACC?⚠合流@0x104a5b6` (0x104a876 の rint の入力) は線形近似の誤り。CFG 上では 0x104a861 の `[rbp+0x5b8]` の読みに届く定義は入口の edx だけ (BFS でも確認)。0x104a984 の読みも同じ。

## 2. 測定条件

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (= `$HOME/artifacts/fl-win64.tar.zst`・2.3 GB) から `block00031_PE.bin` (22,227,016 B) を展開。`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py163 --wildcards '*block00031_PE.bin'` (2.9 秒)。`work/` は gitignore。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py163/extracted/block00031_PE.bin work/py163/py53` → `fn=4664 dispatch=13 r8d_tests=174` (0.10 秒)。入力は `work/py163/py53/fn.txt`。
- 測定: `python3 analysis/py163_vcall.py work/py163/py53/fn.txt --check` → `# bfs-check n=12 mismatch=0`・`# n=12 mismatch=0`・exit 0。実時間 0.37 秒 (user 0.37 秒)・load average 0.28 (run 中の `uptime`)。
- 測定 commit: `aa61c729` (`analysis/py163_vcall.py` の最後のコード commit)。`git diff aa61c729 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (後続 commit は REPORT・DOC_MAP・付録のみ)。
- e2e: 対象外 (解析スクリプトだけの変更で wasm 出力に影響しない)。製品 KPI: 対象外 (起動・GUI に関わらない)。

## 3. 3 呼出しの戻り値式と引数

| 呼出し | 書込み | r9d の設定 | 戻り値式 (= 書く値) |
|---|---|---|---|
| A | `0x104a8a0` | `0x104a890 mov r9d, 0x20` | `T(ecx=O2, edx=E, r8d=R_A, r9d=0x20)@0x104a8a0` (書込み 0x104a8a3) |
| B | `0x104a95c` | `0x104a94c mov r9d, 2` | `T(ecx=O2, edx=E, r8d=R_B, r9d=2)@0x104a95c` (書込み 0x104a95f) |
| C | `0x104a9c4` | `0x104a9b3 mov r9d, [rbp+0x5c0]` ← {0x1046d71} | `T(ecx=O2, edx=E, r8d=R_C, r9d=r8_in)@0x104a9c4` (書込み 0x104a9c7) |

記号 (機械側の出力そのまま。`d` は入口 edx・`c` は入口 ecx・`r8_in` は入口 r8d):

- `T` = `VCALL[qword ptr [rax + 0x30]]` = `*(*(O2)+0x30)`。関数 VA は未確定 (§4)。
- `O2` = `VCALL[qword ptr [rax + 0x20]]@0x104a7a8`。[rbp+0x410] の到達定義は 0x104a7ab 1 件 (3 呼出しとも同じ)。
- `O1` = `OUT(0x1331340)@0x104a792`。[rbp+0x118] の到達定義は 0x104a792 1 件 (関数 0x1331340 の out 引数)。
- `E` = edx = [rbp+0x570]。到達定義は 0x104a75e と 0x104c268 (ループ戻り) の 2 件。3 呼出しとも同じ:
  - `(and(c,0xffff) - 0x8000)` (0x104a75e 経路: 0x104a753 `mov eax,[0x564]`・0x104a759 `sub 0x8000`。[0x564] は 0x104756f 1 件で、値は `and(c,0xffff)`)
  - `((and(c,0xffff) + 0x70000000) - 0x70008000)` (0x104c268 経路: 0x104aa97 の store ← `and(c,0xffff) + 0x70000000`、0x104c268 の `sub 0x70008000`)
- `R_A` = r8d (0x104a889 の [rbp+0x5b8])。到達定義 {0x1046d6b, 0x104a876}: `{d, rint(f64(d) * K)}`。`K` = `*(0x104cd00)` (0x104a869 の mulsd の次命令 0x104a871 + disp 0x248f)。
- `R_B` = r8d (0x104a945)。到達定義 {0x1046d6b, 0x104a8a3, 0x104a92b}: `{d, T(…)@0x104a8a0 (= 呼出し A の戻り値), OUT(0xc61250)@0x104a92b (条件付き gen)}`。
- `R_C` = r8d (0x104a9ac)。到達定義 {0x1046d6b, 0x104a999}: `{d, rint(f64(d) * K)}` (0x104a98c の mulsd disp 0x236c → 0x104cd00)。
- 入口の値: [0x5b0] ← ecx (0x1046d65)、[0x5b8] ← edx (0x1046d6b)、[0x5c0] ← r8d (0x1046d71)。入口から 0x1046d71 までの命令列 (0x1046a30〜) に call と、ecx・edx・r8d への書込みは無い (fn.txt の線形走査)。

## 4. 呼出し先 `T` の VA が決まらない理由 (受入 1)

chain (VA つき):

1. 0x104a78b `lea rdx,[rbp+0x118]`・0x104a792 `call 0x1331340` (rcx = [rbp+0x548] = this)。0x1331340〜0x133137f (py160_dis で逆アセンブル): `rax = [this+0x38]`。`rdx = rax ? rax+0x48 : 0`。`call 0x41a7b0(rbx=out, rdx)`。`[out]==0` なら `call 0x41a7b0(out, [rip+0x63d9c6])` (.bss の VA 0x1968d38)。0x41a7b0 は `*out = rdx` (AddRef・Release を伴う代入。0x41a7d5 `mov [rbx], rsi` は無条件)。よって [rbp+0x118] は必ず書かれ、O1 = `[this+0x38]+0x48` (その object 内の interface ポインタ) か、その値が null のときの .bss の既定値。
2. 0x104a797 `mov rcx,[rbp+0x118]`・0x104a7a8 `call [rax+0x20]` (rax = `[O1]`)。戻り値 O2 を 0x104a7ab で [rbp+0x410] に入れる。
3. [rbp+0x548] (this) at 0x104a784 の到達定義は {0x104a77d, 0x104c29a}:
   - 0x104a77d: `.data` の `G[0x15e2218]` (0x104a76b + disp 0x597aad = 0x15e2218) → `[+8]` の配列 → 添字 `[rbp+0x580]` (0x10474a0 で `shr([0x5b0], 0x10)`)。
   - 0x104c29a: `G[0x15e06a0]` 系の別の配列。添字は [rbp+0x574]・[rbp+0x578] (py88 の SLOT? 印・未解決)。
4. したがって O2 のクラスは実行時の配列要素で決まり、`T` = vtbl(O2)[+0x30] の VA は静的な機械語からは出ない。3 呼出しは同じ O2 (同じ反復内) を使うので、同じ反復では同じ `T` を呼ぶ。

不足情報 (VA を確定するために要るもの):

- (a) `.data` の `G[0x15e2218]` と `G[0x15e06a0]` の実行時の内容 (配列の要素数の上限は 0x10474b6 の比較 `[rax+0x10]`)。
- (b) (a) の要素 (O1 の元) のクラスの vtable のアドレスと、その vtbl[+0x20] の関数 (O2 を返す関数)。
- (c) 0x1331340 の `[this+0x38]` の値 (O1 の具体型)。
- (d) O2 のクラスの vtable と、その vtbl[+0x30] の VA (= `T`)。

(a)〜(d) は実行時のメモリの値で、静的な機械語からは読めない。この関数の中には G の初期化は見当たらなかった (見た範囲は本 fn.txt のみ)。

## 5. 突合 (手計算の式と機械側の式)

手計算 (HAND) は呼出し直前の機械語を読んで手で書いた式。機械側は `py163_vcall.py` が CFG の到達定義から出した式。

| 項 | 手計算 | 判定 |
|---|---|---|
| ecx = O2 (A・B・C) | `VCALL[qword ptr [rax + 0x20]]@0x104a7a8` | 一致 ×3 |
| edx (A・B・C) | `(and(c,0xffff) - 0x8000)`・`((and(c,0xffff) + 0x70000000) - 0x70008000)` | 一致 ×3 (各 2 項) |
| r8d A | `d`・`rint((f64(d) * *(0x104cd00)))` | 一致 |
| r8d B | `VCALL[qword ptr [rax + 0x30]]@0x104a8a0`・`OUT(0xc61250)@0x104a92b`・`d` | 一致 |
| r8d C | `d`・`rint((f64(d) * *(0x104cd00)))` | 一致 |
| r9d A・B・C | `0x20`・`2`・`r8_in` | 一致 ×3 |

- 測定: `python3 analysis/py163_vcall.py work/py163/py53/fn.txt --check` → `# n=12 mismatch=0`・exit 0。
- ネガティブコントロール: `--check --negctl r9c` (r9d C の手計算を `0x20` にする) → `r9d C 不一致 hand=['0x20'] mach=['r8_in']`・`# n=12 mismatch=1`・exit 1。
- 別算法: `bfs_defs` (命令単位の BFS。kill は命令単位・0xc61250 は gen) で 12 読みの到達定義集合を求め、ブロック単位の固定点と突合: `# bfs-check n=12 mismatch=0`。
- 用法の誤り: `--negctl foo` は usage を出して exit 2 (測定済み)。

## 6. 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `T` = vtbl(O2)[+0x30] の関数 VA (§4 の (a)〜(d) の実行時データ) | 受入 1 (3 呼出しの呼出し先)。戻り値の関数部分 | #3101 (PY-161)。PY-161 の vtbl 解決の項に含める (PM 判断) |
| 戻り値の数値 (`d`・`c`・`K` = `*(0x104cd00)` の値) | 書く値の数値。式は確定 | 同上 (実行時の入力依存) |
| 0x104c29a の表 (`G[0x15e06a0]`・[rbp+0x574]/[0x578] の SLOT? 印) | [rbp+0x548] の 2 件目の定義の式 | 同上 |

## 7. 再現

```
python3 analysis/py53_dispatch.py work/py163/extracted/block00031_PE.bin work/py163/py53
python3 analysis/py163_vcall.py work/py163/py53/fn.txt            # 3 呼出しの式と連鎖の一覧
python3 analysis/py163_vcall.py work/py163/py53/fn.txt --check    # exit 0 が正 (n=12 mismatch=0)
python3 analysis/py163_vcall.py work/py163/py53/fn.txt --check --negctl r9c   # exit 1 が正
```

`work/` は gitignore。素材の展開先は §2 の通り。
