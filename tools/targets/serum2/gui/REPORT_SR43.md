# REPORT — [SR-43 #2174] SerumController 間接呼出の受信 base の this 遡り (候補 1052 件・静的・関数内)

- 日付: 2026-10-14 / 親: #2135 (SR-41) / 前段: `REPORT_SR41.md` §2 (受信レジスタの直前の定義元の分類 `receiver_origin.py`)
- 範囲: 静的解析のみ。所属関数の中だけを見る (呼出元の引数は追跡しない)。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-38・SR-41 と一致)。作業用 dir はリポジトリ外。
- 測定 commit: `8bbf9c9e` (`receiver_this_trace.py` を最後に変えた commit)。このコミット以降にコードは変えていない (§4 の差分 0 行)。

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
| ARITH | 1 | 演算結果。`classify()` は mov/movzx/movsx/movsxd/movabs/lea/copy/load 以外の書き込みを既定の ARITH に入れる。`pop` (スタックからの load) もここに入る (分岐していない。`pop rcx` → `('arith', 'pop')` を確認)。この 1 件が `pop` かどうかは本 run では未確認 (入力素材なし) |
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
- **撤回**: 旧記述「間接 jmp を含む関数の NODOM は 0 件だった (switch 表による打ち切りではない)」は根拠にならない。出力の `ind` 行は `r[4].endswith("NODOM")` で数えるが、`receiver()` の top-level 不動点は `R-nodom` (小文字) を返すため、この集計は R 経路の NODOM を数えない (`"R-nodom".endswith("NODOM")` は偽)。間接 jmp 関数の候補件数と、0 件になり得る理由 (候補が無い / 定義が無く entry になる) は未測定。
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
```

- 依存: `pefile` `capstone` `zstandard`。
- 実測 (n=1・逐次・runner 上。測定 commit `8bbf9c9e`。load は実行前後の 1 分値):
  - 展開・`7z x` は本 run では時間を計測していない (展開の所要は SR-41 の別 run の値。本 run の sha256 は一致を確認)。
  - `receiver_this_trace.py`: real 24.95 s / user 23.55 s / sys 1.40 s。load 0.30 → 0.54。出力は同一 commit で 2 回とも一致。
  - 候補件数 1052 は `receiver_origin.py` の出力 (同じ入力) と一致。sha256 は SR-38/41 と一致。
- 検証: `git diff 8bbf9c9e HEAD -- tools/targets/serum2/gui/receiver_this_trace.py` の出力は 0 行 (測定後にスクリプトは変えていない)。
- 報告前コマンド (`docs/WORKFLOW.md` §6・検証 HEAD `26bdd879` の worktree で実行。出力は全て 0 行・rc 0):
  - `git status --porcelain=v1 -- tools/targets/serum2/gui` → 0 行 (取りこぼし・他担当の WIP 混入なし)
  - `find tools/targets/serum2/gui -type f -size +20M -not -path '*/work/*'` → 0 行 (20MiB 超の blob なし)
- 本 run で未実施: n≥3 の再測定 (min–max・load・並列数)、ネガティブコントロール (支配判定 `Fn.dominated`・spill 検出 `find_store`・this 遡り `origin` の 1 件破壊で分類が変わる件数)、間接 jmp 関数の候補件数。`plugins-serum2` が `$ARTIFACTS_DIR` に無く、ローカルの検証スナップショットも無いため。`oc_artifacts: plugins-serum2` で再起動した run で実施する (§5 (d))。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) ARG 240 件・ARG-CHILD 68 件の呼出元をたどり、引数の型 (SerumController か) を確定する。THIS 67 件・THIS-CHILD 191 件の所属関数の型 (SC 伝播の拡張) | 受入 1 | [SR-48] |
| (b) 関数内の未解決: STACKSLOT 95 件 (spill 対応の拡張)・NODOM 242 件 (支配の判定の精度)・INDEX 58 件・CALLRET 43 件・CLOBBER 12 件・ENTRY 15 件 | 受入 1 | [SR-49] |
| (c) 実 VSTGUI 上の動的確認 | SR-30 受入 4 相当 | `#68` 残作業 (GUI lift 時) |
| (d) n≥3 の再測定 (min–max・load・並列数)・ネガティブコントロール (3 判定点の 1 件破壊で分類が変わる件数)・間接 jmp 関数の候補件数 | §4 の実測の再現性と §3 の検証 | 本 PR (`oc_artifacts: plugins-serum2` で再起動後に実施。子 issue は起票しない) |
| (e) `ind` 集計が `R-nodom` を数えない欠陥 (§3 撤回の原因) | §3 の記述 | 本 PR (修正は測定 commit を変えるため、修正 commit と同時に再測定する) |
| (f) `pop` が ARITH に入る分類 (§2 の ARITH 1 件の内訳) | §2 の内訳 | 本 PR (分類を直す場合は §2 を同時に再測定する) |
