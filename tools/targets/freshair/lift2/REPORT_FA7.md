# lift2 REPORT FA-7 — macro 子 param ID (0x157/0x158/0x15a) の Filter 内部パラメタ同定 (#452, Refs #51)

(`REPORT.md` が 250 行上限のため独立ファイル。§12.4 の未解決 1 件目への部分回答。)
既知類型との関係: 該当なし (lift 欠陥の新規類型は無し。RE による仕様同定)。

## 1. 結論 (先出し)

**部分達成。ID 0x157/0x158/0x15a は Filter model 上で「汎用バンク slot (ID 311..410, 値域 [0,100], 既定 1.0)」の descriptor であり、
Filter process の DSP が読む param (ID 1/2/3/4/416) ではない。model 層の setter `0x1803debc0(M,id,v)` で書いても Filter 出力は不変 (18/18)。**

- 実測した範囲: **Filter model 層** の setter 後の挙動 (native 実機機械語)。
- **実測していない範囲**: 実マクロ経路 `0x180c9d700(child,id,v,key)` → `0x180ca1480` (controller map `C+0x318` 木 → shared_ptr<param>) →
  vtable 経由 setter → `0x180da6c00` (param manager 側) の連鎖。この経路は controller map が空のため harness で実行できておらず、
  ID が controller map 経由で **別の内部 param (ID 1〜4 等) に解決される可能性は排除できていない**。
  したがって「macro は Filter 係数を変えない」とは結論しない。「model 層の直接 setter 経路では変えない」までが実測。

**Closes ではなく Refs**: 受入条件のうち「実 controller map を構築して ID → Filter 内部パラメタを同定し、setter 後の Filter 係数変化を native/wasm bit-exact で確認」は
未達 (controller map 未構築・wasm 側未比較)。残りは §4 の通り起票。

## 2. 方法と実測 (再現: `bash tools/targets/freshair/lift2/run_fa7.sh`)

1. **descriptor 表** (`native/probe_ids.c`): Filter model 実 ctor `0x180b4c040(M,dummy)` を実機機械語で実行。M+8 の descriptor ポインタ vector = **417 件**
   (descriptor 実体は `M+0x19b8+0x148*k` 刻み)。ctor 逆アセンブルで、ID ごとに `vector[id]=&desc` / `desc.id=id` / `desc.cell(+0x28)=M+0x9db8` / `setter 0x1803debc0(M,id,desc.def)` の並びを確認。
2. **値域** (`FA_OBJ=1`): descriptor +0x38 の range object (vtable 0x1810ca8a0) 先頭 8 B = {min,max} f32。
   ID 311..410 (100 件) は全て {0.0, 100.0}・既定 f32 0x3f800000 (=1.0)。0x157=343 / 0x158=344 / 0x15a=346 はここに属する。
   ID 155.. 側に {-1,1} の別バンク 100 件。ID 1/2/3 は個別 vtable (0x1810fa958 / 0x1810cead8)。ID 1〜4 の意味 (型/周波数/Q/ゲイン) は `gen_filter_scen.py` のコメントと M+0x9dc4.. への直書きで出力が変わること (陽性対照) による**推定**。
3. **実 setter 実測** (`native/probe_setid.c`): 同一 M の複製に `0x1803debc0(M,id,v)` を v=0.5/0.25/0.9 で呼び、(a) M の変化バイト位置 (b) その M で Filter process を 3 回 (64 sample・fork 隔離) 実行した L/R の FNV-1a ハッシュがベースラインから変わるか、を判定。
   - ID 0x156..0x15b の変化バイトは全て**自 descriptor の範囲** (例 0x157: 0x4394..0x43a3, desc_off=0x4390) 内。DSP が読む +0x9dc4/0x9e0c/0x9e54/0x9e9c/0x9ee4 には書かない。
   - 出力は **18/18 不変** (type は ctor 既定のみ)。ベースライン出力は決定論 (同一入力 2 回で hash 一致)。
4. **陽性対照**: M+0x9e0c / M+0x9e54 への直書きで出力が変わる (outChanged=1 ×2)。測定系は出力変化を検出できる。
5. **静的** (`fa7_static_reads.py`): Filter closure (mlift 114 関数, 42,532 B, 9,319 命令) の `[reg+disp]` のうち M param 領域 (0x19b8..0xa400) = 8 件 (distinct 7): 0x9dc4/0x9e0c/0x9e54/0x9e9c/0x9ee4 + 0x9f98/0x9fa0 (ring buffer ptr, ID 外)。0x156..0x15b の descriptor 範囲は 0 件。

## 3. 検証結果 (起点 HEAD 8f55002 + 本 PR の追加ファイル, 実測)

| 項目 | 結果 |
|---|---|
| `run_fa7.sh` | **ALL PASS, 2.8 s** (load average 0.00, 並列 1, 判定 5 + ネガコン 3) |
| `run_chainmap.sh` (既存・無変更) | OK 8/8, 3.1 s (本 run で再確認) |
| ネガティブコントロール | NC1 期待集合に 343 を混ぜる → FAIL / NC2 outChanged を 1 に改竄 → FAIL (不変判定の一致 0/18) / NC3 観測行を除去 → 空 PASS せず FAIL。3/3 が期待どおり FAIL |

fail-closed: 判定は観測件数に下限を置き (空 PASS 拒否)、不合格は `exit 1`。`lift2_e2e.sh` は本 PR で未変更・未再実行。

## 4. 範囲外 / 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 controller map (`C+0x318`, 木ノード = key u16 id → shared_ptr<param>) を構築して `0x180c9d700` を実行し、ID → 実 param の解決先を実測 | 本 issue の主目的 (未達) | #452 に残す (本 PR は Refs)。続編は新規子チケット #648 (FA-8) |
| macro → 0x157.. が preset DUMP の接続表経由で Filter ID 1〜4 に届くか | 最終説明 | #648 (FA-8) |
| 型 enum は ctor 既定のみで測定 (`FA_TYPE` で切替可能な実装は入っているが、0x157.. 側の型別実測は未実施) | 弱い一般化 | #648 (FA-8) |
| wasm (mlift) 側に setter `0x1803debc0` が無く、setter 後の native/wasm bit-exact は未実施 | 受入条件の bit-exact 部 | #648 (FA-8) (--root 追加) |
| Compressor/Gain model の同 ID 意味は未調査 | 範囲外 | #648 (FA-8) |
