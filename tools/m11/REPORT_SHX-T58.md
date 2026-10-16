# SHX-T58 (#5690): base_mismatch SSA 値渡しの残件 5 組の修復範囲の確定

親: #5588 / 前提: PR #5670 (SHX-T51・`REPORT_SHX-T51.md`) と PR #5583 (SHX-T48・`REPORT_SHX-T48.md` §4)

## 1. 結論

- 残件 5 組 (`function_d26460`・`function_e4f310`・`function_977f50`・`function_441380`・`function_6905f0`) は、**いずれも alloca の拡幅 (R8) では覆えない**。修復の対象外とする。
- 判定の根拠は親の prologue から測った枠内の空き (§3) と、親が rbp 域を自分の値に使っている衝突 (§4)。
- 再生成 IR (529,619 行) で X・E を測り直した。前 run の表 (REPORT_SHX-T48 §4) と一致した。素材 IR (529,468 行) の差は再生成で解消した (§2)。
- 修復の実装 issue は起票しない。残りは次の 2 件で、いずれも本 REPORT の範囲外 (§5)。

## 2. 測定条件

- 測定 commit: 本 PR の直前の `origin/main` (`739b46e2d`)。コード変更は `tools/m11/frame_share/frame_bound.py` (新規) のみ。
- 素材: `work-m11` の `tools/m11/work/` と、`m11_gen_ir2.sh` で再生成した `boot_final.ll` (490,790 行) から `m11_post.py` で作った `boot_final3.ll` (529,619 行)。
- 判定チェーン: `frame_share/detect.py` → `site_check.py` → `base_check.py` → `unmatched_check.py` を本 PR の作業ツリーで順に実行した。結果は 301 site・`ok` 301。`base_check` は `ir_truncated` 242 / `unmatched` 56 / `no_prologue` 3。`unmatched_check` は `ir_truncated` 56 / `no_ir_call` 3。前 run と一致した。
- `neighbor_gap.py --report REPORT_SHX-T48.md` の出力も前 run と一致した (18 組・次の stack_var 無しの 5 組は未測定のまま)。

## 3. 枠内の空き (prologue から)

局所領域は `[X, -8×push数)`。X = `rbp` の entry 基準位置 = `-(8×push数 + sub 量)`。`-8×push数` より上は退避レジスタ域。枠内の空き = `-8×push数 - X` = `sub 量`。

| 親 | X | push | sub | 枠内の空き | E (需要) | 判定 |
|---|---|---|---|---|---|---|
| `function_d26460` | -104 | 4 | 72 | 72 | 48 | 枠内だが親の `rbp+0x2c` と衝突 (§4) |
| `function_e4f310` | -40 | 1 | 32 | 32 | 56 | 枠超過 |
| `function_977f50` | -88 | 1 | 80 | 80 | 160 | 枠超過 |
| `function_441380` | -40 | 1 | 32 | 32 | 84 | 枠超過 |
| `function_6905f0` | -152 | 2 | 136 | 136 | 176 | 枠超過 |

- 枠超過の 4 組は、callee が親の保存域・戻り番地まで触る (E が枠内の空きより大きい)。alloca の拡幅では親の frame の外まで出るので、覆えない。
- prologue の X は、`base_check.rbp_entry_offset` (前 run の測定と同じ関数) と一致した。

## 4. 衝突参照 (親が rbp 域を自分の値に使う)

callee の需要域は `rbp+[0, E)`。親が同じ範囲の `[rbp + d]` を参照していれば、拡幅すると親の値と衝突する。

| 親 | 衝突する親の参照 (`rbp+d`) |
|---|---|
| `function_d26460` | `0x2c` (`movss dword ptr [rbp + 0x2c], xmm0`。呼出し前の store) |
| `function_e4f310` | `0x20`・`0x30` |
| `function_977f50` | `0x38`・`0x50`・`0x60`・`0x68`・`0x70`・`0x78`・`0x80`・`0x88`・`0x90`・`0x98` |
| `function_441380` | `0x20`・`0x30`・`0x48`・`0x50` |
| `function_6905f0` | `0x20`・`0x28`・`0x38`・`0x40`・`0x48`・`0x4c`・`0x50`・`0x58`・`0x67`・`0x68`・`0x70`・`0x78`・`0x88`・`0xa0`・`0xa8` |

- `function_d26460` は、枠内の空き (72 B) に E (48 B) が収まる。しかし親の `rbp+0x2c` (+44) が需要域 [0, 48) に入る。親が callee の呼出し前に値を置く場所と重なるので、拡幅は親の値を壊す。
- 本 run の途中で `rbp+0x2c` を entry 基準の -60 と混同して読んだが、判定は rbp 基準の +44 で行っている (entry 基準では -104+44 = -60)。

## 5. 残り (修復の対象外・範囲外)

| 未了 | 影響 | 起票先 |
|---|---|---|
| 修復の対象外とした 5 組の、親の frame 再配置 (callee 用の領域を親の保存域の外に取る) | 5 組の修復は別の設計になる。本 REPORT は判定しない | 親 #5588 (判定の範囲外。修復する組が出た時点で子を切る) |
| `function_6905f0` → `function_690580` の欠落候補 4 site | 同上 | #5587 |
| `function_40b620` → `function_40b290` の call 欠落 3 site (`no_ir_call`) | 同上 | #5586 |

## 6. 検証

- `frame_share/frame_bound.py --ir work/boot_final3.ll --report REPORT_SHX-T48.md` の出力は、§3・§4 の表と一致した (5 組)。
- 負荷: 測定時の load average は 1.42 (`uptime`・nproc 4)。
- 測定 commit `739b46e2d` から本 PR の HEAD までのコード差分 (`git diff 739b46e2d HEAD -- tools/m11/frame_share tools/m11/ldfix tools/m11/*.sh tools/m11/*.py`):
  `tools/m11/frame_share/frame_bound.py` | 105 insertions (新規)。判定本体は既存の `base_check.rbp_entry_offset` を使うため、既存の測定値は変わらない。
- `frame_bound.py` の docstring を、測定後に説明文だけ直した (判定ロジックは変えていない)。
