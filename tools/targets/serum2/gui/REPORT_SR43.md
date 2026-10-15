# REPORT — [SR-43 #2174] SerumController 間接呼出の受信 base の this 遡り (候補 1052 件・静的・関数内)

- 日付: 2026-10-14 / 親: #2135 (SR-41) / 前段: `REPORT_SR41.md` §2 (受信レジスタの直前の定義元の分類 `receiver_origin.py`)
- 範囲: 静的解析のみ。所属関数の中だけを見る (呼出元の引数は追跡しない)。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-38・SR-41 と一致)。作業用 dir はリポジトリ外。
- 測定 commit: `06ca6fb0` (`receiver_this_trace.py` を最後に変えた commit。`ind` 集計の修正のみ。分類 (TSV) は直前の `8bbf9c9e` と同一で、TSV md5 `ea2d93a2…` が検収側の測定とも一致)。このコミット以降にスクリプトは変えていない (§4 の差分 0 行)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. 候補 1052 件のうち、受信が SerumController (this) のものを確定する | **未達。確定 0 件**。所属関数の this が呼出先になる候補は 67 件 (63 関数) あるが、その関数が SerumController のメソッドだという証拠は得られなかった。SerumController の this 集合 (slot 関数 + ctor 形 + そこから this をそのまま渡す直接 call) に入る候補は 2 件 (S 1・K 1) で、どちらも未解決 |
| 2. 確定できなかった候補を、遡った経路の停止理由ごとに件数で書く | **達成** (§2) |
| 3. 結果を本ディレクトリの REPORT に書く (測定 commit と再現手順を含める) | **達成** (本ファイル) |

本 run で得たもの: 候補ごとに「呼出先オブジェクトが所属関数のどこから来たか」を分類するツール (`receiver_this_trace.py`) と、未確定の内訳。
受入 1 の残りは、関数間 (引数・this 型の伝播) と関数内 (spill・支配・添字・戻り値) の 2 種類の作業で、1 run に収まらないため子 issue に分けた (§5)。

## 1. 方法 (`receiver_this_trace.py`)

- 候補: `call qword ptr [R + disp]`、disp = `0x30`/`0x38`/`0x88`。件数 1052 は `receiver_origin.py` と一致。
- R の値を、所属関数の中で後ろ向きに遡る (`mov`/`lea`/`load`/`copy`)。
  - `copy` は読み替える。`rsp` 相対の load は、同じ場所への store (spill) を見つけ、store 元の値へ読み替える。見つからなければ `STACKSLOT`。
  - R が `[B+0]` (vptr の読み出し) なら呼出先オブジェクトは B。`[B+d]` (d≠0) なら `B+d` の埋め込み子 (`vptr-emb`)。
- 遡りの終端: 関数先頭まで届けば `rcx` = this、`rdx`/`r8`/`r9` = 引数。途中の `[X+d]` は X を再帰的に遡る (深さ上限 5)。`lea` は埋め込み子 (`+d`)、`call` の戻り値 (rax) は `CALLRET`、`rip` 相対は `GLOBAL`、添字付きは `INDEX`。
- **strict** (本表の値): 遡りで見つけた定義が使用を支配しない (使用へ、定義を通らずに到達できる経路がある) なら `NODOM` として未解決にする。支配は関数内 CFG (fallthrough・jcc・jmp の直接分岐先) の到達性で判定する。
- **loose** (参考): 支配を見ず線形に遡る。分岐の反対側の定義を拾い得るため、確定に使わない。
- SerumController の this 集合 (C): slot 関数 (vtable head `0x180a2bf58` の登録関数, S) と ctor 形 (head を rip 相対で指す lea を持つ関数, K) を起点に、rcx が this のまま渡される直接 call の宛先を不動点まで加える。

## 2. 分類結果 (strict・n = 1052)

| 分類 | 件数 | 意味 |
|---|---|---|
| THIS | 67 | 呼出先 = 所属関数の this (`[this]` の vptr を読んで呼ぶ)。63 関数 |
| THIS-EMB | 20 | this + lea オフセット (埋め込み子)。this そのものではない |
| THIS-CHILD | 191 | this から load を 1 段以上経由した子オブジェクト。this そのものではない |
| ARG | 240 | 引数 (rdx/r8/r9) 由来。呼出元を見ないと型が決まらない |
| ARG-CHILD | 68 | 引数の子オブジェクト |
| STACKSLOT | 95 | rsp 相対の load で、対応する spill store が見つからない (80 + R 経路 15) |
| NODOM | 242 | 定義が使用を支配しない (132 + R 経路 108 + 埋め込み 2) |
| INDEX | 58 | 添字付きアドレス (`[rax+rcx*8+d]` 等) |
| CALLRET | 43 | 関数の戻り値 (ファクトリ等) (41 + 埋め込み 2) |
| CLOBBER | 12 | 途中の call が破壊 (7 + R 経路 5) |
| ENTRY (R 経路) | 15 | vtable レジスタが関数先頭からの値 (callee-saved 等) |
| ARITH | 1 | 演算結果。`classify()` は mov/movzx/movsx/movsxd/movabs/lea/copy/load 以外の書き込みを既定の ARITH に入れる。`pop` (スタックからの load) もここに入る (`pop rcx` → `('arith', 'pop')` を確認)。(f) 本 run で確認: 1 件は `add rdi,-0x120` (0x1806b6b83)。呼出 0x1806b6beb の `[rdi]` (vptr 読み出し) の直前の `rdi` の定義で、`pop` ではない (`objdump -d` で確認) |
| **合計** | **1052** | |

- 「this の型」を確かめる材料として、SC 伝播 (§1 の C) を回した結果:
  - 直接 call 153 件 (宛先は SC 未登録の関数) のうち、rcx が this のまま渡されるのは 2 件。その 2 関数を SC に加えた (集合 21 関数)。
  - その 2 関数の中には候補 call が無い。よって THIS の 67 件の所属関数は、SC の証拠を 1 件も持たない (証拠別 `-` 67)。
  - 所属関数の rcx の遡りの内訳 (153 件): `nodom` 69・`stack` 18・`stackslot`+`stackslot-child` 19・`this-child` 10・`other` 8・`arith`+`arith-child` 9・`clobber` 4・`callret` 3・`global` 3・`index` 2・`arg` 1・`nodom-child` 5・`this` 2。
- SC の中の候補 (S・K 証拠): 2 件 (`0x1800c2f05` in `0x1800c2b50`=S・`NODOM`、`0x1800aa893` in `0x1800a9f40`=K・`STACKSLOT`)。SR-38 の手解析 (子オブジェクトの vtable 呼出) と矛盾しない。
- 参考 (loose・分岐を無視): THIS 74 (strict 67 との差 7)、THIS-CHILD 226、ARG 240、STACKSLOT 91、INDEX 77。strict と loose の差は NODOM の 242 件の中身。

## 3. 限界 (結論を読むときの注意)

- `THIS` は「所属関数の this が呼出先」であって、「その関数が SerumController のメソッド」の証明ではない。型は §2 の SC 伝播でも確かめられなかった。
- 関数間の追跡 (呼出元) はしていない。ARG 240 件と THIS の型は、呼出元をたどらないと決まらない。
- 支配判定は関数内 CFG のみ。間接 jmp を含む関数では `Fn.dominated` が常に偽を返す (`if self.indirect: return False`)。そのため定義が見つかった候補は全て NODOM になり、定義が無ければ entry になる。
- **撤回**: 旧記述「間接 jmp を含む関数の NODOM は 0 件だった (switch 表による打ち切りではない)」は根拠にならない。旧 `ind` 集計は `r[4].endswith("NODOM")` で数えており、`receiver()` の R 経路が返す `R-nodom` (小文字) を数えなかった (`"R-nodom".endswith("NODOM")` は偽)。`ind` 集計は測定 commit `06ca6fb0` で直した。
- 間接 jmp を含む関数の候補は **89 件 (54 関数)**。内訳は `R-nodom` 89 件 (全件)。定義が見つかった候補は全て NODOM になり、定義が無かった候補 (entry) は 0 件。旧記述の「0 件」は誤りで、候補は 89 件ある (全て支配判定で NODOM)。
- 線形の定義走査はループの back edge を見ない。ループを越える定義を取り逃す可能性がある。
- 所属関数の範囲は `.pdata` の関数境界に従う。非連続な関数や、関数境界外の thunk は扱えていない。

## 4. 再現手順・実測

```sh
# $S: リポジトリ外の作業用 dir (RUNNER_TEMP 配下)。$P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv trace.tsv
venv/bin/python $P/negctl_this_trace.py Serum2_win64.vst3 trace.tsv neg
```

- 依存: `pefile` `capstone` `zstandard`。
- 入力の確認: `$ARTIFACTS_DIR/plugins-serum2.tar.zst` から `Install_Xfer_Serum2_2.1.5.exe` (1,313,084,056 B) を `tar --zstd -xf` で取り出し、`7z x` で `Serum2.vst3` を得た。`Serum2_win64.vst3` の sha256 `501e7bb3…` / 19,236,864 B (SR-38・SR-41 と一致)。展開の所要は計測対象外。
- 実測 (n=3・逐次・並列数 1・nproc=4・測定 commit `06ca6fb0`。load は `/proc/loadavg` の 1 分値):

| 実行 | real (s) | user (s) | sys (s) | load 開始 → 終了 |
|---|---|---|---|---|
| 1 | 23.870 | 22.466 | 1.400 | 0.33 → 0.56 |
| 2 | 23.712 | 22.286 | 1.421 | 0.56 → 0.68 |
| 3 | 23.906 | 22.461 | 1.427 | 0.68 → 0.79 |
| min–max | 23.71–23.91 | 22.29–22.47 | 1.40–1.43 | |

- 決定性: 3 回の stdout md5 (`6c9687d6…`) と TSV md5 (`ea2d93a2…`) が全て一致。候補件数は 1052、strict 件数は §2 と一致。
- 候補件数 1052 は `receiver_origin.py` の出力 (同じ入力) と一致 (SR-41 の値)。
- ネガティブコントロール (`negctl_this_trace.py`。基準 = 上の run 1 の TSV。判定点 1 箇所を壊した複製で strict 分類を再計算し、`cat_strict` が変わった件数を数えた):

| 壊した判定点 (1 箇所) | 変更 | 分類が変わった件数 | 内訳 |
|---|---|---|---|
| 支配判定 `Fn.dominated` | 先頭で `return True` (常に支配) | **242 / 1052** | 基準の NODOM 242 件が全て別の分類へ (NODOM が新たに生じた件 0)。THIS 67 → 74 |
| 受信 this の起点 `ARGNAME` | `rcx`: this → arg | **278 / 1052** | THIS 67 → ARG 67、THIS-CHILD 191 → ARG-CHILD 191、THIS-EMB 20 → ARG-EMB 20。THIS 67 → 0 |
| spill 検出 `find_store` | 常に None | **0 / 1052** | この入力では spill 検出の結果が分類を変えない (失敗ではなく、効いていないという事実) |

- 報告前コマンド (`docs/WORKFLOW.md` §6)。検証 HEAD `256d38b3` (測定 commit の後に `negctl_this_trace.py` を追加した commit。REPORT は次の commit で更新) の worktree で実行。全て 0 行・rc 0:
  - `git status --porcelain=v1 -- tools/targets/serum2/gui` → 0 行
  - `find tools/targets/serum2/gui -type f -size +20M -not -path '*/work/*'` → 0 行 (20MiB 超の blob なし)
  - `git diff 06ca6fb0 HEAD -- tools/targets/serum2/gui/receiver_this_trace.py` → 0 行 (測定後にスクリプトは変えていない)
- 未実施の検証はない (支配判定・spill 検出・this 起点の 3 判定点、n=3 の所要、間接 jmp 関数の候補件数は本 run で測定した)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) ARG 240 件・ARG-CHILD 68 件の呼出元をたどり、引数の型 (SerumController か) を確定する。THIS 67 件・THIS-CHILD 191 件の所属関数の型 (SC 伝播の拡張) | 受入 1 | [SR-48] |
| (b) 関数内の未解決: STACKSLOT 95 件 (spill 対応の拡張)・NODOM 242 件 (支配の判定の精度。うち間接 jmp 関数の 89 件は支配を見ないため全件 NODOM)・INDEX 58 件・CALLRET 43 件・CLOBBER 12 件・ENTRY 15 件 | 受入 1 | [SR-49] |
| (c) 実 VSTGUI 上の動的確認 | SR-30 受入 4 相当 | `#68` 残作業 (GUI lift 時) |
| (f) `pop` が ARITH に入る分類 (§2 の ARITH 行)。本入力の影響は 0 件 (ARITH 1 件は `add`)。他の入力では `pop` を誤分類し得る | §2 の分類 | 親 #2174 へ提案 (修正は [SR-49] #3237 の関数内分類と併せて。直すときは §2 を同時に再測定する) |

解消 (本 PR): 旧 (d) の n≥3・ネガティブコントロール・間接 jmp 関数の件数は §4 で実測した。旧 (e) の `ind` 集計は測定 commit `06ca6fb0` で修正し、§3 を書き直した。
