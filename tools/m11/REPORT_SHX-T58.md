# SHX-T58 (#5690): base_mismatch SSA 値渡しの残件の修復範囲の確定

親: #5588 / 前提: PR #5670 (SHX-T51・`REPORT_SHX-T51.md` §3) と PR #5583 (SHX-T48・`REPORT_SHX-T48.md` §4)

## 1. 結論

- 18 組 (53 site) の SSA 値渡しは、**alloca 拡幅 (R8) で覆えるものは 0 組**。修復の対象外とする。
- 内訳 (§3 の表): 枠超過が 13 組、枠内だが親の rbp/rsp 参照と衝突が 5 組 (`43f800→43f550`・`441730→441560`・`d26460→d26430`・`11e7430→11e6c00`・`f40840→f3d5e0`)。R8 候補は 0 組。
- 13 組は T51 §3 で「R8 で覆えない」と判定済み。本 REPORT は、その 13 組も含めた 18 組の X と枠内の空きを PE から測り直し、判定が T51 と変わらないことを §3 で確かめた。
- 18 組の一覧 (親・callee・X・枠内の空き・E・判定) は §3 の表。修復範囲はこの表で決める。
- 5 組 (`d26460`・`e4f310`・`977f50`・`441380`・`6905f0`) は次の stack_var が無いため、T51 では gap 未測定だった。本 REPORT で、枠内の空き・親の rbp/rsp 参照との衝突から判定した (§3)。
- **E (需要) は再測定していない**。T48 §4 の値をそのまま使った。IR が無く、callee の需要を再計算できなかった。
- **IR の再生成はこの run では不可** (`work-m11`・`toolchain-retdec` が ARTIFACTS_DIR に無い)。再生成 IR での X・E の照合は未実施 (§2)。
- 修復の実装 issue は起票しない。残りは §5 の未了で、いずれも本 REPORT の範囲外。

## 2. 測定条件

- 測定 commit: `765b669c4` (本 PR の前 commit)。コード変更は `tools/m11/frame_share/frame_bound.py` (§6)。
- 素材: `fl-win64.tar.zst` の `extracted/block00031_PE.bin` のみ。`work-m11` (`tools/m11/work/`) と `toolchain-retdec` は ARTIFACTS_DIR に無く、IR (`boot_final3.ll`) を再生成できなかった。
- 実行したコマンド:
  - `ls $ARTIFACTS_DIR` → `fl-win64.tar.zst` のみ
  - `ls tools/m11/work` → 無し
  - `which retdec-decompiler`・`ls /opt` → RetDec 無し
  - `FL_WIN64_DIR=<展開先> python3 tools/m11/frame_share/frame_bound.py --report tools/m11/REPORT_SHX-T48.md` (IR 無し。18 組全て。§3 の出力)
- 再生成 IR (490,790 / 529,619 行) からの `detect.py` → `site_check.py` → `base_check.py` → `unmatched_check.py` の判定チェーン、`neighbor_gap.py --ir` の一致は、IR が無いため **この run では再現していない**。前 run の値 (301 site・ok 301・`ir_truncated` 242 / `unmatched` 56 / `no_prologue` 3) は未確認のまま。
- `neighbor_gap.py` は IR を必須とするため、本 run では実行していない。
- 負荷: 測定時の load average は 0.16 (`uptime`・nproc 4)。

## 3. 18 組の判定 (PE から測定)

`frame_bound.py --report REPORT_SHX-T48.md` (IR 無し) の出力。X は `base_check.rbp_entry_offset`、push・sub は prologue から測った。E は REPORT_SHX-T48 §4 の値。

| 親 | callee | X | push | sub | 枠内の空き | E | 親の rbp 参照 (d < E) | 親の rsp 参照 (d < E) | 判定 |
|---|---|---|---|---|---|---|---|---|---|
| `function_43f800` | `function_43f440` | -136 | 3 | 112 | 112 | 153 | 12 個 (0x30〜0x98) | 0x20 | 枠超過 |
| `function_43f800` | `function_43f490` | -136 | 3 | 112 | 112 | 153 | 同上 | 0x20 | 枠超過 |
| `function_43f800` | `function_43f550` | -136 | 3 | 112 | 112 | 84 | 5 個 (0x30〜0x50) | 0x20 | 枠内だが衝突 |
| `function_441730` | `function_441500` | -120 | 1 | 112 | 112 | 136 | 13 個 | なし | 枠超過 |
| `function_441730` | `function_441560` | -120 | 1 | 112 | 112 | 112 | 11 個 | なし | 枠内だが衝突 |
| `function_d26460` | `function_d26430` | -104 | 4 | 72 | 72 | 48 | 0x2c | なし | 枠内だが衝突 |
| `function_e4f310` | `function_e4f2d0` | -40 | 1 | 32 | 32 | 56 | 0x30 | なし | 枠超過 |
| `function_6a25b0` | `function_6a23d0` | -88 | 3 | 64 | 64 | 121 | 8 個 | なし | 枠超過 |
| `function_6a2820` | `function_6a26e0` | -88 | 3 | 64 | 64 | 121 | 7 個 | なし | 枠超過 |
| `function_977f50` | `function_977870` | -88 | 1 | 80 | 80 | 160 | 9 個 (0x38〜0x98) | 0x20 | 枠超過 |
| `function_441380` | `function_440d30` | -40 | 1 | 32 | 32 | 84 | 0x30・0x48・0x50 | なし | 枠超過 |
| `function_441b20` | `function_441930` | -168 | 3 | 144 | 144 | 284 | 15 個 | なし | 枠超過 |
| `function_11e7430` | `function_11e6c00` | -136 | 5 | 96 | 96 | 88 | 4 個 (0x3e・0x3f・0x48・0x54) | 0x20 | 枠内だが衝突 |
| `function_1280530` | `function_1280170` | -648 | 5 | 608 | 608 | 664 | 95 個 | 0x20 | 枠超過 |
| `function_13105d0` | `function_13104e0` | -120 | 4 | 88 | 88 | 136 | 10 個 | なし | 枠超過 |
| `function_de43b0` | `function_de4120` | -136 | 5 | 96 | 96 | 172 | 10 個 | なし | 枠超過 |
| `function_f40840` | `function_f3d5e0` | -18040 | 3 | 18016 | 18016 | 17992 | 265 個 | 0x20・0x28 | 枠内だが衝突 |
| `function_6905f0` | `function_690580` | -152 | 2 | 136 | 136 | 176 | 14 個 | なし | 枠超過 |

- 「枠超過」は E > 枠内の空き。callee が親の保存域・戻り番地まで触る。alloca 拡幅では親の frame の外まで出る。
- 「枠内だが衝突」は E <= 枠内の空きだが、親が [0, E) の範囲の rbp/rsp 参照を自分の値に使っている。拡幅すると親の値を壊す。
- 18 組の全てが R8 不可。R8 候補は 0 組。
- 13 組 (T51 §3 で「R8 で覆えない」) の判定は、PE 測定で T51 の結論と一致する。
- X は T48 §4 の stack_var 列と、E は T48 §4 の E 列と、18 組全てで一致した (T48 §4 の 18 組の site 数の合計は 53)。E は T48 の値を使い、再測定していない (§2)。

### 3.1 T51 の 5 組との対応

T51 §3 で gap 未測定だった 5 組は、上の表で次のとおり判定した。

- `d26460`: 枠内 (72 B) に E (48 B) は収まるが、親の `rbp+0x2c` と衝突。R8 不可。
- `e4f310`・`441380`・`977f50`・`6905f0`: 枠超過。R8 不可。

## 4. 残件作業 1: 5 組の親の rbp+d の分類 (引数 home か局所か)

PE の逆アセンブル (`block00031_PE.bin`) で、5 組の親の `[rbp + d]` の参照と、直前の call、callee が読む領域を照合した。

| 親 | d | 参照命令 (親) | 分類 | 根拠 |
|---|---|---|---|---|
| `d26460` | 0x2c | `d2649d movss dword ptr [rbp + 0x2c], xmm0` (store・呼出し前) | 引数 home | callee `d26430` が `d2643f divss xmm3, [rcx + 0x2c]` で読む。`rcx = rbp` (`d264a9`) |
| `d26460` | 0x30 | `d2646b movdqa [rbp + 0x30], xmm6` (store・prologue) | 局所 (xmm6 の退避) | 関数末尾で `d26555 movdqa xmm6, [rbp + 0x30]` で復元。callee に渡らない |
| `d26460` | 0x48 | `d2655a lea rsp, [rbp + 0x48]` | frame 復元 (参照ではない) | 末尾の rsp 復元基準 |
| `e4f310` | 0x20 | `e4f392 lea rsp, [rbp + 0x20]` | frame 復元 | 末尾の rsp 復元基準 |
| `e4f310` | 0x30 | `e4f318 mov [rbp + 0x30], rcx` (store・prologue)、以降 `mov rcx, [rbp + 0x30]` の load が各 call の前 | 引数 home | 第 1 引数 `rcx` の退避。callee `e4f2d0` が `e4f2d9 mov rbx, [rcx + 0x30]` で読むのは、この rcx (親の rbp ではなく、親の第 1 引数 `[rbp+0x30]` が指す構造体) |
| `441380` | 0x30 | `441388 mov [rbp + 0x30], rcx` (store・prologue) | 引数 home | 第 1 引数の退避。callee `440d30` が `rbx = rcx` で `[rbx + 0x30]` を読む |
| `441380` | 0x48 | `44138c mov dword ptr [rbp + 0x48], r9d` (store・prologue) | 引数 home | 第 4 引数の退避。callee `440d30` が `[rbx + 0x48]` を読む (rbx = 親の rbp) |
| `441380` | 0x50 | `441390 mov eax, [rbp + 0x50]`・`441393 mov [rbp + 0x50], eax` (load/store・prologue) | 引数 home | 第 5 引数 (スタック渡し) の再書込み。callee `440d30` が `[rbx + 0x50]` を読む |
| `441380` | 0x20 | `4413b4 lea rsp, [rbp + 0x20]` | frame 復元 | 末尾 |
| `977f50` | 0x20 | `977fe7`・`978012` の `[rsp + 0x20]` store (body の rsp == rbp) | 未確定 | 引数 home か局所かは callee `977870` の読みと未照合。判定は枠超過 (E=160 > 枠内の空き 80) で決まり、この分類に依らない |
| `977f50` | 0x38 | `977f58 mov [rbp + 0x38], rbp` (store・prologue) | 未確定 | 親の rbp 自体の保存。読み先と、この値を渡す call の有無は未照合。判定は同上 (E > 枠内の空き) で決まり、分類に依らない |
| `977f50` | 0x60 | `977f5c mov [rbp + 0x60], rcx` (store・prologue) | 引数 home | 第 1 引数の退避。callee `977870` が `[rbx + 0x60]` を読む |
| `977f50` | 0x98 | `977f9b mov rax, [rbp + 0x98]` (load)・`978021` 等 | 引数 home | callee `977870` が `[rbx + 0x98]` を読む |
| `6905f0` | 0x20 | `6905fc mov [rbp + 0x20], 0`・`690a37 lea rcx, [rbp+0x20]` | 未確定 | `690a42` の call (`8da350`、`690580` ではない) の読みと未照合。判定は枠超過 (E=176 > 枠内の空き 136) で決まり、分類に依らない |
| `6905f0` | 0x28 | `690604 mov [rbp + 0x28], rbp` (store・prologue) | 未確定 | 親の rbp 自体の保存。読み先は未照合。判定は同上 (E > 枠内の空き) で決まり、分類に依らない |
| `6905f0` | 0x38・0x40・0x48・0x4c・0x50・0x58 | 多数の store/load (複数の call を経由) | 未確定 | 同じ親の複数 call (`690580` を含む) 経由で、命令単位の照合は未了。判定は同上 (E > 枠内の空き) で決まり、分類に依らない |
| `6905f0` | 0x67・0x68・0x70・0x78 | `69068x`〜`6906b7` の store (呼出し前) | 候補 | callee `690580` が `[rbx + d]` を読む (rbx = 親の rbp) が、完全な照合は未了。判定は同上 |

- 分類が完了したのは、`d26460`・`e4f310`・`441380` の全 offset と、`977f50` の 0x60・0x98。`977f50` の 0x20・0x38、`6905f0` の 0x20・0x28・0x38〜0x58 は未確定。
- 未確定の offset は、どれも R8 不可の判定に影響しない (§3 の判定は枠超過 or 枠内の衝突で決まり、枠超過の組は分類によらず枠超過のまま)。完全な分類には、各 call の引数レジスタの追跡 (rcx/rdx/r8/r9 の由来) と callee の読みの照合が要り、本 run では完了していない。

## 5. 残り (修復の対象外・範囲外)

| 未了 | 影響 | 起票先 |
|---|---|---|
| 修復の対象外とした 18 組の、親の frame 再配置 (callee 用の領域を親の保存域の外に取る) | 修復は別の設計になる。本 REPORT は判定しない | 親 #5588 (判定の範囲外。修復する組が出た時点で子を切る) |
| §4 の未確定 (`977f50` の 0x20・0x38、`6905f0` の 0x20・0x28・0x38〜0x58) | 引数 home か局所かの確定。判定 (R8 不可) には影響しない (§4 の各行) | #5690 へのコメント |
| 再生成 IR での X・E の照合 (§2)・E の再測定 | 再生成 IR での照合は未実施。T48 §4 との一致は stack_var 列・E 列で確認済み (§3) | #5690 へのコメント (素材 `work-m11`・`toolchain-retdec` が要る) |
| `function_6905f0` → `function_690580` の欠落候補 4 site | 同上 | #5587 |
| `function_40b620` → `function_40b290` の call 欠落 3 site (`no_ir_call`) | 同上 | #5586 |

## 6. 検証

- `tools/m11/frame_share/frame_bound.py` を修正 (§6.1)。
- 測定 commit `765b669c4` から本 PR の HEAD までのコード差分 (`git diff 765b669c4 HEAD -- tools/m11/frame_share`):
  - `frame_bound.py` の書き直し。m2 の `[rsp + imm]` を含む本体参照の集計、IR を任意引数にした、18 組の一括出力。
- 負荷: 測定時の load average は 0.16 (`uptime`・nproc 4)。

### 6.1 frame_bound.py の変更 (m2)

- `parent_refs` を追加。本体 (mov rbp, rsp の後、rsp を書き換える命令・ret・leave の前) の `[rbp+d]` と `[rsp+d]` を両方集める。
- `977f50` の `[rsp+0x20]` (rsp == rbp の区間) が衝突判定に入るようになった。ただし判定は変わらない: 977f50 は枠超過で、他の組も rbp 側の衝突が既にあった。m2 の指摘のとおり、判定ロジックの欠落は直した。
- IR 無しでも 18 組を測れるようにした (`--ir` は任意)。
