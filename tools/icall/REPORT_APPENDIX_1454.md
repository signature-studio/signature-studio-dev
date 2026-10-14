# icall REPORT 付録: Fresh Air 残落ち 6 件の RetDec 段の切り分け (ICALL-29 / #1454)

> 親: #1298 (ICALL-24)。前段は `REPORT_APPENDIX_1298.md`、分類は `REPORT_APPENDIX_1067.md` §13。
> 測定 commit: `3f582a52` (origin/main 取得時点。本 run はコードを変えていない)。本付録以外の `tools/icall/` 差分は 0。

## 0. 結論 (本 run の到達点)

- 受入条件は未達 (`lost 6` のまま。修復はしていない)。
- 確定したこと: `lock` 接頭辞と `xadd` を nop / mov に置換しても生成 IR の diff は空だった (§2)。確定と言えるのはこの IR diff が空だったことだけ。
- 未確定: 欠落が起きる段と条件。§3 の `--backend-no-opts` でも `0x180c97aa0` の `br i1 undef` 12 件は残ったが、表の間接 call 列 (0 のまま) は本計測では間接 call を検出できない (§4) ため、欠落の有無の根拠にならない。よって「backend optimizer の内部では起きない」とは言えず、未確定とする。pass 単位の計測も検証が不十分で、結論に使わない。
- 本 run では再計測していない (素材 `plugins-freshair`・`work-icall` と RetDec が runner に存在しないため)。§1〜§3 の数値は記録時点の実測。

## 1. 再現 (実測)

`python3 tools/icall/diff/fa_residual.py tools/icall/work/rt_freshair-core` (素材 `work-icall` の `rt_freshair-core` のみ展開):

```
non-IAT call sites 91 / lost 6 (audit call_lost_non_iat=6)
by IR status: {'other_insn:br': 1, 'dropped': 5}
va=0x180c97e17 fn=0x180c97aa0 call qword ptr [rax + 0x10]  ir=other_insn:br
va=0x180c97e38 fn=0x180c97aa0 call qword ptr [rax + 0x20]  ir=dropped
va=0x180c97e56 fn=0x180c97aa0 call qword ptr [rax + 8]     ir=dropped
va=0x180c97e71 fn=0x180c97aa0 call qword ptr [rax + 0x20]  ir=dropped
va=0x180da7261 fn=0x180da6e60 call qword ptr [rax + 0x30]  ir=dropped
va=0x180da72fc fn=0x180da6e60 call qword ptr [rax + 0x30]  ir=dropped
```

全体 dump は `before.0.drc.ll` で、`0x180c97aa0` は `br i1 undef` が 12 件。この 12 件は、§2 の表の「原 PE」行 (`--select-ranges 0x180c97aa0-0x180c97ee0 --select-decode-only`、最適化オプションなし) と、§3 の `--backend-no-opts` 付きの単独関数実行の両方で数えた値。全体 dump の 12 件と単独関数実行の 12 件が同じ条件かは未確認。`*(var12) = -1` 警告は 5 件出るが、関数名がログに無く、対応は未確認。

## 2. 切り分け 1: `lock xadd` は原因ではない (実測)

素材 `plugins-freshair` の `SlateCore.core_64` (36,285,952 B、一時展開先は作業用ディレクトリ。サイズは issue 記載と一致) を用い、`RetDec` を `--select-ranges 0x180c97aa0-0x180c97ee0 --select-decode-only` で単独関数に実行した。

| 入力 | call (間接) | `br i1 undef` |
|---|--:|--:|
| 原 PE | 0 | 12 |
| `lock` 接頭辞 (`f0`) を `nop` に置換 | 0 | 12 |
| `lock xadd` を `mov` + `nop` に置換 | 0 | 12 |

`lock` 接頭辞の有無で生成 IR の diff は空。よって `lock` と `xadd` は欠落の条件ではない。

## 3. 切り分け 2: 後段の最適化を止めても消える (実測)

`--backend-no-opts` を付けて単独関数を実行すると、`0x180c97aa0` は間接 call 0・`br i1 undef` 12 のまま。`0x180da6e60` は間接 call 0 だが、`undef` は 0 件で、同関数の `%243`・`%cond` の比較は残る。

ただし本計測は間接 call を検出できない (§4) ので、間接 call 0 と 0 の比較は欠落の有無の根拠にならない。`undef` 件数だけでは欠落段を決められない。よって「欠落は backend optimizer の内部ではない」は未確定。段の切り分けは本 run では未達。

## 4. 切り分け 3: pass 別の推移 (未確定・検証不足)

`--print-after-all` の stderr を pass 単位に切って、IR の call 数を記録する試みを行った (`work/` 外の一時ファイル)。

- decode 直後の dump では、`0x180c97aa0` と `0x180da6e60` の両方に間接 call が無い。
- 同じ dump で、kept として扱われる間接 call (例 `0x1803dfcea`・`call [rax+0x10]`) も call として現れない。よって decode 直後の IR に間接 call が無いことは、欠落した 6 件の証拠にならない。
- 集計の `call` 数は `llvm.ctpop` 等の intrinsic を含んでおり、pass 単位の件数推移は検証できていない。

結論: pass の特定は本 run では未達。次の run では、間接 call を kept と欠落で区別できる計測 (例: 命令アドレスの `!insn.addr` メタデータで追跡) を先に作る。

## 5. 未解決 (起票先)

| 項目 | 状態 | 起票先 |
|---|---|---|
| 欠落を起こす RetDec pass の特定 (間接 call の表現・intrinsic 除外の補正計測を含む) | 未達 | 子 #1612 ([ICALL-35]、親 #1454) |
| `0x180c97aa0` の `undef` 化の条件と警告 5 件の対応 | 未達 | 同上 (#1612) |
| `lost 0` (修復 / 段と条件の分類) | 未達 | 同上 (#1612) |

## 6. 再現手順

```
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" tools/icall/work/rt_freshair-core   # 素材名は docs/WORKFLOW.md §11
python3 tools/icall/diff/fa_residual.py tools/icall/work/rt_freshair-core
unzip -o "<plugins-freshair の Fresh Air.Win.zip>" '*SlateCore.core_64'   # 展開先は作業用の一時ディレクトリ
[RETDEC] (`docs/REFERENCES.md`) の `retdec-decompiler` <PE> -o x.c --select-ranges 0x180c97aa0-0x180c97ee0 --select-decode-only --backend-no-opts --output-llvmir x.ll
```

一時展開先と `work/` 配下の dump は gitignore 対象で、commit していない。
