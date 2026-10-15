# REPORT PY-355 (#4696): G11 の 55 件の分類・G2〜G6・G8 の照合は未着手

親: #3101 (PY-161) の受入 1。前段: `tools/python/REPORT_PY161.md` §6・§7、`tools/python/REPORT_PY41_APPENDIX.md` §2 (G1〜G11 の到達集合)。
既知類型との関係: 該当なし (逆アセンブルの読解と解析スクリプトのみ・lift 作業ではない)。KPI: 起動・GUI に関わらないため対象外。

## 1. 結論

- G11 (0x104aa21・0x104aa2e・0x104aa59・0x104aa82 を入口とする 55 件の到達 store) を、式の型で分類した。内訳は直接式 23・rint 型 (F) 18・rint 4・CALL 5・VCALL 3・入口 1・間接書込み 1。件数は 55 で一致。
- G11 の 4 辺の到達集合が同一であることをスクリプトで確認した (不一致なら停止する)。
- **値式の確定は未達**。G11 の各式の SLOT 葉 (`SLOT[...]?@...`・`ACC?⚠合流`) は未閉。型の分類と件数までを確定した。
- **G2〜G6・G8 の py88 式の手計算照合は未着手**。`analysis/py64_check_expr.py` の HAND 表は G7・G9・G10 相当の 6 点しか持たない。G2〜G6・G8 の 10 地点は、ポインタ変数 (`[rbp+0x508]`・`[rbp+0x3f8]`・`[rbp+0x3b0]`・`[rbp+0x398]`) の代入元をたどって手で式を組む必要があり、本 run では終えられなかった。子 issue に分ける (§5)。

## 2. 測定条件

- 測定 commit: `9628f3c3b` (`analysis/py355_g11.py` を入れた commit。コードを変えた最後の commit)。main 取り込み前の HEAD は `fe0c406e9` (origin/main 時点)。
- 素材: `oc_artifacts: fl-win64`。`ls $HOME/artifacts` で `fl-win64.tar.zst` (2.3GB) の実在を確認。`tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'` (2.9 秒)。`work/` は gitignore。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53` → `fn=4664 dispatch=13 r8d_tests=174`。
- 測定時の load average: 0.51 (測定開始時)。
- 分類の所要時間: `py355_g11.py` 0.12 秒 (`time` の real)。

## 3. G11 の 55 件の分類

`python3 analysis/py355_g11.py work/py53/fn.txt work/g11_kinds.tsv` の出力 (測定 commit `9628f3c3b`):

| 型 | 件数 | 到達 store VA |
|---|---|---|
| 入口 (edx) | 1 | 0x1046d6b |
| 直接式 (M32/M8/SLOT) | 23 | 0x1047779 0x10479c7 0x1047c92 0x1047e09 0x1047f9c 0x1048094 0x1048152 0x104821e 0x1048445 0x1048655 0x10488fa 0x1048ae3 0x1048be9 0x1048d2c 0x1049469 0x1049719 0x104985d 0x1049cbe 0x1049cf3 0x1049fb8 0x104a1de 0x104a1fb 0x104a5b0 |
| rint 型 (F) | 18 | 0x1047c18 0x1047f42 0x104802e 0x1048894 0x1048a7d 0x1048b83 0x1048cea 0x1048e36 0x1048ffd 0x1049178 0x10493bf 0x104968b 0x10497e2 0x1049b7f 0x1049cd6 0x1049f24 0x104a13b 0x104a4e2 |
| rint 型 | 4 | 0x10483d3 0x1048ed3 0x104906e 0x10491ed |
| CALL (call 0x10469f0) | 5 | 0x1047719 0x1047969 0x1047d98 0x1049b31 0x104a494 |
| VCALL | 3 | 0x104a8a3 0x104a95f 0x104a9c7 |
| 間接書込み (0xc61250 経由) | 1 | 0x104a92b |
| **計** | **55** | |

- 型の定義: 直接式 = `py88_writes.py` の式が `M32[`・`M8[`・`SLOT[` で始まる。rint 型 (F) = `(M32[...] + rint(...))` の形。rint 型 = `rint(...)` で始まる。
- 値 (SLOT 葉の代入) は未閉。`py88_writes.py` の出力 (`work/g11_py88.txt`・直接 store 54 行) のうち `ACC?⚠合流` を含む行は 23 行 (`grep -c`)。`SLOT[...]?@...` の葉は全行にあるため件数は取っていない。

## 4. 照合の状況 (G2〜G6・G8)

| 群 | 入口辺 | 追加される到達 store | 手計算照合 |
|---|---|---|---|
| G2 | 0x104ad3f・0x104ad50・0x104ae38 | 0x104aba9・0x104ad2e | 未着手 |
| G3 | 0x104b188・0x104b19d・0x104b1f8 | 0x104af7f・0x104b093 | 未着手 |
| G4 | 0x104b668・0x104b67d・0x104b734 | 0x104b305・0x104b5aa | 未着手 |
| G5 | 0x104bbab・0x104bc54・0x104bc84・0x104bcb8・0x104bd1d | 0x104b843・0x104b94e | 0x104b843 のみ確認済み (PY-161 §3・§4)。0x104b94e は未着手 |
| G6 | 0x104c077・0x104c08c・0x104c0ad・0x104c0ce・0x104c159・0x104c1ea・0x104c263 | 0x104bebf・0x104bffa | 未着手 |
| G8 | 0x104c5ab・0x104c64a | 0x104c51a・0x104c56d | 未着手 |

- 各地点の機械側の式 (`py88_writes.py`) は取得済み。例: 0x104aba9 は `(M32[M64[M64[G[0x15e3ac8]]+(shl(SLOT[rbp+0x574]?,2)*8)+8]+0x3b8] + rint(...))`、0x104ad2e は `M8[M64[&M64[G[0x15e06a0]]+(imul(SLOT[rbp+0x578]?)*8)+0x134c+(SLOT[rbp+0x574]?*8)]+0x148]`。
- 手計算の側で必要な情報: 0x104aba9 の `[rbp+0x508]` の代入元 (0x104ab4f: `[rax+rcx*8+8]`・`rax=[G[0x15e3ac8]]`)、0x104ad2e の `[rbp+0x3e0]`・`[rbp+0x578]`。これらの鎖を組み、`py64_check_expr.py` の HAND 表に加えて突合する。
- 1 地点ごとに「asm を読む → 手計算の式を書く → 突合」を行う。10 地点で 1 run の残り時間を超えると判断した。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| G2〜G6・G8 の 10 地点 (0x104aba9・0x104ad2e・0x104af7f・0x104b093・0x104b305・0x104b5aa・0x104bebf・0x104bffa・0x104c51a・0x104c56d) と G5 の 0x104b94e の手計算照合 | r9d の G2〜G6・G8 の式が未確認 | #4703 (PY-359・子) |
| G11 の 55 件の SLOT 葉 (`SLOT[rbp+0x564]`・`SLOT[rbp+0x520]`・`[rbp+0x4e8]` の代入元 など) と `ACC?⚠合流` | G11 の値式が未確定 | #3101 (受入 1 の残り) |
| `OUT(0xc61250)` の値・0x7a0c20 の vtbl (PY-161 §7) | 0x104a945・0x104cc65 | #3101 (既存) |

## 6. 再現

```
cd tools/python
mkdir -p work/py64 work/py53
tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'
python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53
python3 analysis/py355_g11.py work/py53/fn.txt work/g11_kinds.tsv    # 件数 55・exit 0
```
