# lift2 REPORT FA-8 — Filter model setter の wasm 側 bit-exact と型別 ID 感度 (#648, Refs #452 #51)

既知類型との関係: 該当なし (lift 欠陥の新規類型は無し)。ただし **FA-7 (`REPORT_FA7.md`) の probe に測定バグを 1 件発見・修正** (§3)。
検証起点: base = `origin/452-fa-filter-param-id` e47f751 (FA-7 PR #649 の head)。FA-7 は未 merge のため本 PR の diff に #649 の commit を含む (merge 順: #649 → 本 PR)。

## 1. 結論 (先出し)

**部分達成 (Closes ではなく Refs)。受入条件 5 項のうち 3 (型別) と 4 (wasm setter の bit-exact) を達成、1・2・5 は未達。**

| # 本 issue の項目 | 状態 | 根拠 |
|---|---|---|
| 1. 実 controller map 経由の ID 解決先の実測 | **未達** | §4 に静的読みのみ (推定)。実行していない |
| 2. preset DUMP の接続表経由で Filter ID 1〜4 に届くか | **未達** | 未着手 |
| 3. type enum 別 (FA_TYPE) の実測 | **達成 (model 層のみ)** | type 0..7 の 8/8 で ID 0x157/0x158/0x15a の setter は Filter 出力不変 (§2 G2) |
| 4. wasm 側に setter を `--root` 追加し setter 後 native/wasm bit-exact | **達成** | 400 本 × fma0/1 全バイト一致 (§2 G1) |
| 5. Compressor/Gain model の同 ID 意味 | **未達** | 静的な手掛かりのみ (§4) |

「macro は Filter 係数を変えない」とはまだ結論しない。model 層 setter (`0x1803debc0`) 経由では変えない、までが native/wasm 両方で実測された範囲。

## 2. 実測 (再現: `bash tools/targets/freshair/lift2/run_fa8.sh`)

構成: `build_setter.sh` が Filter model ctor `0x180b4c040` + setter `0x1803debc0` + Filter process `0x180b6f050` / reset `0x180b6f390` を mlift → wasm。
**198 関数 / 193,492 B / 35,207 命令 / 非対応 0** (mlift report の値)。descriptor の range object が setter 内で vtable 間接 call されるため、
5 本の vtable (0x1810ca8a0/ca910/ca980/cead8/fa958) の全 slot 先 29 VA を `vt_slots.py` で自動列挙して `--icall` 登録する (固定 12 slot では slot 12 以降 `0x1803de640` 等が未解決で wasm が trap した = 実測)。

| 判定 | 内容 | 結果 |
|---|---|---|
| G1 | ランダム 400 シナリオ × fma0/1。各: type 0..7 / setter 1〜8 回 (ID 母集団: DSP 実読出し {1,2,3,4,416} 30% / 0x156..0x15b 25% / 311..410 20% / 155..254 10% / 全域 15%) / process 1〜3 回 (各 64 sample・L/R)。比較: L/R 全バイト + DSP が読む M param 5 dword | native 行 400 / wasm 行 400、ERR 0/0、**mismatch 0** (fma0・fma1 とも) |
| G2 | type 0..7 それぞれで {base, 0x157+0x158+0x15a 設定, ID2+ID3 設定, ID4 設定} を同一入力 seed で process 3 回し L/R を比較 | 0x157+0x158+0x15a は **8/8 type で出力不変** (native・wasm 一致) |
| G3 陽性対照 | 同上の ID2+3 / ID4 | ID2+3 (周波数/Q) は **8/8 type で出力が変わる**。ID4 は **type 4,5,6 のみ**変わる (native・wasm 一致) |

数え方: シナリオ = 1 回の (ctor → setter 列 → process 列)。mismatch = native と wasm の出力行が 1 文字でも違う行数 (`paste | awk`)。
ID4 が type 4..6 でのみ効くのは、`run_fa7.sh` で `FA_TYPE=0..7` に変えた実測 (ID 4: chg=3 は t4,t5,t6 のみ) と一致。

**既知の制約**: ID 416 (0x1a0) は整数 enum (descriptor 既定 1)。float bits を渡すと process が範囲外で落ちる (初版の生成器で 40 本中 4 本が native・wasm とも PROCERR)。`gen_setter_scen.py` は 416 に整数 0..4 だけを渡す。

## 3. FA-7 probe の測定バグ修正 (重要)

FA-7 の `probe_setid.c` は M0 に setter を適用してから **複製 T で process** を走らせていた。setter は M 内の descriptor を M0 内への絶対ポインタで引くため、
書込みは M0 側に入り T の出力は構造的に変わらない。実際 **ID 2 (周波数) / ID 3 (Q) でも outChanged=0** だった (= FA-7 の「不変 18/18」は陽性対照の無い空洞な測定)。
修正後 (setter を適用した M0 そのもので process): ID 2/3 は 3 値とも outChanged=1、ID 0x156..0x15b は従来どおり 18/18 不変。**FA-7 の結論は変わらないが、根拠が初めて有効になった**。
`run_fa7.sh` に陽性対照 `ID2/ID3 の outChanged=1 が 6/6` を追加 (修正前 probe なら FAIL する)。

## 4. 静的読み (推定。実行していない)

- `.pdata` 全 25,063 関数の呼出元走査 (`fa8_scan.py`、10.8 s): `0x180ca1480` の呼出元は `0x180c9d700` のみ / `0x180c9d700` の呼出元は slot[12] `0x1803dfc10` の 3 箇所 + 自己再帰 / `0x180ca7db0` (map 検索) の呼出元は 5 関数。
- `0x180ca1480(C, out, key)`: key={count,idx}。`C+0x2d0 != C+0x328` かつ count==1 かつ idx==0 のとき **map を引かず** `{C+0x308, C+0x470}` を返す (静的読み)。それ以外は `C+0x318` の木を key u16 で `0x180ca7db0` 検索。
  macro 経路の key は FA-4 実測で `{1,0}` (`MAPTRACE keycnt/key0`)。したがって実機で `C+0x2d0 != C+0x328` なら、ID は **子 snapin 自身の param block** で解決される可能性が高い (その場合の最終 setter は model 層と同系で 0x157 は汎用バンク slot のまま = 推定)。`C+0x2d0 == C+0x328` なら map 検索 (本 issue 項目 1 の実 map が必要)。
- 実機の `C+0x2d0` / `C+0x328` が等しいか、`C+0x318` の木に何が入るかは **PE の静的解析では決まらない** (実行時構築)。FLEngine 側の snapin 構築 (`FLEngine` boot 連鎖, #227 FLE 系) が必要。
- 項目 5 の手掛かり: 即値 0x157 を `mov edx, 0x157` で使う関数が 6 (`180e38e10 180e6f3b0 180ea6b10 180f567e0 180fa1340 180fd5630`, 各 21 hit)、`imul rcx, rcx, 0x157/0x158/0x15a` を持つ関数が 6 (`180e5d6a0 180e94680 180f2b1b0 180f7c790 180fc4a20 180ffa240`) ある (`fa8_imm.py`、全 161 関数中。`sub rsp, 0x158` 等の無関係ヒットを含む)。他 model の descriptor 登録 ctor の可能性があるが **未解析**。

## 5. 検証結果 (コミット済み HEAD 413f4e3, 実測)

| 項目 | 結果 |
|---|---|
| `run_fa8.sh` (n=3) | **ALL PASS ×3**。所要 4.41 s / 4.39 s / 4.42 s (実行後 load average 1.07 / 1.14 / 1.13、並列 1) |
| `run_fa7.sh` | **ALL PASS**, 2.96 s (判定 6 + ネガコン 3) |
| `lift2_e2e.sh` | **FAILED**, 71.84 s。内訳: comp 400/400 / filter 400/400 / fuzz 4×1200 mismatch 0 / ABI 0 違反 / **工程 6 (ctrl) が FAIL** (`mlift: rep prefix rep movsb` 非対応で ctrl wasm が作れず native_ctrl が Abort)。**`origin/main` 0865903 の clean worktree でも `build_ctrl.sh` + `run_ctrl.sh` が同一 FAIL を再現** (本 PR 無関係)。環境は capstone 5.0.7 / python 3.14.8 (capstone 4 は distutils 欠落で導入不可)。原因 (capstone 版) は未検証の推定。起票先は §6 |
| ネガティブコントロール (`run_fa8.sh`) | NC1 wasm 出力 1 文字改竄 → mismatch=1 で FAIL / NC2 wasm 出力 399 行に欠落 → 行数不一致で FAIL / NC3 実判定に「0x157 行を ID2+3 行に差替え」を食わせ不変 type 集合が空 → 8/8 判定が FAIL / NC4 「ID2+3 行を base 行に差替え」で陽性対照 8/8 判定が FAIL。**4/4 が期待どおり FAIL** |
| fail-closed | 行数 N 必須 (空・欠落 PASS 拒否) / ERR 1 件でも FAIL / 不合格は `exit 1` / 前提不足は `exit 2` |

`git status --porcelain=v1 -- tools/targets/freshair/lift2` clean、20 MiB 超 blob なし (生成物 `fset.ll` 21 MB は `work/` で gitignore)。

## 6. 範囲外 / 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 controller map (`C+0x318`) を構築して `0x180c9d700` を実行し ID の解決先を実測 (項目 1)。`C+0x2d0 == C+0x328` の別が鍵 (§4) | 本 issue の主目的 | #665 [FA-9] |
| preset DUMP 接続表経由の到達 (項目 2) | 最終説明 | #665 [FA-9] |
| Compressor/Gain model の同 ID 意味 (項目 5)。§4 の 12 関数が手掛かり | 範囲外 | #665 [FA-9] |
| `lift2_e2e.sh` 工程 6 (ctrl) の `rep movsb` 非対応 FAIL (main でも再現) | lift2 の既存 e2e が赤 | #666 [FA-10] |
| `docs/DEFECTS.md` 行案: 「測定器が構造的に出力を変えられない空洞な不変判定」(setter が M0、process が複製 T) — 陽性対照の欠如が原因 | 類型候補 | PM 判断 (DEFECTS.md の直接編集はしない) |
