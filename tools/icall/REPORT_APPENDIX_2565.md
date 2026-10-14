# #2565 REPORT — BLK 域を再配置範囲の外へ (`icall_rewrite.py` の配置・検査・0 埋め)

- 担当 issue: #2565 `[PLG-P0b-20]` (親 #2510)。根拠の REPORT は `tools/plugins/framework/REPORT_2510.md` (`origin/2510-plg-p0b-18-stage2-fold` 枝 `ec7ca77c`。main 未取り込み)。
- 既知類型との関係: `docs/DEFECTS.md` の既存行 (D1a〜D23) に該当なし。新類型候補 D24 の行案は REPORT_2510 §6 (PM 判断・本件で登録しない)。icall §4 の D1〜D13 とは対応を取っていない。
- **結論 (1 行)**: BLK の VA `0x8A1000` は据え置き、再配置する関数・stub を BLK 域 `[blk, blk+0x280)` の外へ送るよう `icall_rewrite.py` を変えた。交差は旧 1 件 → 0 件、出力 PE の BLK 域 640 B は全て 0。

## 0. 検証起点と測定 commit

- 検証起点: `origin/main` `acb7d6d4`。worktree `../ws-2565`・branch `2565-icall-blk-placement`。
- **測定 commit (コードを変えた最後の commit): `f4be6900`** (`tools/icall/icall_rewrite.py`・`tools/icall/check_blk_domain.py`)。
- 差分の確認 (本書の commit より後も、コード範囲は変わらない):
  ```
  git diff f4be6900 HEAD -- tools/icall ':!*.md'     # 出力は空 (差分 0)
  ```
- 素材: `work-fw-stage1` を repo ルートで展開 (tar 内の path が `tools/plugins/work/fw/` を含む)。`fl-win64` は `extracted/block18983_PE.bin` のみ `$RUNNER_TEMP/fl-win64/` へ展開 (`FL_WIN64_DIR` 相当)。他の素材は使わない。
- F.ranges は `tools/icall/mk_franges.py` で作った (fw_prep.py は `work/fw_hash_counts.json` を要するため使わず。規約は同じ。11,736 件 = 成果物 `fw_map.json` の `nfuncs`)。
- 実行環境: runner 4 vCPU・RAM 15 GiB。並列 1 (icall_rewrite は直列)。所要は実測 (下表)。load は終了後の 1 分値 `0.20` のみ採った (実行中の load は未計測)。

## 1. 配置の方式 (issue の 2 案と採らなかった理由)

issue の受入 1 は「`sect_end` 以降へ置く」か「BLK 専用の書込み可能セクション」を挙げる。どちらも採らず、**BLK の VA を据え置く** 方式にした。

| 案 | 内容 | 採否 | 根拠 |
|---|---|---|---|
| (a) BLK を `sect_end` 以降へ移す | BLK の VA が変わる | 不採用 | BLK の VA `0x8A1000` は消費側に直書きされている: `fw_rt.c`・`fw_boot.c`・`hostshim/hostshim.c` `hs_plug.c` `hs_utl.c` (`FW_BLK`)、`fw_run.mjs`・`hostshim/hs_*.mjs` (`0x8a1000+o` を 0 埋め)、`fw_stage2.sh`・`fw_table.py`・`fw_retw.py`・`fw_hostfix.py`・`hostshim/hs_*.sh` (`--blk 0x8A1000`)。移すと、`fw_run.mjs` 系の 0 埋めが再配置済みの関数コードを壊す (silent)。 |
| (b) BLK 専用の書込み可能セクション | 別セクションに置く | 不採用 (今回) | `0x8A1000` は `.icall` の VA 範囲 (`0x7A1000`〜) の中にあるため、別セクションにするには `.icall` を BLK の前後で分割し、PE のセクション表を変える。関数の配置は (c) と同じく BLK 域を空けることになる。RetDec が BLK slot を `constant` にする機構も未特定 (REPORT_2510 §3.3) なので、機構が分かってから選ぶ案として残す (子 #2566 の調査項目)。 |
| (c) **採用**: VA 据え置き・再配置を `place()` で BLK 域の外へ送る | `.icall` 内に 0 埋めの 0x280 B を残す | 採用 | 消費側の変更が 0。BLK 域は `[0x8A1000, 0x8A1280)` のまま。BLK より後ろの関数は VA が変わる (同入力の旧版と比べ 11,736 件中 9,567 件がシフト。BLK より前の 2,170 件は 2,169 件が VA 不変で、移動したのは BLK と重なっていた `0x494cf0` の 1 件だけ)。成果物 (stage-1) は旧 layout なので子 #2566 で再生成する。 |

実装 (`icall_rewrite.py`): `blk` を layout より前に決める (既定値は不変)。`place(c, n)` は `[c, c+n)` が BLK 域と重なれば BLK 域の直後 (16 byte 整列) へ送る。関数の配置・stub・comis_stub の全てに適用する。`blk_overlap()` は再配置範囲と BLK 域の交差を返し、交差があれば `sys.exit` (fail-closed)。BLK 域は emit 前に 0 埋めし、emit 後に非ゼロが無いことを assert する。map に `blk_reserve` (0x280) を足した。

## 2. 検査の数値

検算は `tools/icall/check_blk_domain.py` (交差は開始 VA でソートして二分探索。`icall_rewrite.py` の線形フィルタとは別算法)。

| 入力 | 交差 (BLK 域 0x280) | 非重複違反 | rc |
|---|---|---|---|
| 成果物 `fw_map.json` (旧 layout) | **1** (`0x494cf0` = `[0x8a0fe0, 0x8a1271)`。REPORT_2510 §3.2 と一致) | 1 (※ 下の注) | 1 |
| 同じ入力・旧コード (`acb7d6d4`) の再生成 | 4 (`0x48a5c0` ほか) | 0 | 1 |
| 同じ入力・修正版 (`f4be6900`) | **0** | 0 | 0 |
| 修正版 + `--blk-va 0x8a0fe0` (旧関数位置へ強制) | 0 | 0 | 0 |

- ※ 成果物の非重複違反 1 件は `stub` (0xd01e20) と `comis_stub` (0xd01e70) の重なりで、成果物は古い版で作られ `stub_len` キーが無い (stub 長 0x50)。現版の stub 長は 162 B のため、`check_blk_domain.py` は既定値 162 を当てて数えている。成果物の再生成は子 #2566。
- **成果物は現版で再生成できない** (同じ PE と同じ F.ranges で `section_size` が `0x560E8D` ではなく `0x5A650D`、交差も 1 件でなく 4 件)。したがって成果物の 1 件は「旧配置の基準値」としてだけ使う。修正の判定は同じ入力での旧版と新版の比較で取る。

出力 PE (`f4be6900` の `icall_rewrite.py`・入力 `block18983_PE.bin`):

| 項目 | 値 |
|---|---|
| `.icall` の VA・VirtualSize・flags | `0x7A1000`・`0x5A67FD`・`0xE0000060` (旧 `0x560E8D` ではなく同入力の旧版 `0x5A650D` より +0x2F0) |
| BLK 域 `[0x8A1000, 0x8A1280)` (640 B) の非ゼロ数 | **0** (`check_blk_domain.py` の pefile 読み出し) |
| 同 (objdump) | `objdump -s -j .icall --start-address=0x8a1000 --stop-address=0x8a1280` の 40 行が全て `00000000 00000000 00000000 00000000` (非該当 0 行) |

ネガティブコントロール:
- 交差数の差: 旧 4 件 (同入力) / 旧 1 件 (成果物) → 修正版 0 件 (上表)。
- `blk_overlap()` の境界 (半開区間): `[0x8a0fe0,0x8a1271)` → 1 件 / `[0x8a1280,0x8a1300)` → 0 件 / `[0x8a0f00,0x8a1000)` → 0 件。
- fail-closed の `sys.exit` 経路は、`place()` が BLK 域を避けるため CLI からは到達しない (BLK をどの VA にしても交差 0)。検出器 (`blk_overlap`) の境界で検査し、経路そのものは到達しないことを確認した。

回帰 (BLK が再配置範囲と交わらないときに挙動を変えていないこと): `--blk-va 0x9000000` で旧版と修正版を比べた → **DLL は `cmp` で一致**、map は `blk_reserve` キーの追加のみ。

## 3. 実測 (所要・並列・load)

| 手順 | commit | 結果 | 所要 (実測) | 並列 / load |
|---|---|---|---|---|
| 旧コードで同入力の再生成 | `acb7d6d4` | rc 0 (`section +5924109 B`・交差 4) | 22 s (15:17:06→15:17:28) | 1 / 終了後 0.20 |
| 修正版で同入力の再生成 | `f4be6900` | rc 0 (`section +5924861 B`・交差 0) | 23 s (15:19:04→15:19:27) | 1 / 終了後 0.20 |
| `check_blk_domain.py` (4 入力: 成果物・同入力旧版・修正版・強制 `--blk-va`) | `f4be6900` | rc 1・rc 1・rc 0・rc 0 | 各 1 s 未満 | — |

## 4. 変更ファイル

- `tools/icall/icall_rewrite.py`: `BLK_RESERVE`・`blk_overlap()`・`place()`・BLK 域 0 埋め・事後 assert・map の `blk_reserve`。
- `tools/icall/check_blk_domain.py` (新規): 交差の独立検算と PE の BLK 域読み出し。
- `tools/icall/mk_franges.py` (新規): 再現用の F.ranges 生成。
- `tools/icall/REPORT_APPENDIX_2565.md` (本書)・`docs/DOC_MAP.md` (登録)。

再現 (repo ルートで。素材は `$ARTIFACTS_DIR` から展開済みとする):
```sh
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst                          # tools/plugins/work/fw/ (gitignore)
mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 extracted/block18983_PE.bin
cd tools/plugins/work/fw
python3 ../../../icall/mk_franges.py $RUNNER_TEMP/fl-win64/extracted/block18983_PE.bin > F.ranges
python3 ../../../icall/icall_rewrite.py --pe $RUNNER_TEMP/fl-win64/extracted/block18983_PE.bin --funcs F.ranges --out $RUNNER_TEMP/new.icall.dll --map $RUNNER_TEMP/new.map.json
python3 ../../../icall/check_blk_domain.py $RUNNER_TEMP/new.map.json $RUNNER_TEMP/new.icall.dll; echo rc=$?   # 期待: cross=0, nonzero=0, rc=0
python3 ../../../icall/check_blk_domain.py fw_map.json; echo rc=$?                                       # 期待: cross=1 (旧配置の基準), rc=1
```

## 5. 受入条件の状態 (issue #2565)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. BLK を再配置範囲の後ろ・または専用セクションへ | **達成 (方式は (c))**。issue の 2 案は §1 の理由で採らず、BLK 域を再配置範囲の外へ置いた | §1・§2 (交差 0) |
| 2. BLK 域と再配置範囲の交差を検査し、重なれば exit 1 | 達成 (`blk_overlap` + `sys.exit`。経路は CLI から到達しない) | §2 の境界テスト |
| 3. BLK 域を 0 埋め・コードバイトを残さない | 達成 | §2 (640 B の非ゼロ 0・emit 後 assert) |
| 4. 負のコントロールを数値で | 達成 (旧 1 件 (成果物) / 4 件 (同入力) → 修正後 0 件) | §2 |

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| stage-1 の再生成 (RetDec) と stage-2 smoke の PASS (n≥3)・`init_reach` の計測 | 本件の効果は未確認。成果物 `work-fw-stage1` は旧 layout で、現版から再生成できない | 子 **#2566** `[PLG-P0b-21]` (既存) |
| RetDec が BLK slot を `constant` として宣言する機構 (REPORT_2510 §3.3) | 0 埋めで `"$"` の fold は消えるはずだが、0 への fold が起きるかは未確認。起きる場合は (b) の別セクション案を検討 | #2566 の調査項目 |
| DEFECTS.md の D24 候補の登録 | 類型が未登録 | PM 判断 (REPORT_2510 §6) |
