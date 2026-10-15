# ildsp PSOLA_CreateInstance 閉包の x64c lift — T-SH-82 (#3428)

親: #3401 (ildsp の子)。本件: #3428 (T-SH-82)。REPORT.md §8 から参照する付録 (測定値の正本)。
検証起点: `a1325f0e4` (origin/main)。測定 commit (コードを変えた最後の commit): `d4d828b18` (`tools/flelift/x64c.py`・`tools/flelift/tests/x64c_vex_diff.py`)。

## 1. 結論と範囲

- PSOLA 閉包 (CreateInstance + vtable slot 先・`--closure 99`) の unsup を **2,472 → 0** にした (ymm 2,396 + その他 76 の全 site)。関数 235・命令 60,095 は不変。
- 命令単位の差分テスト (`tests/x64c_vex_diff.py`) **83/83 PASS**。WaveformColouring の回帰 `lift_wc.sh ok` は **PASS 64/64** のまま。
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

| 命令 (unsup 名) | origin/main | d4d828b18 |
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
- VEX.128 の `vcvtss2sd`・`vcvtsi2sd`・`vsqrtsd`・`vmovhpd`・`vpunpcklqdq`・`vunpckhpd` は既存の `VEX3` 表 (d=s1 複写 → legacy (d,s2)) に載せた。`vpunpcklqdq` は d==s2 で非可換のため専用分岐。
- `div r/m8` は AX/r8 → AL 商・AH 余り。商が 255 超は `ott_unsup` (実機の #DE 相当の未対応扱い。64/32bit の既存分岐と同じ方針)。
- `pushfq` は RFLAGS (bit1 = 1・CF/PF/AF/ZF/SF/DF/OF) を push。

## 5. 差分テスト (`tests/x64c_vex_diff.py`)

- 方式: GNU as で機械語にし、x64c で C に lift して fle_cpu runtime と共に gcc で実行、X/YL/R/フラグ/MBUF を Intel SDM 式の Python 参照値と比較する (既存方式 #3065)。元の機械語を実行して比べる方式ではない (§6 の子で扱う)。
- 追加した harness: memory operand は `MBUF` (32B) を R[reg] に割り当て、`off` で RSP 相当の位置を指定できる。AF/DF は 0 に固定。FAIL 時は `sys.exit(1)` (従来は rc 0 だった)。
- ケース: **83 件** (既存 43 + 追加 40)。追加 40 件の内訳:
  - ymm 20: vaddpd・vsubpd・vmulpd (d=s1 / d=s2 の別名)・vdivpd・vmulpd (mem)・vaddps・vmulps (mem)・vxorpd・vandpd・vorps (mem)・vunpcklpd・vunpckhpd・vshufpd (imm 6 reg / imm 9 mem)・vextractf128 (reg 0/1・mem)・vcvtdq2pd (xmm・mem)
  - VEX.128・非 VEX 20: vsqrtsd・vcvtss2sd・vcvtsi2sd (ecx / rdx)・vpunpcklqdq (2、うち d==s2)・vmovhpd (load / store)・movddup (reg / mem)・lddqu・movntpd・palignr (3)・shlx (rax / edx)・div cl・div byte ptr [rbx]・pushfq
- 結果 (測定 commit `d4d828b18`): **83 PASS / 0 FAIL**、rc 0。
- ネガティブコントロール:
  - vsubpd の参照を `b - a` に壊す (複製テスト・当時 63 件) → `FAIL vsubpd ymm4, ymm4, ymm5`、62 PASS / 1 FAIL。
  - pushfq の参照の CF 項を壊す (`0 | CF`) → `FAIL pushfq`・`SUMMARY pass 82 fail 1`・rc 1 (新 harness)。
  - 複製は削除済み (作業ツリーに残らない)。

## 6. 回帰と実測

- `lift_wc.sh ok` (WaveformColouring、`d4d828b18`): **PASS 64/64**、FAIL 0、traps 0、native 64 (SIGSEGV 0)。閉包の unsup は 3 → 2 (`vcvtss2sd` が解消。残りの `vpmovsxdq`・`vshufps` は本件の範囲外で、従来どおり)。
- 生成 C のコンパイル: PSOLA 閉包の `fle_lifted.c` を `gcc -c -I tools/flelift/rt` で通過 (rc 0)。

| 測定 (`d4d828b18`、4 core、各 3 回) | 結果 |
|---|---|
| `x64c_vex_diff.py` | 0.81 / 0.80 / 0.80 s、rc 0、83 PASS |
| PSOLA lift (final: d4d828b18) | 2.46 / 2.46 / 2.47 s、unsup 0 |
| PSOLA lift (base: origin/main) | 2.44 / 2.47 / 2.53 s、unsup 2,472 |
| `lift_wc.sh ok` | 2.08 s (emcc キャッシュ温): PASS 64/64。初回 (キャッシュ冷) は 15.97 s |

load (1 分平均): 実行前 0.20〜0.34・実行後 0.34〜0.49 (4 core)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 閉包単位の native 差分 (元の機械語の実行と wasm の全バイト比較)。issue 本文の検証方法が参照する `lift_psola.sh` は repo に無く未作成 | 受入の「native と一致」は命令単位 (83 件・Intel 参照値) でのみ示した | 子 issue (T-SH-82 の後続) |
| issue 本文が参照する `tools/shared/lift/ildsp/REPORT_APPENDIX_3401.md` が repo に無い (git 履歴にも無い) | 本文の内訳は §3 の実測で再現した。付録の代替は本ファイル | 本 PR で代替 (追加の起票なし) |
| WaveformColouring 閉包の残り unsup 2 (`vpmovsxdq`・`vshufps`) | WC の lift 規模 (本件の範囲外) | #3216 (T-SH-52) の残り |
