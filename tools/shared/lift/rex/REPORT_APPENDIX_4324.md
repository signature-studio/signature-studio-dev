# tools/shared/lift/rex 付録 — movnti reach 16 件を arena 内で完了させる (#4324)

測定 commit: `de7667530` (`tools/shared/lift/rex/` と `tools/flelift/` を最後に変えた commit = reach 判定に memset 通過を追加し、木のキーを直した修正)。以降の差分は本付録と REPORT の文言のみ (差分 0 の証跡は §4)。
既知類型との関係: 該当なし (不一致 0)。lift の出力 (`fle_lifted.c`) は変えていない。

## 1. 結論 (1 行)
reach 16 件 (fn=0・a1 ∈ [0x70000, 0x80000)) は、movnti モードの arena を 0x80000 にし、木の検索キーとロック構造を揃えたうえで、native と wasm の両方が memset (`arena[0:a1]` が全 0) を通って完了し、arena が一致した (reach 16/16・memset 通過 16/16・不一致 0)。

## 2. 決定事項 (受入 1)
- 変えたもの:
  (a) movnti モードだけ arena を 0x80000 にする (`lift_x64c.sh` が `REX_ARENA_SZ=0x80000` を export。他モードは 0x10000 のまま)。
  (b) reach の入力に木の構造 (木のノードのキー = `key_of(a0)` = `OBJ`・`OBJ+0x630` = S・`OBJ+0x690` = B・`OBJ+0x20` = Z) とロック構造 `ctx+8 → LK`・`[LK] = 0x10` を置く (`gen_movnti.py` の `reach_case`)。
  (c) memset の通過を判定するため、`arena[0x10000:0x70000]` に非ゼロ (0x01) の番兵を置く。memset (`dst = a2 = ARENA`・`count = a1`) が走れば native と wasm の `arena[0:a1]` は全 0 になり、走らなければ番兵が残る。`movnti_check.py` は「native と wasm の両方で `arena[0:a1]` が全 0」を reach の判定に入れた。
- 変えなかったもの: a1 の値域 [0x70000, 0x80000)・lift (`fle_lifted.c`)・wasm の `INITIAL_MEMORY` (0x31000000 で arena 末尾 0x30180000 を覆う)。
- 理由: memset の a1 ≥ 0x70000 は 64 KiB の arena を越える。reach を arena 内で完了させるには、arena を 0x80000 に広げ、木の検索 (0x12a50 → 0x1800022b5 の `f_180001de0`) とロック経路 (0x16030) の入力を揃える必要があった。0x16039 (`[rcx]` の NULL 参照) はロック構造が無いことが原因だった。
- 前回 (`7d591151b` 時点) の誤り: 判定は「trap なし・arena 一致」だけで、memset が走らなくても PASS した。さらに、木のノードのキーを `key_of(OBJ)` と書いていたため、検索キー `key_of(a0) = OBJ` と一致せず、`f_180001de0` が false を返して `0xca` で早期 return していた。memset に届いていないのに 16/16 と数えていた。今回 (c) の判定を入れたところ 0/16 になり、原因を §4 の前に特定してキーを `OBJ` に直した。
- 限界: これは harness の入力モデルの変更で、x64c の lift の正しさの検証ではない。reach の a1 は memset の書込が arena 内に収まる範囲に限った。a1 < 0x70000 の sweep (表示のみ・#3894) は判定に入れていない。

## 3. 実測 (測定 commit `de7667530`・`bash tools/shared/lift/rex/lift_x64c.sh all`・`FL_WIN64_DIR` は `fl-win64` 展開先・`EMSDK_ENV` は `[EMSDK]` (Emscripten 6.0.12) の `emsdk_env.sh`。エントリ ID は `docs/REFERENCES.md` の `[EMSDK]` を参照)

| 項目 | 値 |
|---|---|
| `all` の wall / rc | 16 s / rc 0 (`ALL OK`) |
| load (1 分値) | 開始 0.57 0.40 0.19・終了 0.66 0.43 0.20 (nproc 4) |
| `ok` | PASS (`RESULT PASS`) |
| ネガコン | neg-cmp FAIL・neg-ctx FAIL・neg-owner FAIL (いずれも期待どおり・rc 1) |
| `movnti` | 実装 `ott_unsup` 0 件 OK・reach 16/16 (arena 内完了・不一致 0)・memset 通過 16/16・`RESULT PASS` |
| `movnti` の elapsed | 3 s (load 0.64 → 0.66) |

### 判定の反証 (番兵と木のキーの修正前後)
- 木のキーを `key_of(OBJ)` と書いた版 (`7d591151b` 相当): reach 0/16・memset 通過 0/16 (`f_180001de0` が false → `0xca` で早期 return。native と wasm の arena は一致していた)。旧判定の「16/16」はこの早期 return を数えていた。
- 木のキーを `OBJ` に直した版 (`de7667530`): reach 16/16・memset 通過 16/16。

直前の commit `6c2c5a030` (main 取り込み前) でも `all` は ALL OK だったが、memset 通過は判定していなかった。

### sweep (表示のみ・判定に入らない)
main 取り込みで `run_wasm.mjs` が trap VA を名前付き wasm 関数から取るように変わった。このため、取り込み前は `-` だった a1 ≥ 0x6a000 の trap 記録が `0x1800011c0` (関数 `f_1800011c0`・REXGetCreatorInfo の入口) と表示されるようになった。これは境界外 trap の位置を示す表示で、判定 (`movnti_check.py`) には使わない。movnti の VA (0x18001c9a0) で trap する case は 0 件。

## 4. 測定後のコード差分 (差分 0 の証跡)
`git diff de7667530 HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (本付録と REPORT の文言だけの差分)。

## 5. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| sweep の wasm trap (境界外 VA `0x1800011c0` 等) の原因の確定。判定に入れていない | 表示のみ | #3894 (付録 `REPORT_APPENDIX_3894.md` の未解決) |
| memset の x64c 対応 (movnti VA 0x18001c9a0 の `ott_unsup`) は 0 件のまま。実装の対応は #3893 で完了済み | なし | #3893 [T-SH-93] |
