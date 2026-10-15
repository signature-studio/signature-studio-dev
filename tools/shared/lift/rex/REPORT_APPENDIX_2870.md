# tools/shared/lift/rex 付録 — REPORT §9 全文 (T-SH-46 / #2870)

## 9. 成功経路 (戻り値 1 / 3) と書込の一致 — T-SH-46 (#2870, 部分達成)

測定 commit: `80c5ff7a` (`tools/shared/lift/rex/` の最後のコード変更)。以降の差分は本 REPORT のみ (差分 0 の証跡は §9.6)。
既知類型との関係: 該当なし (不一致 0)。

### 9.1 結論 (1 行)
木の根 (ctx+0x20) の key をアリーナ内オブジェクト O に向け、O+0x688 → B の経路を作る 48 件を追加した。比較 175 件のうち戻り値 1 が 29 件・3 が 13 件、アリーナ書込が 42 件で、元の機械語と全バイト一致 (不一致 0)。**`.data` への書込は 0 件で `.data` の一致は未検証**。落ちた 73 件のうち 36 件は入力から原因を説明できたが、37 件は未分類。movnti (24 箇所) は wasm 側で未到達 (traps 0)。

### 9.2 方法
- 成功経路の入力 (`gen_cases.py` の末尾 48 件・seed 2870・fn=0): 0x2260 の逆アセンブルから、戻り値 1 は 0x1de0 (木の検索 0x1a80 = 連結リストの先頭から key を比較) → 0x12a50 (`cmp [key+0x688],0`) → 0x12ed0 (B の SSO 文字列 3 本を出力へ書く) の経路。`key_of` は対合 (`key_of(key_of(a)) = a`) なので、`a0 = key_of(O)` (O = ARENA+0xC200) で木の key が O になる。B = ARENA+0xC300、B+0x28/+0x50/+0x78 = 0 (SSO)。O+0x688 = 0 の 1/4 は戻り値 3。a1 ∈ [0x500, 0x800)、a2 は arena 内。
- gate 追加 (`diff_test.py`): 戻り値 1・3 がそれぞれ 1 件以上、書込 case が 1 件以上、でなければ FAIL。
- 落ちた case の分類 (`crash_class.py`・新規): 入力から予測する原因 (ctx-null = ctx 0 で addr 0x8、key-deref = addr が key+0x688、timeout、out-overrun)。

### 9.3 実測 (測定 commit `80c5ff7a`・測定 HEAD `acafc52b5`・`bash tools/shared/lift/rex/lift_x64c.sh all` を 3 回)
| 項目 | 値 |
|---|---|
| `ok` | PASS。比較 175・一致 175・不一致 0。除外 73 (SIGSEGV/SIGBUS 72・SIGALRM 1) |
| 戻り値 (比較対象) | 0xca 44 / 0xcb 48 / 0xcc 41 / **1: 29** / **3: 13** |
| 書込 (比較対象) | arena 書込 42 件 (全件一致)・`.data` 書込 0 件 |
| 落ちた 73 件の分類 (`crash_class.py`) | ctx-null 24 / key-deref 11 / timeout 1 / **未分類 37** |
| wasm の traps (248 件) | 0 (movnti 24 箇所は比較入力で未到達。到達すれば fail-fast で trap) |
| `neg-cmp` | FAIL (期待どおり・1 件不一致) |
| `neg-ctx` | FAIL (期待どおり・全件不一致) |
| 所要 (`elapsed`・n=3 の min–max。3 回の件数は上表と同一) | ok 2–3 s・neg-cmp 2–3 s・neg-ctx 3 s。lift・emcc・native・node・diff を含む。load (1 分値) は各 mode の開始時 0.00〜0.34・並列数 4 (`nproc`) |

### 9.4 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未分類の落ち 37 件 (fn=0 が 14・fn=1 が 23)。fault アドレスは実測で 0x0 が 20 件・arena (0x30100000〜0x3010ffff) 内が 0 件・それ以外が 17 件 (例: 0xc84016c0・0x7bf41e92)。原因は未特定 (推定は未確定) | 比較数 175/248 | #3588 (T-SH-89・受入 3) |
| `.data` への書込を伴う成功経路が無い (`.data` の一致は未検証) | 受入 2 の `.data` 部分が未達 | #3587 (T-SH-88・受入 2) |
| REXGetInfo (fn=1) の成功経路 (戻り値 1) の入力は未構成 | fn=1 の書込は未検証 | #3587 (T-SH-88・受入 2) |
| movnti 24 箇所の到達 (traps 0 のため比較入力では未到達) | 到達すると fail-fast。x64c 対応の要否は未決 | #3589 (T-SH-90・受入 4) |
| side module 化・ビルドフラグ (受入の範囲外) | 公開 tier への混入防止が未実装 | #2896 (T-SH-47) |

### 9.5 検証範囲
- **検証した**: 戻り値 1 / 3 の経路に入ること (29 / 13 件)、arena 書込 42 件の全バイト一致、ネガコン 2 件の FAIL、traps 0。
- **範囲外**: `.data` への書込 (0 件)、fn=1 の成功経路、movnti の到達、未分類 37 件の原因。

### 9.6 測定後のコード差分 (差分 0 の証跡)
`git diff 80c5ff7a HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (0 = コード差分なし)。
