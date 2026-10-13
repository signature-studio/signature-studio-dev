# tools/plugins/synth/gr/REPORT.md — PLG-G2-1 (#533) Gen_Render native-vs-wasm 差分 harness

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/synth/gr/` のみ / 検証起点 commit: §5
- 再現: `bash tools/plugins/synth/gr/gr_e2e.sh` (native 実行 + 判定) / `python3 tools/plugins/synth/gr/gr_nega.py` (判定器のネガコン)
- 素材: `fl-win64` のみ (`docs/WORKFLOW.md` §11)。 親 #207、測定は `tools/plugins/synth/REPORT.md`
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift を行っていない)

## 0. 結論 (先出し)

1. **#533 の受入条件は未達。 PR は `Refs #533` (Closes しない)。** 出来たのは「native 側の実行器」と「fail-closed な判定器 + ネガコン」で、
   **12 shell のどれについても native と wasm の bit 比較は 1 件も成立していない**。
2. **wasm 側が存在しない**。 Gen_Render を呼べる wasm は repo に無い (#195 / #196 / #197 が OPEN。 #533 本文の前提「完了後に着手可能」が未達)。
   本 harness は wasm 側の出力を `<wasm-dir>/<block>.bin` (§2 の形式) で受け取る契約だけを定め、無ければ `MISSING-WASM` で **exit 1** にする。
3. **native 側も「this = 0 埋め」では基準にならない。 実測: 12 本中 11 本が Gen_Render 内で SIGSEGV、 FL Slayer 1 本は正常 return したが dst に 1 word も書かない** (§3)。
   つまり判定は現状 12/12 本が `INVALID-REF` で exit 1。 native を基準にするには、ctor を通した実 instance (または host オブジェクトのモック) が要る。 これは #196 作業 5 (P0b) と同じ前提。
4. **受入条件のうち未着手**: 「固定 MIDI/パラメータ列」 (TriggerVoice / ProcessParam を呼ぶ列)。 this が成立しないため、列を native へ流しても意味のある出力にならない。 case 列は length / 出力 padding のみ (§2)。
5. **ネガティブコントロール**: 判定器の 13 ケース (control 1 + 改変 12) すべて期待通り (§4)。 ただし**合成データによる判定器の検査**で、実プラグインの出力による NC ではない。

## 1. 構成

| ファイル | 役割 |
|---|---|
| `native_gen.c` | DLL を VA 0x400000 に MAP_FIXED 敷設し、`Gen_Render(this, dst, &Length)` (ms_abi) を実機械語で呼ぶ (`lift/t0_balance/native_ref.c`・`f1/pi/native_pi.c` と同方式)。 SIGSEGV 等は `sigsetjmp` で捕捉して**結果に記録**し、次 case へ進む |
| `gr_targets.py` | 12 shell の Gen_Render VA と instance size を `inventory/win_abi.py` の `scan` で DLL から実測 (`synth/targets.py shell` が 12 本でなければ失敗) |
| `gr_lib.py` | case 生成・結果 bin の入出力・bit/ulp 比較。 NaN は bit 一致以外を不一致にする |
| `gr_judge.py` | shell ごとに PASS / PASS-TOL / DIFF / SHAPE / WASM-ABORT / MISSING-WASM / INVALID-REF。 **exit 0 は 12 本全部が PASS (`--ulp N` 指定時は PASS-TOL も可) のときだけ** |
| `gr_e2e.sh` | 上を連結 (`--wasm-dir`, `--ulp`)。 native が落ちても判定まで進み、最後に judge の rc で終わる |
| `gr_nega.py` | `gr_judge.py` のネガコン (合成 results.bin) |
| `gr_static.py` | Gen_Render / TriggerVoice のサイズと call 数 (§3 の表) |

## 2. 入出力形式 (native / wasm 共通)

- `cases.bin`: u32 ncases + 各 case `{u32 length; u32 padD; u32 reset}`。 `length` = Gen_Render の `Length` (frame 数)、`padD` = dst の 4 B 単位ずらし、`reset` = case 前に this を 0 埋めし直すか。
  固定 6 case: `(64,0,1) (64,0,0) (17,3,0) (1,0,0) (512,1,0) (64,0,1)` (`gr_lib.make_cases`)。
- `results.bin`: 各 case `{u32 status; u32 sig; u64 fault_rip; u64 fault_addr; u64 ret; u32 nd; u32 dst[nd]}`、`nd = 2*length + 16`。 dst の初期値は `0xA5A5A5A5` で、書かれなかった word を見分ける。
- 許容条件: 既定は **bit-exact (許容 0)**。 `--ulp N` は float32 の順序整数距離 ≤ N を許容し、PASS-TOL に分類する。 bit-exact にならない shell の許容値は、**比較が成立した後に**ここへ記録する (現状 0 件)。

## 3. native 実行の実測 (this = 0 埋め、case 6 件)

数え方: `gr_e2e.sh` が出す `work/synth_gr/native/<block>.bin` の case 0 の `status` と、dst のうち 0xA5A5A5A5 でない word 数。 Gen_Render のサイズは `.pdata`、call 数は capstone の linear disasm (`gr_static.py`)。

| プラグイン | block | Gen_Render VA | サイズ B | direct / 間接 call | instance B | native の結果 | 中断位置 (rip, 参照 addr) |
|---|--:|---|--:|--:|--:|---|---|
| Autogun | 21151 | 0x885600 | 1,658 | 12 / 15 | 1,568 | SIGSEGV | 0x885669, 0x20 |
| BooBass | 21204 | 0x6b8cb0 | 27 | 0 / 1 | 320 | SIGSEGV | 0x6b8cbf, 0x0 |
| FL Slayer | 22433 | 0x853aa0 | 282 | 4 / 1 | 504 | **正常 return、dst 書込 0 word** | — |
| Harmless | 23738 | 0x7886b0 | 2,302 | 18 / 21 | 2,088 | SIGSEGV | 0x7886ef, 0x0 |
| Kepler | 23913 | 0x6d5790 | 27 | 0 / 1 | 464 | SIGSEGV | 0x6d579f, 0x0 |
| Kepler Exo | 23915 | 0x7231f0 | 27 | 0 / 1 | 4,136 | SIGSEGV | 0x7231ff, 0x0 |
| Ogun | 24146 | 0x86d450 | 1,417 | 12 / 14 | 1,552 | SIGSEGV | 0x86d4ab, 0x20 |
| PoiZone | 24158 | 0x6dc7b0 | 27 | 0 / 1 | 1,600 | SIGSEGV | 0x6dc7bf, 0x0 |
| Sakura | 24162 | 0x718dc0 | 130 | 1 / 1 | 816 | SIGSEGV | 0x718de6, 0x0 |
| Sawer | 24165 | 0x722360 | 27 | 0 / 1 | 1,112 | SIGSEGV | 0x72236f, 0x0 |
| Transistor Bass | 24297 | 0x6e0310 | 27 | 0 / 1 | 344 | SIGSEGV | 0x6e031f, 0x0 |
| Wave Traveller | 24315 | 0x74c410 | 303 | 3 / 3 | 360 | SIGSEGV | 0x4056f7, 0x18 |

読み取れること (機械語の目視で確認したもの):
- 27 B の 6 本 (BooBass / Kepler / Kepler Exo / PoiZone / Sawer / Transistor Bass) は `mov rax,[rcx+0x120]; mov rax,[rax]; call [rax+0x40]` で、**this+0x120 の engine オブジェクトの vtable slot 8 へ転送するだけ**
  (BooBass の TriggerVoice も同形で `[rax+0x48]`)。 DSP は engine DLL (C++) 側にあり、shell 殻の差分試験だけでは DSP を検証できない。 engine 側は #534 / #207 §4 の通り lift 未通過。
- FL Slayer は `[this+0x148]` (engine オブジェクト) が 0 のとき何もせず return する分岐があり、this=0 埋めではその経路を通る。 正常 return でも**何も出力しない**ため基準にならない (judge は空出力を `INVALID-REF` にする)。
- IAT は未解決 (0) のまま。 Win32 呼出を含む経路は、実 DLL なしの native では到達できない。

## 4. ネガティブコントロール (`gr_nega.py`、合成データ、3 回実行して 0.50〜0.51 s)

合成 native (決定的な疑似乱数の finite float) を 12 本分作り、wasm = native のコピーに 1 箇所だけ改変を入れて `gr_judge.py` を実行。 期待 rc と出力文字列の**両方**を検査する (rc だけ見ると別の理由で落ちても緑になる: `synth/REPORT.md` §6 の教訓)。

| ケース | 期待 | 実測 |
|---|---|---|
| control (wasm = native) | rc 0、`OK 12/12` | OK |
| 1 サンプルの 1 bit 反転 (1 shell、許容 0) | rc 1、`DIFF=1` | OK |
| 差 1 ulp、許容 0 | rc 1、`DIFF=1` | OK |
| 差 1 ulp、`--ulp 2` | rc 0、`PASS-TOL=1` | OK |
| 差 8 ulp、`--ulp 2` | rc 1、`DIFF=1` | OK |
| wasm が中断 / 結果ファイルなし / 出力長 1 word 短い | rc 1、`WASM-ABORT=1` / `MISSING-WASM=1` / `SHAPE=1` | 3 件 OK |
| 戻り値 (rax) だけ違う | rc 1、`DIFF=1` | OK |
| wasm が NaN (`--ulp 100000000` でも) | rc 1、`DIFF=1` | OK |
| native が中断 / dst 無書込 / 結果ファイルなし | rc 1、`INVALID-REF=1` | 3 件 OK |

13 ケース中 NG 0。 **実 DLL に対する NC (native の実行器を壊す等) は未実施** — 実行器が基準を作れていない (§3) ため、壊す対象となる合格状態が無い。

## 5. 検証

| 項目 | 実測 |
|---|---|
| 検証起点 | **コミット済み HEAD 73c540e** をクリーン worktree (`git worktree add --detach`) に展開して実行 (4 core / 開始時 load average 0.07) |
| `gr_nega.py` | 3 回すべて exit 0、0.50 s (13 ケース中 NG 0) |
| `gr_e2e.sh` (wasm 結果なし) | 3 回すべて **exit 1**、0.43〜0.44 s。 出力: `INVALID-REF=12` (12 本中 11 本が native SIGSEGV、1 本が dst 無書込) |
| 作業ツリー (未コミット作業中) での同じ実行 | `gr_nega.py` 0.50〜0.51 s ×3 / `gr_e2e.sh` 0.463 s (1 回目) と同じ結果 |

検証範囲: 12 shell の Gen_Render VA / instance size の導出、native 実行器の挙動 (落ちる事実を結果に残すこと)、判定器の識別力。
範囲外: wasm 実行、ctor を通した this での native 実行、MIDI / パラメータ列、engine DLL、Render test .flp。 範囲外の項目について本書は何も主張しない。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側の Gen_Render 実行体が無い (P0a / P0b / P0c 未完) | bit 比較が成立しない。 #533 の受入条件 1 を満たせない | #195 / #196 / #197 (既存)。 完了後に本 harness の `--wasm-dir` へ接続 |
| native の this が成立しない (11 本 SIGSEGV、1 本は無出力)。 ctor を通した instance か host / engine オブジェクトのモックが要る | native 基準が作れない | #196 作業 5 (host shim)。 engine 分離型 7 本は #534 (engine の lift) |
| 固定 MIDI / パラメータ列 (TriggerVoice / ProcessParam / Voice_*) | 受入条件 1 の「固定 MIDI/パラメータ列」未達 | #533 に残す (this が成立してから) |
| bit-exact にならないものの許容条件 | 受入条件 2 | 比較が成立してから #533 で記録 |
| #200 (PLG-F3) の Eff_Render 版との共通化 | 保守 | `gr_lib.py` / `gr_judge.py` / `native_gen.c` は slot と引数だけが Gen_Render 固有。 共通化は PM 判断 (#544 [PLG-F6-1] にも同種の Eff_Render harness 起票あり) |
