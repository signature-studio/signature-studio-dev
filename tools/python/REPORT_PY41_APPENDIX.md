# PY-41 REPORT 付録 (PY-52 #1875 の節を分割移動)

親: #1911 (PY-53)。本体 `REPORT_PY41.md` の 250 行上限のため、`## PY-52` 節を無変更で移動した (Git 履歴に残る)。

## PY-52 (#1875): `ecx=0x40000001`・`edx=0`・`r8d=2` 経路の確定 (実測・逆アセンブル)

- 測定: `analysis/py41_disasm.py` で `0x1046a30`〜`0x104ccca` (関数末尾の ret) を逆アセンブル (4,664 命令)。`ecx`/`edx`/`r8d` の引数は `[rbp+0x5b0]`・`[rbp+0x5b8]`・`[rbp+0x5c0]` に退避される (0x1046d65〜0x1046d71)。
- RIP 相対の参照先 VA は、命令長を含めて `ins.address + ins.size + disp` で解決した (手計算は 7 バイト命令の長さを誤ったため採用しない)。
- 対象は getSwing (0xd5dc01) と呼出し元 0x10473a5 のうち `ecx=0x40000001` の経路。getSwing の引数は `ecx=0x40000001`・`edx=0`・`r8d=2`。

### 経路 (r8d=2 で確定する部分)

| VA | 命令 | 判定 (r8d=2, ecx=0x40000001) |
|---|---|---|
| 0x1046d79 | `[rbp+0x584] = -1` | 戻り値の初期値 |
| 0x1046d8d | `[flag@0x15e1890]` が非 0 なら 0x104cc72 へ (戻り値 -1) | **実行時依存** (フラグの値は静的に決まらない) |
| 0x1046dc4 | `test r8d, 0x8a1` → 0 なら 0x1046e05 | 2 & 0x8a1 = 0 → 0x1046e05 へ (確定) |
| 0x1046e00 | `call 0xf82c20` | **通らない** (0x1046dc4 の `test r8d, 0x8a1` が 0 で 0x1046e05 へ飛ぶため) |
| 0x1046e23 | `test r8d, 0x240` → 0 なら 0x1047424 | 2 & 0x240 = 0 → **0x1047424 へ (確定)**。0x1046e2e〜0x1046edf (`ecx` の範囲判定・0x1046edf 以降の分岐) は**通らない** |
| 0x1047436 | `ecx == 0x40000001` なら 0x104c4af | 確定 |
| 0x104c4c7 / 0x104c520 | `test r8d, 0x20` / `test r8d, 1` | いずれも 0 → 分岐先へ (確定) |
| 0x104c557 | `test r8d, 2` が非 0 → 0x104c564 へ fall-through | 確定 |
| 0x104c564 | `eax = dword [*(0x15e3290)]`・`[rbp+0x5b8] = eax` | **edx=0 は捨てられ、この読み値が以降の戻り値になる** |
| 0x104c573〜0x104c5a6 | `test r8d, 0x10` / `test r8d, 4` | いずれも 0 → 0x104caae へ |
| 0x104caae〜0x104cb0a | `[rbp+0x52f]` (0x1046e05 で 0 に設定済み)・`test r8d, 0x100` | 0 → 0x104cc2e へ |
| 0x104cc34 | `test r8d, 0x80` が 0 → 0x104cc65 | 確定 |
| 0x104cc65〜0x104cc6b | `eax = [rbp+0x5b8]`・`[rbp+0x584] = eax` | 戻り値確定 |
| 0x104ccba | `eax = [rbp+0x584]`・`ret` | 戻り値 |

- **戻り値 (この経路)**: `dword [*(0x15e3290)]` (VA 0x15e3290 の qword を指すポインタの先の 32bit 値)。getSwing の `cvtsi2sd` はこの値を使う。
- **0x15e3290 の書込み元は未特定**: PE の `.data` 生データでの初期値は qword `0x0000000001 96ec34` で、実行時に書き換わる前提。書込み元 (初期化経路) の調査は子 issue に移管。よって getSwing の戻り値の数値は、現時点では静的に確定しない。
- `ecx=0x40000001` の意味: 0x1047436 で専用経路 (0x104c4af) に入る値。0x104c4af の経路は 0x104c5a6 等の条件で分岐するが、各ブロックの意味 (何の値を読み何を描画するか) は未確定。`r8d=2` の意味は未確定 (0x104c557 の `test r8d, 2` で 0x104c564 の読みを選ぶ分岐として確認したのみ)。

### 呼出し元 0x10473a5 (ecx ≠ 0x40000001 の経路)

- 呼出し元の `ecx = [rbp+0x5b0]` は `0x40000001` とは限らない。`ecx ≠ 0x40000001` の経路 (0x1047424 の後半・0x104746a〜0x104aa87・0x104c2a6 など) は本 run では未読。残りは子 issue に移管。

### 受入条件の達成状況

- `0x1046a30` の本体の分岐構造: **部分達成**。`ecx=0x40000001`・`r8d=2` の経路は確定 (上表)。他の `ecx`・`r8d` の組は未確定。
- 戻り値の経路別記録: **部分達成**。この経路の戻り値式は確定。値そのものは 0x15e3290 の書込み元に依存して未確定。
- 未解決:

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ecx ≠ 0x40000001` の経路 (0x1047424 後半〜0x104c2a6 など) と `r8d` の残りのビット (0x8a1・0x10000・0x2000・0x4000・0x1000・0x2800・0x200・0x40・0x80・0x100・0x800) の意味 | 呼出し元 160 件の大半の戻り値が決まらない | #1911 (PY-53) |
| 0x15e3290 (戻り値の読み先) の書込み元と初期化 | getSwing の数値が決まらない | #1912 (PY-54) |

## PY-49 (#1828): 0x1046a30 の呼出し元 全件 と 戻り値 (実測)

- 呼出し元: `.text` 全体の E8 rel32 を走査 (`analysis/py49_callers.py`)。**160 件**。全件の一覧 (call 元 VA・ecx/edx/r8d の直前代入式) は `analysis/py49_callers_0x1046a30.tsv`。引数式は呼出し直前 12 命令の直線区間からの推定で、代入が分岐をまたぐ箇所は拾えない (表の `-` 4 件は未特定)。
- 引数の集計: `r8d=2` が 27 件 (getSwing 0xd5dbf0 を含む)。`ecx=0x40000001` が 3 件 (0xd5dc01・0xd5dcb5・0xfde5e7)。呼出し元 0x10473a5 は同関数内の自己呼出し (`ecx=[rbp+0x5b0]`・`edx=0`・`r8d=2`)。
- getSwing (0xd5dbf0) の直前: `mov ecx,0x40000001` (0xd5dbf4)・`xor edx,edx`・`mov r8d,2` → `call 0x1046a30` (0xd5dc01)。戻り値 `eax` は `cvtsi2sd` で使われる。
- **戻り値 (確定)**: 関数末尾の出口 `0x104ccba` は `[rbp+0x584]` を返す (`ret` は 0x104ccca の 1 箇所のみ)。`[rbp+0x584]` は入口で -1 (0x1046d79)、通常経路で `0x104cc6b` の `mov [rbp+0x584],eax` (`eax=[rbp+0x5b8]`) により置き換わる。`[rbp+0x5b8]` は入口で `edx` を受け (0x1046d6b)、途中の分岐で書き換えられる。早期 exit (0x1046d8d・0x10471f9・0x10474b9 の各 `jne`/`jmp`/`jge` → 0x104cc72) は -1 のまま返る。
- **未確定 (子 issue に移管)**: 関数本体の全分岐の意味 (0x1046edf 以降・`ecx` 0x40000001 の経路 0x104c4af の詳細)、`r8d` ビットの意味、`[rbp+0x5b8]` の各書換えの意味。

## PY-64 (#2033): 分岐先 6 件の読む値・書く値・`[rbp+0x5b8]` 式 (実測・逆アセンブル)

親: #1911 (PY-53)。前段: #1982 (PY-60)。既知類型との関係: 該当なし (逆アセンブルの読解のみ)。

## 結論 (部分達成)

- 分岐先 4 件 (0x104caae・0x104c2a6・0x104c64f・0x104c919) は、共通後半 0x104caae の手前の読む値・書く値・`[rbp+0x5b8]` の式を VA つきで確定。
- 残り 2 件 (0x1047497・0x104aa87) は `[rbp+0x5b8]` 書込み箇所 (55 件・15 件) の列挙まで。式は未読 (PY-88 に移管)。
- 検算: jcc/jmp 614 辺の制御フロー照合 (objdump 対 capstone) は mismatch 0。式の別算法照合は未実施。

## 測定

- 素材を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'` で展開 (2.3 秒)。展開先は `work/py64/extracted/block00031_PE.bin`。
- `analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53` → 4,664 命令・`work/py53/fn.txt`。`analysis/py60_objdump_check.py` → 614 辺 一致 614・不一致 0 (exit 0)。
- `analysis/py64_branch_regions.py work/py53/fn.txt` → 到達命令数 (0x1047497 2556・0x104aa87 1284。両者で 141 命令が重なる) と書込み 76 件 (重複込み。0x1047497 55・0x104aa87 15・他 3 件は各 2)。一意な書込みは 71 件 (重なる 5 件は 1 件と数える)。関数全体の直接書込みは 74 件。

## 分岐先ごとの式 (入口 `[rbp+0x5b8]` = edx、0x1046d6b)

- 共通: r8d は `[rbp+0x5c0]`。F = `P.0x3b8 + rint(K · [rbp+0x5b8] · (P.0x3bc − P.0x3b8))`。`rint` は `call 0x40c660` (`cvtsd2si`・最近接偶数)、K = 2^-30 (VA 0x104ccd8)。F は r8d&0x20 のときだけ適用する。
- 0x104c2a6 (ecx=0x40000000): P = `*(*(*(0x15e2eb8))+0x9e0)` (3 段。0x104c2a6 `mov rax,[rip+..]`・0x104c2ad `mov rax,[rax]`・0x104c2b0 `mov rax,[rax+0x9e0]`。初版は 2 段と誤記し、PY-88 節の照合で修正)。(a) F (0x104c311)。(b) r8d&1=0 かつ r8d&2≠0 で `[rbp+0x5b8] = dword[*(0x15e36d8)]` (0x104c3f0)。r8d&1 では `dword[*(0x15e36d8)] = [rbp+0x5b8]` (0x104c335) と `dword[*(0x15e2110)] = [rbp+0x2cc]` (0x104c3ca) を書く。
- 0x104c64f (ecx=0x40000002): P = `*(*(*(0x15e2eb8))+0xb28)` (3 段。0x104c64f・0x104c656・0x104c659 の同じ形)。(a) F (0x104c6ba)。(b) r8d&1=0 かつ r8d&2≠0 で `[rbp+0x5b8] = dword[*(0x15e2c50)]` (0x104c769)。r8d&1 では `dword[*(0x15e2c50)] = [rbp+0x5b8]` (0x104c6ea) と `[*(0x15e2218)]` の各要素の `vtbl[0x128]` 呼出し。
- 0x104c919 (ecx=0x40000005): P = `*(*(*(0x15e2eb8))+0x778)` (3 段。0x104c919・0x104c92d・0x104c930 の同じ形)。(a) F (0x104c984)。(b) r8d&1=0 または `byte[0x15e3500]≠0` で r8d&2≠0 なら `[rbp+0x5b8] = dword[*(0x15e28c8)]` (0x104c9e6)。r8d&1 かつ `byte[0x15e3500]=0` かつ `byte[*(0x15e2900)+0x3c]=0` なら `dword[*(0x15e28c8)] = [rbp+0x5b8]` (0x104c9c0)。
- 0x104caae (ecx の既定値): `[rbp+0x5b8]` は書かない。共通後半で `[rbp+0x5b8]` を読んで `call 0x12df2a0` の引数 (r9d) にする (条件: `[rbp+0x52f]≠0` かつ r8d&0x40)。
- 共通の出口: `[rbp+0x584] = [rbp+0x5b8]` (0x104cc6b)。早期 exit は `[rbp+0x584] = -1` のまま 0x104cc72 へ飛ぶ。

## 未了 (2 件)

| 分岐先 | 入る ecx | 到達命令数 | `[rbp+0x5b8]` 書込み | -1 exit への分岐元 |
|---|---|---|---|---|
| 0x1047497 | [0, 0x10000000) | 2556 (0x104aa87 と 141 命令が重なる) | 55 件 | 0x10474b9・0x104846a・0x104847b・0x10495f6・0x1049621・0x104a7ba・0x104a7d0 |
| 0x104aa87 | [0x70000000, 0xf0000000) (2 区間の和: [0x80000000, 0xf0000000) と [0x70000000, 0x80000000)) | 1284 (0x1047497 と 141 命令が重なる) | 15 件 | 0x104a7ba・0x104a7d0 |

書込み箇所の VA と直前命令は `analysis/py64_branch_regions.py` の出力が正本。各式の読む値・書く値は未読。書込み件数は直接 `mov dword ptr [rbp+0x5b8], reg` の列挙で、一意な書込みは 71 件。
間接書込みは列挙に含まれない: 0x104a924 `lea r8,[rbp+0x5b8]` → `call 0xc61250` の 0xc6129a `mov dword ptr [rdi], eax` (0xc62db0 の戻り値の下位 1 byte が非 0 のとき書く)。この箇所は 0x1047497 と 0x104aa87 の到達範囲に含まれ、確定 4 件の到達範囲には含まれない。

## 受入条件・未解決

- (1) 6 件の読む値・書く値・式の VA つき確定: 部分達成 (4/6)。(2) mismatch 0 の検算: 部分達成 (制御フローのみ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1047497 (55 件) と 0x104aa87 (15 件) の書込み式・読む値・書く値 | ecx ∈ [0, 0x10000000) と [0x70000000, 0xf0000000) 経路の戻り値 | PY-88 (子) |
| 4 件の式の別算法照合 | 式の確定の検算 | PY-88 (子) |

## PY-88 (#2788): 0x1047497・0x104aa87 の `[rbp+0x5b8]` 書込み 65 件の式 (機械スライス・部分達成)

親: #2033 (PY-64)。前段: 上節の PY-64。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。
測定 commit: `7e6c748a` (`analysis/py88_writes.py` の ACC 合流表示・store 検出の修正と `analysis/py64_check_expr.py` を入れたコード commit)。`git diff 7e6c748a HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (後続 commit は REPORT のみ)。

後続 (#3086・PY-159): 65 件の全件表は `REPORT_PY159.md` §3。手計算突合とネガティブコントロールを実施。結果は `REPORT_PY159.md` §4。

### 結論 (部分達成・`Refs #2788`)

- 受入 1 (65 件の式・読む値・書く値の確定): **未達**。機械スライスで 65 件すべての式を出したが、式が一意に決まるものは 0 件。フレーム変数 `[rbp+X]` の store が分岐合流を越える SLOT? が 49 件、`call 0x10469f0` の戻り値が 7 件、`call 0x40c660` (rint) が 6 件、vtbl 呼出しが 3 件 (マークなし・呼出し先未確定)。ACC (= `[rbp+0x5b8]` の書込み前の値) が合流を越える場合は ACC に黙って置換せず `ACC?⚠合流` と明示した (30 件)。
- 受入 2 (PY-64 の式の別算法照合・mismatch 0): **部分達成**。PY-64 の 6 書込みを、式を式木に正規化して突合する `analysis/py64_check_expr.py` で照合した。初版の手計算の P (2 段) は 3 件の不一致として検出され、3 段に直して 6 件一致になった (修正前 不一致 3 件 → 修正後 一致 6 件)。0x104caae の r9d 引数 (`call 0x12df2a0`) は未照合。

### 測定条件

- 素材: `oc_artifacts: fl-win64`。`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/python/work/py64 --wildcards '*block00031_PE.bin'` (2.7 秒)。`work/` は gitignore。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53` → `fn=4664 dispatch=13 r8d_tests=174`。
- 対象 65 件: `analysis/py64_branch_regions.py` と同じ到達範囲 (0x1047497 の 55 件・0x104aa87 の 15 件・重なり 5 件 → 一意 65 件) の `mov dword ptr [rbp + 0x5b8], reg`。
- 式の列挙: `python3 analysis/py88_writes.py work/py53/fn.txt` (stderr に分類件数)。
- 分類 (実測・n=65。先頭の形と、未確定マーク):

| 先頭の形 | 件数 | 未確定マーク (件数) |
|---|---|---|
| 直接式 | 49 | SLOT? 49 (うち ACC?⚠合流 20) |
| `CALL[0x10469f0]` の戻り値 | 7 | ACC?⚠合流 7 (うち SLOT? 3・call で clob 1) |
| rint(xmm0) (`call 0x40c660`) | 6 | SLOT? 3・ACC?⚠合流 3 |
| VCALL (vtbl 呼出しの戻り値) | 3 | なし (呼出し先が未確定) |

- ACC?⚠合流 は計 30 件 (初版で ACC と黙って置いた件数と同じ。直前の線形順 store が分岐先を越える)。
- 旧版 (`7ad3c22b`) との差: 出力 65 行中 32 行が変わった。内訳は ACC の印 30 行 (B4) と、SLOT 参照の @addr が変わった 2 行 (0x1049cf3・0x104a1fb)。SLOT 参照は旧版 133 件中 12 件が `cmp` 命令を store と誤認していた (m1)。新版は 136 件中 0 件 (残る `and` 7 件は実 store で、値は解かず SLOT? のまま)。

### PY-64 の 6 書込み: 手計算の表 と 機械スライスの突合 (negative control 込み)

| 分岐先 (ecx) | 書込み | 手計算の式 (上節 PY-64・P は 3 段) | 機械スライス | 判定 |
|---|---|---|---|---|
| 0x104c2a6 (0x40000000) | 0x104c311 | F: `*(P+0x3b8) + rint(K·ACC·(*(P+0x3bc) − *(P+0x3b8)))`、P = `*(*(*(0x15e2eb8))+0x9e0)`、K = `*(0x104ccd8)` | `M32[M64[M64[M64[G[0x15e2eb8]]] +0x9e0] +0x3b8] + rint(...)` | 一致 |
| 〃 | 0x104c3f0 | `dword[*(0x15e36d8)]` | `M32[M64[G[0x15e36d8]]]` | 一致 |
| 0x104c64f (0x40000002) | 0x104c6ba | F、P = `*(*(*(0x15e2eb8))+0xb28)` | `…+0xb28…` | 一致 |
| 〃 | 0x104c769 | `dword[*(0x15e2c50)]` | `M32[M64[G[0x15e2c50]]]` | 一致 |
| 0x104c919 (0x40000005) | 0x104c984 | F、P = `*(*(*(0x15e2eb8))+0x778)` | `…+0x778…` | 一致 |
| 〃 | 0x104c9e6 | `dword[*(0x15e28c8)]` | `M32[M64[G[0x15e28c8]]]` | 一致 |

- 突合の方法: `analysis/py64_check_expr.py` が、手計算の式 (スクリプト内の HAND。照合表と同じ文字列) と `py88_writes.Slicer` の出力を、同じ文法で式木にして並べ替え (+ と · は可換) してから比較する。機械側の `ACC?⚠合流@...` は ACC と同一視する (値は照合していない。3 件の F 式の ACC は分岐先入口の `[rbp+0x5b8]`)。
- 実測 (コミット `7e6c748a` の code で実行):
  - 正しい式 (P 3 段): `python3 analysis/py64_check_expr.py work/py53/fn.txt` → `n=6 mismatch=0`・exit 0。
  - negative control (1) 初版の P (2 段) を 3 件の F 式に入れる: `--negctl p2` → `mismatch=3`・exit 1。0x104c311・0x104c6ba・0x104c984 が不一致、ほかの 3 件は一致 (初版の PR 本文の「mismatch 0」は、この手計算の誤りのため成立しなかった)。
  - negative control (2) 0x104c311 の P だけ 2 段: `--negctl one` → `mismatch=1`・exit 1。
- K の実値: `pefile` で `block00031_PE.bin` の VA 0x104ccd8 を double として読むと 9.313225746154785e-10 = 2^-30 (変更なし)。

### 限界

- 合流を越える store は解かず SLOT? / ACC?⚠合流 として残す。経路ごとの式は出していない (子 #2874 の範囲)。
- 照合は PY-64 の 6 件のみ。残りの 59 件は式の形の出力であり、照合は未実施。
- ACC?⚠合流 の 30 件は、分岐先入口の `[rbp+0x5b8]` の値に依存する。照合は記号の同一視までで、値は確定していない。
- 0x104a924 の間接書込み (0xc61250 経由) は ACC に反映していない。
- 0x104caae の r9d 引数 (`call 0x12df2a0`) は照合していない。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 65 件のうち SLOT? 49 件・ACC?⚠合流 30 件の経路別の式 (合流の各先行経路ごと) | 受入 1 | #2874 (PY-99) |
| `call 0x10469f0` (7 件) の本体と戻り値・引数の意味 | 受入 1 | #2874 (PY-99) |
| vtbl 呼出し (3 件・`[rax+0x30]`) の呼出し先 | 受入 1 | #2874 (PY-99) |
| 0x104caae の r9d 引数 (`call 0x12df2a0`) の式の照合 | 受入 2 の一部 | #2874 (PY-99)。未追記 (#2874 本文に項目なし) |
| 0x104a924 の間接書込み (0xc61250 経由) を ACC に反映 | ACC の定義 | #2874 (PY-99) |

## PY-99 (#3085・親 #2874): SLOT? 49 件の先行辺ごとの store 集合 (実測)

親: #2874 (PY-99)。前段: 上節 PY-88 (#2788)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。
前提: 同名 path `analysis/py99_slot_paths.py` を open PR #3092 (`2874-py99-slot-paths`) が別実装で追加している。本節の script は本 PR で新規作成した (未解決表の PM 判断待ち)。
測定 commit: `cbe89029` (negctl の S_p 表示と `--md` を入れたコード commit)。main 取り込み後の `3d25011b` で再測定し、stdout と表が一致した。`git diff cbe89029 3d25011b -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 9 ファイル (+344/−3)。py99 の入力 `py88_writes.py`・`py53_dispatch.py` は 0 行。

### 結論 (受入 2 達成・受入 1 の閉包は子 #3104 に移管・`Closes #3085` (範囲縮小))

- 受入 1 (SLOT? 49 件の書込みについて、合流の先行経路ごとの式を VA つきで記録): **S_p (先行辺ごとの store の VA 集合) と式の記録まで実施**。式の閉包は未達 (子 #3104)。閉じた書込みは **0/49**。読み 77 件 (異なり) の全件 (合流 65・先行辺 136) を `analysis/py99_slot_paths.md` に書き出した。
- 受入 2 (閉じた式の検算 mismatch 0・ネガティブコントロールを数値で): 算法 A (前向き固定点) と算法 B (後ろ向き BFS) の 77 件で mismatch **0**。辺 1 本を外すと mismatch **15**・exit **1**。

### 測定条件

- 素材: `fl-win64` の `block00031_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'`・2.8 秒)。`analysis/py53_dispatch.py` → fn=4664 命令 → `work/py53/fn.txt`。
- 対象: py88 の既定 65 件のうち直接式で SLOT? のもの 49 件。読み = py88 の式の `SLOT[rbp+X]?@j` 葉 (読む命令 r と X の組) の異なり 77 件。
- 算法 B (後ろ向き): r から CFG の逆辺を BFS で遡り、`[rbp+X]` への dword/qword store で止める。線形に遡って最初の合流 J と、J の先行辺 p ごとの S_p を出す。CFG は fall-through・jmp・jcc から作る (間接分岐 0 件)。
- 算法 A (前向き): 同じ X の reaching-definitions 固定点 (gen・kill = 同 X の store)。読み r の IN(r) と B を 1 件ずつ比べる。
- store の式: py88 の `Slicer.def_value` (線形)。式に `⚠合流`・`SLOT[` 等が残るものは未閉。

### 件数 (実測・`python3 analysis/py99_slot_paths.py work/py53/fn.txt` の出力)

| 項目 | 件数 |
|---|---|
| 対象の書込み (直接式で SLOT?) | 49 |
| 異なる SLOT? の読み (書込み単位の和も 77) | 77 |
| うち合流 J を持つ読み / 合流なし | 65 / 12 |
| 先行辺の和 (合流 J の先行辺 p の総数) | 136 |
| 入口 (IN) に届く読み | 0 |
| 閉じた (読み,store) 対 / 未閉 | 17 / 77 |
| 閉じた書込み | 0 / 49 |

- 先行辺 p ごとの S_p: |S_p|=1 の辺 閉 16・未閉 119 / |S_p|=2 の辺 閉 0・未閉 1。
- 書込みごとの読み数 (`# 0x...` 行): 読みが 1 件の書込みが 27 件・読みが 2 件の書込みが 16 件・読みが 3 件の書込みが 6 件 (計 49)。

### S_p の全件表 (`analysis/py99_slot_paths.md`・自動生成)

- 生成: `cd tools/python && python3 analysis/py99_slot_paths.py work/py53/fn.txt --md analysis/py99_slot_paths.md` (先頭行に同じコマンドを書く。DOC_MAP §2)。
- 内容: 合流を持つ 65 件の先行辺 136 行 (読み・X・書込み・J・p・S_p・閉否)、合流なし 12 件の到達 store、store の式 32 件 (閉 3)。閉の S_p 行は 16 件 (|S_p|=1 の閉辺と一致)。

### 検算と negative control (実測)

| 実行 | 対象 | mismatch | 終了コード |
|---|---|---|---|
| `analysis/py99_slot_paths.py work/py53/fn.txt` (A と B) | 77 件 | 0 | 0 |
| 同 `--negctl drop-pred` | 77 件 | 15 | 1 |

- negctl の辺: `0x104754a → 0x104755d` (合流 J = 0x104755d)。読み `0x1047b93 [rbp+0x520]` の S_p = {0x1047543} は、この辺以外に寄与しない store (`mov qword ptr [rbp+0x520], rax`) を選んだ。B の結果は {0x1047556} のみになり、A の {0x1047543, 0x1047556} と 15 件 (すべて X = 0x520) で食い違う。
- `--negctl` の出力は、外した辺の S_p を cut 後の値で出し、その行に「B の到達集合からは除外」と付ける。
- 選び方: 読みを VA 順に見て、S_p が他の先行辺の S_q に無い store を含む最初の p。

### 限界

- 閉じた式は、store の式に `⚠合流`・`SLOT[`・`ACC`・`IN[`・`_in`・`clob@`・`VCALL`・`CALL[`・`<`・`…`・`⚠addr-taken` のいずれも含まないもの。式の同値性は見ていない (文字列の規則)。
- 算法 A と B は同じ CFG を使う。検算が見るのは到達計算だけで、CFG 構築の誤りは両方に効く。
- py88 が線形で IN とした読み (線形に先行 store が無い読み) は CFG 上の到達を見ていない (ループの戻り辺で届く store を取りこぼし得る)。
- 解析した X は 21 種。`lea` で取られたもの 0・X と重なる別オフセットの frame store 0 件・frame の非定数オフセット store 0 件 (実測)。ポインタ経由の書込み (callee 内) は見ていない。
- 算法 B の S_p の式は py88 の線形の式なので、store の値に含まれる他の SLOT? 葉は、その葉の読みの経路を別途解いていない。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 閉じた書込み 0/49: 未閉の (読み,store) 77 対。store 値に残る SLOT? 葉 (入れ子の読み) と ⚠合流 の閉包 | 元の受入 1 (閉じた式) | #3104 (PY-162) |
| ACC?⚠合流 (`[rbp+0x5b8]` の合流読み・30 件) を同じ算法で解く | 元の受入 1 の一部 (ACC 側) | #3104 (PY-162) |
| py88 が線形で IN とした読みの CFG 到達 (ループの戻り辺) | 取りこぼしの有無 | #3104 (PY-162・2 項目をコメントで追記) |
| CFG 構築 (A・B 共通) の検証。mismatch 0 は到達計算の一致のみ | 検算の範囲 | #3104 (PY-162・同上) |
| 同名 path `analysis/py99_slot_paths.py` を open PR #3092 (`2874-py99-slot-paths`) も別実装で追加 (両 PR が PY-99 節も追加) | add/add の競合 (同名 path の共存は不可) | PM agent の判断待ち: 同名 path を #3092 と本 PR が別実装で追加している。どちらの script を正とするか。既定案: 先に merge された方を正とし、後の PR が rebase で統合 |

### 再現コマンド

    cd tools/python
    python3 analysis/py99_slot_paths.py work/py53/fn.txt                      # 終了コード 0 (mismatch 0)
    python3 analysis/py99_slot_paths.py work/py53/fn.txt --negctl drop-pred   # 終了コード 1 (mismatch 15)
    python3 analysis/py99_slot_paths.py work/py53/fn.txt --md analysis/py99_slot_paths.md  # 表の再生成

`work/` は作業用ディレクトリ (`py53/fn.txt` を置く場所。PY-88 と同じ入力)。
