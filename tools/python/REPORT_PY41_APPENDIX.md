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

## PY-99 (#2874): 後ろ向き CFG 経路列挙で `[rbp+X]` の読みの到達 store を出す (受入 1・3 は #3085・#3086 へ移管。範囲縮小後の `Closes #2874`)

親: #2788 (PY-88)。前段: 上節 PY-88 (線形の後ろ向きスライス) と PY-64 (式照合)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。

### 結論

- 経路列挙を実装し、印つきの `[rbp+X]` 読み 116 件 (SLOT? 86・ACC?⚠ 30) すべてに適用した (`analysis/py99_slot_paths.py`)。到達 store を分岐先つきで出した。入口 (IN) まで届く読みは 0 件。
- 値の確定は未達。格納値が閉じた式になった読みは 0 件で、残りは別の読みへの依存 (63 件) か入口レジスタ (32 件)。
- 突合: 線形で一意な読み (印なし) 55 件は、到達 store が線形の直前 store 1 件で式も一致 (mismatch 0)。前向きの検算 (store から前向きに届く読みを列挙) も 171 件すべてで後ろ向きと一致 (mismatch 0)。
- py88 の合流印は保守的だった。ACC (`[rbp+0x5b8]`) の 30 件は、経路上では全件 0x1046d6b (入口 edx) の 1 store にだけ届く。SLOT? 86 件のうち 85 件は線形 store が到達集合に入り、1 件 (0x104b7ec) は入らない (下記)。
- issue の「79 読み」は書込み単位の件数 (直接式 SLOT? 49 と ACC?⚠ 30 の和。うち 20 件は両方に入る) で、読み単位ではない。読み単位 (読み位置 × スロット、重複除去) は T 116 件 + U 55 件 = 171 件。

### 測定条件

- 測定 commit: `69530065` (`analysis/py99_slot_paths.py` の最後のコード commit。`--lea-write` の追加を含む)。`41a6d7af` で測った 171 読みの結果は、`69530065` で再測定して一致した。前段の測定 commit は `7e6c748a` (py88_writes.py・py64_check_expr.py の最後の変更)。`git diff 7e6c748a HEAD -- tools/python/analysis/py88_writes.py tools/python/analysis/py64_check_expr.py tools/python/analysis/py53_dispatch.py tools/python/analysis/py64_branch_regions.py tools/python/analysis/py60_objdump_check.py` の出力は 0 行。`git diff 69530065 HEAD -- tools/python/analysis/py99_slot_paths.py tools/python/analysis/py88_writes.py tools/python/analysis/py53_dispatch.py tools/python/analysis/py60_objdump_check.py` の出力は 0 行 (main 取り込み後の `analysis/` の差分は他 PR の新規ファイルで、本節の測定は読まない)。
- 素材: `oc_artifacts: fl-win64`。`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'` は 1.58 秒 (展開前後で一致)。
- 逆アセンブル: 既存の `work/py53/fn.txt` (fn=4664)。
- 実行: `python3 analysis/py99_slot_paths.py work/py53/fn.txt --lea-write > work/py99/paths.txt 2> work/py99/summary.txt` (exit 0・`time` の real 0.53 秒)。load average (1 分値): 0.21 (22:08:55)。
- CFG: 関数内の jcc/jmp の辺 614・間接 jmp 0 件。`python3 analysis/py60_objdump_check.py work/py64/extracted/block00031_PE.bin work/py53/fn.txt` は objdump 614 辺・agree 614・disagree 0 (exit 0)。

### 結果 (読み 171 件。65 書込みの式の評価に現れた `[rbp+X]` の読みを (読み位置, X) で重複除去)

| 区分 | 件数 | 内訳・注 |
|---|---|---|
| T: py88 が印つき (SLOT? / ACC?⚠) | 116 | SLOT? 86・ACC?⚠ 30 (30 件はすべて `[rbp+0x5b8]`) |
| T・到達 store 1 件・格納値が閉じている | 0 | |
| T・到達 store 1 件・値は入口レジスタ | 32 | ACC 30 件 (0x1046d6b の edx) と他 2 件 |
| T・到達 store 1 件・値に別の読みが残る | 63 | 格納値に SLOT[...] 等が残る (限界の行を参照) |
| T・到達 store 1 件・非 mov (kill) | 3 | `and`/`add` 等で同アドレスを書く。値は `OP:<命令>` |
| T・分岐 (到達 store 複数) | 18 | 2 件が 17・3 件が 1。各 store に届いた分岐先 VA を出力 |
| T・入口 (IN) まで届く | 0 | |
| T・到達 store 0 件 | 0 | |
| T・addr-taken (lea で取られた X) | 30 | X = 0x5b8 のみ (`lea r8, [rbp + 0x5b8]` @0x104a924) |
| U: py88 の線形結果が一意 (印なし) | 55 | 突合で match 55・mismatch 0 |

### 突合 (独立算法の検算)

- 線形で一意な U 55 件: 経路列挙の到達 store が py88 の線形 store 1 件に一致し、式も一致。**一致 55・不一致 0**。
- 前向きの検算 (各 store から前向きに届く読みを列挙し、後ろ向きの結果と比べる): 171 件。**不一致 0**。
- SLOT? 86 件の線形 store (@VA) は、到達集合に 85 件で入る。例外は 0x104b7ec (`[rbp+0x5c0]`)。線形 store は 0x104a8a9 の `and dword ptr [rbp+0x5c0], 0xffffffdf` (非 mov) だが、経路はこれを通らず 0x1046d71 (`mov [rbp+0x5c0], r8d`・入口 r8) に届く。
- ACC?⚠ 30 件は、経路上では全件 0x1046d6b の 1 store のみ。線形の合流印が付いても、到達 store は一意なことがある。

### ネガティブコントロール

- (a) 分岐辺を全部落とした CFG (`--negctl fallthrough`): 171 読みのうち **115 件** で到達 store 集合・IN・到達不能が変わった (T では 114 件が到達 store 0 件)。検出力あり。exit 0 (診断モード)。
- (b) U の先頭 1 件の期待式を書き換える (`--negctl expect`): 突合は match 54・**mismatch 1**。exit 1 (期待どおり)。

### 限界

- 格納値が別の読み (SLOT[...] 等) に依存する 63 件と、入口レジスタに帰着する 32 件は値を閉じていない。経路列挙は store までで、格納レジスタの値の合流は越えていない。
- `[rbp+0x5b8]` (ACC) は lea で取られている。間接書込み (0xc61250 経由) は lea を may-write とみなして検査した (`--lea-write`): lea から直接 store を経ずに届く ACC 読みは 0 件 (lea から届く節点 155 件)。よって ACC 30 件の結論は変わらない。ただし書込み幅は 0x5b8 の 1 スロットと仮定しており、0xc61250 本体は未読。
- 対象は py88 と同じく dword/qword の `[rbp+X]` 書込みのみ (byte/word の部分書込みは見ない)。call は `[rbp+X]` を書かないと仮定 (addr-taken の X を除く)。
- 0x104caae の r9d 引数 (`call 0x12df2a0`) は対象外。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 格納値が別の読みに依存する 63 件 (T) の閉じた式 | 受入 1 の残り | #3085 (PY-158) |
| 入口レジスタに帰着する 32 件 (ACC 30 件を含む) の引数の意味・全件の式表 | 受入 3 | #3086 (PY-159) |
| 0xc61250 本体の書込み幅 (0x5b8 の 1 スロット超への書込み)。lea 経由で届く ACC 読みは 0 件と検査済み | 0x5b8 以外のスロットの読みの到達 | #3087 (PY-160) |
| 0x104caae の r9d 引数 (`call 0x12df2a0`) | 受入 2 の一部 | #3087 (PY-160) |
| 0x104b7ec の SLOT? 印の線形 store が真の到達 store でない例 (1 件) | py88 の印の解釈 | #3085 (PY-158) |

call 0x10469f0 の本体式と 7 件の戻り値式は `REPORT_PY99_APPENDIX.md` に記録 (受入 2 の完了分)。
