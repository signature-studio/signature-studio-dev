# lift2 REPORT FA-7 — macro 子 param ID (0x157/0x158/0x15a) の Filter 内部パラメタ同定 (#452, Refs #51)

(`REPORT.md` が 250 行上限のため独立ファイル。§12.4 の未解決 1 件目への部分回答。)
既知類型との関係: 該当なし (lift 欠陥の新規類型は無し。RE による仕様同定。測定系の欠陥は §2.5 に記載)。

## 1. 結論 (先出し)

**部分達成。ID 0x157/0x158/0x15a は Filter model 上で「汎用バンク slot (ID 311..410, 値域 [0,100], 既定 1.0)」の descriptor であり、
Filter process の DSP が読む param (ID 1/2/3/4/416) ではない。model 層の setter `0x1803debc0(M,id,v)` で 0x156..0x15b の 18 件 (6 ID × 3 値) を書いても Filter 出力は不変 (18/18)。
この不変判定は、同じ測定系で setter が出力を変える陽性対照 (ID 2/3 の setter 6/6) により検出力を確認済み。**

- 実測した範囲: **Filter model 層** の setter 後の挙動 (native 実機機械語)。
- **実測していない範囲**: 実マクロ経路 `0x180c9d700(child,id,v,key)` → `0x180ca1480` (controller map `C+0x318` 木 → shared_ptr<param>) →
  vtable 経由 setter → `0x180da6c00` (param manager 側) の連鎖。この経路は controller map が空のため harness で実行できておらず、
  ID が controller map 経由で **別の内部 param (ID 1〜4 等) に解決される可能性は排除できていない**。
  したがって「macro は Filter 係数を変えない」とは結論しない。「model 層の直接 setter 経路では変えない」までが実測。
- **測定系の訂正 (旧版 e47f751 からの変更点)**: 旧版は M を `memcpy` で複製してから setter を掛けていた。モデルは自己参照ポインタを持つため、
  複製に setter を掛けると元モデル側が書き換わり (§2.5 alias_check: 14 B)、setter の効果を検出できなかった (ID 1〜4 を含め全て outChanged=0)。
  本版は測定ごとに ctor を新規実行したモデルで測り直した。旧版の 18/18 は検出力の無い測定に依存していたため根拠にしない。
  本版でも同じ 18/18 不変が得られ、かつ陽性対照で検出力を確認した。

**Closes ではなく Refs**: 受入条件のうち「実 controller map を構築して ID → Filter 内部パラメタを同定し、setter 後の Filter 係数変化を native/wasm bit-exact で確認」は
未達 (controller map 未構築・wasm 側未比較)。残りは §4 の通り起票。

## 2. 方法と実測 (再現: `bash tools/targets/freshair/lift2/run_fa7.sh`)

1. **descriptor 表** (`native/probe_ids.c`): Filter model 実 ctor `0x180b4c040(M,dummy)` を実機機械語で実行。M+8 の descriptor ポインタ vector = **417 件**
   (descriptor 実体は `M+0x19b8+0x148*k` 刻み)。ctor 逆アセンブルで、ID ごとに `vector[id]=&desc` / `desc.id=id` / `desc.cell(+0x28)=M+0x9db8` / `setter 0x1803debc0(M,id,desc.def)` の並びを確認。
2. **値域** (`FA_OBJ=1`): descriptor +0x38 の range object (vtable 0x1810ca8a0) 先頭 8 B = {min,max} f32。
   ID 311..410 (100 件) は全て {0.0, 100.0}・既定 f32 0x3f800000 (=1.0)。0x157=343 / 0x158=344 / 0x15a=346 はここに属する。
   ID 155.. 側に {-1,1} の別バンク 100 件。ID 1/2/3 は個別 vtable (0x1810fa958 / 0x1810cead8)。
3. **setter 実測** (`native/probe_setid.c`): 測定単位は「ctor を毎回新規実行した独立モデル T」。setter 前の T のスナップショットとの差分で変化バイトを取り、
   同じ T で Filter process (0x180b6f050) を 3 回 (64 sample) 実行して L/R の FNV-1a を、ctor 既定の基準出力と比較する。
   基準出力は同一入力 2 回で一致 (`base_out_hash=86e4b27f6a91a7bf`, `deterministic=1`)。
   - **0x156..0x15b (18 件)**: 変化バイトは全て自 descriptor `[desc_off, desc_off+0x48)` 内 (例 0x157: desc_off=0x4390、変化は 0x4394..0x43a2、1〜6 B/件)。
     DSP が読む `+0x9dc4/0x9e0c/0x9e54/0x9e9c/0x9ee4` には書かない。出力は **18/18 不変**。
   - **陽性対照 (setter 経路, `PC` 行)**: ID 2 (周波数 `+0x9e0c`) を 200/1000/8000、ID 3 (Q `+0x9e54`) を 0.25/0.5/0.9 で setter すると **6/6 で出力が変わる** (outChanged=1、変化 8〜14 B、
     変化位置は +0x9e0c..0x9e1b / +0x9e54..0x9e62)。ID 2 は 0.5/0.25/0.9 を与えると 20 Hz に下限クランプされるため、PC 行は Hz 単位の値を使う。
   - **陽性対照 (POKE 直書き, `P` 行)**: M+0x9e0c=1000 / M+0x9e54=2 の直書きで outChanged=1 ×2 (従来どおり)。
   - **未解明 (setter 経路)**: ID 1 は float の bit 列をそのまま `+0x9dc4` (type enum) に書くため、不正な enum 値での測定になり判定に使えない。
     ID 4 は `+0x9e9c` に値を格納するが、既定 type=0 では出力不変 (型別の測定は未実施)。
   - ID 1〜4 の意味 (型/周波数/Q/ゲイン) は setter 格納先と既定値からの**推定** (型=`+0x9dc4` 既定 0 / 周波数=`+0x9e0c` 既定 440 Hz / Q=`+0x9e54` 既定 0.707 / ID 4=`+0x9e9c` 既定 0)。
     ID 2・3 は setter で出力に効くことを実測した。
4. **静的** (`fa7_static_reads.py`): Filter closure (mlift 114 関数) の `[reg+disp]` のうち M param 領域 (0x19b8..0xa400) = 8 件 (distinct 7):
   0x9dc4/0x9e0c/0x9e54/0x9e9c/0x9ee4 + 0x9f98/0x9fa0 (ring buffer ptr, ID 外)。0x156..0x15b の descriptor 範囲は 0 件。
5. **測定系の欠陥 (旧版の訂正)**: 旧版は基準モデル M0 を `memcpy` で複製し、その複製 T に setter を掛けていた。モデル内部の自己参照ポインタ (descriptor vector 等) は
   複製後も元の M0 を指すため、setter の書込みが元モデル側に流れる。実測: 複製 C に setter (ID 0x2, 1000) を掛けると元モデル B の **14 B** が変化
   (`# alias_check` 行)。その結果、旧版では ID 1〜4 を含む全 setter が出力不変 (outChanged=0) となり、陽性対照は POKE しか効かない測定になっていた。
   本版は ctor を毎回新規に実行して測り直し、setter 陽性対照 (PC) を判定に加えた。
   ※ 2 つの独立 ctor の間で内部ポインタ値は異なる (ヒープ絶対アドレス) ため、差分は「同一モデルの setter 前後」で取る (モデル同士の比較はしない)。

## 3. 検証結果 (起点 HEAD 8f55002 + 本 PR の差分, 実測)

| 項目 | 結果 |
|---|---|
| `run_fa7.sh` | **ALL PASS** (判定 6 + ネガコン 4)。初回 (mlift/emcc ビルド込み) 43.3 s (load average 0.76)、ビルド済みの再実行 3.008 s (load average 0.05、並列 1) |
| `run_chainmap.sh` (既存・無変更) | **OK 8/8** (EPF 8 本、2.634 s)。EPF を展開していない環境では `0/0 epf` の空振りになり `native_ctrl_trace` が終了時に Abort する (`free(): invalid size`)。素材の有無による差で、本 PR の変更は chainmap の入力 (`native_ctrl.c`・`build_ctrl.sh`・`fa4_chain_map.py`) に触れていない |
| ネガティブコントロール | NC1 期待集合に 343 (0x157) を混ぜる → FAIL / NC2 setter 0x156..0x15b の outChanged を 1 に改竄 → FAIL (18 件中 0 件一致) / NC3 観測行を除去 → 空 PASS せず FAIL / NC4 (新規) setter 陽性対照 PC 行の outChanged を 0 に改竄 → FAIL。4/4 が期待どおり FAIL |

fail-closed: 判定は観測件数に下限を置き (空 PASS 拒否)、不合格は `exit 1`。`lift2_e2e.sh` は本 PR で未変更・未再実行。

## 4. 範囲外 / 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 controller map (`C+0x318`, 木ノード = key u16 id → shared_ptr<param>) を構築して `0x180c9d700` を実行し、ID → 実 param の解決先を実測 | 本 issue の主目的 (未達) | #452 に残す (本 PR は Refs)。続編は #648 (FA-8) |
| macro → 0x157.. が preset DUMP の接続表経由で Filter ID 1〜4 に届くか | 最終説明 | #648 (FA-8) |
| 型 enum は ctor 既定 (type=0) のみで測定。ID 4 (`+0x9e9c`) の setter は既定型で出力不変、型別の効き方は未確認。ID 1 は不正 enum 値での測定 | ID 1/4 の意味・一般化の範囲 | #648 (FA-8) に型 1..5 の setter 陽性対照を追加 (PM 判断) |
| wasm (mlift) 側に setter `0x1803debc0` が無く、setter 後の native/wasm bit-exact は未実施 | 受入条件の bit-exact 部 | #648 (FA-8) (--root 追加) |
| Compressor/Gain model の同 ID 意味は未調査 | 範囲外 | #648 (FA-8) |
