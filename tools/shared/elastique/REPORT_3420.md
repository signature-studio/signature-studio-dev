# tools/shared/elastique — 間接 call 宛先 0x1803c4710 の IPP 同定 (T-SH-80 / #3420)

親: #3334 (付録 §9.5 の宛先。その付録は未 merge の PR #3396 にあり main には無い)。既知の類型との関係: 該当なし (`docs/DEFECTS.md`)。静的解析のみで、Windows 実行ではない。所有者限定 tier 専用 (`docs/DECISIONS.md` D20)。公開 tier の成果物に含めない。

## 0. 結論

| 受入条件 (#3420 の本文) | 結果 |
|---|---|
| 1. 宛先の本体と呼出元を読み、IPP API 名か「未同定」を付ける | **API 名 `ippsSum_32f` の内部カーネル** (経路上の API。宛先自体は export ではないので、export 名は付かない)。根拠は正規化命令列の SHA-1 完全一致 (dsp_ippv2 の 3 本体) と、dsp の直接 call 経路 (`ippsSum_32f` の dispatch 変種 3 本から到達)。呼出元 `0x1803c4850` の dsp 側の呼出元は静的に見つからず (§7) |
| 1 の後段. API 名が付いたら tools/ipp の実装対応 | `ippsSum_32f`: `implemented_poc=0` (fail-soft stub のみ・PoC 未実装)。本件は同定のみで実装しない (§6) |
| 2. 測定 commit・再現コマンド・差分を REPORT に書く | 測定 commit `b7695367b` (§2)。`git diff b7695367b HEAD -- tools/shared/elastique` は 0 行 (§2) |

## 1. 対象・素材・前提

- 対象: `elastique_x64.dll` (素材 `block24357_PE.bin`)。照合先: `dsp_ippv2_x64.dll` (`block24356_PE.bin`)。素材 `fl-win64` の 2 ファイルだけを `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" extracted/block24357_PE.bin extracted/block24356_PE.bin` で取り出した (`tools/**/work/` には置かない)。
- 前提の扱い: #3334 の付録 §9.5 (分岐元 `0x1803c480a`・宛先 `0x1803c4710`・rate48k で 8 回) は PR #3396 (未 merge) にある。本 REPORT は main の素材から静的に組み直した。動的の再現 (`dyn_trace.py` の rate48k) は main に無いので行っていない。
- 以下のアドレスは VA (ImageBase `0x180000000` + RVA)。

## 2. 再現・測定

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" extracted/block24357_PE.bin extracted/block24356_PE.bin
ELASTIQUE_DLL="$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" DSP_IPP_DLL="$RUNNER_TEMP/fl-win64/extracted/block24356_PE.bin" python3 tools/shared/elastique/ipp_target_ident.py
```

- 測定 commit: **`b7695367b`** (`ipp_target_ident.py` を追加した commit。以後このファイルは変えていない)。
- 差分 (測定後のコード範囲): `git diff b7695367b HEAD -- tools/shared/elastique` → 0 行。
- 実測 (real): **51.22 s** (user 51.01 s)・load average (1 分) 0.33 → 0.71。HEAD で再実行した出力は、初回の出力と全行一致した。
- 出力は標準出力のみ。`tools/shared/work/` は使わない。

## 3. 実測出力 (測定 commit `b7695367b`)

```
elastique: $ELASTIQUE_DLL
dsp_ippv2: $DSP_IPP_DLL
[1] 宛先 0x1803c4710: 正規化 44 命令 SHA-1 6302466faf91e42277f047b5a6eafd5b9726958e
    分岐元 0x1803c480a の関数 0x1803c47b0-0x1803c4844: 正規化 43 命令 SHA-1 5ed6dc1a1c9f4634a0da44b69ce96b93fde1cdfa
    宛先を指す lea rip: ['0x1803c47c8', '0x1803c4868']
    宛先を指す rel32 call/jmp: 0 箇所
    分岐元の関数内の lea rip (IPPCODE 宛先): 0x1803c47c8->0x1803c4710, 0x1803c47db->0x1803c46d0
    IPPCODE 内の間接 call/jmp (レジスタ・メモリ経由): 186 箇所
[2] 既存の照合 (ipp_entries.py と同じ候補集合): export 446・reach 12 段・候補 5825 本体
    宛先: 完全一致 0 本体・export 名 なし
    分岐元の関数: 完全一致 3 本体・export 名 なし
[3] 広い照合 (dsp IPPCODE 全体で同じ先頭 7 byte の位置を SHA-1 で照合)
    宛先: 完全一致 3 件 ['0x181a94620', '0x181a95430', '0x181a96240']
    分岐元の関数: 完全一致 3 件 ['0x181a946c0', '0x181a954d0', '0x181a962e0']
    dsp の lea 0x181a946d8 -> 0x181a94620 は分岐元の関数の完全一致 0x181a946c0 内
    dsp の lea 0x181a954e8 -> 0x181a95430 は分岐元の関数の完全一致 0x181a954d0 内
    dsp の lea 0x181a962f8 -> 0x181a96240 は分岐元の関数の完全一致 0x181a962e0 内
    宛先を lea で指す別の関数 0x1803c4850 (50 命令・SHA-1 1e790968d438): dsp 完全一致 ['0x181a94760', '0x181a95570', '0x181a96380']
[4] dsp の呼出し経路 (rel32 の直接 call を逆に遡る。export 名または dispatch 変種に当たるまで)
    0x181a946c0: 経路 0x180cb45a0 → 0x180db08e0 → 0x181a946c0 → 名 ippsSum_32f
    0x181a954d0: 経路 0x180cb4600 → 0x180db0920 → 0x181a954d0 → 名 ippsSum_32f
    0x181a962e0: 経路 0x180cb4660 → 0x180db0960 → 0x181a962e0 → 名 ippsSum_32f
    0x181a94760: 6 段内で export に当たらず
    0x181a95570: 6 段内で export に当たらず
    0x181a96380: 6 段内で export に当たらず
[5] tools/ipp の実装対応 (tools/ipp/data/ipp_matrix.csv の implemented_poc)
    ippsSum_32f: implemented_poc=0
```

数え方: 「正規化命令数」は `ipp_entries.tokens` の出力数 (`ret` まで・分岐先と rip 相対変位は伏せる)。「dsp 候補」は `ipp_entries.py` の照合対象と同じ集合 (export 表の変種を 12 段まで direct call で辿ったもの + dsp .text 由来の IPPCODE 着地点)。

## 4. 同定

- 宛先 `0x1803c4710` (44 命令) は、float の SSE 総和カーネル。`xorps`・`addps` のアンロールで 16 要素ずつ加算し、末尾の `shufps` / `addps` で水平和を取る。`rcx` に残り要素数、`rdi` に先頭ポインタが入る。
- 呼出し: 分岐元 `0x1803c480a` (`call rax`) は関数 `0x1803c47b0` (43 命令) の中にある。`rax` には直前の `lea rax,[rip-0xbf]` (`0x1803c47c8` → `0x1803c4710`) か `lea rax,[rip-0x112]` (`0x1803c47db` → `0x1803c46d0`) が入る。宛先を指す `lea` は 2 か所 (`0x1803c47c8` と、別の関数 `0x1803c4850` 内の `0x1803c4868`)。rel32 の直接 call は 0 箇所。
- 完全一致 (SHA-1):
  - 宛先: dsp の 3 本体 (`0x181a94620`・`0x181a95430`・`0x181a96240`)。
  - 分岐元の関数 `0x1803c47b0`: dsp の 3 本体 (`0x181a946c0`・`0x181a954d0`・`0x181a962e0`)。各々が、上の 3 本体のどれか 1 つを `lea` で指す。
- dsp の呼出し経路 (rel32 を逆に辿る): `0x180cb45a0` → `0x180db08e0` → `0x181a946c0`、`0x180cb4600` → `0x180db0920` → `0x181a954d0`、`0x180cb4660` → `0x180db0960` → `0x181a962e0`。先頭の 3 つは `ippsSum_32f` の dispatch 表の変種 (`ipp_entries.dispatch_table`)。
- 結論: 宛先は `ippsSum_32f` の経路上の内部カーネル。API 名として `ippsSum_32f` を付ける (入口ではない)。

## 5. 方法の限界・既存結果への影響

- 既存の reach (`ipp_entries.py` の `direct_calls`) は、関数を最初の `ret` で止める。`0x180db08e0` は `0x180db0906` で早期 `ret` し、`call 0x181a946c0` (`0x180db090c`) はその後にある。このため §3 [2] で `0x181a946c0` は export 名なしの候補になり、`data/entries.csv` の `0x1803c47b0` (`exact_dsp_internal_no_export`) も同じ理由で名前が付いていない。修正は子 #3457 (T-SH-85)。
- 静的な lea 走査 (`ipp_entries.py` の `indirect_scan`) は `.text` だけを数える。本 REPORT では IPPCODE 内の `lea rip` も数えた (宛先への `lea` 2 件は、どちらも IPPCODE 内)。REPORT.md §6 の文言の直しは #3457。
- 呼出元 `0x1803c4850` (50 命令) の dsp 複製 3 本 (`0x181a94760`・`0x181a95570`・`0x181a96380`) には、dsp 内の `lea`・rel32・データ中の関数ポインタの参照が 0 件。したがって、この経路は静的には追えなかった (§7)。
- 動的な呼出し (rate48k での `0x1803c480a` → `0x1803c4710` の 8 回) は PR #3396 の結果の引用。main では再現していない。
- 近似比は使っていない。一致は正規化命令列の SHA-1 完全一致だけ。

## 6. tools/ipp の実装対応

`tools/ipp/data/ipp_matrix.csv`: `ippsSum_32f` は `implemented_poc=0` (fail-soft stub のみ・`tools/ipp/REPORT.md` §11)。同じく `ippsSum_64f` も 0。本件は同定のみで、tools/ipp の実装は行わない (#2613 の受入 2 と同じ方針)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出元 `0x1803c4850` の dsp 複製 3 本 (`0x181a94760`・`0x181a95570`・`0x181a96380`) の呼出し経路。dsp 内に静的な参照が 0 件 | この呼出元の API 名が未同定。宛先の API 名 (`ippsSum_32f`) は、呼出元 `0x1803c47b0` の経路で確定している | PM の判断 (追跡のみ。子は作らない) |
| `direct_calls` の最初の `ret` での停止、と IPPCODE の lea 走査範囲 (`ipp_entries.py`・REPORT.md §3・§6) | §3 の名前付けが過小 (`0x1803c47b0` など)。§6 の文言が測定範囲に合わない | 子 #3457 (T-SH-85) |
| 動的な再現 (rate48k・`dyn_trace.py`) | 呼出し値の実行時確認が main に無い | PR #3396 (未 merge。#3334 の残り) |
