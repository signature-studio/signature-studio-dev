# PY-5388 (#5771): 動的トレース採取道具の構築 — linkToLastTweaked の boot 経路判定

親: #5767 (PY-5387)・#4831 (PY-261 系)。本 REPORT は #5771 の受入 1 (lane 判定) の結果を書く。
測定 commit: 本 PR のコード変更は `tools/python/analysis/flapi/py5388_refs_probe.py` の 1 commit (下の「コミット」節)。

## 1. 結論

- **受入 1 (boot 経路で `linkToLastTweaked` が呼ばれるかの判定): 静的に判定した。直接 call は 0 件。**
  PE の全 section で `0xd76c90` を指す `call`/`jmp` は **0 件**。参照は PyMethodDef 表の 1 箇所
  (`0x151d4c8`・項目 `0x151d4c0`・name `linkToLastTweaked`・flags=3) だけで、呼出しは Python の
  メソッド dispatch (間接) を経る。
  boot 経路が Python のメソッド表を通るかは**未確認** (boot harness の実行でその経路を観測していない)。
  よって「boot 経路では呼ばれない」とは言えず、「直接の call はないが、間接経路の有無は未確定」が結論。
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
  絶対 8 byte は 8 byte 刻みで `== 0xd76c90` を判定。
- `flags=3` は METH_VARARGS|METH_KEYWORDS。`REPORT_PY215.md` §表の `PyMethodDef flags=3` と一致。
- 同じ走査を `0xd76c90` 以外の既知の PyMethodDef 項目へ当てた検算は行っていない (未実施)。

## 3. boot 経路との関係 (判定の根拠と限界)

- 根拠: `0xd76c90` へ直接飛ぶ命令は PE に無い (§2)。呼出しはメソッド表 `0x151d4c0` の経由のみ。
- 限界 (未確認):
  - boot 経路 (`tools/flelift/boot`・`CreateFruityInstance` 〜 `InitUnits`) が、この PyMethodDef 表を
    登録・dispatch する Python 初期化を通るかは観測していない。
  - `tools/flelift/boot/REPORT.md` の unit 進行 (895 units) は FLEngine の unit 初期化の記録で、
    Python メソッドの呼出しを記録する観点では測っていない。
  - したがって「boot 経路で呼ばれる」「呼ばれない」のどちらも本 REPORT では断定しない。

## 4. 受入 2 (動的 run) を行わなかった理由

- 道具 (`tools/flelift/boot`) の実行には `work/boot` の lift・shimx obj・link が要る。
  この runner には `tools/flelift/boot/work` が無い (`ls` で不在を確認)。
- `REPORT_APPENDIX_4783.md` §表: 1 TU の clang が peak 11,380〜11,458 MB で cap 11,000 MB を超え停止。
  `FLE_SHARDS=8` でも `boot_e2e.sh` の `cc()` は shard しないと記録がある。
- 残り 58 分の run で lift (8 shard)・link・実行を完了できる見込みは、実測が無いため判断できない。
  本 run では build を始めず、動的 run は未達として残す (推定の所要時間は書かない)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| boot 経路が PyMethodDef (`0x151d4c0`) を通るか (受入 1 の残り) | lane (a)/(b) の選択 | #5771 の再 run (本 issue は未達のまま残す) |
| 動的 run (受入 2)・boot build の clang RSS cap | 採取道具が動くかは未確認 | #5771 の再 run。build の分割 (shard の cc 対応) は既存 `boot_e2e.sh` の制約 (REPORT_APPENDIX_4783) |
| wine64 (lane b) の apt 導入可否 | runner 環境の変更 | PM 判断 (本 issue のコメントで依頼) |

## コミット

- 本 PR のコード変更: `tools/python/analysis/flapi/py5388_refs_probe.py` と `tools/python/REPORT_PY5388.md`・`docs/DOC_MAP.md` の登録行 (同一 commit)。
- 測定 commit: 上の 1 commit (probe を走らせたのは commit 前の同じ内容の作業ツリー。diff は commit のみ)。
