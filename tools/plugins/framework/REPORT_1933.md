# #1933 REPORT — 0x4181e0 の基底構造体と native 境界の確認 (途中経過)

- 担当 issue: #1933 `[PLG-P0b-10]` (親 #1891・#1891 は CLOSED)。
- 起点: `origin/main` 46faf265。worktree `ws-1933`・branch `1933-plg-p0b-10-base-struct`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`。`work-fw-stage1` をリポジトリ直下に展開。
  `work-liftlib` / `toolchain-*` / `plugins-ott` は本 run で未使用。

## 1. 受入条件の達成状況

本 PR の範囲は受入 3 の VA 境界修正と受入 4 (REPORT)。受入 1・2 と受入 3 の残りは子 #2016 `[PLG-P0b-12]` へ移管した (issue #1933 本文も縮小済み)。

| # | 受入条件 | 結果 |
|---|---|---|
| 1 (移管 → #2016) | `0x4181e0` の呼出元の基底構造体 (`+24` / `+520`) を確定 | **未達**。§3.2 で未確定の理由を記録 |
| 2 (移管 → #2016) | `0x4181e0` の正しい戻り値を確定し `fw_hostfix.py` を修正 | **未達** (1 が前提。コード変更なし) |
| 3 (本 PR) | `hs_callee_disasm.py` の VA 境界を修正 | **達成** (§3.1)。`@441`/`@443` の文言確認は #2016 へ移管 |
| 4 (本 PR) | REPORT に実測 (所要時間・load・PASS/FAIL) と Phase A 回帰 `dispatch=38 ff=0` | **達成** (§2) |

## 2. 実測

環境: 4 vCPU・メモリ 15 GiB。load は `uptime` の 1 / 5 / 15 分値。

| 手順 | commit | 結果 | 所要時間 (real) | load (開始時) |
|---|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用) | 46faf265 (`hs_callee_disasm.py` 変更前) | exit 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 458.49 s | 0.26 / 0.39 / 0.21 (07:59) |
| `hs_e2e.sh --fresh` | 46faf265 (同上) | exit 1 / Phase A `dispatch=38 ff=0` (回帰 OK) / `Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` / `E2E FAIL: 1 項目` | 158.40 s | 1.79 / 2.11 / 1.09 (08:07) |

- Phase B の失敗は REPORT_1891 §2 と同一 (OOB・`plug=0x0 rec=7`)。本 run で変化なし。
- `hs_callee_disasm.py` は `hs_e2e.sh` の経路外のため、e2e の測定 commit は 46faf265 のまま。

## 3. 読解

### 3.1 `hs_callee_disasm.py` の VA 境界 (受入 3)

- 修正前: VA から直接読むため、`0x52cf40` は `adc eax, ...`、`0x4181e0` は `je ...` と命令境界を外して出ていた。
- 修正後: `block00031_PE.bin` の `.pdata` (RUNTIME_FUNCTION) で関数境界を引き、関数先頭から逆アセンブルする。
  - `0x52cf40` → 関数 `[0x52ce50, 0x52cf67)`。
  - `0x4181e0` → 関数 `[0x418190, 0x41820c)`。
- `.pdata` に含まれない VA は従来どおり VA から読み、「関数境界なし」と明示する。

### 3.2 `0x4181e0` の native 側 (受入 1・2 の前提)

- `0x4181e0` は関数 `0x418190` の**内部ラベル**。`0x418190` の先頭は `push rsi` で、`[rbx]` を取り出し、
  `lock xadd` の参照カウント処理の後、`[rax+6]` 経由の分岐を経て `call 0x416230` に入る。
  `0x4181e0` 自体は `je 0x4181f6` の位置。
- `.text` 全体の直接 `call` を走査すると、`0x418190` には 2645 箇所の呼出元があるが、`0x4181e0` を直接呼ぶ箇所は 0。
  つまり `hs_flat3.ll` の `@function_4181e0` は、native の関数先頭ではなく lift 側の名前である。
- IR 側の呼出元は `hs_flat3.ll` に 67 件 (9072 行など)。戻り値を `[ret+24]` 系の基底として読む。
- 基底構造体の型は、この内部ラベルの仕様 (0x418190 の引数規約と呼出元) を読まないと確定しない。**本 run では未確定**。
- 補足: `0x4e6060` は `.pdata` の関数に含まれず、その VA の先頭 16 バイトが ASCII 文字列 (`Object>.Parrayof…`) に見える。
  `0x4e5f50` も同様に文字列 (`tem.Generics.Def…`) に見える。REPORT_1891 §3.2 の `0x4e6060` 分岐読解 (IR 側) と、
  native の対応関係は未確認。
- `0x52cf40` の直接 call は 0 件。`.text` 上の関数は `[0x52ce50, 0x52cf67)` の先頭から読むのが正しい。

## 4. 残作業 (子 #2016 `[PLG-P0b-12]` へ)

- 受入 1・2: `0x418190` の引数規約と呼出元 (IR 9072 行 ほか) から、`0x4181e0` の戻り値が指す基底構造体 (`+24` / `+520`) を確定し、`fw_hostfix.py` の注釈を修正する。Phase B の実測を伴う。
- 受入 3 の残り: `0x52cf40` の `@441`/`@443` に対応する native の文言 (見つからない経路の意味)。
- `0x4e6060` / `0x4e5f50` の IR 名と native の対応 (文字列列に見えるため、lift の VA 対応を確認する必要がある)。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1・2: `0x4181e0` の基底構造体と正しい戻り値 | `fw_hostfix.py` の 0 注釈が deref の障害になっている可能性 | #2016 `[PLG-P0b-12]` |
| 受入 3 の残り: `0x52cf40` の `@441`/`@443` 文言 | 「見つからない」の意味が推定のまま | #2016 `[PLG-P0b-12]` |
| `0x4e6060` / `0x4e5f50` の native 対応 | fail-soft 注釈の根拠が未確定 | #2016 `[PLG-P0b-12]` |
| fold deref (`0x40d6e0` / `[0x710040]`) と `plug != 0` | Phase B が OOB のまま | #1890 `[PLG-P0b-8]` / #2008 `[PLG-P0b-11]` (既存) |
| `fw_stage2.sh` の所要時間 | 本 run で 458.49 s を取得 (旧 REPORT_1891 は未計測) | 解消 |
