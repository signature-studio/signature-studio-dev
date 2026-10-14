# PY-41 (#1554): channels reroll/setSwing の未確定意味論と C provider 実装 (部分達成)

検証起点 commit: `ecf6d6e5` (origin/main)。既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブル読解のみ)。
親: #1525 (PY-38 / #1515 の子)。前提の PY-38 報告: `tools/python/REPORT_PY38.md`。

## 結論

- 受入条件 4 件のうち **未達 4 件すべて**が残る。本 run では C 実装・mock 差分検査・`all_tools.mjs` は未実施。
- 未確定 3 点のうち、汎用 helper `0x1046a30` の入口部分 (引数の退避と分岐構造) のみ確認した。中身の確定は未完。
- 残りは子 issue **[PY-45]** (番号は下記「分割先」) に分割する。

## 測定条件

- 素材: `oc_artifacts: fl-win64` の `flstudio_win64_26.1.7.5653.exe/extracted/block00031_PE.bin` (22,227,016 B)。
  `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C tools/python/work/py41 extracted/block00031_PE.bin` で `work/` に展開 (gitignore)。展開 2.5 秒 (実測)。
- 逆アセンブル: `python3 tools/python/analysis/py41_disasm.py tools/python/work/py41/extracted/block00031_PE.bin 0x1046a30` (capstone 5.0.7・pefile)。
- コード差分 0 の確認 (測定 commit = 本 commit、`provider/` は未変更): `git diff ecf6d6e5 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR で変更なし)。

## 0x1046a30 の入口 (確認済み・実測)

- フレーム 0x590 バイト。引数は `ecx` → `[rbp+0x5b0]`、`edx` → `[rbp+0x5b8]`、`r8d` → `[rbp+0x5c0]` に退避。
- 入口で `[rbp+0x584] = -1` を入れ、`[rip+0x59ab06]` のフラグが立っていれば `0xf82c20` を呼ぶ (エラー経路。0xf82c20 の中身は未確認)。
- `r8d` のビット判定:
  - `test r8d, 0x8a1` が 0 なら分岐 0x1046e05 へ飛ぶ。
  - `test r8d, 0x240` (0x1046e23) と `test r8d, 0x20` / `0x10000` / `0x8000` が分岐の条件に使われている。
- `ecx` の判定 (0x1046e7c〜): `test rax, rax` / `cmp rax, 0xfffffff` の 2 段で範囲を見て、`ecx >> 16` を `[rbp+0x55c]` に取り出す。
  - `0x40000001` は `0xfffffff` より大きいので、この範囲判定で `0x1046edf` へ飛ぶ経路になる。
  - **推定**: `ecx` の上位ビット (0x40000000) がカテゴリ、下位 16 bit が index ではなく別種の値。確定には 0x1046edf 以降の読解が必要。

## 未確定 (本 run で残したもの)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1046a30` の本体 (0x1046edf 以降) と `ecx=0x40000001`・`edx=0x3dd`・`r8d=2` の意味 | setSwing/getSwing の実装が書けない | [PY-45] |
| `chan` のフィールド `+0x739` / `+0x794` / `+0x79c` と `0xffa6d0` の戻り値 2 の意味 | rerollLoopStarter* の実装が書けない | [PY-45] |
| status 値 (-1〜-10) と `finish` のエラー文字列 10 件の対応 | エラー時の例外文字列が決まらない | [PY-45] |
| C 実装 (`provider/fl_engine.c` 4 関数 + getSwing)・mock 差分 0・`all_tools.mjs` 48/48 | 受入条件 3 件 | [PY-45] |
