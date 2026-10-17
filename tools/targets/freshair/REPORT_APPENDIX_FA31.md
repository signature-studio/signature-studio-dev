# freshair FA-31 (#2207): 実機 controller map (C+0x318 木) の node 有無 — 木を埋める経路の特定と harness 観測

FA-30 (#2187, `REPORT_APPENDIX_FA30.md` §5) で未解決として #2207 に移した「実機 controller map に node があるか」の付録。
判定基準 (`run_fa9.sh` (a) の期待値) は変更していない。既知類型: 該当なし。

## 1. 結論

- **受入 1 (実機の controller map を空 map 以外の実経路で観測): 未達。** 本 harness の経路では木 (`[ctl+0xa8]`) を埋める関数が 1 回も実行されない。
  F ctor と PROCESS の全 8 シナリオで、木への挿入候補 `0x180caa820` と、その上流 5 関数 (`0x180e13590`・`0x180e12f20`・`0x180e15030`・`0x180d8ae60`・`0x180d8c4f0`) の呼出は 0 回 (§3)。
  UI 入口 (`0x180d8c0b0`・`0x180d8d700`・`0x180d8c140`) は probe していない (§5)。したがって node の有無は本 harness では観測できない。
- **受入 1・2: 未達** (2 は 1 の未達により判定対象なし。node の有無を前提にする判定は未実施)。**受入 3・4: 達成** (3: (a) の期待値は不変。4: 測定 commit と実測値は §4)。
- **新しい静的事実:** 木を埋める候補の上流のうち確認できたものは、UI 系クラスの vtable (slot 5) から到達する (§2)。前回の候補 `0x180a79c30` も UI 系 vtable (`UIGraphicEq`) から呼ばれる。
  直接の E8 呼出とデータ内の絶対ポインタ参照で見える範囲では、挿入候補 `0x180caa820` の根のうち UI 系と確認できたのは popup vtable slot 5 (`0x180d8c0b0`) だけ。`0x180d8cc20` の呼出元 `0x180d8b560` は未展開で、`0x180d8c4f0`・`0x180d8c8b0`・`0x180d8cfe7` は参照が見えず UI 系かは未判定 (§6)。
  実機で木に node が入るのは、GUI の操作 (モジュレーション表示・編集) 経由の可能性がある。**未確認**: 挿入先が C+0x318 の controller と同一か、UI 経路だけで足りるか (boot 連鎖 #672 が要るか)。

## 2. 経路 (静的読み。capstone・pdata 関数境界・vtable 所属。VA)

| 関数 | 静的な役割 | 到達 |
|---|---|---|
| `0x180d8c0b0` | ModulationKnobsPopup の vtable (`0x18110a420`) slot 5 | vtable 経由 (直接 E8 の呼出元なし) → E8 `0x180d8d700` |
| `0x180d8d700` (0xd2d B) | `0x180d8c140` を 4 回呼ぶ | E8 (`0x180d8c140` の呼出元はこの関数のみ) |
| `0x180d8c140` (0x1ad B) | `0x180d8ae60` を呼ぶ | E8 `0x180d8c24b` |
| `0x180d8ae60` (0x298 B) | `0x180e15030` を呼ぶ | E8 `0x180d8aec7` |
| `0x180d8c4f0` (0x3be B) | `0x180e15030` を呼ぶ。上の slot 5 の経路の外 (`0x180e15030` の別の呼出元)。直接の呼出元なし | E8 `0x180d8c7b9` |
| `0x180e15030` (0x67a B) | `0x180e12f20` を呼ぶ | E8 `0x180e1511e` |
| `0x180e12f20` (0x1f3 B) | ModulationFormatter (vtable `0x181110fc8`) を構築する | `lea` で vtable を書く (`0x180e12fae`) |
| vtable `0x181110fc8` slot 2 = `0x180e13590` | 仮想呼出 (直接の E8 なし) | `.?AVModulationFormatter@?A0xc6f8f7e4@@` |
| `0x180e13590` (0x8fe B) | `0x180caa820` を呼ぶ | E8 `0x180e139a2` |
| `0x180caa820` (0x862 B) | **挿入候補**: `[this+0xa8]` を `0x180ca7db0` で lower_bound し、`[this+0x380]` の木を走査、key は u16 (`[r12]`)。無ければ node を作る (vtable `+0x50`/`+0x58` 呼出と、割当と見られる `0x18100beb0` 呼出を含む。詳細は未読) | E8 (`0x180e13590` と自身の再帰) |
| `0x180ca7db0` | 陽性対照: ca1480 の map 経路の lower_bound | E8 `0x180ca1537` (ca1480 の内部) |

- 前回 run の候補 `0x180a79c30` (C+0x2d0/0x328/0x318 を書く) は `0x180a79100` から呼ばれ、`0x180a79100` は `UIGraphicEq` の vtable (`0x1810f5128`) slot 5。UI 側。
- `0x180dde530` (大きな構築関数。`0x180ddef50` を呼ぶ) の呼出元 3 つは未特定 (本付録の範囲外)。

## 3. 観測 (測定 commit `e11367a6b`・`fa31_ctl.sh`・8 シナリオ S900–S907 の epf)

`FA_CTL31=1` の診断フック (`native/native_ctrl.c`, 既定 OFF) で、各関数の入口の呼出回数を数えた。
各 probe は元の機械語を一時復元して本物を呼ぶ (`ca1480` の probe と同じ方式)。陽性対照で方式が効くことを確認した。

| 条件 | ca7db0 (陽性対照) | caa820 (挿入候補) | e13590 | d8c4f0 | d8ae60 | e15030 | e12f20 |
|---|---|---|---|---|---|---|---|
| base (既定・空 map) | **72** | 0 | 0 | 0 | 0 | 0 | 0 |
| node1 (`FA_NODE1=1`・1 node 注入) | 8 | 0 | 0 | 0 | 0 | 0 | 0 |

- ca7db0 が base で 72 回 = ca1480 の呼出数 (72) と一致。probe の方式は効いている。
- caa820 が 0 回のため、CAA31 行 (木のノード数 `tree=`) は出ていない。木のノード数は未観測。
- node1 で ca7db0 が 8 回に減る理由は未確認 (ca1480 の found 経路の違い)。本付録の判定には使わない。
- 0 回の解釈: 観測したのは挿入候補の上流 5 関数までで、UI 入口 `0x180d8c0b0`・`0x180d8d700`・`0x180d8c140` は未 probe。UI 経路が実行されたかは未観測のため、0 回は「挿入候補の上流に到達しなかった」までを示す。

## 4. 測定 (測定 commit `e11367a6b`・HEAD 差分 0 行)

- 測定 commit: `e11367a6b` (コード差分の最終 commit)。`git diff e11367a6b HEAD -- tools/targets/freshair/lift2` = 0 行 (本付録・DOC_MAP の修正は lift2 の外)。WORKFLOW §6 の鮮度基準により再測定は不要。
- 再実行: 素材 `plugins-freshair` が本 fix run の `$ARTIFACTS_DIR` に無いため、e2e は再実行していない。以下は測定 commit の結果。
- 所要時間は全て n=1 の参考値。判定には使わない (未取得の min–max レンジは §5)。
- `bash tools/targets/freshair/lift2/run_fa9.sh`: 初回 (build_ctrl を含む、work 無し) **40.8 s (n=1)**、load 0.10→0.54。**GATE PASS**。
  (a) base: ERR=0・ca1480=72・path=map・eq=1・found=0・da6c00=0 / (b) alt: ERR=8/8 path=static / (b-wasm) alt: wasm ERR=8/8 / (c) pert: 差分 395 トークン・L/R 同一 40 呼出・差分 0 呼出。
- `bash tools/targets/freshair/lift2/run_ctrl.sh 2 5`: **BIT-EXACT 15/15** (epf 8 + structured 2 + random 5, fma0+fma1)、**wall 4.4 s (n=1)**、load 0.50→0.54、rc=0。
- `bash tools/targets/freshair/lift2/fa31_ctl.sh`: rc=0、wall 0.5 s (n=1)、load 0.54→0.54。§3 の表。
- 製品 KPI (FLEngine 起動 dispatch 数・units_run・最初のウィンドウ): **動かしていない** (native harness の診断のみ。起動経路と GUI の挙動は既定で不変)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 木 (`[ctl+0xa8]`) に node が入る経路の実行: UI 系 `0x180d8c0b0` (ModulationKnobsPopup slot 5) から `0x180caa820` までを harness で実行し、木の node 数を観測 | 受入 1・2 が未達 | #2207 (本 issue・open のまま。Refs) |
| UI 入口 `0x180d8c0b0`・`0x180d8d700`・`0x180d8c140` の probe 未実施 | UI 経路が実行されたかが未観測。§3 の上流 5 関数の 0 回は「挿入候補の上流に到達しなかった」までの解釈 | #2207 (Refs) |
| `0x180caa820` の `this` (controller) が C+0x318 の controller と同一か | 挿入先の同定 (受入 1 の前提) | #2207 |
| UI 経路だけで木が埋まるか、boot 連鎖 (#672) が要るか | blocked_by の要否 | PM 判断 (#2207 コメント) |
| `0x180dde530` の呼出元 3 つ (snapin 構築側) の特定 | 木の初期化の全体像 | #2207 |
| node1 で ca7db0 が 8 回に減る理由 | 観測の解釈 (判定には未使用) | #2207 |
| 所要時間の n≥3 min–max レンジ (WORKFLOW §5) の未取得 | §4 の秒数は n=1 の参考値で判定に使わない。素材 `plugins-freshair` が無く再測定できない | #2207 (Refs) |

## 6. 静的到達性: 挿入候補の呼出元の根 (`lift2/fa31_refs.py`)

pdata の関数境界ごとに逆アセンブル (capstone) し、E8/E9 の直接呼出元と、`.text` 以外に現れる 8 バイト絶対ポインタ (vtable 候補) を列挙した。
「直接呼出と絶対ポインタで見える範囲」の結果であり、レジスタ経由の間接呼出・32bit 相対の関数表は走査していない。

| 関数 (VA) | 直接呼出元 (所属関数) | 非 .text の絶対ポインタ参照 |
|---|---|---|
| `caa820` 挿入候補 | `caa820` 自身 (`caa934`)・`e13590` (`e139a2`) | なし |
| `e13590` (ModulationFormatter slot 2) | なし | `.rdata:181110fd8` (vtable `0x181110fc8`) |
| `e12f20` (formatter 構築) | `e15030` (`e1511e`) | なし |
| `e15030` | `d8ae60` (`d8aec7`)・`d8c4f0` (`d8c7b9`) | なし |
| `d8ae60` | `d8c140` (`d8c24b`) | なし |
| `d8c140` | `d8d700` (4 箇所) | なし |
| `d8d700` | `d8c0b0` (`d8c11d`)・`d8c8b0` (`d8c8c8`)・`d8cc20` (`d8cf48`)・`d8cfe7` (`d8d002`) | なし |
| `d8c0b0` (ModulationKnobsPopup slot 5) | なし | `.rdata:18110a448` (vtable `0x18110a420`) |
| `d8cc20` | `d8b560` 内 (`d8b5a8`) | なし |
| `d8c4f0`・`d8c8b0`・`d8cfe7` | なし | なし (静的な参照が見えない) |

読み:
- 挿入候補 `caa820` の直接呼出元は `e13590` と自身だけ。直接呼出・絶対ポインタの範囲では、`e13590` は ModulationFormatter の vtable slot 2 としてのみ到達し、formatter を作るのは `e12f20` だけ (`lea` 参照は未走査。`e12f20` の vtable 書込み `0x180e12fae` は手読み)。
- 上流は `d8d700` → `d8c140` → `d8ae60` → `e15030` の鎖と、`d8c4f0` → `e15030` の枝 (`e15030` の直接呼出元は `d8ae60` と `d8c4f0` の 2 つ)。根は (a) popup vtable slot 5 (`d8c0b0`)、(b) `d8cc20` (← `d8b560`、もう 1 段未展開)、(c) 参照が見えない `d8c4f0`・`d8c8b0`・`d8cfe7` (間接呼出か未使用の経路。未判定)。
- 静的に言えるのは「直接参照で見える範囲では、確認できた挿入の根は UI 系 (`d8c0b0`) の 1 つだけで、他の根は未判定」まで。「UI 以外から到達しない」は言えない (間接呼出は未走査)。よって実機の木に node が有るかは、本付録では判定しない。

未解決 (本 §6 の追加分):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `d8c0b0` (popup slot 5) の入力オブジェクトを構築し、`caa820` まで駆動して木のノード数を観測 | 受入 1・2 (§5 の 1 行目と同じ作業の入口) | #3718 (子 issue [FA-42]・親 #2207) |
| `d8b560` (`d8cc20` の呼出元) の特定と、`d8c4f0`・`d8c8b0`・`d8cfe7` の間接呼出元の走査 | 挿入の根の網羅 | #2207 (Refs) |
| 陰性対照 (呼出元の無い既知関数で `callers=-` が出ることの確認)。本 run では素材が無く実バイナリで実行できない | §6 の『なし』の検出力が未確認 (正対照は caa820・e15030 の呼出検出のみ) | #2207 (Refs) |

## 8. FA-42 (#3718): UI 入口 popup slot 5 (`0x180d8c0b0`) の harness 駆動

- 測定 commit: `863e07193` (`FA_UI31` 診断を追加した commit。`native_ctrl.c` のみ変更)。`git diff 863e07193 HEAD -- tools/targets/freshair/lift2` = 0 行 (以後の変更なし)。
- 診断は既定 OFF。`FA_UI31=1` のときだけ、各シナリオの build_tree 後に `0x180d8c0b0(P, G, NULL, NULL)` を guard 付きで 1 回呼ぶ。
  `P` は 0x1000 B のゼロ埋め。`[P+0xb48]=1`・`[P+0xbb8]=[P+0xbc0]=非 NULL`。`G` は `0x180d215e0` のゲート対象 (先頭 byte=1)。
  カウンタは `d8d700`・`d8c140` を追加 (`CTL31 summary` に `d8d700=` `d8c140=` を追記)。
- 静的な読み (`disasm.py`): `0x180d8c0b0` は先頭で `0x180cb79c0(rcx)`、次に `0x180d215e0(G, [P+0xb48] の参照)` を呼び、真なら `0x180d8d700(P)` を呼ぶ。`0x180d215e0` は第 1 引数 (G) の先頭 byte が非 0 なら即 true、0 なら第 1 引数の配列 (`[G+8]`〜`[G+0x10]`) を第 2 引数の値で走査する。
  SEGV の正確な位置 (どの call か・どのフィールドが偽ポインタか) は未特定。`0x180cb79c0` は `[P+0x1c8]`・`[P+0x1d0]` を読む。
- 実測 (`FA_UI31=1 bash fa31_ctl.sh`、コミット済み HEAD):
  - 8 シナリオ S900–S907 とも **`FAULT rip=0x125afc6 addr=0x125afc6`** (guard の SEGV 捕捉。呼出後に戻らない)。
  - `caa820`・`e13590`・`d8c4f0`・`d8ae60`・`e15030`・`e12f20`・`d8d700`・`d8c140` は全て **0 回**。`CAA31` 行は無し。
  - 落ちる位置 `0x125afc6` は `.text` の外 (`0x18...` の VA ではない)。popup 入力の内部ポインタを 0 埋めのまま辿った結果と見られる。**未確認**: どのフィールドが偽ポインタか (`P` の構築の不足)。
- 既定経路 (`FA_UI31` 無し) の回帰確認: `run_ctrl.sh 2 5` は **BIT-EXACT 15/15** (rc=0)。`fa31_ctl.sh` の base は §3 と一致。
- 所要 (n=1・参考値): `build_ctrl.sh` 30.0 s・`fa31_ctl.sh` 0.37 s・`run_ctrl.sh 2 5` 2.7 s・load 0.30→0.55。この節が所要の唯一の記載箇所。
- 製品 KPI: **動かしていない** (native harness の診断のみ)。

### 8.1 FA-46 (#4036): popup 入力 PB の範囲修正

- 逆アセンブル (`disasm.py`): `0x180d8c0b0` は `[P+0xbb8]` (PB) を this にして `0x180d0a040` を呼ぶ。`0x180d0a040` は `[this+0xb30]`〜`[this+0xb40]` を読み書きし、`0x180d09ac0`・`0x180f8feb0`・`0x180cbb270` を呼ぶ。旧 harness は PB を 0x100 B しか確保しておらず、`+0xb40` まで範囲外だった。
- 修正: `native_ctrl.c` の `FA_UI31` 節で PB を 0x1000 B に拡張 (既定 OFF の診断経路のみ)。
- 実測 (コミット済み HEAD `e6a608487`、`FA_UI31=1 bash fa31_ctl.sh`): base・node1 とも rc=0、S900–S907 は 8 件とも `FAULT rip=125afc6`。`caa820=0 d8d700=0 d8c140=0`。**SEGV は解消せず**。PB の範囲だけでは原因が残ることを確認した。
- SEGV の呼出元 (どの間接 call が `0x125afc6` を指すか) は未特定。gdb は素材環境に無く、guard の `rip`/`addr` だけでは呼出元が取れない。
- 判定: `run_ctrl.sh 2 5` = BIT-EXACT 15/15 (rc=0・2.657 s・load 0.04)。既定経路は不変。
- 測定 commit: `e6a608487`。`git diff e6a608487 HEAD -- tools/targets/freshair/lift2` は本節の追記のみ (コードは変えない)。
- 残り (受入 1〜3・P の構築根拠) は子 issue に分割 (FA-53)。

受入の状況 (#3718):
- 受入 1 (`0x180d8c0b0` から `caa820` まで到達): **未達**。`0x180d8c0b0` は実行されるが、popup 入力が不完全で `d8d700` に届く前に SEGV。
- 受入 2 (`this` と controller の同一判定): **未達** (1 の未達により判定対象なし)。
- 受入 3 (木のノード数 `tree=`): **未達** (`caa820` 未到達)。
- 受入 4 (判定基準 (a) の期待値は不変): **達成** (`run_fa9.sh` の判定式は変更していない)。
- 受入 5 (測定 commit と実測値を REPORT に残す): **達成** (本節)。

## 7. 測定 (`lift2/fa31_refs.py`)

- 測定 commit: `12c4a4fda` (`fa31_refs.py` を追加した commit)。`git diff 12c4a4fda HEAD -- tools/targets/freshair/lift2` = 0 行 (以後の変更は本付録のみ)。
- `python3 tools/targets/freshair/lift2/fa31_refs.py "<SlateCore.core_64>"`: 前回 run の記録で rc=0・9.8 s (n=1)・load 0.14→0.27 (素材 `plugins-freshair` を展開済み (`fetch.sh`))。出力は **26 行** (対象 13 件 × 各 2 行: VA 行 + data-ptr 行。script が対象ごとに `print` を 2 回呼ぶため)。前回の『13 行』は誤記。
- 本 run では素材が無く実バイナリで再実行できない (`$ARTIFACTS_DIR` は `fl-win64` のみ)。行数は、pefile を一時的に差し替えた合成入力 (`.text` 全 ret・pdata に全対象 VA を配置。リポジトリ外・非コミット) で script を実行して確認: rc=0・`wc -l` = 26。9.8 s と load は前回 run の記録で、本 run では再測定していない。
- 判定には使わない (表示のみ)。harness (`native/native_ctrl.c`) と `run_fa9.sh`・`run_ctrl.sh` の経路は本 commit で変えていないため、再測定は不要 (WORKFLOW §6)。
- 製品 KPI: 動かしていない (静的解析のみ。起動・GUI の挙動は不変)。

### 8.2 FA-53 (#4389): SEGV `rip=0x125afc6` の呼出元と IAT 未束縛

- 呼出元 (guard の `FA_BT=1` の戻り番地。`[rsp]` = 最初の bad call の戻り): `0x180d09ae2` → `0x180d09ac0` の `call 0x180f8feb0` (GetTickCount の import thunk) ← `0x180d0a040` ← `0x180d8c0b0` (popup slot 5)。
- 原因: thunk `0x180f8feb0` は `jmp [0x1810c4208]` で、この slot は KERNEL32!GetTickCount。`iat_slots.txt` (ctrl build の roots 由来 76 件) に無く、生の hint-name RVA `0x125afc6` のまま。`jmp` 先が `.text` 外のため SEGV。
- 修正: `FA_UI31=1` のときだけ `patch_iat_all()` で全 IAT を shim / `nat_unk0` に束縛 (既定 OFF。他経路は不変)。
- 実測 (測定 commit `5308b492d`・`FA_UI31=1 bash fa31_ctl.sh`): base・node1 とも rc=0。S900–S907 の FAULT は `rip=0x125afc6` → 全件 `rip=0x180cb9ce9 addr=0xa80` (d8d700 内で `[P+0xb98]`→`0x180cbaec0` 経由の null this・`[rcx+0xa80]`) に変化。`d8d700=1` (受入 2 の一部: `d8c140=0` は未達)。`caa820=0`・`d8c140=0`・`UI31 returned` 0 件。
- 判定: `run_ctrl.sh 2 5` = BIT-EXACT 15/15 (rc=0・4.37 s・load 0.07)。既定経路は不変。
- 試行 (棄却): `FA_UI31_P=1` で `P+0xb98`/`P+0xba8` に 0 埋めの 0x200 B を置いた (推測の値)。`0x180d8d7ac` (`[P+0xb88]+0x298`) の `addr=0x298` SEGV に移るだけで `returned` 0 件。推測の P 構築は採らず、コードには残していない。
- 未解決 (受入 1〜3・P の構築根拠): `caa820` 未到達。`P+0xb88`・`+0xb98`・`+0xba8` の実機の構築元は未特定 (推測)。起票先は子 issue (本 PR 末尾)。

### 8.4 FA-72 (#5254): P の構築根拠 (静的読み)

- 対象: `SlateCore.core_64` (`plugins-freshair` の `Fresh Air.Win.zip` 内、36,285,952 B)。`fetch.sh` で展開して読んだ (`work/` は gitignore)。
- 構築関数 `0x180d8a6e0` (0x1c7 B)。`[rdi] = 0x18110a420` を書く。`0x18110a420` は ModulationKnobsPopup の vtable で、slot 5 = `0x180d8c0b0`。vtable を書くのはこの関数だけ (`lift2/fa31_ctor.py`)。
- 構築関数の引数: `rcx` = P (this)、`rdx` = 第 2 引数の指す 2 語 (`[rdx]`・`[rdx+8]`)、`r8b`・`r9b` = フラグ。
- 構築関数が書くフィールド (確定):

| フィールド | 構築関数での書込み | 出所 |
|---|---|---|
| `+0x0` | vtable `0x18110a420` | 定数 |
| `+0xb88` | `[rdx]` (第 2 引数の 1 語目) | 引数由来 |
| `+0xb90` | `[rdx+8]` (参照カウント付きの 2 語目。`lock xadd` を `[rcx+8]` に行う) | 引数由来。shared_ptr 形式と読めるが『推測』 |
| `+0xb98`・`+0xba8` | **0 で初期化** (`rax=0` の `mov`) | 定数。構築関数内では以後書かれない |
| `+0xb48`・`+0xb4c`・`+0xb50`・`+0xb51` | 0・`r12d`・`r14b`・`r15b` | 引数 (`r8b`・`r9b`) 由来 |
| `+0xb52`〜`+0xbc0` | 0 で初期化 | 定数 |

- 構築後の充填 (静的): `+0xb98`・`+0xba8` を書く箇所は、構築関数の呼出元 13 箇所 (`fa31_ctor.py`) の直後 60 命令内には無い。呼出元の所属は `1808377b0`・`18083b510`・`18083f4c0`・`18083fb00`・`180841f60`・`180842cc0`・`1809d5720`・`1809dc4b0`・`1809df610`・`1809e2120`・`1809e3a50`・`1809e4090`・`180d28320`。`.text` 全体で `[reg+0xb98]`・`[reg+0xba8]` へのスタック外の書込みは 115 件あるが、どの P を指すかは同定できない。
- 構築時の子呼出 `0x180cb6b10`・`0x180cbb220` は、先頭命令が `lea` で P 内のアドレス (`+0x8b8`・`+0x928`) を作る。先頭 0x120 B に `+0xb98`・`+0xba8` への書込みは無い (先頭命令の確認のみで、全体は未読)。`0x180d8acb0` は `[rcx]` に vtable を書くデストラクタ (`+0xb98`・`+0xba8` は書かない)。
- 読み手: `0x180d8d700` (slot 5 の下流) は `r14=P` で `[P+0xb98]`・`[P+0xba8]` を読み、それぞれ `0x180cbaec0` の this として渡す。`[P+0xb88]` は `[rcx+0x298]` の基底になる (harness の `addr=0x298` と一致)。

結論 (受入の『P の構築根拠』に対する現時点の答え):
- **確定 (静的)**: P の構築元は `0x180d8a6e0`。`+0xb98`・`+0xba8` は構築時に 0 にされ、この関数の中では埋まらない。`+0xb88`・`+0xb90` は呼出元の第 2 引数から入る。
- **推測**: 実機でも `+0xb98`・`+0xba8` は 0 のまま、`d8d700` は null this 経路に入らない (呼出元の別の P を読んでいる) か、呼出後に間接書込み (memcpy・呼出先の参照) で埋まる。harness の 0 埋めがそのまま実機と同じかは、本付録では判定しない。
- **未特定**: 13 呼出元のうち UI (popup) を作るものの同定 (各呼出元の役割は未読)、間接書込みの有無、`0x180cbaec0` の this の由来。受入 4 の『どの実機 ctor / 呼出元に対応するか』は、構築関数 `0x180d8a6e0` までは対応付けたが、呼出元の 1 つを UI と結び付けるところまでは達していない。

測定:
- 測定 commit: 本 PR の `fa31_ctor.py` を追加した commit (コードの対象は `lift2/` 内の新規 1 ファイル)。
- `python3 tools/targets/freshair/lift2/fa31_ctor.py "<SlateCore.core_64>"`: rc=0、出力 20 行 (VT 書込み関数 2・ctor 呼出元 13・`+0xb98`/`+0xba8` のスタック外書込み 115 件の集計)。所要・load は未測定 (静的解析のみで判定には使わない)。
- 製品 KPI: **動かしていない** (静的解析のみ。起動・GUI の挙動は不変)。

### 8.5 FA-74 (#5255): 実機 ctor で P を構築する試行 (FA_UI31_CTOR・既定 OFF)

- 追加: `FA_UI31_CTOR=1` のとき、`FA_UI31` の slot 5 呼出前に P を実機 ctor `0x180d8a6e0` で構築し、構築前後の `[P+0xb98]`・`[P+0xba8]`・vtable を `UI31CTOR` 行に記録する。既定 (未設定) は従来どおり 0 埋めで、判定基準・既定経路は不変。
- 測定 commit: `451c9fb76` (`ca3d50` 経由の A を入れた commit。以下の FA_UI31_CTOR の数値はこの commit で取った記録)。`git diff 451c9fb76 HEAD -- tools/targets/freshair/lift2` = 0 行 (`72a31de09` まで。本 fix の commit は lift2 の外のみ変更)。WORKFLOW §6 により、この差分 0 行で `451c9fb76` の記録を現 head の記録として扱う。現 head `819b921df` でも同じ件数を再現済み (『再測定の状況』参照)。
- 基準の差分: `git diff 97a5bd8ab 451c9fb76 -- tools/targets/freshair/lift2/native/` は `FA_UI31_CTOR` 分岐の内側の +22 行・-0 行 (`if (getenv("FA_UI31_CTOR"))` の中)。既定経路 (`FA_UI31_CTOR` 未設定) は同じ分岐に入らない。`97a5bd8ab` は既定経路の基準値の commit で、FA_UI31_CTOR の測定 commit ではない。
- 実測 (測定 commit `451c9fb76`・`FA_CTL31=1 FA_HEAP_ZERO=1 FA_UI31=1 FA_UI31_CTOR=1 ./native_fa31 SlateCore.core_64 fa31_epf.txt 0`・S900〜S907): rc=0。以下の数値は現 head `819b921df` でも再現した (『再測定の状況』参照)。
  - ctor の構築は **全 8 シナリオで FAULT**: `rip=0x18040ddbb addr=0x394e0`。ctor が呼ぶ shared_ptr 解放経路 (`0x18040dd9a`〜`0x18040ddbb`) の `[rdi+0xc]` 参照で落ちる。引数 `A = {P 所有, 制御ブロック}` の与え方が実機と合っていない (推測)。
  - ctor 前の `+0xb98`・`+0xba8` は 0、FAULT 後も 0 のまま。vtable は `0x18110a420` (ctor の先頭まで実行されたことは確認)。
  - その後の slot 5 は従来どおり `rip=0x180cb9ce9 addr=0xa80` で FAULT (`returned` 0 件)。
- 結論 (本 run): **受入 1〜3 は未達**。ctor の引数 (第 2 引数の 2 語・制御ブロック) を実機の呼出元どおりに与えない限り、P は構築できず、`+0xb98`・`+0xba8` への書込みも捕まえられない。書込みフックは ctor が通った後の段階でしか意味を持たないため、本 run では設置しない。
- 製品 KPI (FLEngine 起動 dispatch・units_run・最初のウィンドウ): 動かしていない。harness の観測のみ。
- 測定 (旧 run): `fa31_ctl.sh` (既定) は rc=0・31 s・`caa820=0 ca7db0=72 d8c140=0 d8d700=0`。FA_UI31_CTOR 試行は real 0.021 s (FAULT で即終了・n=1)。
- 再測定の状況 (現 head `819b921df`・素材 `fl-win64 plugins-freshair toolchain-emsdk toolchain-retdec` を展開・`[EMSDK]`・`[RETDEC]` を使用。detached worktree で実行):
  - `build_ctrl.sh`: rc=0 (`ctrl build ok`・27 s)
  - `run_ctrl.sh 2 5`: rc=0・**BIT-EXACT 15/15** (fma0/fma1 とも lines 15/15・mismatch 0・ERR native/wasm 1/1 (同一 scenario: yes)・3 s)
  - `fa31_ctl.sh` (既定 base): rc=0・`caa820=0 ca7db0=72 e13590=0 d8c4f0=0 d8ae60=0 e15030=0 e12f20=0 d8d700=0 d8c140=0` (旧 run の値と一致)。node1: `ca7db0=8` 他は base と同じ
  - `FA_UI31_CTOR=1` (S900〜S907): `UI31CTOR post` は 8/8 `FAULT rip=18040ddbb addr=394e0 vt=18110a420 +b98=0 +ba8=0`・`returned` 0 件。その後の slot 5 は `rip=180cb9ce9 addr=a80` で FAULT (従来どおり)
  - `git diff 451c9fb76 819b921df -- tools/targets/freshair/lift2` = 0 行。よって下の旧 run の数値 (測定 commit `451c9fb76`) は現 head の結果と同じ。
- 差し戻し round 4 の fix run (旧): `plugins-freshair` の展開と `fetch.sh` (factory `.epf` 8 本) は通ったが、`build_ctrl.sh` が `[EMSDK]`・`[RETDEC]` (`docs/REFERENCES.md` §2) を前提にしており、`toolchain-emsdk`・`toolchain-retdec` が無かったため `run_ctrl.sh 2 5` は実行できなかった。上の現 head の再測定で解消した。
- 静的 (本 run・PM 第 30 波の再投入): ctor 呼出元 13 箇所は全て `rcx=this`・`rdx=A`・`r8=0`・`r9=0` で呼ぶ。`A` は `ca3d50(weak, out)` の戻り値 (`ca3d50` は weak の `+0x60`=ptr・`+0x68`=制御ブロックから shared 相当を作る) で、ctor 先頭は `A` を `+0xb88`/`+0xb90` に移す。
- 試行 (旧 run・commit `451c9fb76`): `A` を `ca3d50` 経由に変えた (`Q={+0x60=P 所有, +0x68=cb}` → `ca3d50(Q, A)` → `ctor(P, A, 0, 0)`)。`ca3d50` は FAULT しない。ctor は 8/8 で従来どおり `rip=0x18040ddbb addr=0x394e0` で FAULT。
- 読み (静的): FAULT 箇所は `0x18040dd9a` 以降の shared_ptr 解放 (`lock xadd [rdi+0xc]`) の後で、`addr=0x394e0` は `[r15+0x20]` (vector の end ポインタ相当) の読み。`r15` が不正 (ctor 呼出し元の外側の状態に依る) と推測。`A` の組み方を直しても消えないため、`A` の内容ではなく ctor の外側の状態 (呼出元の this の由来) が原因と推測 (未判定)。
