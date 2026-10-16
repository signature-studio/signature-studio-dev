# PY-359 (#4703): py88 式の手計算照合 (G8 の 2 地点)

親: #4696 (PY-355)。前段: `REPORT_PY41_APPENDIX.md` (PY-64・PY-88 節)・`REPORT_PY159.md`・`REPORT_PY161.md`。親 #3101 (PY-161) の受入 1 の残り。

## 1. 結論 (`Closes #4703`・親 #3101 の受入 1 は残り)

- #4703 の受入 (G8 の 2 地点 0x104c51a・0x104c56d の py88 式の手計算照合・mismatch 0): **達成**。既存の式文法で手計算式と一致した。
- 親 #3101 の受入 1 (G2〜G6・G8 の 11 地点の py88 式の手計算照合): 残りは G2〜G6 の **9 地点** (0x104aba9・0x104ad2e・0x104af7f・0x104b093・0x104b305・0x104b5aa・0x104b94e・0x104bebf・0x104bffa)。分岐合流・`shl`/`imul`・`CALL`・配列添字を含み、この run では式を確定できなかった → 子 PY-360 (#4712)。
- 受入 2 (不一致があれば VA と手計算式を書く): **不一致 0**。手計算式を確定できた地点はすべて機械式と一致した。

## 2. 測定

- 測定 HEAD: `ed462de49` (main 取り込みの merge。`tools/python/analysis` の最後のコード変更)。load average 0.90 (1 分平均・測定開始時)。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`) から `block00031_PE.bin` を展開。`tar --zstd -xf ... --wildcards '*block00031_PE.bin'` 2.428 秒 (real)。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53` → `fn=4664 dispatch=13 r8d_tests=174` (0.082 秒 real・exit 0)。
- 突合: `python3 analysis/py64_check_expr.py work/py53/fn.txt` → `# n=8 mismatch=0 ACC?⚠合流 (機械側・ACC と同一視) = 4`・exit 0 (0.031 秒 real。HAND 6 点 + G8 2 点)。
- ネガティブコントロール: `--negctl p2` → exit 1 (修正前の 2 段の P は不一致になる。既存どおり)。
- 機械式の全件: `python3 analysis/py88_writes.py work/py53/fn.txt 0x104aba9 0x104ad2e 0x104af7f 0x104b093 0x104b305 0x104b5aa 0x104b94e 0x104bebf 0x104bffa 0x104c51a 0x104c56d` → 11 件とも式が出た。0x104c56d は印なし。0x104c51a は `ACC?⚠合流@0x104c3f6` を含み、それ以外の 9 件は SLOT?・CALL・ACC?⚠合流 のいずれかを含む。
- 測定 commit: `ed462de49` (コードを変えた最後の commit)。鮮度: `git diff ed462de49 HEAD -- tools/python/analysis` の出力は 0 件。旧測定 commit `53b9e3a73` からの差分は main 取り込み分 (329 行・`tools/python/analysis` 内の他 PY の変更) で、G8 の式の照合 (`py64_check_expr.py`) には影響しない。

## 3. G8 の手計算 (一致)

| VA | store | 手計算式 | 機械式 | 判定 |
|---|---|---|---|---|
| 0x104c51a | `mov [rbp+0x5b8], ecx` | `*(*(*(0x15e14a0))+0x808)` を基準とした F 式 (`*(p+0x3b8) + rint(*(0x104ccd8) · ACC · (*(p+0x3bc) − *(p+0x3b8)))`) | 同一 (ACC は `ACC?⚠合流@0x104c3f6` を ACC と同一視) | 一致 (ACC の値は未照合) |
| 0x104c56d | `mov [rbp+0x5b8], eax` | `*(*(0x15e3290))` | `M32[M64[G[0x15e3290]]]` | 一致 |

0x104c51a の基準ポインタ鎖は `0x104c4af`〜`0x104c4c0` で `[rip+0x594fea]`→`[rax]`→`[rax+0x808]` を `[rbp+0x398]` に保存し、`0x104c4f2`〜`0x104c512` でその `[rbp+0x398]` を読む。ACC (`[rbp+0x5b8]` の書込み前の値) は 0x104c3f6 で合流し、その値は本 run では照合していない (`py64_check_expr.py` の方式どおり ACC と同一視)。

## 4. 未確定 9 地点 (子 PY-360 へ)

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

この run では式を確定していない。残り 9 地点は子 #4712 (PY-360) へ移す。SLOT 解決の道具は #2874 (PY-99) の `py99_slot_paths.py` に既にある (使えるかは PY-360 で確認する)。

## 5. 再現

```
cd tools/python
mkdir -p work/py64 work/py53
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'
python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53
python3 analysis/py64_check_expr.py work/py53/fn.txt          # n=8 mismatch=0・exit 0
python3 analysis/py64_check_expr.py work/py53/fn.txt --negctl p2   # exit 1
```

## 6. PY-4909 (#5800): SLOT・CALL の展開を突合に接続 (0x104b305 の 1 地点)

親 #5313 の 5 地点のうち、0x104b305 (G4) だけを機械照合に接続した。

- 展開: `analysis/py99_slot_paths.py` に `ExpSlicer` と `expand()` を追加した。py88 の式の `SLOT[rbp+X]?` は、届く store が 1 件・入口へ届かない・到達不能なしの 3 条件を満たすときだけ、その store の値で置き換える。`CALL[0x10469f0]` は `edx + rint(M64[G[0x1046a20]] · ecx · (r8d − edx))` (`py99_call10469f0.py` で PASS 済みの式) に置き換える。
- 0x104b305 の展開結果: `(0 + rint(M64[G[0x1046a20]] · (d_in)@0x1046d6b · (0x3e80 − 0)))@0x104b300`。未解決印は 0。
- 手計算の式: `0 + rint(*(0x1046a20) · d_in · (0x3e80 − 0))`。`ecx` は `[rbp+0x5b8]` の読み (0x104b2f2) で、届く store は `0x1046d6b` の 1 本だけ。`d_in` は入口の edx。0x104b099〜0x104b2f2 の `[rbp+0x5b8]` の書込み 3 件 (0x104b0cf・0x104b16b・0x104b1e1) は 0x104b2f2 に届かないことを前向き CFG で確かめた。`edx` は 0x104b2f8 の `xor` で 0 になるため、式の `edx` は 0。
- 突合: `analysis/py64_check_expr.py` の `expanded_check()` で 0x104b305 を比べた。`mismatch=0`。ネガティブコントロール (手計算式の `d_in` を定数 `0x3e80` に置換) では `mismatch=1`・関数の戻り値 1。
- 注意: 手計算の `d_in` と機械側の `d_in` は同じ記号の名前一致で、値の一致は示していない (入口の edx が `0x1046d6b` の store で `[rbp+0x5b8]` に入る、という関係の手計算による確認まで)。機械側の展開が正しいかの独立検算は未了。

残り 4 地点 (0x104b5aa・0x104b94e・0x104bebf・0x104bffa) は展開しても `SLOT`・`…` (深さ上限) が残る。分岐を越える経路を手で追う必要があり、本 run では式を確定していない。子 issue に分けて残す。
