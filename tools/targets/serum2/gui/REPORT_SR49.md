# REPORT — [SR-49 #3237] SerumController 間接呼出の受信 base: 関数内の未解決 (spill・支配・添字・戻り値) の解決

- 日付: 2026-10-15 / 親: #2174 (SR-43) / 前段: `REPORT_SR43.md` §2 (`receiver_this_trace.py` の分類)
- 範囲: 静的解析のみ。所属関数の中だけを見る。関数間 (呼出元) は #3237 の範囲外 ([SR-48] へ)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-43 と一致)。
- 測定 commit: `ddfb27fb4` (`receiver_this_trace.py` を最後に変えた commit)。ベースライン: `06ca6fb0` (SR-43 の測定 commit)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. STACKSLOT 95 件: spill の store 検出を広げ、解決件数と残りの理由を書く | **部分達成**。spill 検出を call 越えに広げ、STACKSLOT 80 件 (vptr 経路) のうち 59 件を `OUTPARAM` (呼出の出力引数として書かれたスロットと仮定した分類。個別確認は 1 件・§3) に移した。残り 10 件は STACKSLOT のまま。R 経路 15 件は 11 件が ENTRY・4 件が OUTPARAM に移った (§2) |
| 2. NODOM 242 件: 支配判定の精度を上げ、偽陰性・偽陽性を書く | **未達 (未着手)**。本 run では支配判定に触れていない。子 issue へ分割 (§5) |
| 3. INDEX 58・CALLRET 43・CLOBBER 12・ENTRY 15: 残りの原因を件数で分類する | **達成** (§2 に件数。原因の深掘りは未着手) |
| 4. 測定 commit と再現手順を書く | **達成** (§4) |

## 1. 変更 (`receiver_this_trace.py`)

1. **`find_store` の call 越え**: 従来は窓内の `call` で打ち切っていた。スロットのアドレスを `lea` で取っていない (escape していない) 限り、call を越えて store を探す。
2. **escape の判定**: `slot_escapes(fn, mem, 0, k)` は、関数先頭から使用 `k` までに `lea` でスロットの address を取る命令の有無。escape したスロットは call を越えず、store が無ければ `OUTPARAM` にする。
3. **新分類 `OUTPARAM`**: escape したスロットの load で store が見つからないもの。例: `0x18000f55b` は `lea r8,[rbp-0x10]` を出力引数にして直前の `call [r9]` (QueryInterface 型) が書いたスロットを `call [rax+0x38]` の receiver に読んでいる。spill の取り逃しではなく、呼出の出力。
4. **lea 規則 (`find_store`)**: 後ろ向きの store 探索の途中で、同じスロットへの `lea` (escape) に当たったら store を探さず `None` を返す。意図: `lea` でアドレスを渡した後は、呼出先がスロットを書き換えうるため、それより前の store の値は信用できない。この規則を通ると、`store → lea → load` の並びは store が見つからず、`value()` が escape を理由に `OUTPARAM` へ落とす。つまり store 済みのスロットが `OUTPARAM` に入りうる。本入力での件数は §3。

限界: `slot_escapes` は使用より前の `lea` だけを見る。使用より後に escape するスロットは対象外 (本入力の 10 件の STACKSLOT に該当するかは未確認)。

## 2. 分類結果 (strict・n = 1052)

| 分類 | SR-43 (06ca6fb0) | SR-49 (ddfb27fb4) | 増減 |
|---|---|---|---|
| vptr:THIS | 67 | 69 | +2 |
| vptr:THIS-CHILD | 191 | 197 | +6 |
| vptr:ARG | 240 | 240 | 0 |
| vptr:ARG-CHILD | 68 | 68 | 0 |
| vptr:NODOM | 132 | 132 | 0 |
| R-nodom | 108 | 108 | 0 |
| vptr-emb:NODOM | 2 | 2 | 0 |
| vptr:STACKSLOT | 80 | 10 | −70 |
| vptr:OUTPARAM | (なし) | 59 | +59 |
| R-stackslot | 15 | 0 | −15 |
| R-entry | 15 | 26 | +11 |
| R-outparam | (なし) | 4 | +4 |
| vptr:INDEX | 58 | 59 | +1 |
| vptr:CALLRET | 41 | 42 | +1 |
| vptr-emb:CALLRET | 2 | 2 | 0 |
| vptr-emb:THIS-EMB | 20 | 20 | 0 |
| vptr:CLOBBER | 7 | 7 | 0 |
| R-clobber | 5 | 5 | 0 |
| vptr:ARITH | 1 | 2 | +1 |
| **合計** | **1052** | **1052** | 0 |

- STACKSLOT の移動先 (vptr 経路 70 件・R 経路 11 件は R-entry へ): OUTPARAM 59・THIS-CHILD 6・THIS 2・INDEX 1・CALLRET 1・ARITH 1 (内訳は TSV の `cat_strict` で確認可能)。
- 増えた THIS 2 件 (`0x180149bc0`・`0x180149d87`): 所属関数 `0x180149a70` で `mov [rbp-0x10], r14` (r14 = rcx = this) の store があり、後続の `call` は `[rbp-0x10]` を書き換えていない。元の STACKSLOT は取り逃しだった。
- `R-stackslot` が 0 になったのは、R 経路の spill 検出も同じ `find_store` を通るため。R-entry 11 件は、store を call 越えで見つけた結果 `rsi` 等の関数先頭からの値に行き着いた件 (件数の内訳は未確認)。

## 3. 限界 (結論を読むときの注意)

- `OUTPARAM` は「呼出の出力引数として書かれた」を仮定した分類。出力であることを個別に確認したのは `0x18000f55b` の 1 件のみ。残り 58 件は未確認。
- lea 規則 (§1 の 4) の件数: 測定 commit `ddfb27fb4` の分類器で、`find_store` が lea 規則に当たった回数は **0 件** (一時計測・`work/` 内・非コミット)。規則を外した一時コピーでも TSV md5 は `1e1f5500…` で同一 (分類の変化 0 件)。したがって `OUTPARAM` 59 件・`R-outparam` 4 件・件数表は、lea 規則の有無で変わらない。
- `slot_escapes` は使用より前の `lea` だけを見る (§1 限界)。
- NODOM 242 件 (支配判定) は本 run で手を入れていないため、偽陰性・偽陽性の件数は未測定。
- SR-43 §3 の限界 (関数間の追跡・支配判定の関数内 CFG のみ・間接 jmp 関数の 89 件) は変わらない。

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

- 入力の確認: `Serum2_win64.vst3` の sha256 `501e7bb3…` / 19,236,864 B (SR-43 と一致)。
- 決定性: 測定 commit の 3 回の実行で TSV md5 が全て `1e1f5500…` で一致。ベースライン (`06ca6fb0`) の TSV md5 は `ea2d93a2…`。
- 実測 (`ddfb27fb4`・n=3・逐次・並列数 1・nproc=4。load は `/proc/loadavg` の 1 分値):

| 実行 | real (s) | user (s) | sys (s) | load 開始 → 終了 |
|---|---|---|---|---|
| 1 | 24.61 | 23.26 | 1.34 | 0.21 → 0.48 |
| 2 | 24.48 | 23.07 | 1.40 | 0.48 → 0.63 |
| 3 | 24.23 | 22.88 | 1.34 | 0.63 → 0.76 |
| min–max | 24.23–24.61 | 22.88–23.26 | 1.34–1.40 | |

- 報告前コマンド (`docs/WORKFLOW.md` §6): `git diff ddfb27fb4 HEAD -- tools/targets/serum2/gui/receiver_this_trace.py` は 0 行 (測定後にコードを変えていない)。`git diff ddfb27fb4 HEAD --stat -- tools/targets/serum2/gui` は `REPORT_SR49.md` の 95 行追加のみ。`git status --porcelain -- tools/targets/serum2/gui` は 0 行 (commit 後)。20MiB 超の blob は 0 件。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (b-1) NODOM 242 件の支配判定の精度 (偽陰性・偽陽性) | 受入 2 | #4097 [SR-58] |
| (b-2) OUTPARAM 59 件の出力引数であることの個別確認・呼出先の型 | 受入 1 の解釈 | #3236 [SR-48] |
| (b-3) 使用より後に escape するスロット (`slot_escapes` の限界)・INDEX 59・CALLRET 42・CLOBBER 12・ENTRY 26 の原因の深掘り | 受入 1・3 | #3237 に残す (次の run) |
| (a) ARG 240・ARG-CHILD 68 の呼出元 | SR-43 の (a) | #3236 [SR-48] |
| (f) `pop` の ARITH 分類 | §2 の分類 | #2174 は CLOSED のため、open の #3237 にコメントで提案 |
