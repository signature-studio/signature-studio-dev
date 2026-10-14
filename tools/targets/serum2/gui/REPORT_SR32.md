# REPORT — [SR-32 #2054] Splice 生成の上流 (0x1800c9680 の呼出元と vtable 0x180a2bfe0 の所属) の特定 (静的)

- 日付: 2026-10-14 / 親: #2000 (SR-30) / 前段: `REPORT_SR30.md` §2-2・§5(A)
- 範囲: 静的解析のみ。入力・手順は `REPORT_SR30.md` §1 と同じ (`Serum2_win64.vst3`, sha256 `501e7bb3…`, 19,236,864 B を本 run で再確認)。作業用 dir はリポジトリ外。
- 測定 commit: `9e8e89ff` (解析スクリプト 4 本を追加した commit。以降このディレクトリのコードは未変更)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `0x1800c9680` の呼出元 (直接 call と vtable 経由) | **部分達成**。直接 call は 0 件。仮想呼出 `call [reg+0xc8]` は 33 件 (25 関数)。レシーバ型で絞る作業は未達 (§2-3) |
| 2. vtable `0x180a2bfe0` のクラス (RTTI) | **達成**。`0x180a2bfe0` は vtable 先頭ではなく、`.?AVSerumController@@` の副 vtable `0x180a2bf18` の slot 25 (§1) |
| 3. Splice テンプレート選択の state 条件 | **未達**。`0x1800c9680` の内部条件は Splice ctor 呼出しを制御しない (§2-4)。選択は呼出元側の条件、または `0x180498090` 内にある。受信型の解決は #2102 (SR-38) が担う |
| 4. REPORT 追記 | 本書 |

### 0-1. 前段 (REPORT_SR30) の訂正

- REPORT_SR30 §2-2 の「`0x180a2bfe0` は `0x1800c9680` の vtable 位置 (`.rdata` slot 0)」は**誤り**。`0x180a2bfe0` は vtable の先頭ではない。`0x180a2bf18 + 0xc8` の slot 25 である (§1)。
- `vtable_dump.py <pe> 0x180a2bfe0` の `RTTI=?` は、先頭でない位置を head として読んだための結果であり、RTTI の欠落ではない。`0x180a2bf18` を head にすると `.?AVSerumController@@` が出る。

## 1. vtable の所属 (受入 2)

| 対象 | 読み方 | 結果 |
|---|---|---|
| `0x180a2bf18` (ctor `0x1800a9f40` が `[rsi+0x18]` に格納) | COL を `[head-8]` の VA から読む | COL `0x180a2c7e0` sig=1, offset `0x18`, RTTI `.?AVSerumController@@` |
| `0x180a2bfe0` | `0x180a2bf18 + 0xc8` | slot 25。値 `0x1800c9680`。同じアドレスは `0x180a2bf58 + 0x88` (slot 17) としても読め、head `0x180a2bf58` の RTTI も `.?AVSerumController@@` (#2102 の記述と一致) |
| `0x180a2bff8` / `0x180a2c038` / `0x180a2c0b8` | 同様 | 順に offset `0x38` / `0x68` / `0xb8` の SerumController 副 vtable (ctor が格納) |

- COL の offset `0x18` は、この vtable が SerumController の `+0x18` の副オブジェクトに属することを示す。
- `0x1800a9f40` (ctor) の内容: `[rsi+0x18]=0x180a2bf18`, `[rsi+0x30]`・`[rsi+0x38]`・`[rsi+0x68]`・`[rsi+0xb8]`・`[rsi+0xc8]` に他の副 vtable を格納。RTTI は全て SerumController。
- 注: 前段で「vtable head `0x180a86b88` は SerumEditor」とした件 (REPORT_SR30 §0-1) は、本 run では再確認していない。

## 2. 呼出元 (受入 1)

### 2-1. 直接 call

`call 0x1800c9680` (rel32) は `.text` 全体で **0 件**。直接呼出の上流を辿ることはできない。

### 2-2. vtable 経由

`0x1800c9680` は SerumController 副 vtable `0x180a2bf18` の slot 25 (`+0xc8`) からのみ参照され、呼出は `call qword ptr [reg+0xc8]` になる。`.text` 全体で `[reg+0xc8]` の call は 33 件 (25 関数)。

| 所属関数 (代表) | 件数 | 備考 |
|---|---|---|
| `0x18012929d`・`0x1801292dc` (所属 `0x1801283b0`) | 2 | 同一関数内 |
| `0x1804ba36a`・`0x1804ba3b6` (所属 `0x1804ba310`) | 2 | 同一関数内 |
| `0x18054483f`・`0x18054488a` (所属 `0x1805446b0`) ほか | 計 33 件 | 全件は実行結果を参照 |

- 実行結果の全 33 件: `virt_callers.py` 出力 (本 run の実測)。ここでは件数と代表のみを書く。
- この 33 件は `[reg+0xc8]` の**全ての** call で、SerumController 以外の型の slot 25 も含む。レシーバ型を絞っていないため、受入 1 の「全て列挙」はここで未達。

### 2-3. 受入 1 の未達理由

- 33 件それぞれのレシーバ (rax/rdx の由来) をたどって SerumController の副オブジェクトか判定する必要がある。本 run では時間内に終えられなかった。

### 2-4. `0x1800c9680` 内の条件 (受入 3 の手がかり)

`0x1800c9680` (size 834) の流れ:

1. `[rcx+0x20408]` → `[rax+0x30]` の bit0 が 0 なら `0x1800c9941` へ飛ぶ (`0x1800c96b3`)。
2. `[rsi+0x22798]` が非 null かつ `[rsi+0x227a0]==1` かつ `[rax+0xb8]==1` なら `0x1800c9941` へ飛ぶ (`0x1800c96cc`・`0x1800c96d9`)。
3. それ以外のときだけ、`0x120` byte の副オブジェクト生成と `[rsi+0x22798]` への格納 (`0x1800c96df`〜`0x1800c9933`)。
4. `0x1800c9941` (全経路の合流点): `mov ecx,0x3a0` で確保し、`call 0x180498090` (`r8d=1`)。これが Splice ctor の**唯一の呼出**。

**結論**: Splice ctor の呼出 (`0x1800c995b`) は、手順 1〜3 の条件に依らず全経路で実行される。よって `0x1800c9680` 内の条件は「Splice を作るか」ではなく「副オブジェクト `+0x22798` を作り直すか」を決める。Splice テンプレート選択の state 条件は、`0x1800c9680` の**呼出元 (2-2 の 33 件)** か、`0x180498090` の内部にある。

## 3. demo bit との関係

本 run では扱わない (#2055 SR-33 の範囲)。`REPORT_SR30` §3 の判定のままとする。

## 4. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (A) 2-2 の 33 件 `call [reg+0xc8]` のレシーバ型を判定し、SerumController 副オブジェクト (vptr `0x180a2bf18`) からの呼出のみ残す | 受入 1 | #2102 (SR-38) |
| (B) Splice テンプレート (`SpliceRTO` / `SpliceExpired` / `SpliceMaxLimit`) の選択分岐 (`0x180498090` 内、または (A) の呼出元の条件) | 受入 3 | #2102 (SR-38) |
| (C) demo bit 読書 (`0x1800c2b50` / `0x1800c6090`) と Splice 生成の結線 | 受入 2・3 (demo bit) | #2055 (SR-33) |
| (D) 間接呼出 `0x180a24048` slot 12 / `0x180a24158` slot 5 | 受入 3 (間接) | #2053 (SR-34) |
| (E) 実 VSTGUI 上の動的確認 | 受入 4 | `#68` 残作業 |

## 5. 再現手順・実測 (本 run, runner 上)

```sh
# $S: リポジトリ外の作業用 dir。$P: tools/targets/serum2/gui
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/vtable_dump.py Serum2_win64.vst3 0x180a2bf18 1
venv/bin/python $P/upstream_refs.py Serum2_win64.vst3 0x1800c9680 0x180a2bfe0
venv/bin/python $P/vt_window.py Serum2_win64.vst3 0x180a2bf00 0x180a2c100
venv/bin/python $P/virt_callers.py Serum2_win64.vst3 0x1800a9f40 0xc8
venv/bin/python $P/disasm_range.py Serum2_win64.vst3 0x1800c9680 0x1800c9780
```

- 解析スクリプトは `tools/targets/serum2/gui/` に追加 (`upstream_refs.py`・`vt_window.py`・`virt_callers.py`・`disasm_range.py`)。`vtable_dump.py` は既存のまま使用。
- 実測 (n=1, 逐次, load は実行直前の `uptime` 1 分平均 0.16〜0.30): `vtable_dump.py` 2.5 s / `upstream_refs.py` 6.3 s / `vt_window.py` 5.5 s / `virt_callers.py` 5.3 s / `disasm_range.py` (1 関数) 未計時。
- インストーラ展開 (`7z x`) 4.4 s。展開後の vst3 sha256 とサイズは REPORT_SR30 と一致。
