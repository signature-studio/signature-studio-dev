# M11 652500 の 1 段 deref 復元 (gate 付き, #748, 部分達成)

親: #748。子 issue: #1019 (unit 149 の `412e40 ← 653660` の原因特定 と unit 888 の ok→halt0 退行)。関連: #683 (414ad0 の ldfix 復元), #901 (M11-N48, 同型 `412d60(&slot)` の D4 判定)。
変更: `m11_ov.c` の `function_652500` を `M11_FIX_652500` (既定 0) で gate。`m11_build.sh` は `M11_FIX_652500` を ov.o の stamp に含めて切替時の古い ov.o 再利用を防ぐ。既定 0 のため既定ビルドの挙動は変わらない。`m11_survey.mjs` に `M11_SURVEY_DETAIL` (unit 別の kind と trap 種別) を追加。

## 1. 測定条件 (前回 run の実測・生データはコミット済み)

- 数値の出所: コミット済みの生データ `tools/m11/results/N748/` (測定コード head `41d0516b`)。本節は、その測定時の条件を記録したもの。**本 fix run では再測定していない** (`$ARTIFACTS_DIR` に `fl-win64` が無く、`m11_gen_ir2.sh` を実行できないため)。
- 測定 base: **`origin/main` `6e96689d`** (PR ブランチの merge-base)。**main 追従後の再測定は未実施** (本 PR で base に関する数値を記載する箇所はこの 1 つ)。
- 測定コード: PR HEAD `41d0516b` (`935fdc65` + `m11_survey.mjs` の `M11_SURVEY_DETAIL` 追加)。
- 素材 (測定時): `fl-win64` (`$RUNNER_TEMP/fl-win64`)、`work-m11` (`tools/m11/work/` 233 件)、`toolchain-emsdk` (`/opt/emsdk`, emcc 6.0.12)、`toolchain-retdec` (`/opt/retdec`)。展開は `tar --zstd -xf` (work-m11 含め計 8 秒)。
- 依存: `capstone 5.0.7` / `pefile 2024.8.26` を `pip install --user` (`m11_gen_ir2.sh` の ldfix が要求)。
- 手順: `m11_gen_ir2.sh` → `M11_FIX_652500={0,1} m11_build.sh` → `M11_SURVEY_UNITS=… M11_SURVEY_DETAIL=… node m11_survey.mjs` (OFF/ON 直列)。
- 実測時間 (wall, 秒): `m11_gen_ir2.sh` 43 / build OFF 24 / survey OFF 14 / build ON 19 / survey ON 9。runner は 4 vCPU・15 GiB。load average は未記録。
- wasm sha256 (先頭 16 桁): OFF `179a849040d388a9` / ON `1ab8848813ac1db4` (gate は実際にビルドへ効いている)。
- 再現性: ON の survey を 2 回実行し、`survey_on_detail.json` が `cmp` で一致 (決定的)。
- 生データ: `tools/m11/results/N748/` (`survey_{off,on}_units.json` = 粗い kind 942 件、`survey_{off,on}_detail.json` = kind + trap 種別、`survey_{off,on}.txt` = 要約、`survey_on_run2.txt`)。

## 2. 集計表 (実測, HEAD 41d0516b 相当・base 6e96689d)

| 構成 | ok | oob | halt0 | miss | unreachable | noproc | oom+halt0 | 計 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| OFF (`M11_FIX_652500=0`) | 869 | 16 | 7 | 47 | 1 | 1 | 1 | **942** |
| ON (`M11_FIX_652500=1`) | 869 | 17 | 6 | 47 | 1 | 1 | 1 | **942** |

- 合計は 942 に揃った。前回表 (941 / 表記 942) の 1 件差は、表に列が無かった **noproc (unit 941, `0x0`)** で、前回は数え落としだった。
- 前回表 (OFF oob 16 / halt0 8、ON oob 15 / halt0 9) は今回の実測と一致しない。前回値は再現できなかったため、本ファイルから除いた。
- `survey` の `ok` 869 / `miss` 47 / `trap` 25 / `noproc` 1 は OFF/ON とも同じ。`trap` 25 は oob 16 + halt0 7 + unreachable 1 + oom-halt0 1 (OFF)、ON は oob 17 + halt0 6 + unreachable 1 + oom-halt0 1。

## 3. kind 変化 (実測, OFF → ON)

per-unit detail (942 件) を直接比較した結果、**kind が変わった unit は 1 件 (unit 895, `0xeddfe0`)**。

| unit | VA | OFF | ON |
|---|---|---|---|
| 895 | 0xeddfe0 | trap: halt0 → longjmp | trap: memory access out of bounds |

- 前回 PR 本文・旧 §3 が挙げた 8 unit (280 291 296 302 304 368 659 888) は、今の head では **OFF/ON とも kind が同じ** (下表)。前回の遷移記録は再現しなかった。
- 888 (`0xeaea40`) は OFF/ON とも ok。前回記録の「ok → halt0 退行」は再現しない。
- 149 (`0x264260`) は OFF/ON とも oob (変化なし)。前回記録の `412e40 ← 653660` の frame は、この survey の出力 (粗い kind と trap 種別のみ) からは確認できない。frame の詳細は別途 `M11_SURVEY_STACK=149` で取る必要がある (未実施)。

| unit | VA | OFF | ON |
|---|---|---|---|
| 149 | 0x264260 | oob | oob |
| 158 | 0x26d1a0 | ok | ok |
| 280 | 0x416010 | oob | oob |
| 291 | 0x432660 | ok | ok |
| 296 | 0x446130 | ok | ok |
| 302 | 0x46d240 | ok | ok |
| 304 | 0x483140 | oob | oob |
| 368 | 0x5810f0 | oom + halt0 | oom + halt0 |
| 659 | 0x8eaa30 | oob | oob |
| 888 | 0xeaea40 | ok | ok |
| 895 | 0xeddfe0 | halt0 | **oob** |

- ok 件数が OFF/ON で同じ 869 なのは、kind の遷移が 895 の 1 件だけなので当然。前回の「888 の ok→halt0 を相殺する ok 化」という説明は不要になった。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 895 (`0xeddfe0`) が halt0 → oob に変わる理由 (652500 の復元が 895 の経路を変えた) | ON で 895 の trap 種別が変わる。ok 化・退行いずれかは未判定 | #1019 |
| unit 149 の `412e40 ← 653660` の原因 (frame の詳細は未取得) | 受入条件 1 未達 | #1019 |
| 同型 `412d60(&slot)` 呼びの残り D4 判定 | 他 unit の silent 誤動作の恐れ | #901 |
| main 追従後の再測定 (§1 の base 以降の main 差分) | 現 main との差は未測定 | 本 PR の続き (追従 merge 後に再測定) |
| closure (7421 関数) と liftdiff への波及 | 未測定 | #1019 |

## 5. 前回記録との差分 (訂正)

- 前回 (初回 run, base 6e96689d) の表・kind 変化・888 退行の記述は、今回の素材・手順では再現しなかった。今回の結果を正とする。
- 前回の「ON で 888 が ok→halt0 退行」は誤り。ON の 888 は ok。ON 時の退行は unit 895 (halt0 → oob) の 1 件。
