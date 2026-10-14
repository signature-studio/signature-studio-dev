# KH-35 (#2176): 対照 Gain の before 160 関数の人手判定 (付録)

- 親: #2155 (KH-34)。本付録は `REPORT_KH19.md` §11 の KH-35 節の詳細 (本体の行数上限のため分割)。
- 測定 commit (コードと TSV を変えた最後の commit): `c4240c54`。以降の commit は本付録と REPORT の追記のみ。
  `git diff c4240c54 HEAD -- tools/targets/kilohearts/scripts` の出力は空 (0 行)。

## 0. 結論

- `gain_before_160.tsv` の 160 行すべてを `verified=manual` にした (列の変更は本 PR)。
- **判定者の注記**: 判定は実装エージェント (AI) が `gain_manual_dump.py` の出力と RTTI 出力を読んで行った。
  独立した人の検証ではない。検収では同じ dump を独立に読み直すこと (§7 未解決)。
- 受入 1 (各行の呼び出し元と call 位置を確認): **達成** (判定者の注記つき)。
- 受入 2 (手検証集合と before 集合の差分): **差分 0 行** (160 と 160。§4)。
- 受入 3 (機械照合・ダンプを手検証と書かない): 達成。検算スクリプト (§6) の結果は「検算」と書き、手検証とは分けた。
- 機械照合 (`gain_mech_check.py`・`verify_gain_tsv.py`) の結果は REPORT_KH19 §8 の値のまま (再実行していない)。

## 1. 測定条件

- 素材: `plugins-kilohearts.tar.zst` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745`
  → `HeartCore.core_64` (76,642,304 B、REPORT_KH19 §9 と一致)。展開先は `$RUNNER_TEMP` (repo 外・gitignore 外)。macOS 側は未展開。
- 環境: 4 vCPU。load average (1 分値) は開始時 0.33、判定中 0.27。
- 再生成 (測定 commit で 1 回ずつ): `rtti_walk.py` 1.9 s → `callgraph.py` 8.1 s (120,856 関数、4 round) →
  `gain_before_list.py` 0.3 s (before 160、roots 27。列 1〜5 は origin/main の TSV と全行一致) →
  `vtable_closure.py gain all` 11.3 s (`before_funcs` 160・`before_bytes` 39,357・`after_funcs` 1,995。REPORT_KH19 §2 と一致)。
- ダンプ: `gain_manual_dump.py` 0.10 s。出力 1,039 行 (ROOT 27 ブロック・非 ROOT 133 ブロック)。
  call 位置が命令境界に乗らない行 0 件。

## 2. 判定基準

- **ROOT 27 行** (`parent_rva` が空): root_class の vtable のいずれかの slot が `0x180000000 + func_rva` に等しい (`rtti_walk.py` の出力)。
- **非 ROOT 133 行**: (a) `parent_rva` が TSV 内 (`in_set=True` 133/133)、(b) ダンプの call 位置の行 (`>>`) の命令が
  `call` または `jmp` で、遷移先が `0x180000000 + func_rva`、(c) call 位置が親の `[parent, parent+size)` 内。
  内訳は direct call 122 行・tail `jmp` 11 行。

## 3. 判定結果

| 種別 | 行数 | 判定 | 根拠 |
|---|--:|---|---|
| ROOT (vtable 入口) | 27 | 27 OK | §3.1 の slot 番号 |
| 非 ROOT・direct call | 122 | 122 OK | ダンプの `>>` 行が `call 0x18xxxxxxx` (遷移先 = func_rva) |
| 非 ROOT・tail jmp | 11 | 11 OK | `#3 #19 #50 #67 #82 #120 #129 #130 #141 #152 #157` の `>>` 行が `jmp` (遷移先 = func_rva) |

特記 (読み取りで確認した点):
- `#2` (0x5c50): 呼び出し位置 0x4d096 は親 `#18` (0x4cf20) の `ret` (0x4d095) の直後。ただし同じ親の 0x4cfb4 の `jae 0x18004d096` から到達する (ダンプ `#47` ブロックの直前行)。
- `#155`〜`#160` (RVA 0x1327120 以上): `.text` (section 0 = RVA 0x1000〜0x13a08ac) の内側。ダンプが `sections[0]` を読む前提は成り立つ。

### 3.1 ROOT 27 行の vtable 所属 (`rtti_walk.py` 出力の slot 番号)

| # | func_rva | root_class | vtable | slot |
|--:|---|---|---|--:|
| 1 | 0x3370 | GainDspModel | 0x1817b53c8 | 1 |
| 4 | 0x65e0 | GainDspModel | 0x1817b53c8 | 3 |
| 5 | 0x65f0 | GainDspModel | 0x1817b53c8 | 4 |
| 6 | 0x6600 | GainDspModel | 0x1817b53c8 | 5 |
| 7 | 0x128a0 | GainDsp | 0x1817d9c88 | 1,2,3,4,5,16 |
| 8 | 0x1dab0 | GainMasterDsp | 0x1817bae18 | 1 |
| 9 | 0x1dac0 | GainMasterDsp | 0x1817bae18 | 2 |
| 10 | 0x20710 | GainDsp | 0x1817d9c88 | 6 |
| 11 | 0x20740 | GainDsp | 0x1817d9c88 | 8 |
| 12 | 0x20e10 | GainDsp | 0x1817d9c88 | 9 |
| 13 | 0x20e20 | GainDsp | 0x1817d9c88 | 10 |
| 14 | 0x20e30 | GainDsp | 0x1817d9c88 | 12 |
| 15 | 0x20e50 | GainDsp | 0x1817d9c88 | 18 |
| 16 | 0x20e60 | GainDsp | 0x1817d9c88 | 19 |
| 24 | 0x4f2a0 | GainDspModel | 0x1817b53c8 | 2 |
| 29 | 0x7a6d0 | GainMasterDsp | 0x1817bae18 | 3 |
| 30 | 0x7a760 | GainMasterDsp | 0x1817bae18 | 4 |
| 31 | 0x7a7e0 | GainMasterDsp | 0x1817bae18 | 5 |
| 32 | 0x7a830 | GainDsp | 0x1817d9c88 | 11 |
| 39 | 0x4aa230 | GainDspModel | 0x1817b53c8 | 0 |
| 40 | 0x4ae940 | GainMasterDsp | 0x1817bae18 | 0 |
| 41 | 0x4b0060 | GainDsp | 0x1817d9c88 | 15 |
| 42 | 0x4b0140 | GainDsp | 0x1817d9c88 | 17 |
| 43 | 0x4b0160 | GainDsp | 0x1817d9c88 | 7 |
| 44 | 0x4b0200 | GainDsp | 0x1817d9c88 | 13 |
| 45 | 0x4b0380 | GainDsp | 0x1817d9c88 | 14 |
| 46 | 0x4b05f0 | GainDsp | 0x1817d9c88 | 0 |

## 4. 集合の差分 (受入 2)

- 手検証集合 (`verified=manual` の行の func_rva): 160。
- before 集合: `gain_before_list.py` の再生成 (本測定の `callgraph.pkl` から) 160。TSV 160。
- 差分: 手検証 vs 再生成 **0 行**。TSV vs 再生成 **0 行**。
- `vtable_closure.py` は件数のみ出力する (集合は出さない)。件数は 160 で一致。集合の比較は `gain_before_list.py` 側で行った。

## 5. 再現コマンド

```sh
W=$RUNNER_TEMP/kh2176; mkdir -p $W && cd $W
tar --zstd -xf $HOME/artifacts/plugins-kilohearts.tar.zst
unzip -q -o "Kilohearts Offline Installer.zip" payload.dat -d win
unzip -q -o win/payload.dat index.json 'windows.zip/*' -d blobs
unzip -q -o blobs/windows.zip/1ccb1df8c8f10745 -d winpkg
C=$W/winpkg/HeartCore.core_64
cd <repo>/tools/targets/kilohearts
python3 scripts/rtti_walk.py $C $W/rtti.json
python3 scripts/callgraph.py $C $W/rtti.json $W/callgraph.pkl 14
python3 scripts/gain_before_list.py $C $W/callgraph.pkl $W/rtti.json gain $W/regen_gain.tsv
python3 scripts/gain_manual_dump.py $C gain_before_160.tsv > $W/dump.txt
python3 scripts/gain_manual_check.py $W/dump.txt gain_before_160.tsv $W/rtti.json
```

## 6. 検算とネガティブコントロール

- 検算 `scripts/gain_manual_check.py` (dump のテキストを TSV と RTTI の値だけで照合する別アルゴリズム):
  `{"rows": 160, "roots": 27, "root_slot_ok": 27, "nonroot": 133, "edge_ok": 133, "bad": []}`。
- ネガティブコントロール: dump の 1 行 (`#2` の `call 0x180005c50`) を `call 0x180005c51` に改ざんした写し →
  `"edge_ok": 132, "bad": [2]` (FAIL して行番号を返す)。
- `gain_before_list.py` の保持規則 (本 PR で追加。既存 TSV の `verified` を、`(func_rva, parent_rva, call_site_rva)` が一致する行に限って残す):
  - 初回生成 (既存 TSV なし): 160 行 `auto` (従来どおり)。
  - 既存 manual の TSV で再生成: 160 行 `manual`、列 1〜6 の差分 0 行。
  - 既存 TSV の 1 行 (0x5c50) の親だけを `0x4cf21` に変えて再生成: 当該行は `auto` に戻り、他 159 行は `manual` のまま (親の食い違いで保持されないことの確認)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 判定者が実装エージェント (AI) で、独立した人手検証ではない | 「人手検証済み」の強さが弱い。検収で dump を独立に読み直す必要がある | 本 PR の検収 (reviewer)。必要なら #2155 にコメント |
| 判定は静的な call 辺の存在まで。実行時に到達するか・this 型が実際にその vtable を使うかは未判定 | after 1,995 の過大評価は残る (REPORT_KH19 §5) | #848 (型追跡) |
| ROOT 27 行の vtable 所属は RTTI 出力の値で確認。生バイトを手で読んでいない | 同上 (RTTI 自体は `rtti_walk.py` の結果に依存) | — |
| 親 #2155 は本 PR では閉じない (親の受入 2 件は本 issue の範囲外) | 親は open のまま | PM が判断 |
