# lift2 REPORT 付録 — FA-4 (#51): チェーン構成 / マクロ→子パラメタ ID 写像 (REPORT §12 全文)

- 本付録は `REPORT.md` の上限 (250 行) のため分割移動した §12 全文 (`docs/DOC_MAP.md` §1)。内容は無変更。節番号は元のまま。
- 再現: `bash run_chainmap.sh` (FA-4 当時の記録。現 HEAD で再実行していない)。


再現: `bash run_chainmap.sh` (native_ctrl を `FA_MAP_TRACE=1` で実行 → `fa4_chain_map.py` が FRAR/DUMP 解析 + .epf 8 本と突合。実測 3 s)。
`FA_MAP_TRACE` は `0x180c9d700` を観測フックに差替える (harness の controller map は空で実 setter は no-op のため挙動不変。env 未設定時は従来バイナリと同一)。

### 12.1 チェーン (core `.rsrc` `FRAR/DUMP` 2,614 B, preset 名 "FRESH AIR v8")
子 snapin は fourcc (LE 格納) + 名前の順に DUMP へ直列化されており、出現順 = 子リスト index:

| idx | DUMP off | fourcc | snapin |  | idx | DUMP off | fourcc | snapin |
|---|---|---|---|---|---|---|---|---|
| 0 | +0x6a3 | ksfi | Filter | | 4 | +0x821 | ksgn | Gain |
| 1 | +0x6f8 | kscp | Compressor | | 5 | +0x864 | kscp | Compressor |
| 2 | +0x764 | ksfi | Filter | | 6 | +0x8d0 | ksgn | Gain |
| 3 | +0x7b9 | kscp | Compressor | | 7 | +0x913 | ksgn | Gain |

Filter×2 / Compressor×3 / Gain×3 = 8。`native_ctrl.c` の `CHAIN {1,0,1,0,2,0,2,2}` と一致 (スクリプトが assert)。
DUMP 末尾のラベル文字列: `Main`×5 / `HF3` / `HF9` / `Gain` / `Trim` / `Both` / `Macro 6,7,8`。

### 12.2 slot[12] 0x1803dfc10 の写像 (逆アセンブル + native 実測)
子リスト = `[F+0x90]+0xa080` (count=`0x180c8b9c0`, get=`0x180c8b9f0(list,&sp,i)` が shared_ptr を取得)。

| 手順 | 呼出 | 実測 |
|---|---|---|
| 1. マクロ → **子リスト index 0 (Filter)** へ 3 値 | `0x180c9d700(child0, id, value, {1,0})` | 下表。宛先は 3 本とも index 0 固定 (get の r8=0) |
| 2. 全子 (0..7 順) | `0x180ca0d50(child, ctx)` | 8 回 |
| 3. 全子 | `0x180ca2450(child, ctx[+0x28])` → `0x180c9f070(child, 1.0f)` → `0x180ca0d90(child, ctx, 0, 1)` | 子毎 |
| 4. 遅延集計 | `r14 = 0x180c9e040(child)` (最終子の値) → `[F+0x58]` と clamp 後 `[F+0x20]/[F+0x40]` | — |

| マクロ (model M の float) | 子 param ID | 値 |
|---|---|---|
| Mid Air `M+0x9dc4` | **0x157** | `powf(x, 0.62)` (関数 0x18103fd60, 指数は rdata 0x1810cac08 の f32 0.62) |
| High Air `M+0x9e0c` | **0x158** | `powf(x, 0.62)` |
| Trim `M+0x9e60` | **0x15a** | 無変換 (f32 そのまま) |

factory .epf 8 本 (+0x10 = Mid Air, +0x14 = High Air の f32, Trim=0) で native 実測と期待値 (`powf` 0.62) を突合:
**8/8 一致 (ULP 差 ≤2 を許容、実測は全て 0)**、`calls/scenario=9` (3 process 呼出 × 3 ID)、宛先 `k=0 type=filter` 全件、Trim=0 (id 0x15a)。
例: Shiny mid 0.6725 → 0x157=0.7819324 / high 0.75 → 0x158=0.8366389。

### 12.3 検証結果 (HEAD dd9bc5e, 実測)
- `lift2_e2e.sh`: **ALL PASS, 73 s** (Compressor 400/400 / Filter 400/400 / fuzz 4×1200 mismatch 0 / ABI 0 違反 / ctrl 15/15 / ablation 80〜200 mismatch)。
- `run_chainmap.sh`: **OK 8/8**, 3 s。

### 12.4 限界 (未検証の境界)
- **FA-7 (#452) で部分回答 → `REPORT_FA7.md`**: 0x157/0x158/0x15a は Filter model の汎用バンク slot (ID 311..410, 値域 [0,100]) で、model 層 setter では Filter 出力不変 (18/18、setter 陽性対照 6/6 で較正済み。controller map 経由の解決は未実測)。以下は FA-4 時点の記述:
- ID (0x157/0x158/0x15a) が Filter snapin の**どの内部パラメタ**に当たるか (名前・値域) は未解決: harness の controller map (`C+0x318`, `0x180ca7db0` の木) は空で、実 setter は param を解決せず no-op。実 map を構築して Filter の係数が変わることの確認は未実施。
- 宛先が子リスト index 0 の Filter 固定である点は静的 (get の r8=0) + 実測で確定。他 7 子へマクロは直接届かない (子自身の param は preset DUMP 由来の値で、本関数は触らない)。
- .epf の他フィールド (+0x4cc/+0x4d4 の 1、Mixbus 系の +0x4d8 f32 -0.93/-1.41 等) の意味は未解析 (macro 以外は現行 slot[12] 駆動に影響しない)。
- FA-10 (#666, 2026-10-13): 工程 6 (ctrl) FAILED の原因は epf 素材の展開漏れ (epf を展開すると同一コードで ctrl 15/15 PASS, A/B 実測)。rep movs/stosw を実装したが既存 e2e は未実行 (未解決)。詳細・未解決は `REPORT_APPENDIX.md`。
