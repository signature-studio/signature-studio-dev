# tools/shared/lift/rex 付録 — movnti reach 16 件を arena 内で完了させる (#4324)

測定 commit: `7d591151b` (`tools/shared/lift/rex/` と `tools/flelift/` を最後に変えた commit = main 取り込みの merge。その前のコード変更は `6c2c5a030`)。以降の差分は本付録と REPORT の文言のみ (差分 0 の証跡は §4)。
既知類型との関係: 該当なし (不一致 0)。lift の出力 (`fle_lifted.c`) は変えていない。

## 1. 結論 (1 行)
reach 16 件 (fn=0・a1 ∈ [0x70000, 0x80000)) は、movnti モードの arena を 0x80000 にし、ctx のロック構造 (`ctx+8` → `[LK] = 0x10`) を置くことで、native と wasm の両方が trap せず完了し、arena が一致した (16/16・不一致 0)。受入 1・2・3 を満たした。

## 2. 決定事項 (受入 1)
- 変えたもの: (a) movnti モードだけ arena を 0x80000 にする (`lift_x64c.sh` が `REX_ARENA_SZ=0x80000` を export。他モードは 0x10000 のまま)。(b) reach の入力に木の構造 (`gen_cases.py` の SUCC1 と同じ) とロック構造 `LK` を置く (`gen_movnti.py` の `reach_case`)。
- 変えなかったもの: a1 の値域 [0x70000, 0x80000)・lift (`fle_lifted.c`)・wasm の `INITIAL_MEMORY` (0x31000000 で arena 末尾 0x30180000 を覆う)。
- 理由: memset の a1 ≥ 0x70000 は 64 KiB の arena を越える。reach を arena 内で完了させるには、arena を 0x80000 に広げ、木の検索 (0x12a50) とロック経路 (0x16030) の入力を揃える必要があった。0x16039 (`[rcx]` の NULL 参照) はロック構造が無いことが原因だった。
- 限界: これは harness の入力モデルの変更で、x64c の lift の正しさの検証ではない。reach の a1 は memset の書込が arena 内に収まる範囲に限った。a1 < 0x70000 の sweep (表示のみ・#3894) は判定に入れていない。

## 3. 実測 (測定 commit `7d591151b`・`bash tools/shared/lift/rex/lift_x64c.sh all`・`FL_WIN64_DIR` は `fl-win64` 展開先・`EMSDK_ENV` は `toolchain-emsdk` の `emsdk_env.sh`。エントリ ID は `docs/REFERENCES.md` の `[EMSDK]` を参照)

| 項目 | 値 |
|---|---|
| `all` の wall / rc | 16 s / rc 0 (`ALL OK`) |
| load (1 分値) | 開始 0.82 0.41 0.18・終了 0.86 0.44 0.19 (nproc 4) |
| `ok` | PASS (`RESULT PASS`) |
| ネガコン | neg-cmp FAIL・neg-ctx FAIL・neg-owner FAIL (いずれも期待どおり・rc 1) |
| `movnti` | 実装 `ott_unsup` 0 件 OK・reach 16/16 (arena 内完了・不一致 0)・`RESULT PASS` |
| `movnti` の elapsed | 4 s (load 0.85 → 0.86) |

直前の commit `6c2c5a030` (main 取り込み前) でも `all` は ALL OK (15.8 s・rc 0・reach 16/16) だった。

### sweep (表示のみ・判定に入らない)
main 取り込みで `run_wasm.mjs` が trap VA を名前付き wasm 関数から取るように変わった。このため、取り込み前は `-` だった a1 ≥ 0x6a000 の trap 記録が `0x1800011c0` (関数 `f_1800011c0`・REXGetCreatorInfo の入口) と表示されるようになった。これは境界外 trap の位置を示す表示で、判定 (`movnti_check.py`) には使わない。movnti の VA (0x18001c9a0) で trap する case は 0 件。

## 4. 測定後のコード差分 (差分 0 の証跡)
`git diff 7d591151b HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (本付録と REPORT の文言だけの差分)。

## 5. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| sweep の wasm trap (境界外 VA `0x1800011c0` 等) の原因の確定。判定に入れていない | 表示のみ | #3894 (付録 `REPORT_APPENDIX_3894.md` の未解決) |
| memset の x64c 対応 (movnti VA 0x18001c9a0 の `ott_unsup`) は 0 件のまま。実装の対応は #3893 で完了済み | なし | #3893 [T-SH-93] |
