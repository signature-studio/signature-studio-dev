# PY-359 (#4703): py88 式の手計算照合 (G8 の 2 地点・部分達成)

親: #4696 (PY-355)。前段: `REPORT_PY41_APPENDIX.md` (PY-64・PY-88 節)・`REPORT_PY159.md`・`REPORT_PY161.md`。親 #3101 (PY-161) の受入 1 の残り。

## 1. 結論 (部分達成・`Refs #4703`)

- 受入 1 (G2〜G6・G8 の 10 地点 + 0x104b94e の py88 式の手計算照合・mismatch 0): **部分達成**。G8 の 2 地点 (0x104c51a・0x104c56d) は既存の式文法で手計算式と一致 (mismatch 0)。残り 8 地点は分岐合流・`shl`/`imul`・`CALL`・配列添字を含み、この run では式を確定できなかった → 子 PY-360。
- 受入 2 (不一致があれば VA と手計算式を書く): **不一致 0**。手計算式を確定できた地点はすべて機械式と一致した。

## 2. 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`) から `block00031_PE.bin` を展開。`tar --zstd -xf ... --wildcards '*block00031_PE.bin'` 2.835 秒 (real)。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53` → `fn=4664 dispatch=13 r8d_tests=174` (0.100 秒 real)。
- 突合: `python3 analysis/py64_check_expr.py work/py53/fn.txt` → `# n=8 mismatch=0 ACC?⚠合流 = 4`・exit 0 (HAND 6 点 + G8 2 点)。
- ネガティブコントロール: `--negctl p2` → exit 1 (修正前の 2 段の P は不一致になる。既存どおり)。
- 機械式の全件: `python3 analysis/py88_writes.py work/py53/fn.txt 0x104aba9 0x104ad2e 0x104af7f 0x104b093 0x104b305 0x104b5aa 0x104b94e 0x104bebf 0x104bffa 0x104c51a 0x104c56d` → 11 件とも式が出た。0x104c56d は印なし。0x104c51a は `ACC?⚠合流@0x104c3f6` を含み、それ以外の 10 件は SLOT?・CALL・ACC?⚠合流 のいずれかを含む。
- 測定 commit: 本 PR の最後のコード commit (`git log -1 -- tools/python/analysis/py64_check_expr.py` で確認)。

## 3. G8 の手計算 (一致)

| VA | store | 手計算式 | 機械式 | 判定 |
|---|---|---|---|---|
| 0x104c51a | `mov [rbp+0x5b8], ecx` | `*(*(*(0x15e14a0))+0x808)` を基準とした F 式 (`*(p+0x3b8) + rint(*(0x104ccd8) · ACC · (*(p+0x3bc) − *(p+0x3b8)))`) | 同一 (ACC は `ACC?⚠合流@0x104c3f6` を ACC と同一視) | 一致 (ACC の値は未照合) |
| 0x104c56d | `mov [rbp+0x5b8], eax` | `*(*(0x15e3290))` | `M32[M64[G[0x15e3290]]]` | 一致 |

0x104c51a の基準ポインタ鎖は `0x104c4af`〜`0x104c4c0` で `[rip+0x594fea]`→`[rax]`→`[rax+0x808]` を `[rbp+0x398]` に保存し、`0x104c4f2`〜`0x104c512` でその `[rbp+0x398]` を読む。ACC (`[rbp+0x5b8]` の書込み前の値) は 0x104c3f6 で合流し、その値は本 run では照合していない (`py64_check_expr.py` の方式どおり ACC と同一視)。

## 4. 未確定 8 地点 (子 PY-360 へ)

| VA | 未確定の原因 |
|---|---|
| 0x104aba9 (G2) | `SLOT[rbp+0x574]` (`shl`/`and` 由来)・`ACC?⚠合流@0x104a9cd`・`SLOT[rbp+0x578]` |
| 0x104ad2e (G2) | `imul`・`SLOT[rbp+0x578]`/`[rbp+0x574]` の配列添字 |
| 0x104af7f (G3) | `SLOT[rbp+0x574]`・`ACC?⚠合流@0x104ad34` |
| 0x104b093 (G3) | `imul`・配列添字 `[rbp+0x574]*8` |
| 0x104b305 (G4) | `CALL[0x10469f0]` の戻り値 (ecx = `ACC?⚠合流`) |
| 0x104b5aa (G4) | `SLOT[rbp+0x3e0]`・`SLOT[rbp+0x580]` (`0x104b2aa` で `[rbp+0x580]` を `mov` で定義) |
| 0x104b94e (G5) | `SLOT[rbp+0x578]`・`SLOT[rbp+0x580]` (`0x104b744`)・`imul` |
| 0x104bebf (G6) | `SLOT[rbp+0x3b0]` (`0x104bd61` の `mov [rbp+0x3b0],rax` の値 `[rax+rcx*8]`)・`ACC?⚠合流@0x104b954` |
| 0x104bffa (G6) | `SLOT[rbp+0x568]`・`SLOT[rbp+0x580]`・`imul`・`shl` |

この run では式を確定していない。残りは子 #4712 (PY-360) へ移す。SLOT 解決の道具は #2874 (PY-99) の `py99_slot_paths.py` に既にある (使えるかは PY-360 で確認する)。

## 5. 再現

```
cd tools/python
mkdir -p work/py64 work/py53
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'
python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53
python3 analysis/py64_check_expr.py work/py53/fn.txt          # n=8 mismatch=0・exit 0
python3 analysis/py64_check_expr.py work/py53/fn.txt --negctl p2   # exit 1
```
