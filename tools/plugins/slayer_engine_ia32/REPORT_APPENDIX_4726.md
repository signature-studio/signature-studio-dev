# Slayer_Engine.dll の未被覆区間の分類: prologue を持たない関数の誤判定 (#4726 / 親 #3546)

- 測定 commit: `2f9147207` (コードを変えた最後の commit)。 `git diff 2f9147207 HEAD -- tools/plugins/slayer_engine_ia32/gap_classify.py tools/plugins/slayer_engine_ia32/lift_text.py` の出力は本 PR 作成時点で空。
- 対象: `block22434_PE.bin` (179,512 B・SHA-256 `84b64c43…`)。 素材は `fl-win64` の `extracted/`。

## 1. 結論

- `0x1000eab4` は関数 (34 B・`mov ecx,[esp+4]` で始まり `ret` で終わる leaf)。 従来の分類器は、その直前の区間 `0x1000ea92` (466 B) を reloc 値 8 本の「ポインタ表 (a)」と判定していた。 誤り。
- 区間 `0x1000ea92` の 466 B は単一関数ではない。 内訳は次のとおり (§3)。 issue 本文の「432 B の関数」は、`0x1000eab4` から次の区間の境界 `0x1000ec64` までの長さで、単一関数の長さではない。
- 規則の追加 (`gap_classify.py` の `func_end` と (b) の「コード側 push 即値」規則) で、この区間は (b) になり、指された関数 (`0x1000eaac`・`0x1000eab4`・`0x1000eb8c`) が第 2 パスの roots に入る。 最終 lift で `0x1000eab4` は関数として lift される (`functions` 479 (base 472)・命令 21,505 (base 21,354)・被覆 62,704 B (base 62,320 B))。
- `measure.py` gate C1〜C4 (4/4)・ネガコン (`0/3 miss`)・`jt_check.py` (OK)・`iat_check.py` (OK) は全て PASS。

## 2. 分類の規則 (本 PR で変えた部分)

旧規則 (`origin/main`): (a) reloc 値 2 本以上 → prologue 判定より前に (a)。
本 PR: 次を (a) の前に置く。

| 条件 | 分類 | 根拠 |
|---|---|---|
| 区間の先頭が pad (`cc`/`90`/`00`)、かつ区間内を指す **`push` 即値** があり、その VA から `ret` まで逆アセンブルできる (`func_end`) | (b) | SEH フレーム登録 (`push <関数>`) の形。 prologue は要求しない |

- `push` のみを対象にした理由: 検証中、`mov`/`cmp` の即値 (データ参照) を含めると、ジャンプテーブルへの分岐先や関数の途中を指すものまで (b) になった (`0x10012a06` の `0x10012a2c` は関数の途中。 `0x10010bbf` は jt の分岐先を含む 46 本の reloc 表)。 これらは本 issue の範囲外として据え置く (§4)。
- 逆アセンブル走査の不備を直した: 旧 `classify()` は `md.disasm(code, T0)` の 1 回呼びで、`0x1000a1a0` (デコード不能 `c8 a1 00 10`) で止まっていた。 本 PR は `sweep()` (不能 1 バイトを飛ばす resync 掃引) で `push` 即値を集める。 call/jmp の (b) 判定は従来の経路のまま。

## 3. 区間 `0x1000ea92` (466 B) の内訳

| VA | 内容 | 根拠 |
|---|---|---|
| `0x1000ea92`〜 | `cc cc` pad・`55 8b ec` (prologue) ・push 系の列 | 区間の先頭は pad |
| `0x1000eab4` | 関数 34 B (`mov ecx,[esp+4]` … `ret` @`0x1000ead5`) | 参照: `push 0x1000eab4` @`0x1000eae0`・`cmp [ecx+4], 0x1000eab4` @`0x1000eb47` |
| `0x1000eaac` | 区間内の関数 (SEH の入口 `push 0x1000eaac` @`0x1000ea9f` が参照) | `func_end` で ret 到達を確認 |
| `0x1000eb8c` | `push ebp; mov ebp,esp` の関数 | `push 0x1000eb8c` @`0x1000a311` ほか (区間外からの参照) |

注: `0x1000eab4` を指す reloc は 2 本 (`0x1000eae1`・`0x1000eb4a`)。 `0x1000eae1` は `push 0x1000eab4` の即値 (コード側)、`0x1000eb4a` は命令の途中 (オペランド位置) の値で、いずれも区間内のコード側の参照。 本 PR は `push` 即値でこれを拾う (`cmp` の即値 `0x1000eb47` は対象外)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x10010bbf` (822 B・reloc 46 本) は旧分類 (a) のまま | 46 本の reloc が jt の分岐先か、データか未確認。 (b) にすると誤りになり得る | 子 issue (本 PR では起票しない・PR 本文の表で扱う) |
| `0x10012a06`・`0x10012cec`・`0x10007ce2` の (c) 区間 | 区間内の関数の途中を指す参照があり、 `mov`/`cmp` 規則で (b) にすると誤り。 `push` 規則の対象外のため据え置き | PR 本文の表 |
| 残りの未被覆 | 最終 lift の未被覆は 10,298 B (base は 10,682 B)。 残りの区間の分類は #3546 の範囲 | #3546 |

## 5. 測定 (実測)

| 項目 | 値 |
|---|---|
| 入力 SHA-256 | `84b64c43cc6528401e1c4e84074785e100e8453c4db4c8322a5d5f608de724a9` (一致) |
| capstone | 5.0.7 |
| 第 1 パス・同一入力 (origin/main 分類器) | (a) 17 区間 2,677 B / (b) 1 区間 552 B / (c) 219 区間 7,453 B (計 237 区間) |
| 第 1 パス・同一入力 (本 PR 分類器) | (a) 16 区間 2,211 B / (b) 2 区間 1,018 B / (c) 219 区間 7,453 B (計 237 区間) |
| 変わった区間 | 1 件: `0x1000ea92` 466 B・(a)→(b) |
| 最終 lift (origin/main) | functions 472・insns 21,354・被覆 62,320 / 73,002 B (85.37%)・未被覆 10,682 B (実測 `lift_text.py`・24.1 s) |
| 最終 lift (本 PR) | functions 479・insns 21,505・被覆 62,704 / 73,002 B (85.89%)・未被覆 10,298 B (実測 22.8 s) |
| `lift_text.py` | emcc rc 0 × 2・selftest PASS・check PASS |
| `measure.py` | gate C1〜C4 PASS (4/4)・in-process 0.86 s |
| `measure.py --nega` | `nega: 0/3 miss` (rc 0) |
| `jt_check.py` | OK (switch 表 23 本・case 値合計 245・生データ一致 23・不一致 0) |
| `iat_check.py` | OK (絶対 disp32 IAT 参照 80 件・名前の不一致 0) |
| 負のテスト | 規則を無効化 (`elif False`) すると `lift_text.py` が `[gap_classify #4726] FAIL: 0x1000eab4 の区間の分類が a (b のはず)` で exit 1 |

再現:

```
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PY=$RUNNER_TEMP/venv_ia32/bin/python
PATH=$RUNNER_TEMP/emsdk-root/emsdk/upstream/emscripten:$PATH \
  $PY tools/plugins/slayer_engine_ia32/lift_text.py
$PY tools/plugins/slayer_engine_ia32/measure.py && $PY tools/plugins/slayer_engine_ia32/measure.py --nega
```

## 6. 訂正 (issue #4726 本文)

- 「`0x1000eab4` (432 B・`mov ecx,[esp+4]` で始まる `ret` で終わる関数)」は、関数の長さとしては誤り。 関数は 34 B。 432 B は同じ区間の残りで、3 つ以上の関数を含む (§3)。
- 出典の `tools/plugins/slayer_engine_ia32/REPORT_APPENDIX_3546.md` は main に存在しない (本 PR で作成していない)。 本付録がその代わりの測定の正本。
