# PY-274 (#3937): 公開表 0x12acb70 と動的メソッド表 0x12ab520 (TFXForm) の第 2 引数 rdx の発火側

親: #3901 (PY-268)。前段: `tools/python/REPORT_PY268.md` §1〜§4 (公開表・DMT・DFM の確定と、発火側の未確定)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと参照走査による解析)。
KPI: 起動・GUI に関わらないため記載不要 (解析のみ)。

## 結論

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. 0x12acb70 の発火側 (OnClick を呼ぶ Click 系) を特定し、rdx の出どころを確定 | **未確定** (本 run では同定できず) | §3 |
| 2. 0x12ab520 の発火側 (DMT を引く動的ディスパッチ関数) を特定し、rdx の出どころを確定 | **部分確定**: 動的ディスパッチ関数は `0x410090` (TObject.Dispatch 相当) と確定。rdx は Dispatch に渡された TMessage* をそのまま handler へ渡す。TMessage* の上流 (0x410090 を呼ぶ箇所) は未同定 | §2 |

issue #3937 の受入は満たしていない。`Refs #3937` の部分達成。

## 0. 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) を `tar --zstd -xf ... -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin'` で展開 (1.6 秒)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- 検証起点: origin/main `c12d6f08b` の worktree (`ws-3937`・branch `3937-py274-rdx-firing-sites`)。
- 既存 probe `pe_py268_rdx.py` は 22/22 PASS を再現 (23.8 秒)。

## 1. 公開表 (参照)

PY-268 §1 の確定を前提とする。0x12acb70 は VMT 0x1277f38 (TFXForm) の公開表 (0x12793f3・120 件) のエントリで、DFM の `TQuickMenuItem "MoveLeftMenu"` の `OnClick` に対応する。

## 2. 0x12ab520 の発火側 (受入 2・部分確定)

- 動的ディスパッチ関数 `0x410090`: `rsi = rdx` (TMessage* を退避)。`movzx rax, word [rsi]` で msgid を読み、`1 ≤ msgid < 0xc000` のとき `0x40ff70(rcx=[rbx], edx=msgid)` で DMT を引く。見つかれば `call [rbp+0x20]` で handler を `(rcx=obj, rdx=rsi)` で呼ぶ。見つからなければ `call [vmt-0x38]` (DefaultHandler) へ同じ rdx を渡す。
- 検索関数 `0x40ff70`: `rcx` の VMT から `[VMT-0x90]` (DMT) を読み、msgid を線形探索する。無ければ `[VMT-0x78]` (親 VMT) へ進む (PY-72 の既述と一致)。
- 0x12ab520 は DMT 0x127a2b7 の handler。DMT の index 0x057f を msgid とした検索で、`0x410090` の経路に乗る。rdx の意味: `rdx = TMessage*` (推定。handler の受ける第 2 引数はメッセージ構造体のポインタ)。
- 0x410090 への direct call は 0 件。呼出し元は関数ポインタ経由 (rdx = TMessage* を作る上流は未同定)。
- 未同定: 0x410090 を呼ぶ箇所 (TMessage を作って Dispatch に渡す窓プロシージャ等)。`pe_callgraph.py callers` は direct call のみを数えるため、間接呼出しの追跡は別 probe が要る。

## 3. 0x12acb70 の発火側 (受入 1・未確定)

- 発火側は TMenuItem 系の Click (`FOnClick(Self)` に相当) とみられる。rdx = Sender (推定)。
- `TMenuItem` の VMT 0x838c10 の仮想スロットを走査し、`[rcx+0x...]` 経由で `FOnClick` を呼ぶ関数の候補 (0x8413f0・0x83d6f0・0x83d3f0 等) を確認したが、`FOnClick` のフィールドオフセットと呼出し形 (`call [FOnClick.Code]`・rdx = Sender) を一致させるところまでは未完了。
- 0x12acb70 への direct call・RIP 相対参照は 0 件 (PY-268 §2 と同じ検査)。

## 4. 検証

- probe: `tools/python/analysis/flapi/pe_py274_dispatch.py` (8 件)。0x410090 の rsi/rdx の受け渡し、0x40ff70 の `[VMT-0x90]`・`[VMT-0x78]`、0x410090 への direct call 0 件を照合する。
- 測定 commit (コードを変えた最後の commit): `ba8eac379`。同一 commit で 3 回測定し、いずれも 8/8 PASS・終了 0。
  - 所要: 20.57 秒・20.50 秒・19.90 秒。load average (1 分値・4 コア): 開始前 0.37・0.55・0.68。
  - 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py274_dispatch.py`
- 差分の証跡: `git diff ba8eac379 HEAD -- tools/python/analysis/flapi` の出力は 0 行 (本 REPORT の commit は docs のみ)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x12acb70 の発火側 (TMenuItem の Click 系・FOnClick の呼出し形) と rdx = Sender の出どころ | 受入 1 | [PY-320] #4346 |
| 0x410090 を呼ぶ上流 (TMessage を作る窓プロシージャ・間接呼出しの経路) と msgid 0x057f の送り手 | 受入 2 の rdx (TMessage*) の出どころ | [PY-321] #4347 |
