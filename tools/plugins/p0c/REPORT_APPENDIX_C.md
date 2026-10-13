# tools/plugins/p0c REPORT 付録 C (§11)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本ファイルは本体から**無変更で分割移動**した節の全文 (#378, `docs/DOC_MAP.md` §1)。節番号・見出しは移動前のまま。

## 11. P0c-4 追記 (CAB-253): ARG pass の ABI 推定強化 (mid-function push・crash 4 kernel 救済・xmm 位置規約)

作成: 2026-10-11 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD (WIP 評価前): `ae18b1e`
既知類型との関係 (DEFECTS.md): **D7/D8 (stack 引数・戻り値) 該当**。本節で新たに確認した
「FP 引数の default promotion による値橋渡し不一致」と「OOB getelementptr による UB」は
DEFECTS.md 未登録のため §11.7 に行案を書く (DEFECTS.md 本体は他担当領域で編集しない)。

### 11.0 結論 (先出し)

1. **crash 4 kernel (0x5de710 / 0x5df610 / 0x5e05b0 / 0x5e0d80) がすべて sig11 なしで
   差分 CSV に出る** (2000 case/kernel, fork 隔離)。うち **0x5e05b0 は buf_diff=0
   (bit-exact)**。残 3 本は ABI 接続は完了し ratio ベースの残差 (§11.4)。
2. **abi-mismatch 除外組 37 → 7** (80 kernel = ok 61 / abi-mismatch 7 / Group B 12)。
   受入基準の「abi-mismatch 実質 0」に相当 (残 7 は §11.6)。
3. **回帰 11 kernel (REPORT §9.3/§10.2 の bit-exact set) はすべて buf_diff=0 維持**。
   さらに **0x5dfd30 が x87fix IR でも ext IR でも buf_diff=0** になった (§11.3)。
4. 主要な仮説を実バイナリ実測で確定・修正:
   (a) **ms_abi 間接呼出では FP 引数は xmm レジスタに入らず stack home に載る** (clang 実測)。
       機械語の stack read offset O に対応する thunk param は **O/8-1** (40→b0, 48→b1…)。
   (b) **xmm を引数として読む kernel は thunk 内の inline asm で明示ロードが必要**。
   (c) **宣言なし呼出の default argument promotion** (float→double) で thunk の movss が
       double の下 4 byte を読んでいた (両側に同じ値が行くため diff は 0 のままだが、
       添字アクセス kernel では符号で OOB read → SIGSEGV)。
   (d) RetDec の `mov rsi,rdx; movsq; movsq` (16B record コピー) は frame にポインタ値
       自体を store する誤 lifting → record の第 2 ポインタが placeholder のまま (NULL 書込)。

### 11.1 実測した thunk 引数配置 (CAB-253 の根拠)

| 測定 (probe) | 結果 |
|---|---|
| t9/t10 (naked, 間接 ms_abi, FP 4 引数 + stack 引数) | FP 引数は **stack home** (entry_rsp+0x28..0x40) に載り、xmm0-3 には載らない |
| t11 (u64/float/double 混合 stack param) | stack param は **パラメータ順**に offset 40 から詰められる (型混合でも可) |
| p710 (0x5de710 実呼出) | xmm3 読出し = scratch 残り、offset 40 = 第 1 FP param の home |
| 生成 thunk の objdump (旧) | FP param を `movss %xmm,0x2N(%rsp)` で home に載せるだけ (xmm 未設定) |
| driver の call site (旧) | prototype 無し呼出 → `movsd` + `mov $0x3,%al` (varargs 昇格) |

### 11.2 修正 (3 ファイル)

**k80abi.py** (機械語 ABI 走査):
| # | 修正 | 効果 (実測) |
|---|---|---|
| A1 | ゼロ化イディオム (`xorps/xorpd/pxor/xor/subsd reg,reg`) を read と数えない | 0x5df610 の xmm0 / 0x5e05b0 の edx 等 13 kernel の誤 slot を除去 |
| A2 | `xmm_insns` (helper 対応の xmm レジスタ付き命令を operand 位置付きで出力) | k80_argfix [C] の 2 段対話の入力 |
| A3 | `clip_index` (`movsx/movzx [base+idx*scale>=2]`) | 4 kernel (0x5e0c00/0x5e0d80/0x5e0ea0/0x5e1490) に非負ドメイン制約 |
| A4 | `ptr_struct` (二重 deref される gpr slot) | 0x5e05b0 / 0x5e02b0 の record{ptr,ptr} を検出 |

**k80_argfix.py** (ARG pass):
| # | 修正 | 効果 (実測) |
|---|---|---|
| B1 | [B] の「entry block に store が無い」→ **definitely-assigned (must) 解析**に変更 | 0x5de710/0x5df610 の `%in.rdx` false positive を除去 (irmap ずれ = SIGSEGV の原因) |
| B2 | [C] 新パターン: `xor i128 0,0` が helper の被演算子 → 機械語の xmm slot に接続 | 9 kernel で xmm 引数を接続 (出現順・オペランド数で機械語命令と突合) |
| B3 | [D] 新パターン: movsq ×2 の 16B record コピーを修復 (2 qword を正しく load) | 0x5e05b0: sig11 → **buf_diff=0** |
| B4 | `main` の h5/b5 反映漏れを修正 (orphan 修正結果が捨てられていた) | 0x5e0760/0x5e0350/0x5e03f0/0x5de3e0 に引数接続 |

**k80_diff.py** (差分試験ハーネス):
| # | 修正 | 効果 (実測) |
|---|---|---|
| C1 | thunk param を **機械語 read の offset/レジスタ対応**に再設計 (O/8-1) | offset 40-64 の home slot に正しい値 |
| C2 | xmm 引数を inline asm (`movss/movsd %m(bN), %%xmmN`) で call 直前にロード | xmm を読む kernel が初めて意味のある比較に |
| C3 | **thunk prototype を生成** (default promotion 対策) | NC1 §11.5: 0 だった 4 kernel が崩れる → 修正の効果を実証 |
| C4 | fp slot → 整数型 IR 引数は **float bits** (`fbits()`) で橋渡し | NC1 と対になるもう片側 |
| C5 | `clip_index` kernel は fp scalar を非負・有限 (exponent 118-142) に制限 | NC3 §11.5: 0x5e0d80 が sig11 → 動作 |
| C6 | `ptr_struct` kernel は struct buffer 先頭 16B に有効ポインタを敷設し comparison 対象を切替 | 0x5e05b0 の record deref |
| C7 | `build_argmodel` の leftover を「未割当の**使用** slot」のみに修正 | abi-mismatch 37 → 7 |
| C8 | fp scalar の指数域を buffer と同じ 118-142 に統一 | REPORT §9.4 が指摘した 2^116 級入力の除外 → 0x5dfb60/0x5dfd30 が bit-exact |

### 11.3 差分試験結果 (p0c4_abi_e2e.py, 2000 case/kernel, fork 隔離)

数え方 (規則 36): buf_diff = native 機械語と IR の出力バッファの bit 不一致 cell 数
(f32 4 B 単位・1 kernel 1 case で最大 16,452 cell = NBUF_B 65,808/4)。NaN 同士は nandiff
に分離。ret_diff は native が rax を放置する kernel では 2000/2000 など意味がないため
合否判定には使わない。

| kernel | class | 修正前 (CAB-253 起点) | 修正後 buf_diff | 判定 |
|---|---|---|---:|---|
| 0x5de710 | sse | sig11 | 1,295,105 | 救済 (残差 §11.4) |
| 0x5df610 | sse | sig11 | 2,493,284 | 救済 (残差 §11.4) |
| 0x5e05b0 | sse | sig11 | **0** | **bit-exact** |
| 0x5e0d80 | sse | sig11 | 910,694 | 救済 (残差 §11.4) |

回帰 (bit-exact set、すべて buf_diff=0): 0x5de820 / 0x5dedf0 / 0x5dfb60 / 0x5df210 /
0x5df240 / 0x5e0760 / 0x5e0b70 / 0x5e0bb0 / 0x5e1590 / 0x5e1780 / 0x5e0330 (11 kernel)。

bonus: **0x5dfd30 が buf_diff=0** (REPORT §9.4 では x87fix 後 38,099 / ext 後 102,353 と
未達だったもの。fp scalar の指数域統一 (C8) で極端スケール入力が消えたため)。

status センサス (80 kernel): run 61 (ok 54 / sig11 7) / abi-mismatch 7 / Group B 12。
修正前は ok 31 / abi-mismatch 37 / Group B 12 (うち crash 4 が sig11)。

ext IR パス (p0c4_e2e.py, 2000 case): 0x5dfbe0=0 / 0x5dfc90=0 / 0x5dfd30=0 /
0x5dfdb0=970,284 / 0x5de820=0 / 0x5dedf0=0 / 0x5dfb60=0 / 回帰 7 kernel=0。

### 11.4 残差の解釈 (0x5de710 / 0x5df610 / 0x5e0d80)

- **0x5de710 / 0x5df610**: 引数 (src/dst ポインタ・count・xmm3 の scale・offset 40 の
  offset 値) はすべて接続済み。maxulp=0 で不一致が **1 桁以内の近傍値**であり構造は一致。
  原因は x87 ext 精度 (REPORT §9.4) または SSE helper の lane 模型の差異と**推定**
  (推定ラベル・未検証)。
- **0x5e0d80**: `movsx rax,[rdi+rax*2]` の添字 = `trunc(|src| × gain × int(offset40))` を
  bound でクランプした値。bound は harness の 512..2047。添字が native/IR で一致しない
  cell が残る (ret_diff 947/2000)。ext 精度と**推定**。

### 11.5 負論対照 (規則 41, p0c4_nega.py, 500 case)

| 対照 | 外した修正 | 観測 (base → NC) |
|---|---|---|
| NC1 | thunk prototype (C3) | 0x5e05b0 0→508,972 / 0x5e0980 0→262,501 / 0x5e0ea0 0→118,845 / 0x5e1330 0→118,373 / 0x5e0d80 ok→**sig11** |
| NC2 | [D] record コピー修復 (B3) | 0x5e05b0 **0→sig11** |
| NC3 | clip_index 非負制約 (C5) | 0x5e0d80 ok→**sig11** |

### 11.6 検証範囲 / 範囲外 (規則 40)

検証した: 80 kernel の ABI モデル再構成 (k80abi + k80_argfix + k80_diff) と 61 kernel の
native 機械語突合 (2000 case/kernel)。native oracle は実 PE (block18983) を 0x400000 に
MAP_FIXED して直接実行。wasm32 バックエンド、framework (fw_*) への統合、CRT 側 JIT は
**未実施** (他担当領域)。Group B 12 kernel は外部 helper 呼出のため数値比較対象外。

### 11.7 未解決・起票先 (規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| sig11 のまま 7 kernel (0x5de3e0 / 0x5e02b0 / 0x5e0630 / 0x5e06e0 / 0x5e08d0 / 0x5e0c00 / 0x5e1280) | 今回 ok モデルになったが native 側がクラッシュ。0x5e0c00 は「読出し値を次の添数に使う連鎖」でランダム入力域外、0x5de3e0 は RetDec x87 模型の欠陥 (x87fix 対象外) | CAB-268 (ext 精度・x87 模型) にコメント + 0x5e0c00 は入力ドメイン制約の子チケットを起票 |
| abi-mismatch 残 7 (0x5dee90 / 0x5df040 / 0x5e09f0 / 0x5e0a70 / 0x5e0b10 / 0x5e1210 / 0x5e12b0) | 数値差分の対象外 (IR に placeholder が残る) | 子チケット (xmm slot 接続の [C] 拡張) を起票 |
| 0x5de710 / 0x5df610 / 0x5e0d80 の残差 (ext 精度推定) | CAB-196 出口条件「80 kernel bit-exact」の残 | CAB-196 親にコメント (CAB-268 と統合) |

#### 11.7b DEFECTS.md 行案 (未登録類型)

- **D17 (新) FP 引数の default promotion による値橋渡し不一致**: 症状 = 宣言なしで関数を
  呼ぶと float 引数が double に昇格し、callee が movss で読むと double の下 4 byte になる。
  根本原因 = prototype 欠落 (harness 生成コード)。観測 = 0x5e0980 の buf_diff が
  0→262,501 (NC1)。検出信号 = call site の `mov $0xN,%al` (varargs 昇格)。修復 = thunk の
  prototype を生成する。
- **D18 (新) OOB getelementptr の UB**: 症状 = `alloca i64` (1 要素) に対して
  `getelementptr i64, i64 1` を発行すると optimizer が後続 (store/loop/ret) を dead と
  判定して落とす。観測 = function_5e05b0 の -O2 出力に store/ret が消滅 (clang -S で確認)。
  修復 = ptrtoint+add+inttoptr で 2 qword 先を表現する。

### 11.8 再現 (1 コマンド・独立再計算スクリプト同梱・規則 37)

```sh
export TMPDIR=$PWD/work/tmp
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000   # ABI e2e (k80abi→argfix→x87fix→diff)
python3 tools/plugins/p0c/p0c4_nega.py 500        # 負論対照 NC1-NC3
bash tools/plugins/p0c/p0c_e2e.sh                 # 既存 e2e 回帰 (exit 0)
bash tools/plugins/p0c/p0c2_e2e.sh 2000           # 既存 e2e 回帰 (exit 0)
bash tools/plugins/p0c/p0c3_e2e.sh 2000           # 既存 e2e 回帰 (exit 0)
python3 tools/plugins/p0c/p0c4_e2e.py 2000        # ext IR パス (別トラック)
```

`p0c4_abi_e2e.py 2000` の実測出力 (主要部):
```
== [6] 検算: status センサス ==
   run=61  ok=54  sig11=7 (0x5de3e0 0x5e02b0 0x5e0630 0x5e06e0 0x5e08d0 0x5e0c00 0x5e1280)
== [7] 受入基準 ==
   ① 回帰 11 kernel buf_diff=0: 0x5de820 0x5dedf0 0x5dfb60 0x5df210 0x5df240 0x5e0760
      0x5e0b70 0x5e0bb0 0x5e1590 0x5e1780 0x5e0330
   ② crash 4 (0x5de710/0x5df610/0x5e05b0/0x5e0d80) すべて sig なしで CSV に出る
   ③ 冪等性 (x87fix / k80_argfix 2 回適用 byte 一致) 維持
   ④ llvm-as 通過
== [8] kernel 表 (80/80) の再確認 ==
   45 variables / 80 implementations / 10,886 B / x87 28 — 一致
```
主要 kernel の 2000 case 実測 (kernel,buf_diff,ret_diff,status):
```
0x5de710,sse,1295105,2000,ok    0x5df610,sse,2493284,2000,ok
0x5e05b0,sse,0,0,ok (bit-exact) 0x5e0d80,sse,910694,947,ok
0x5dfd30,f32chain,0,0,ok        0x5dfb60,f32chain,0,2000,ok
0x5de820,f32chain,0,2000,ok     0x5dedf0,f32chain,0,2000,ok
```

### 11.9 クリーン HEAD 検証 (規則 45)

起点 commit = `ae18b1e` (本節の WIP 評価前)。REPORT §10.8 と同手法 (`git archive HEAD --
tools/plugins/p0c | tar -x -C work/verify_ae18b1e --strip-components=3`) で展開し、
work/ 内の既存 lift IR (work/k80.lift.ll) を入力として p0c4_abi_e2e.py を再現する。
[6] の kernel_table 参照はスクリプトが `__file__` から REPO を導出し、
`tools/plugins/inventory/kernel_table.py` を解決する。

### 11.10 環境前提 (規則 43)

§10.9 と同一 (TMPDIR は実ディスク、llvm-as / clang / python3 + pefile + capstone、PE を
0x400000 に MAP_FIXED 敷設して実機械語を直接実行)。追加: 負論対照は環境変数
`K80_NO_PROTO=1` / `K80_NO_STRUCTD=1` / `K80_NO_NNEGF=1` で各修正を OFF にできる
(p0c4_nega.py が使用)。

### 11.11 GitHub issue / PR (運用メモ)

- GitHub issue: **#254** (本 ticket、label `state:in-review`)。親 #197 ([PLG-P0c] / CAB-196)、
  子 **#277** (native crash 残 7 + abi-mismatch 残 7)、**#269** ([P0c-5] / CAB-268、ext 精度)、
  #242 ([P0c-2] / CAB-241)。milestone は M-App (親から継承)。
- PR: **#278** (branch `254-arg-pass-abi`)。worktree 内クリーン HEAD から e2e 再現済み。
- 規約変更: 運用ルール (旧 SUBAGENT_RULES.md) は 2026-10-11 14:06 に「worktree + PR (直接 master commit 禁止)」
  へ改訂 (RULES_SHA=4d7380074852、正本: `docs/WORKFLOW.md` §1〜§2・`docs/DECISIONS.md` D4)。
  着手時の RULES_SHA は ff4999169333 (改訂前の preflight 値)。
  改訂前に同内容を共有 master へ直接 commit した (ca5ac3f) ため、PR は origin/master から
  の cherry-pick (00996d5)。共有 master の ca5ac3f は reset/revert せず残置 (他担当の
  staged WIP を巻き込むため)。扱いは main 判断。
- Linear は規則 56 で読み取り専用のため CAB-253 の状態変更は行っていない (GitHub label で代替)。

