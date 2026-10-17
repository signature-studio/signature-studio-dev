# tools/plugins/p0c REPORT 付録 N (§27) — #3281 残件 B: 0x5e12c0 の ucomisd flags を一般 pass で接続

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。親 #3952 (手書き本体の削減)・#3281 (k80_hand_bodies 残件)。

## 27. 0x5e12c0 (in-place clip) の手書き本体を一般 pass に置換

### 27.1 結論

- 0x5e12c0 の手書き本体を外し、`k80_ucomi_br.py` (新規・一般 pass) で置換した。`k80_hand_bodies.py` の BODIES は **14 → 13**。
- 2000 case・10000 case の buf_diff は **0** (負論対照 `K80_NO_UCOMI_BR=1` で 2000 case の buf_diff = 1,814,580)。
- 残りの BODIES は 13 本 (0x5dfff0 / 0x5dee20 / 0x5e0300 / 0x5dee50 / 0x5de620 / 0x5dedb0 / 0x5dea40 / 0x5dec40 / 0x5dffc0 / 0x5e1490 / 0x5df340 / 0x5dfae0 / 0x5e0350)。

### 27.2 根本原因 (機械語と raw lift の突き合わせ)

- 機械語 (VA 0x5e12f6〜0x5e12fa): `ucomisd xmm0, xmm1` の直後に `jbe 0x5e1304`。jbe は CF|ZF (非順序を含む) で分岐する。
- RetDec の raw lift (`work/k80.final.ll`): `ucomisd` は `call void @__asm_ucomisd(i128, i128)` になり、戻り値 (flags) が捨てられる。分岐条件は `%cf.0.reload` で、`alloca i1` に入った初回値 (`arg2 == 0`) と以降の `store i1 false` の reload になる。
- 結果、分岐は compare の結果に依らず、入力 (`arg2`) の整数判定で決まっていた。
- 対照: 同じ構造の 0x5e12b0 は #3439 の `k80_argfix.py` [D] (`fix_ucomi_flags`) が `or i1 %CF, %ZF` の placeholder を接続して直す。0x5e12c0 は分岐の条件が `reload` 経由の `br` で、placeholder の形ではないため [D] の対象外だった。

### 27.3 修復 (一般 pass)

- `tools/plugins/p0c/k80_ucomi_br.py` (新規): ucomi 直後の基本ブロック内で、唯一の `br i1 %cf.N.reload` の条件を、ucomi のオペランドから作る `fcmp` に置換する。
  - jcc の対応: `jb` → `ult` / `jbe` → `ule` / `ja` → `ogt` / `jae` → `oge` (ucomi の flags は CF = a<b または非順序、ZF = a==b または非順序)。
  - fail-closed: ucomi が無い・分岐が 1 本でない・reload の use が分岐以外にある・function が無いときは止める。1 関数の対象 site が 0 件のときも止める (再実行を含む)。
- 配線: `p0c4_abi_e2e.py` で `k80_deref_fix` の後、ext pass の前に実行 (`K80_NO_UCOMI_BR=1` で外せる)。
- 実 IR の確認: `llvm-as` 通過。生成された式は `%ucb.c = fcmp ule double %ucb.af, %ucb.bf` (double の入力は `%4` = cvtss2sd の結果, `%11` = pand の結果)。

### 27.4 測定

測定 commit は `ba6009b23` (コードを変えた最後の commit)。ブランチ `6047-p0c-ucomi-jbe`。

| 検証 | 条件 | rc | 所要 | 結果 |
|---|---|---|---|---|
| `p0c4_abi_e2e.py 2000` (修復あり) | `K80_NO_UCOMI_BR` 未設定 | 0 | 28.2 秒 | `run=68 ok=68 sig11=0`・CSV 全 68 kernel buf_diff=0・0x5e12c0 buf_diff=0 |
| `k80_diff.py --cases 2000 --only 0x5e12c0` | 修復あり IR (`k80.hb.ll`) | 0 | — | buf_diff=0 |
| `k80_diff.py --cases 10000 --only 0x5e12c0` | 修復あり IR (`k80.hb.ll`) | 0 | — | buf_diff=0 |
| 負論対照 `K80_NO_UCOMI_BR=1 p0c4_abi_e2e.py 2000` | 修復なし | 1 | 28.1 秒 | `[FAIL] 0x5e12c0 buf_diff=1814580 (期待 0: #2182)`・rc 1 |

- 測定時の load average: 開始 0.47 (06:48 頃)・終了 0.37 程度。4 コア runner。
- 基準 (修復前の HEAD `df5e40d69` の同じ harness): rc 0・30.2 秒・0x5e12c0 buf_diff=0 (旧 hand body 使用)。REPORT_APPENDIX_H §18.3 の census (非 ext 鎖) では 0x5e12c0 buf_diff=1,814,580 で、この差は ext 鎖 (`k80_hand_bodies` 経由) の結果。

### 27.4a レビュー差し戻し (round 1) の対応

- 差し戻し (round 1・round 2) の指摘に対し、`k80_ucomi_br.py` のコードを測定 commit `ba6009b23` の内容に戻した (差分縮小 (b))。残る差分は docstring の訂正のみ。実行結果に影響しないため、測定は `ba6009b23` のまま。
- docstring の訂正: 「冪等」を「再実行は 0 site として fail-closed で止まる」に直した。合成 IR (`/tmp/opencode/ucb_test/in.ll`, `ba6009b23` のコード) で確認: 1 site は `sites: 1` で rc 0・`%ucb.c = fcmp ule double` を生成。その出力を再入力すると `分岐の対象が無い (fail-closed)` で rc 1。
- 戻したため、複数 site の判定 (1 関数に ucomi+分岐が 2 件以上あるときの `%ucb.` 名前衝突) は未実装。将来の対象拡大時に #3952 で扱う (27.5)。現在の対象 0x5e12c0 は 1 site。
- 再測定はしていない: この run では `toolchain-retdec` の素材と `p0c/work` が無く、`p0c4_abi_e2e.py` を実行できなかった。

### 27.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残 13 本の手書き本体 (0x5dfff0 ほか) | BODIES が 13 本のまま | 親 #3952 (本 PR は残件のうち 1 本) |
| 0x5dfff0 等 xmm 入替え・SIMD 加算順・ポインタ global の 3 類型 | 未着手 | 親 #3952 |
| `k80_ucomi_br.py` の複数 site 判定 (1 関数に対象 site が 2 件以上あるときに止める。`%ucb.` の名前衝突防止) | 現在の対象 0x5e12c0 は 1 site のため影響なし。対象を広げる前に必要 | 親 #3952 |
