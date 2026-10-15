# REPORT — WIN-35 (#3618): native の窓 import (RegisterClassW・CreateWindowExW) を tools/gui の headless host へ向ける

親: #2760 (WIN-7 系)。前提: [`REPORT_WIN33_3556.md`](REPORT_WIN33_3556.md) (#3556・PR #3638 で close 済み)、[`REPORT_APPENDIX_3557.md`](REPORT_APPENDIX_3557.md) (窓 import の trace)。
再現: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/liftdiff/win35_gui.sh` (約 30 秒。出力は `work/flelift/win35/`・gitignore 対象)。

測定 commit: `4448a6ae0` (コードを変えた最後の commit。`349e1aa3d` の後に `GetClassInfoW` を振り分けに足した)。
既知類型との関係 (DEFECTS.md): 該当なし (harness の窓応答の接続。lift 欠陥ではない)。
素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff (`$HOME/artifacts` に実在を `ls` で確認してから展開)。
実行環境: GitHub Actions runner (4 コア)。load average は e2e の前後で 0.94 → 3.49 (e2e 内の並列 batch による)。

## 0. 結論 (実測)

1. **接続は動く。** `LD_GUI_HL=1` の native (`-DLD_GUI_HL` ビルド) では、窓の import を `tools/gui` の shim (`gui_core.c`) と headless host (`gui_headless.c`) が処理する。CFI の経路で `CreateWindowExW` は戻り `0x1100010` (窓)、既定は `0` (従来の stub)。
2. **surface の統計は出る。ただし画素は書かれていない。** 生成された隠し surface は 3 件 (boot の `ep`・`u880` と CFI)。各 1×1 (実寸 0×0 を shim が 1×1 に丸める)・`visible=0`・非背景画素 0・色数 1。**可視の窓は作られない。** 受入条件 1 の「surface に画素が書かれた」は未達。
3. **既定は不変。** 既定ビルドの spike は改修前 (`68eb512cd`) と同じ 928/942・first_fail 830・止まり `segv 0x4e0fab`・import 35。`liftdiff_e2e.sh --m11-only` は HEAD で 360/234/206・PASS (2 回。`349e1aa3d` と `4448a6ae0`)。
4. **止まりは動かない。** GUI 経路でも CFI は同じ `0x4e0fab` の null 読みで止まる。可視窓の作成段に届かないため、画素は取れない (前提の #3636 WIN-36 が open)。

## 1. 方法 (何を、どこへ向けたか)

- `rt/ld_native.c` (`#ifdef LD_GUI_HL` のみ): `ld_stub_c` で `GetClassInfoW`・`RegisterClassW`・`CreateWindowExW`・`DefWindowProcW`・`SetWindowLongPtrW` を、既定の stub の代わりに `tools/gui` の同名 API (`gui_core.c`) へ渡す。`CreateWindowExW` の第 5〜12 引数は wt_rec と同じく `entry+0x28` から読む。呼出し記録 (`calls_full`) の戻り値は gui の結果で直す。
- 窓プロシージャ (guest の VA) の呼出しは `gui_set_icall_hook` で `ld_ms_call` (MS x64 ABI) 経由にする。`rt/ld_gui.c` が hook・`ld_gui_init` (`gui_hl_start(1920,1080,0)`)・`ld_gui_dump` (case 終了ごとに全 live surface の統計を 1 行ずつ出す) を持つ。
- 到達ログ表 `gui_reach_tab` は生成物 (gen_api.py) なので、件数 0 の空表を `rt/ld_gui.c` に置いた (到達ログは使わない)。
- ビルドは `spike_cfi.py` が `LD_GUI_HL=1` のときだけ gui の 7 ファイルを足す。既定の gcc 行は変えていない。実行時の有効化は `LD_GUI_HL=1` (出力先 `LD_GUI_OUT`・既定 stderr)。

## 2. 実測 (測定 commit `4448a6ae0`・`win35_gui.sh` 1 回)

| 項目 | 既定 (`LD_GUI_HL` なし) | GUI (`LD_GUI_HL=1`) |
|---|---|---|
| hybrid boot units_run / first_fail | 928/942・830 | 928/942・830 (不変) |
| CFI の止まり | segv `rip_rva=0x4e0fab` | segv `rip_rva=0x4e0fab` (不変) |
| CFI の import 数 | 35 | 39 (`RegisterClassW` 1 件減・`DefWindowProcW` 5 件増) |
| `GetClassInfoW` の戻り | 0 | `0xc001` (boot で登録済みのクラスを返す) |
| `RegisterClassW` (CFI) | 0 (stub) | 呼ばれない (GetClassInfoW が見つけるため) |
| `CreateWindowExW` (CFI) の戻り | 0 | `0x1100010` (窓) |
| `DefWindowProcW` (窓プロシージャ内) | 呼ばれない | 5 件 (戻り `1` = WM_NCCREATE → TRUE、他は 0) |
| `SetWindowLongPtrW` の戻り | 0 | `0x424920` (旧 wndproc = TPUtilWindow の rva `0x24920`。整合) |
| 窓 surface (case 終了時) | なし | 3 件 (下の 2.1) |

### 2.1 surface の統計 (GUI run・`case=cfi` の行。全行は `gui.txt` の 749 行)

```
gui case=cfi surf=0 x=0 y=0 w=1 h=1 visible=0 title="" nonbg=0 colors=1 bg=0x000000 sha256=709e80c8…8147c
gui case=cfi surf=1 x=0 y=0 w=1 h=1 visible=0 title="" nonbg=0 colors=1 bg=0x000000 sha256=709e80c8…8147c
gui case=cfi surf=2 x=0 y=0 w=1 h=1 visible=0 title="" nonbg=0 colors=1 bg=0x000000 sha256=709e80c8…8147c
```

- 生成元: surf 0 は case `ep` (boot)、surf 1 は case `u880` (boot)、surf 2 は case `cfi`。surface は同一プロセス内で case をまたいで残る (統計は case ごとに生存中の全 surface を出す)。
- 実寸 0×0 は `gui_core.c` の `surf_alloc` が `w<1→1`・`h<1→1` で丸める。`visible=0` は窓が `WS_POPUP` のみ (`WS_VISIBLE` 無し)。
- 統計の定義 (`gui_hl_stats.c`): RGB 3 バイト列の行優先 sha256・背景 `0x000000`・非背景 = 背景と RGB が違う画素・色数 = 2^24 色の厳密な一意数。
- sha256 `709e80c8…` は、1 画素 `00 00 00` の sha256 を `printf '\x00\x00\x00' | sha256sum` で独立に計算した値と一致する (3 バイト全 0)。
- **陽性対照** (`win35_gui.sh` の `control`): 2×1 で 1 画素だけ `0xFF112233` を描いた合成 surface は `nonbg=1 colors=2` を返し、その sha256 `2a4f7764…f2bae` は `printf '\x00\x00\x00\x11\x22\x33' | sha256sum` と一致する。統計は描かれた画素を数えられる。
- **陰性対照 (経路)**: 既定ビルドは gui の出力を作らず、`CreateWindowExW` の戻りは 0 のまま (2 節の既定列)。GUI 経路と既定の差は env と build で切り替わる。

## 3. 受入条件の判定

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| 1. RegisterClassW・CreateWindowExW を headless host へ向け、surface の画素統計 (w×h・非背景・色数・sha256) を出す | **部分達成** | 向け先と統計出力は達成 (2・2.1)。「画素が書かれた」は未達 (可視窓が無い) |
| 1 の既定の応答 (影響) | 書いた | 既定は不変 (env・build で隔離)。GUI 経路では窓の応答と窓プロシージャの呼出しが変わる (2 節) |
| 2. PNG は repo・issue・PR・artifact に置かない | 満たす | PNG を作っていない (非背景画素 0 のため画像にする対象が無い)。受け渡し: PM 判断待ち |
| 3. `liftdiff_e2e.sh --m11-only` の回帰 | 満たす | HEAD `4448a6ae0` で 360/234/206・PASS (4 節) |

## 4. 検証 (コミット済み HEAD)

- `4448a6ae0`: `FL_WIN64_DIR=… bash tools/liftdiff/liftdiff_e2e.sh --m11-only` → `関数数 800: 一致 360 / 不一致 234 / 実行不能 206`・`LIFTDIFF_E2E PASS`。
- `349e1aa3d` (前の測定 commit): 同じ e2e → 360/234/206・PASS (所要 2 分 58 秒)。`4448a6ae0` の所要は記録していない。
- `4448a6ae0`: `win35_gui.sh` → 2 節の表と 2.1 の行・陽性対照。
- コード差分 (測定 commit から HEAD まで): `git diff 4448a6ae0 HEAD -- tools/liftdiff ':(exclude)*.md'` は、本 REPORT の commit 後に実行して結果を PR 本文に載せる (本ファイルは `.md` のみ)。
- 既定の spike の比較元: 改修前の `68eb512cd` (main) で 928/942・830・`0x4e0fab`・35 import (本ファイルの既定列と同値)。

## 5. 製品 KPI (起動・窓に関わる。`docs/WORKFLOW.md` §7)

| KPI | 前 (既定) | 後 (既定・不変) | 後 (GUI 経路 `LD_GUI_HL=1`) |
|---|---|---|---|
| FLEngine 起動の dispatch 数・通過 unit 数 | 928/942・first_fail 830 | 928/942・830 | 928/942・830 |
| 最初のウィンドウ (可視) | 無し | 無し | **無し** (可視窓は .mo 読込み後の段で作られ、CFI はその前の `0x4e0fab` で止まる) |
| 窓 surface の画素 | 無し (隠し窓 0 件) | 無し | 隠し 1×1 surface 3 件・非背景 0 画素・色数 1 (画素は描かれていない) |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 可視窓 (TApplication) の作成と「画素が書かれた」統計 | 受入条件 1 の後半が未達。可視窓は .mo 読込み後の段 | #3636 (WIN-36・open)。読込み位置の同定・修正が先 |
| 既定の止まり `0x4e0fab` (null 読み) | CFI の止まり地点は不変 | #3636 (WIN-36)。親 #2760 |
| 窓の残りの import (`ShowWindow`・`UpdateWindow`・`PeekMessage`・`GetDC` 系) を gui へ向ける | 可視化の経路 (WM_PAINT 配送) が未接続。今は到達しない | 未起票。可視窓が作られた後の実測で必要になった時点で起票 (#3636 の後) |
| stk 位置の不一致 (`ld_stub_common`) | 範囲外。MS 第5 引数の位置 | #3619 (LD-170・open) |

## 7. 検証範囲 / 範囲外

- 範囲: native の窓 import の接続・surface 統計・既定の不変 (spike・e2e)。
- 範囲外: 可視窓の作成と画素統計 (#3636 の後)・wasm 化 (`rt/fle_ldbridge.c` は触らない)・`tools/gui` の本体の変更 (読むだけ)。
- 限界: 窓の wndproc は PE の VA を `ld_ms_call` で呼ぶ bridge 経由。WM_CREATE 以降の guest の処理は未解析。surface は case をまたいで残るため、case ごとの統計は「生存中の全 surface」の値。
