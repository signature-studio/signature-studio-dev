# PY-5388 (#5771): 動的トレース採取道具の構築 — linkToLastTweaked の boot 経路判定

親: #5767 (PY-5387)・#4831 (PY-261 系)。本 REPORT は #5771 の受入 1 (lane 判定) の結果を書く。
測定 commit: 本 PR のコード変更は `tools/python/analysis/flapi/py5388_refs_probe.py` の 1 commit (下の「コミット」節)。

## 1. 結論

- **受入 1 (boot 経路で `linkToLastTweaked` が呼ばれるかの判定): 静的に一部判定した。**
  PE の全 section で `0xd76c90` を指す E8/E9 rel32 の `call`/`jmp` は **0 件** (他の形式は未走査)。
  参照は PyMethodDef 表の 1 箇所 (`0x151d4c8`・項目 `0x151d4c0`・name `linkToLastTweaked`・flags=3) だけ。
  この参照が呼出しに至る経路 (Python のメソッド dispatch を経ると推定・未確認) は観測していない。
  boot 経路が Python のメソッド表を通るかは**未確認** (boot harness の実行でその経路を観測していない)。
  よって「boot 経路では呼ばれない」とは言えず、「E8/E9 の直接 call はないが、間接経路の有無は未確定」が結論。
- **受入 2 (採取道具が 1 回動く): 未達。** 動的 run は行っていない。理由は §4。
- lane の判断: lane (a) (boot の unit 実行への記録の追加) は、boot 経路が PyMethodDef を通るかを
  先に確定しないと意味がない。その確定は boot の実行観測が要るので、**lane (a) の前提が未確定**。
  lane (b) (wine64 + watchpoint) は apt 導入が runner 環境の変更になるため、導入可否の判断を PM に渡す。

## 2. 静的判定の手順と実測

道具: `tools/python/analysis/flapi/py5388_refs_probe.py` (PE 静的走査・pefile)。
素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf`・実測 9.95 s・real)。
PE: `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` (22,227,016 byte)。

実行:

```
FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" python3 tools/python/analysis/flapi/py5388_refs_probe.py
```

出力 (実測):

```
rel32 call/jmp to 0xd76c90: 0
abs8 pointer to 0xd76c90: 1
  meth 欄 0x151d4c8 (項目 0x151d4c0) name=linkToLastTweaked flags=3
```

- 走査: 全 section の raw 全域。rel32 は `E8`/`E9` の disp32 を `次命令 VA + disp == 0xd76c90` で判定。
  絶対 8 byte は 8 byte 刻みで `== 0xd76c90` を判定 (非整列の格納は検出されない)。
  未走査: `FF /2`・`FF /4` (間接 call/jmp)、rel8 の `EB`、条件分岐 `0F 8x`、`lea` で取った関数ポインタ経由の呼出し。
- `flags=3` は METH_VARARGS|METH_KEYWORDS。`REPORT_PY215.md` §表の `PyMethodDef flags=3` と一致。
- 同じ走査を `0xd76c90` 以外の既知の PyMethodDef 項目へ当てた検算は行っていない (未実施)。

## 3. boot 経路との関係 (判定の根拠と限界)

- 根拠: `0xd76c90` へ E8/E9 rel32 で直接飛ぶ命令は PE に無い (§2・他の形式は未走査)。
  確認できた参照はメソッド表 `0x151d4c0` の 1 件のみ。
- 限界 (未確認):
  - boot 経路 (`tools/flelift/boot`・`CreateFruityInstance` 〜 `InitUnits`) が、この PyMethodDef 表を
    登録・dispatch する Python 初期化を通るかは観測していない。
  - `tools/flelift/boot/REPORT.md` の unit 進行 (895 units) は FLEngine の unit 初期化の記録で、
    Python メソッドの呼出しを記録する観点では測っていない。
  - したがって「boot 経路で呼ばれる」「呼ばれない」のどちらも本 REPORT では断定しない。

## 4. 受入 2 (動的 run) を行わなかった理由

- 道具 (`tools/flelift/boot`) の実行には `work/boot` の lift・shimx obj・link が要る。
  この runner には `tools/flelift/boot/work` が無い (`ls` で不在を確認)。
- `tools/flelift/boot/REPORT_APPENDIX_4783.md` §表: 1 TU の clang が peak 11,380〜11,458 MB で cap 11,000 MB を超え停止。
  `FLE_SHARDS=8` でも `boot_e2e.sh` の `cc()` は shard しないと記録がある。
- 残り 58 分の run で lift (8 shard)・link・実行を完了できる見込みは、実測が無いため判断できない。
  本 run では build を始めず、動的 run は未達として残す (推定の所要時間は書かない)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| boot 経路が PyMethodDef (`0x151d4c0`) を通るか (受入 1 の残り) | lane (a)/(b) の選択 | #5771 の再 run (本 issue は未達のまま残す) |
| 動的 run (受入 2)・boot build の clang RSS cap | 採取道具が動くかは未確認 | #5771 の再 run。build の分割 (shard の cc 対応) は既存 `boot_e2e.sh` の制約 (REPORT_APPENDIX_4783) |
| wine64 (lane b) の apt 導入可否 | runner 環境の変更 | PM 判断 (本 issue のコメントで依頼) |

## 6. 動的 run (受入 2・#5771 の再 run)

道具: `tools/flelift/boot/fle6_measure.sh` に `FLE_TRAP_VA` を追加 (x64c `--trap`)。指定 VA は lift せず `ott_unsup` の trap stub にする。呼ばれると `boot_threw=unsup` で止まる。
測定 commit: `075a23d42` (`feat(flelift): fle6_measure.sh に FLE_TRAP_VA を足す`)。HEAD で再現。素材 `fl-win64` (`$ARTIFACTS_DIR` の実在を確認)。emsdk (`[EMSDK]`) は本 run で未確認 (素材に無く、使っていない)。shard 8・既定経路 (`FLE_IPP` 未指定 = mode 3)・`FLE_EXTRA_ROOTS=` (root 無し)。

実行: `FLE_TRAP_VA=0xd76c90 FLE_BOOT_RUNS=default FLE_SHARDS=8 FL_WIN64_DIR=<展開先の親> bash tools/flelift/boot/fle6_measure.sh`

| 実行 | 結果 (`FLEBOOT_RESULT`) | 所要 (real) | load (開始時) |
|---|---|---|---|
| `0xd76c90` を trap (測定) | units 895・`boot_threw=exit`・`unsup` 0 件 | 2 分 34 秒 | 1.9 |
| 陽性対照 `0x976da0` を trap (一時コピーの sed・repo 外) | units 851・`boot_threw=unsup` | 未記録 (time の出力を取り損ねた) | 1.9 |

- 陽性対照で trap が検出されることを確認した (unit 851 で `unsup`)。このため「`0xd76c90` が 0 件」は trap が効かなかった結果ではない。
- 比較の出典: trap なしの既定経路の記録は `tools/flelift/boot/REPORT_APPENDIX_672.md` §C-2 (測定 commit `dec8fa928`・既定 `FLE_IPP` 未指定 = mode 3・`FLE_EXTRA_ROOTS` 未指定) の units 895・`exit` (code 0)。本 §6 の trap 版 (units 895・`exit`) は units と停止理由が同値。ただし、この記録は別 commit・別 run のもので、本 PR では trap なしの既定経路は再実行していない。GetMem/FreeMem は本 run で未記録のため比較していない。

### 判定

- **受入 1 の結論: 既定経路の boot では `linkToLastTweaked` (`0xd76c90`) は呼ばれない。** 観測: units 895 まで進み `exit` で終わり、trap に到達しない。この判定は既定経路 (ILTools 擬似なし・mode 3) に限る。
- 他の IPP mode・survey 経路・`FLE_IPP=0` では未確認。
- lane (a) (boot 経路への記録の追加) は、この経路では観測対象が呼ばれないため不要。lane (b) (wine64 + watchpoint) の要否は PM 判断。

## コミット

- 本 PR のコード変更: `tools/python/analysis/flapi/py5388_refs_probe.py` と `tools/python/REPORT_PY5388.md`・`docs/DOC_MAP.md` の登録行 (同一 commit)。
- 測定 commit: 上の 1 commit (probe を走らせたのは commit 前の同じ内容の作業ツリー。diff は commit のみ)。
