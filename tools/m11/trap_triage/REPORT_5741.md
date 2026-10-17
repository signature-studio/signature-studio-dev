# REPORT_5741: unit 275 の OOB 原因の判定と DEFECTS 行案 (#5741、親 #1676 の受入 2 の移送)

既知類型との関係: 原因は**未確定**。確定したのは「list B の `base(+8)=0` の NULL 付近書込み (D15 同型の Grow 脱落、REPORT_2408 §4)」と「unit 275 内の callback による count 増加」まで。DEFECTS 行は確定させず、§5 に案を残す。

## 0. 結論

1. **REPORT_881 の前提を訂正**: REPORT_881 §2・§3 は `obj=[G]` を list の持ち主とし、list=0 と読んでいた。実際は `obj=[[G]]` (2 段) で、unit 114 の後は `obj=0x10b58160`、`list=[obj+188]=0x10bd4c20` (非 0)。`[G2]+188` (callback が push する list B) と同一。よって REPORT_881 §4.1・§4.2 の「list A と list B は別物 / 矛盾点」は、段数の読み違いによる誤りだった。
2. **unit 275 の OOB の直接の経路 (実測)**: list B は unit 114 で生成され `base(+8)=0`、`count(+16)=1` (n=2)。`base=0` のため `this=[base+8*idx]` は NULL 付近の残骸 (`mem[0..]`) を読む。残骸は list B の Add (`function_50a830`) が `FItems=0` に対して `mem[cnt*8]` に書いたもの (store 監視で `[0,32)` への書込み 117 件を確認、全て `function_50a830`)。
3. **unit 275 の中で count が 1→2 に増える**: unit 275 の中で callback `85df70` (monitor 列挙) が `50a830` を呼び、count が 2 になる (probe `probe5741_trace275.mjs`・`probe5741_loop275.mjs`、n=1)。trap は `864fe0` の OOB で起きるが、count 増加と trap の因果 (loop のどの添字で落ちるか) は未実測。
4. **機構の未確定点**: `80e040` の loop 上限 (`8657d0` の戻り値 = 呼出し時点の count) は 1 のはずだが、trap は loop 内の `this` (添字 1 以降) で起きる。`count` が callback で増えた後の再読か、`80e040` 内の別の経路かは未特定。
5. **ON の反証 (`M11_FIX_50A830=1`、REPORT_2408 §7 の再現・本 run で再測定)**: ON では list B の `base` が非 0 になるが、unit 275 は oob のまま (frames 同じ)。unit 144 が ok→oob の回帰 (既知、#2521)。survey ok 874 / oob 15 (OFF 875 / 14)。よって「NULL 残骸が 275 の OOB の唯一の原因」は反証された (base を正しく入れても 275 は落ちる)。

## 1. 実測の基準 (本 run、HEAD = origin/main `58ee21f1e`、worktree `ws-5741`)

- 素材: `fl-win64` の `block00031_PE.bin` sha256 `b2c64da4…` (REPORT_881 と一致)。`work/` は main の `tools/m11/work` を `cp -a` で複製 (1.6 GiB)。`work/lift_pe.sha256` は PE 指紋を手記録 (REPORT_881 §10.2 と同じ手順)。
- e2e `bash m11_e2e.sh` (増分、foreground、wall 3m03s、load 約 1.0): `reached_stage` 4、`survey_ok` 875、`survey_trap` 20、`miss` 46、`units_run_full` 98。**rc=1** (`TOLERANT_GATE_FAILED: survey ok=875 != 期待 873`)。期待値 873 は `e2e_expect.env` の値で、本 run は main のコードをそのまま使った (コード変更なし)。ゲートの期待値と実測の不一致は本 issue の範囲外。
- survey `SV_RAW=1 survey_units.mjs` n=2 (rc 0、両回): `{"ok":875,"miss":46,"halt0":6,"oob":14,"noproc":1}`。unit 275 は両回 `oob` (frames `864fe0 ← 80e040 ← 80e140 ← 80e170`)。
- ON (`M11_FIX_50A830=1`、e2e wall 1m02s): survey `{"ok":874,"miss":46,"halt0":6,"oob":15,"noproc":1}`、rc=1 (ゲート 873 不一致)。OFF との差は unit 144 の ok→oob 1 件のみ。unit 275 は oob のまま。

## 2. 実測 (probe、本 run)

| probe | 結果 |
|---|---|
| `probe5741_listA.mjs` (全 unit の `[0+8]`・`[0+16]` の変化) | `[0+8]`・`[0+16]` は unit 17・114・144・149・158・189・190・220・233・237・275 で変化。unit 275 後の `[0+16]`=3204488 は unit 237 で入った |
| `probe5741_deref.mjs` (段数の確認) | `[[G]]+188`=`[G2]+188`=`0x10bd4c20` (unit 114 後)。REPORT_881 の段数の読み違いを確認 |
| `probe5741_elem.mjs` (275 直前の base/count と this) | `base=0`・`count=1`。`mem[0]=0x2fa020`、`mem[8]=0x2fa360`、`mem[0x10]=0x30e588`、添字 10 で `this=0x100000000` (範囲外) |
| `probe5741_trace275.mjs` (275 の icall 行) | unit 275 の icall は `0x40e170` → `0x85df70` (callback) → `0xf960`。callback 後に count 1→2 |
| `probe5741_loop275.mjs` | 275 前 `count=1`、275 後 `count=2`・`base=0`・`mem[8]=0x10bd5280` (REPORT_1507 §10 と一致) |
| 全 IR store の計装 (unit 0..274、`WATCH_ADDR=0x0`。計装スクリプトは work/ 内の非 commit、本 PR には含めない) | `[0,32)` への書込み 117 件、全て `function_50a830` (IR line 185815、`store i64 %arg2, ptr %8`)。unit 114・157・188・189 ほかで発生。**この表の 117 件は本 PR のスクリプトでは再現できない** (再現手順は §7 に書かない) |

## 3. 静的 (disasm)

- `80e040`: `obj=[[G]]`→`list=[obj+188]` (8657d0 で count、8657b0→50aa70 で要素)。loop は `ebx` 0..`eax-1`。`this` は `864fe0(this, …)` の第 1 引数。
- `50aa70(list, idx)`: `idx >= [list+16]` のとき `449600` で拡張、その後 `[[list+8]+8*idx]` を返す。
- `864fe0(this, _)`: `this=[rcx+8]` を `5dca40` へ。`this` が範囲外で OOB。
- `85df70` (callback): `40f9e0` でブロックを確保し `50a830(arg4, blk)` で list に push。

## 4. 検証結果

- e2e rc=1 (ゲート期待値 873 と不一致。main の既存状態。本 issue のコードは変えていない)。
- survey n=2 で unit 275 の `oob` を再現。ON 反証の結果も §1 のとおり。
- 測定 commit: 本 PR で追加するのは `trap_triage/` の probe 5 本と本 REPORT のみ。`tools/m11` の実行経路 (`m11_*.sh`・`m11_win.c`・`survey_units.mjs`) の差分は 0。
- 差分確認コマンド: `git diff origin/main HEAD -- tools/m11 ':!tools/m11/trap_triage'`。

## 5. DEFECTS 行案 (未確定。PM 判断)

確定させない。類型は次のどちらかで、現時点では区別できない。

- 候補 A (D15 同型 + 型の誤認): `function_50a830` の Grow/Notify 脱落で list B の `base=0` のまま、NULL 付近を読む (REPORT_2408 §4・§7)。ただし ON で base を正しくしても 275 は落ちるため、275 の唯一の原因ではない。
- 候補 B (unit 275 内の count 増加と loop 上限の不整合): callback が loop の途中で list の count を増やす。`80e040` が呼出し時点の count を前提に読むため、残りの添字で範囲外を読む。機構 (loop 上限の再読か別経路か) は未確定。

行案 (案): `| D27 (案) | fe+ours | 新規 | 列挙 callback が、呼出し元の loop 中に list の count を増やし、呼出し元が範囲外の this を読む | 未確定 (§4 の機構) | unit 275 (`864fe0` OOB) | 未確定 | 未確定 |` — ID の確定は PM 判断 (DEFECTS の最後の行は D26、D27 は空き)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `80e040` の loop 上限と添字の関係 (count=1 のはずで idx≥1 を読む) の機構。loop 内の値を直接取る計装が要る (`m11_trace` は icall 行のみ) | DEFECTS 行案の確定 (候補 A/B の区別) | #5758 (`[M11-N267]`、親 #5741) |
| `5dca40` (`864fe0` の呼出し先) の VA 対応 (`disasm_fn.py` が KeyError。関数表に無い) | `864fe0` の trap 位置の確定 | #5758 (同上) |
| e2e ゲート期待値 873 と main の実測 875 の不一致 (原因未調査) | e2e rc=1 (本 issue のコード変更は無い) | #4749 (`[LD-239]`、追跡中) |
| DEFECTS.md への行追加 | 横断正本の更新 | PM 判断 (`docs/WORKFLOW.md` §5) |

注: #5761 は #5758 と重複 (同じ受入)。起票先は #5758 に統一した。#5761 の close は PM 判断。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP
cd tools/m11
sha256sum "$FL_WIN64_DIR/extracted/block00031_PE.bin" | cut -d' ' -f1 > work/lift_pe.sha256
bash m11_e2e.sh                                    # rc=1 (ゲート 873 不一致。REPORT_5741 §1)
SV_RAW=1 node trap_triage/survey_units.mjs work/trap_triage/s.json   # unit 275 = oob
node trap_triage/probe5741_elem.mjs                # base=0・count=1 (275 直前)
node trap_triage/probe5741_loop275.mjs             # 275 の前後 count 1→2
M11_FIX_50A830=1 bash m11_e2e.sh                   # ON: 275 は oob のまま、144 回帰
```

注意: `M11_FIX_50A830` を使うときは `rm -f work/obj/ov.o` を先に行う (REPORT_2408 §7.3)。
`[0,32)` への書込み 117 件 (§2) は、この再現手順には含まれない (計装スクリプトは未 commit。§2 の表を参照)。

## 8. 80e040 loop の計装 (#5761、`M11_INSTR_80E040=1`、既定 0)

測定 commit: `26aa90724` (計装を入れた最後の commit。既定 0 の build 出力は変えない)。基点 `origin/main` `f82959016`。

- 計装: `m11_post.py` が 80e040 の `864fe0` 呼出し直前に `m11_80e040_loop_obs(ebx, rsi, this)` を挿す。`m11_ov.c` は `list` (`[[G]]+188`)・`base`・`count` を読み直して stderr に出す。
- 基準 e2e (計装なし、増分、foreground): wall 3 分 01 秒、rc=1、`survey_ok` 875、`ok 875 / oob 14 / miss 46 / halt0 6`。§1 と同じ。
- 計装 build: `M11_INSTR_80E040=1 bash m11_build.sh` rc=0 (23 秒)。probe `probe5741_loop275.mjs` の 275 前後は `count` 1→2・`base=0`。
- 観測: 80e040 の loop 行は全 unit で 7994 行。unit 275 の `trap` は probe 上で再現した。観測の上限 (65536) には達していない。
- 実測値: 観測の `list` は全行 `0x10bd4c20`、`base=0x0`、`count=2`。ebx 0 の行から count=2 が既に出ている。
- 未確定: loop 上限 `rsi` の初期値は `3204488` (0x30E588 + 0x100000000。`8657d0` の戻り値 `eax` に相当)。これは観測した `count=2` と一致しない。probe の読み方と `8657d0` の読み方 (IR の `[obj+0xbc]+0x10`) の違いが原因かは未確認。trap 時の添字と count の関係は、unit 275 の行だけを抜き出して特定していない。
- 逆アセンブル: `8657d0` は `cmp qword ptr [rax+0x10], 0` の後 `mov eax, dword ptr [rax+0x10]` (0 なら `424ee0`)。`disasm_fn.py` は `FL_WIN64_DIR` が無いと既定パスで落ちる。

判定: 受入 1 (trap 添字と count の読み方の特定) は未達。計装の入口と観測値は揃ったが、上限の食い違いの解消が次の一手。
