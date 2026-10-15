# REPORT PY-161 (#3101): py88 の movabs 対応・0x104b843 の表引きの整数検算・0x104a945 の r8d

親: #2788 (PY-88 の 65 件の式・PY-64 の照合)。前段: PY-160 (#3087・PR #3102 merge 済み) の `REPORT_PY41_APPENDIX.md` PY-160 節 §5・§6。
既知類型との関係: 該当なし (逆アセンブルの読解と解析スクリプトのみ・lift 作業ではない)。KPI: 起動・GUI に関わらないため対象外。

## 1. 結論

- 受入 4 (py88 の movabs 対応と 65 件の式表の変化件数): **完了**。`movabs` を定数の定義として扱うよう `analysis/py88_writes.py` を直した。65 件のうち変化は **1 件** (0x104b843 の call 0x10469f0 の引数 edx・r8d)。他 64 件は文字列が一致し、分類の件数も変わらない。
- 受入 6 (0x104a945 以降の r8d の使い道と値の式): **使い道を確定、値は 3 値の集合として確定**。`mov r8d` の値は VCALL B (0x104a95c) の第 3 引数で、到達集合は {入口 d, VCALL A の戻り値, IND@0x104a92b}。`OUT(0xc61250)` の中身は未確定 (§5)。
- 検算: 0x104b843 の表引き (movabs 2 件を含む 6 命令) を、py88 の式とは独立に整数演算 (mod 2^64) で実行し、4 つの入力 k で期待値 (`0x1539eb4 + 8k`・`0x1539eb8 + 8k`) と一致 (mismatch 0)。py88 の式にも同じ 3 つの要素が現れる。
- 未着手 (#3101 に残す): 受入 1 (G11 55 件・G2〜G6・G8 の照合)・受入 2 (0x7a0c20 の vtbl 解決)・受入 3 (0x104a48f の T ポインタ)・受入 5 (0x104cc65 の戻り値式)。

## 2. 測定条件

- 測定 commit: `91f9b90f3` (`analysis/py88_writes.py` の 1 行と `analysis/py161_movabs_check.py` を入れた commit)。
- 素材: `oc_artifacts: fl-win64`。`ls $ARTIFACTS_DIR` で `fl-win64.tar.zst` の実在を確認。`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/python/work/py64 --wildcards '*block00031_PE.bin'` (2.1 秒)。`work/` は gitignore。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53` → `fn=4664 dispatch=13 r8d_tests=174` (0.08 秒)。
- 測定時の load average: 0.08〜0.23 (測定開始時)。

## 3. 65 件の式表: 修正前後の差分

- 手順: 修正前の出力を `work/py88_before.txt` に、修正後を `work/py88_after.txt` に保存して `diff`。対象は `py88_writes.py` の既定 65 件 (`py64_branch_regions.py` と同じ region)。
- 件数: 65 行 → 65 行。分類 (stderr の件数表) は修正前後で同一 (直接式 49・CALL 7・rint 6・VCALL 3)。
- 変化した 1 件 (0x104b843):

```
前: edx=M32[&SLOT[rbp+0x5c0]?@0x104a8a9 +&G[0x1549cb4] +(SLOT[rbp+0x570]?@0x104aa97*8)]
    r8d=M32[&&SLOT[rbp+0x5c0]?@0x104a8a9 +&G[0x1549cb4] +&G[0x1549cb4] +(SLOT[rbp+0x570]?@0x104aa97*8)]
後: edx=M32[&0xfffffffc7fff0200 +&G[0x1549cb4] +(SLOT[rbp+0x570]?@0x104aa97*8)]
    r8d=M32[&0xfffffffc7fff0204 +&G[0x1549cb4] +(SLOT[rbp+0x570]?@0x104aa97*8)]
```

- 前の式は `movabs rax` を無視し、rax を 1 つ前の `rax` の定義 (0x104a8a3 の戻り値) まで遡っていた。後の式は即値を直接使う。PY-160 §5 の「movabs を含む件数は未計測」はこれで 1 件と確定。
- 残る未確定: `SLOT[rbp+0x570]?@0x104aa97` (j = (ecx_in & 0xffff) + 0x70000000 の入力依存)。受入 1 の残り。

## 4. 検算 (`analysis/py161_movabs_check.py`・別算法)

- 方法: `fn.txt` の 6 命令 (0x104b7ff〜0x104b83a) だけを読み、整数演算 (mod 2^64) で `movabs`・`lea` (rip 相対: 次命令 + disp・レジスタ同士: 和)・`movsxd` (j)・`mov` (base + index×8) を順に実行して、表の要素のアドレスを求める。py88 の式は使わない。
- 期待値: edx 側 `0x1539eb4 + 8k`、r8d 側 `0x1539eb8 + 8k` (PY-160 §3 の式)。
- 結果 (測定 commit `91f9b90f3`):

| k | edx 側 (got = want) | r8d 側 (got = want) |
|---|---|---|
| 0x0000 | 0x1539eb4 | 0x1539eb8 |
| 0x0001 | 0x1539ebc | 0x1539ec0 |
| 0x1234 | 0x1543054 | 0x1543058 |
| 0xffff | 0x15b9eac | 0x15b9eb0 |

  全 8 件 ok。py88 の式 (0x104b843 の edx・r8d) に `0xfffffffc7fff0200`・`0xfffffffc7fff0204`・`G[0x1549cb4]`・`SLOT[rbp+0x570]?@0x104aa97*8` が現れることも確認 (橋渡し ok)。`mismatch=0`・exit 0・所要 0.03 秒。
- ネガティブコントロール (`--negctl`): 1 つ目の movabs の即値を +8 にずらすと、edx 側の 4 件だけが MISMATCH (r8d 側は ok)。`mismatch=4`・exit 1。検算が edx 側の即値の誤りを検出できることの確認。
- 注: 0x1539eb4 は 0xfffffffc7fff0200 + G[0x1549cb4] + 8j (j = k + 0x70000000、8j = 8k + 0x380000000) の mod 2^64 の値。8j の 0x380000000 が桁あふれで消える点が、式の 0x1539eb4 + 8k への還元の要点。

## 5. 0x104a945 の r8d (受入 6)

- 命令列 (fn.txt): `0x104a938 mov rcx,[rbp+0x410]`・`0x104a93f mov edx,[rbp+0x570]`・`0x104a945 mov r8d,[rbp+0x5b8]`・`0x104a94c mov r9d,2`・`0x104a959 mov rax,[rax]`・`0x104a95c call [rax+0x30]`。ecx = O2 (this)、edx = E (j)、r8d = 読み値、r9d = 2 の VCALL B の引数。
- 到達集合 (`python3 analysis/py160_reach.py work/py53/fn.txt reach 0x5b8 0x104a945`): `{0x1046d6b, 0x104a8a3, IND@0x104a92b(0xc61250 経由)}`。
  - 0x1046d6b: 入口の store (edx 受け = d)。
  - 0x104a8a3: VCALL A (0x104a8a0) の戻り値の store。
  - IND@0x104a92b: 間接書込み (0xc61250 → 0xc6129a)。PY-160 §1 のとおり、`sil` が非 0 のときだけ書く。
- PY-163 (#3135) §3 の B の r8d 式 `{d, A, OUT(0xc61250)}` と一致 (3 値)。
- **未確定の部分**: `OUT(0xc61250)` の値は、0xc62db0 が `[r8]` (= 0xc61250 の `[rbp+0x28]`) に書く qword の上位 dword。0xc62db0 の書く値は未読で、PY-160 §5 のとおり式の形だけ。これは受入 5 (0x104cc65 の戻り値) と同じ未読部分。

## 6. 受入条件 (#3101) の対応

| 受入 | 判定 |
|---|---|
| 1 G11 (55 件) の値式・G2〜G6・G8 の py88 式の照合 | 未着手。G2〜G6・G8 の式は SLOT? の葉を含み、閉包は PR #3858 (#3104・open) の対象。依存が未 merge のため着手しない |
| 2 0x7a0c20 の vtbl[+0x28]・vtbl[+0x18]・0x729d20・[this+0x548] の解決 | 未着手 (実行時データ。PE 静的解析の範囲外の可能性が高い) |
| 3 0x104a48f の T ポインタ (`*(0x15e44c8)`)・[rbp+0x564] | 未着手 (`0x15e44c8` の値は実行時に決まる) |
| 4 py88 の movabs 対応と 65 件の変化件数 | **完了** (§3・1 件) |
| 5 0x104cc65 の戻り値式 (間接書込み込み) | 未着手。到達集合に IND が入ることは `py160_reach` で確認済み (`reach 0x5b8 0x104cc65`) |
| 6 0x104a945 以降の r8d の使い道と値 | **完了** (§5・値は 3 値の集合・OUT は未確定) |

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1・2・3・5 (上表) | 65 件の式確定・r9d・r8d・戻り値式 | #3101 (open・既存) |
| `OUT(0xc61250)` の値 (0xc62db0 の書く qword) | 0x104a945 の r8d・VCALL B の引数・0x104cc65 の戻り値 | #3101 (受入 5 と同じ) |
| `SLOT[rbp+0x570]?@0x104aa97` (j の入力依存) | 0x104b843 の edx・r8d の添字 | #3101 (受入 1 の残り) |
| `rint` (call 0x40c660) 6 件の担当 | #2788 受入 1 の 6 件。どの子の本文にも明示がない。SLOT?・ACC? の葉を含むなら PR #3858 (#3104) の閉包の対象の可能性があるが未確認 | PM 判断 (担当未定) |

## 8. 再現

```
cd tools/python
mkdir -p work/py64 work/py53
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'
python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53
python3 analysis/py88_writes.py work/py53/fn.txt > work/py88_after.txt   # 65 件の式表 (stderr は分類件数)
python3 analysis/py161_movabs_check.py work/py53/fn.txt                  # mismatch=0・exit 0
python3 analysis/py161_movabs_check.py work/py53/fn.txt --negctl         # mismatch=4・exit 1
python3 analysis/py160_reach.py work/py53/fn.txt reach 0x5b8 0x104a945 0x104cc65
```
