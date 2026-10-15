# PY-320 (#4346): 公開表 0x12acb70 (MoveLeftMenuClick) を呼ぶ箇所と rdx (Sender) の出どころ

親: #3937 (PY-274)。前段: `tools/python/REPORT_PY268.md` §4 (発火側は未同定)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと参照走査による解析)。
KPI: 起動・GUI に関わらないため記載不要 (解析のみ)。

## 結論

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. 0x12acb70 を TMethod(Code, Data) として呼ぶ箇所 (関数と VA) と rdx の出どころ | **部分達成**。呼出し箇所は確定 (§1)。rdx = Self (`rbx`) は確定 (§2)。0x12acb70 がその枝で実際に `[Self+0x100]` に入ることは**未確定** (静的な推定) | §1・§2・§4 |
| 2. 検証 probe を追加し、既存 probe が PASS のまま | probe `pe_py320_fire_site.py` 追加 (10 件 PASS)。`pe_py268_rdx.py` 22/22 PASS (測定 §5) | §5 |

`pe_py274_dispatch.py` と `REPORT_PY274.md` は main に存在しないため、既存 probe としては照合できなかった (issue 本文の前提と不一致)。

## 0. 対象と前提

- 素材: `$HOME/artifacts/fl-win64.tar.zst` を `tar --zstd -xf ... -C /tmp/opencode/fl --wildcards '*block00031_PE.bin'` で展開 (1.6 秒)。`FL_WIN64_DIR=/tmp/opencode/fl`。
- 検証起点: origin/main `267ee2069`。
- VMT: TMenuItem = 0x838c10 (自己ポインタ + classname "TMenuItem" の照合で 1 件)、TQuickMenuItem = 0x725a58 (同)。

## 1. 呼出し箇所 (受入 1 の前半)

- 仮想スロット 0xd0: TMenuItem (0x838c10+0xd0) = `0x840b50`。TQuickMenuItem (0x725a58+0xd0) = `0x72db20` (TMenuItem のスロットを上書きする関数)。
- `0x72db20` は `mov rcx, rbx` (Self) で `call 0x840b50` する (`0x72db3d`)。`0x840b50` への直接 call はこの 1 箇所だけ。
- `0x840b50` 内で `call qword ptr [rbx + 0x100]` (Code) を `rcx = [rbx + 0x108]` (Data)、`rdx = rbx` (Self) で呼ぶ箇所は 2 件: **`0x840be8`** (`cmp [rbx+0x81]` 系の分岐の後) と **`0x840c2e`** (`[rbx+0x8c]` が無い枝)。
- 同形の箇所は関数外に 5 件あるが、関数の範囲 (0x840b50〜0x840c3a) で絞った。`0x840cd0` は `[rbx+0xf0]` (Code) を `rdx = rbx` で呼ぶ別の枝 (`0x840d1b`)。

## 2. rdx の出どころ (受入 1 の後半)

- `0x840b50` 入口の `mov rbx, rcx` (Self) で保持し、`0x840be8`・`0x840c2e` の直前 8 命令内の `rdx` 設定は `mov rdx, rbx` のみ。
- よって rdx (第 2 引数) = **Self** (`0x840b50` の rcx = 呼出し元の rbx)。Self は `0x72db20` で `rbx = rcx` の `TQuickMenuItem` インスタンスとみられる。
- 対照: `0x840be8` と `0x840c2e` の 0x12acb70 への到達は、`[rbx+0x100]` が 0x12acb70 の値を持つことを要する。その値の書込み先は未確認。

## 3. 未確定 → #3937 (起票先)

- `0x72db20` の呼出し元: `call [reg + 0xd0]` は 244 箇所あり、そのうち MoveLeftMenu の OnClick を発火する箇所は未同定。
- `[Self+0x100]` に 0x12acb70 が書き込まれる箇所 (DFM 読込みの TMethod 生成) は未確認。REPORT_PY268 §3 の推定 (`TMethod(Code = 0x12acb70, Data = TFXForm)`) の裏付けは未取得。
- 動的 (実行) による確認は本 run の範囲外。

## 4. 解釈の限界

- 「rdx = Self」は逆アセンブルの静的な読みで、`0x840b50` の Click 系ディスパッチャという同定 (VMT スロット 0xd0 と `call [Self+0x100]`/`[Self+0x108]` の形) に依る。Code/Data の名前付けは推定。
- 呼出し箇所の関数 (`0x840b50`) は、VMT スロットの同定に基づく。関数の先頭は `int3` パディングの推定 (`pe_callgraph.py` と同じ方式)。

## 5. 検証

- probe: `tools/python/analysis/flapi/pe_py320_fire_site.py` (検査 11 件)。
- 測定 commit (コードを変えた最後の commit): `1dc704e13`。測定は HEAD `ec11dfec5` (差分は REPORT・DOC_MAP のみ) で行った。
- 実行: `FL_WIN64_DIR=/tmp/opencode/fl python3 tools/python/analysis/flapi/pe_py320_fire_site.py`。
  - 実測 (08:36:56 UTC・HEAD `ec11dfec5`): real 23.504 秒・終了 0・PASS 11 / FAIL 0。load average 開始 0.05・終了 0.38。
- 既存 probe: `pe_py268_rdx.py` を同じ素材・同じ HEAD で実行: real 24.283 秒・終了 0・検査 PASS 22 件 (集計行「件数 22 / 22」)。load average 開始 0.29・終了 0.54 (08:37:34 UTC)。
- 負の対照: `0x840cd0` の `[+0xf0]` 枝は `+0x100` 検出 0 件・`+0xf0` 検出 1 件 (`0x840d1b`) で、検出器が枝を区別する。
