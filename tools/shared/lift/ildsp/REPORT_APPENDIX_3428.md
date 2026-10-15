# ildsp PSOLA_CreateInstance 閉包の x64c lift — T-SH-82 (#3428)

親: #3401 (ildsp の子)。本件: #3428 (T-SH-82)。REPORT.md §8 から参照する付録 (測定値の正本)。
既知類型との関係: `docs/DEFECTS.md` の D6 (merge 型命令の dest 上位 lane。VEX.128 のスカラ命令は d=s1 を複写してから legacy 命令で merge し、テストの `xz`・`xl` で上位 lane を検証) と D12 (比較をレジスタ状態全体に広げ、callee-saved 破損を見えるようにした) に関連し、いずれも回避済み。新規の類型は見つからず (D1a〜D25 のうち他は RetDec の IR 段の類型で、x64c は IR を経由しない)。
検証起点: `730320c46` (origin/main。a1325f0e4 から rebase して再測定)。測定 commit (コードを変えた最後の commit): `e49bf7c9d` (`tools/flelift/x64c.py`・`tools/flelift/tests/x64c_vex_diff.py`。前回の測定 commit は `b2b898522`)。

## 1. 結論と範囲

- PSOLA 閉包 (CreateInstance + vtable slot 先・`--closure 99`) の unsup を **2,472 → 0** にした (ymm 2,396 + その他 76 の全 site)。関数 235・命令 60,095 は不変。
- 命令単位の差分テスト (`tests/x64c_vex_diff.py`) **88/88 PASS** (e49bf7c9d)。WaveformColouring の回帰 `lift_wc.sh ok` は前回 (b2b898522) **PASS 64/64**。最終 HEAD での再実行は本 run では未実施 (§6)。
- 範囲外: 閉包単位の native 差分 (元の機械語の実行と wasm の比較)。`lift_psola.sh` は repo に無く未作成。子 issue へ分離 (§6)。

## 2. 再現

root は issue 本文に無かったため、`lift_wc.sh` と同じ規則 (CreateInstance + vtable slot 先) で作った。`tools/shared/work/psola/entries.json` (gitignore):

```
{"roots": [CreateInstance 0x1ab540, slot 0 0x1ab590, slot 1 0x1ab680, slot 2 0x1ab690, slot 3 0x1ab6a0, slot 4 0x1ab6b0, slot 5 0x1ab800] + 0x180000000, "calltgt": []}
```

vtable は RVA `0x3e0030` (6 slot、slot 6 は `.text` 外)。entries の値は `pefile` で PE から読んだ値。

```
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/flelift/x64c.py --pe <展開先>/extracted/block24360_PE.bin --entries tools/shared/work/psola/entries.json --out <dir> --closure 99 --img 0x180000000 --shift 0x150000000 --img-size 0x447000 --impbase 0x1D80000
python3 tools/flelift/tests/x64c_vex_diff.py
FL_WIN64_DIR=<展開先> EMSDK_ENV=<emsdk_env.sh> bash tools/shared/lift/ildsp/lift_wc.sh ok
```

origin/main の x64c で同じ root を lift すると unsup 2,472 (issue 本文の内訳と一致)。

## 3. unsup の before → after (閉包 99 の site 数)

| 命令 (unsup 名) | origin/main | e49bf7c9d |
|---|---:|---:|
| ymm `vmulpd` | 639 | 0 |
| ymm `vaddpd` | 633 | 0 |
| ymm `vsubpd` | 633 | 0 |
| ymm `vextractf128` | 396 | 0 |
| ymm `vunpcklpd` | 31 | 0 |
| ymm `vunpckhpd` | 31 | 0 |
| ymm `vshufpd` | 14 | 0 |
| ymm `vcvtdq2pd` (xmm 入力) | 10 | 0 |
| ymm `vxorpd` | 6 | 0 |
| ymm `vxorps` | 3 | 0 |
| `vcvtsi2sd` | 14 | 0 |
| `palignr` | 12 | 0 |
| `vmovhpd` | 11 | 0 |
| `movddup` | 7 | 0 |
| `div` (8bit 形 `div r/m8`) | 6 | 0 |
| `vunpckhpd` (xmm) | 5 | 0 |
| `shlx` | 4 | 0 |
| `vpunpcklqdq` | 4 | 0 |
| `pushfq` | 4 | 0 |
| `lddqu` | 4 | 0 |
| `vsqrtsd` | 3 | 0 |
| `vcvtss2sd` | 1 | 0 |
| `movntpd` | 1 | 0 |
| **合計** | **2,472** | **0** |

## 4. 実装の要点

- ymm の packed 算術は `ylanes`: 下位 `X[i]` と上位 `YL[i]` を 2 lane の一時配列 (A_/B_/R_) に読み、全部読んでから書く。`d` が `s1`/`s2` と同じでも安全。mem 源は `LDYSPLIT` (m256)。
- `vextractf128` は reg 形 (上位 YL を 0) と mem 形 (`STX` 16B)。
- VEX.128 の `vcvtss2sd`・`vcvtsi2sd`・`vsqrtsd`・`vmovhpd`・`vunpckhpd` は既存の `VEX3` 表 (d=s1 複写 → legacy (d,s2)) に載せた。`vpunpcklqdq` は表に載せず専用分岐のみ (d==s2 で非可換のため。表に載せると専用分岐が先に処理し、表のエントリは到達しない)。
- `div r/m8` は AX/r8 → AL 商・AH 余り。商が 255 超は `ott_unsup` (実機の #DE 相当の未対応扱い。64/32bit の既存分岐と同じ方針)。
- `pushfq` は RFLAGS を push する。bit1 = 1 と IF (bit9) = 1 は定数で、CF/PF/AF/ZF/SF/DF/OF は状態から作る。IF = 1 はユーザモードの native の実測 (このランナーで `pushfq; pop` が `0x202`・`0x206`)。閉包の 4 site は DF だけを判定し、各 site の直接 call 元は call 直後に rax を上書きするため、閉包の出力には影響しない (review 指摘 3)。

## 5. 差分テスト (`tests/x64c_vex_diff.py`)

- 方式: GNU as で機械語にし、x64c で C に lift して fle_cpu runtime と共に gcc で実行、X/YL/R/フラグ/MBUF を Intel SDM 式の Python 参照値と比較する (既存方式 #3065)。元の機械語を実行して比べる方式ではない (§6 の子で扱う)。
- 追加した harness: memory operand は `MBUF` (32B) を R[reg] に割り当て、`off` で RSP 相当の位置を指定できる。AF/DF は 0 に固定。FAIL 時は `sys.exit(1)` (従来は rc 0 だった)。
- ケース: **88 件** (既存 43 + 追加 45)。追加 45 件の内訳:
  - ymm 25: vaddpd・vsubpd・vmulpd (d=s1 / d=s2 の別名)・vdivpd・vmulpd (mem)・vaddps・vsubps・vdivps (ps・review 指摘 6 で追加)・vmulps (mem)・vxorpd・vxorps (review 指摘 6)・vandpd・vandps (review 指摘 6)・vorps (mem)・vorpd (mem・review 指摘 6)・vunpcklpd・vunpckhpd・vshufpd (imm 6 reg / imm 9 mem)・vextractf128 (reg 0/1・mem)・vcvtdq2pd (xmm・mem)
  - VEX.128・非 VEX 20: vsqrtsd・vcvtss2sd・vcvtsi2sd (ecx / rdx)・vpunpcklqdq (2、うち d==s2)・vmovhpd (load / store)・movddup (reg / mem)・lddqu・movntpd・palignr (3)・shlx (rax / edx)・div cl・div byte ptr [rbx]・pushfq (CF=1 に固定して負例を決定的にした)
- 結果 (測定 commit `e49bf7c9d`): **88 PASS / 0 FAIL**、rc 0 (3 回とも)。
- ネガティブコントロール:
  - vsubpd の参照を `b - a` に壊す (b2b898522 時点の複製テスト・当時 63 件) → `FAIL vsubpd ymm4, ymm4, ymm5`、62 PASS / 1 FAIL。
  - pushfq の参照式 `2 | (1 << 9) | f['CF'] | …` の `f['CF']` だけを `0` に置換 (CF=1 固定の case で判定) → `FAIL pushfq`・`MEM exp …0xa42 got …0xa43`・`SUMMARY pass 87 fail 1`・rc 1 (e49bf7c9d、一時複製 `tests/_neg_pushfq_cf.py` で実測し削除済み)。
  - 複製は削除済み (作業ツリーに残らない)。

## 6. 回帰と実測

- `lift_wc.sh ok` (WaveformColouring): 前回 (`b2b898522`) は **PASS 64/64**、FAIL 0、traps 0、native 64 (SIGSEGV 0)。閉包の unsup は 3 → 2 (`vcvtss2sd` が解消。残りの `vpmovsxdq`・`vshufps` は本件の範囲外)。
  - **最終 HEAD (`e49bf7c9d`) では本 run で未実行**。`toolchain-emsdk` が素材に無く (取得済みの素材は `fl-win64` の 1 本のみ)、emcc が無いため。本 PR 本文の `oc_artifacts: fl-win64 toolchain-emsdk` で次の検収 run が再実行する前提 (review 指摘 2)。`e49bf7c9d` の変更 (pushfq の IF 定数・vpunpcklqdq の表除去) が WC 閉包の出力に当たるかは、その再実行で判定する。
- 生成 C のコンパイル: PSOLA 閉包の `fle_lifted.c` を `gcc -c -I tools/flelift/rt` で通過 (rc 0・`e49bf7c9d`)。

| 測定 (`e49bf7c9d`、4 core、各 3 回) | 結果 |
|---|---|
| `x64c_vex_diff.py` | 0.93 / 0.93 / 0.91 s、rc 0、88 PASS |
| PSOLA lift (final: e49bf7c9d) | 2.52 / 2.52 / 2.54 s、functions 235・insns 60,095・unsup 0・traps 0 |
| PSOLA lift (base: origin/main、b2b898522 時点の測定) | 2.38 / 2.40 / 2.41 s、unsup 2,472 (base 側のコードは本 round で変えていない) |
| `lift_wc.sh ok` | 本 run では未実行 (上記) |

load (1 分平均): 測定前 0.04・測定後 0.19〜0.21 (4 core)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 閉包単位の native 差分 (元の機械語の実行と wasm の全バイト比較)。issue 本文の検証方法が参照する `lift_psola.sh` は repo に無く未作成 | 受入の「native と一致」は命令単位 (88 件・Intel 参照値) でのみ示した | 子 issue (T-SH-82 の後続) |
| issue 本文が参照する `tools/shared/lift/ildsp/REPORT_APPENDIX_3401.md` が repo に無い (git 履歴にも無い) | 本文の内訳は §3 の実測で再現した。付録の代替は本ファイル | 本 PR で代替 (追加の起票なし) |
| WaveformColouring 閉包の残り unsup 2 (`vpmovsxdq`・`vshufps`) | WC の lift 規模 (本件の範囲外) | #3216 (T-SH-52) の残り |
