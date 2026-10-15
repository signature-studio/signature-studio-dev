# REPORT — [SR-48 #3236] Serum 2 間接呼出の受信型: 引数・this 型の関数間伝播 (SR-43 残 a)

- 日付: 2026-10-15 / 親: #2174 (SR-43) / 前段: `REPORT_SR43.md` (受信 base の this 遡り・候補 1052 件)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-43 と一致)。作業用 dir はリポジトリ外。
- 測定 commit: `1c21885fb` (`sr48_arg_this.py` を追加した commit)。以降のコード変更は無い。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. ARG 240 件・ARG-CHILD 68 件の呼出元をたどり、SerumController の this かを確定する | **未達。確定 0 件**。直接 call/jmp の呼出元が見えるのは 8 件 (ARG) のみで、その値は this ではなく別の引数・子オブジェクトだった。残り 232 件は直接の呼出元が無い (§2) |
| 2. THIS 67 件・THIS-CHILD 191 件の所属関数について、SC 伝播を拡張し、SC の証拠の件数を書く | **未達。SC 証拠 0 件**。SC 集合は 21 → 22 関数 (末尾 jmp の 1 件を追加) したが、THIS 67 件の所属関数 (63 関数) はどれも SC に入らなかった |
| 3. 測定 commit と再現手順を REPORT に書く | **達成** (§4) |

本 run で得たもの: 「ARG の呼出元が直接 call で見えない」ことの件数 (232 件・うち 230 件は関数アドレスとしてデータ表に現れる) と、SC 伝播を末尾 jmp に広げた場合の結果。型の確定には、関数アドレスを載せるデータ表 (vtable 形) の組立元を見る別の方式が要る (§5)。

## 1. 方法 (`sr48_arg_this.py`)

- `receiver_this_trace.py` (SR-43) を `runpy` で読み込み、その遡り (`value`・候補・SC 集合) を使う。自己検査: 拡張なしの SC 集合が base の 21 関数と一致することを毎回確かめる。
- ARG: 候補の所属関数 F の引数レジスタ R (rdx/r8/r9) について、F へ直接 `call` する呼出元 G ごとに、G で R を遡る。G の rcx が this で G が SC なら `SC`、G の引数なら再帰 (深さ 2)。
- THIS: 所属関数 F の this について、F を直接 `call` する G ごとに、G で rcx を遡る。
- SC 拡張: 直接 `call` に加えて末尾 `jmp` (thunk の tail call) で rcx が this のまま渡される先を不動点まで加える。

## 2. 分類結果 (n = 1052)

SR-43 の分類 (strict) は同一 (`vptr:ARG` 240・`vptr:THIS` 67・`vptr:THIS-CHILD` 191 ほか)。

| 対象 | 件数 | 判定 | 内訳 (呼出元の値) |
|---|---|---|---|
| ARG (直接の引数) | 240 | 確定 0 | `nocaller` 232・`unk` 5・`unk-child` 6 (呼出元が 1 件以上の候補は 8 件) |
| 　うち直接呼出元なし | 231 (関数 117 個) | — | うち 230 件は関数アドレスとしてデータ表 (`.rdata`/`.data`) に現れる |
| ARG-CHILD (親の引数) | 68 | 確定 0 | `nocaller` 57・`unk` 55・`unk-child` 1 |
| THIS | 67 (関数 63) | SC 証拠 0 | 呼出元 `nocaller` 22・`this-nonSC` 16・`unk` 22・`unk-child` 28 |
| THIS-CHILD | 191 | 型未確定 | 所属関数の SC 0 件 |

- SC 集合: 拡張なし 21 関数 (base と一致)。末尾 jmp を加えると 22 関数 (+1)。
- THIS の呼出元で `this-nonSC` と判定された 16 件は、呼出元の this が SC でない (SC の証明ではなく、SC に入らなかったという事実)。
- `unk` は、遡りが this・引数の受け取りに届かなかった (定義が見つからない・store/load を通った等)。

## 3. 限界 (結論を読むときの注意)

- 関数間の追跡は、直接 `call`/`jmp` の即値アドレスだけを見る。vtable 経由の呼出し (`call [reg+disp]`) の宛先は見ない。Serum 2 の GUI ハンドラは vtable 経由で呼ばれるため、直接呼出元が無いのは主にこの理由と見られる (未検証)。
- ARG の型は呼出元の this の型で決まる。`this-nonSC` は「SC でない this」を示すが、SC の型そのものを証明しない。
- 表の組立元による型の確定は試みたが、表の境界 (連続する関数ポインタの run の先頭) の決め方が合わず、組立元を 1 件も得られなかった。このため結果には含めず、スクリプトからも外した (§5 の子に残す)。
- `THIS` の型は証明していない (SR-43 §3 と同じ)。

## 4. 再現手順・実測

```sh
# $S: リポジトリ外の作業用 dir (RUNNER_TEMP 配下)。$P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/sr48_arg_this.py Serum2_win64.vst3 --tsv sr48.tsv
```

- 依存: `pefile` `capstone` `zstandard`。
- 実測 (n=3・逐次・測定 commit `1c21885fb`。load は `/proc/loadavg` の 1 分値):

| 実行 | real (s) | load 開始 → 終了 | stdout md5 | TSV md5 |
|---|---|---|---|---|
| 1 | 25.53 | 0.36 → 0.58 | `83917015…` | `f347f0af…` |
| 2 | 25.58 | 0.58 → 0.73 | `83917015…` | `f347f0af…` |
| 3 | 25.58 | 0.73 → 0.82 | `83917015…` | `f347f0af…` |

- 決定性: 3 回の stdout md5 と TSV md5 が全て一致 (表示の集合は整列済み)。
- 報告前コマンド (`docs/WORKFLOW.md` §6) の結果は §6 に記載する。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) ARG 232 件 (直接呼出元なし) の型確定。vtable 経由・データ表の組立元からの追跡 | 受入 1 | [SR-59] #4122 |
| (b) THIS 67 件・THIS-CHILD 191 件の所属関数の SC 証拠の拡張 (vtable 経由の呼出元) | 受入 2 | [SR-59] #4122 |
| (c) 関数内の未解決 (STACKSLOT・NODOM・INDEX・CALLRET・CLOBBER・ENTRY) | 受入 1 の前提 | [SR-49] #3237 |
| (d) 実 VSTGUI 上の動的確認 | SR-30 受入 4 相当 | `#68` 残作業 (GUI lift 時) |
