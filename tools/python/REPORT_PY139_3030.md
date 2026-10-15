# tools/python REPORT: PY-139 launchMapPages のイベント処理 3 件の PE 契約 (#3030・親 #2984)

> 正本: `tools/python/REPORT_PY120.md` (PE 確定の手順・`0xd82c20` の code 表)、`tools/python/REPORT_PY120_2984.md` (12 件の PyMethodDef・`length` の確定)。本付録は PY-139 の実測のみ。
> 前提 PR #3039 (PY-120) は merge 済み (2026-10-15T00:37Z)。前回 run の停止理由 (前提未 merge) は解消している。

既知類型との関係: 該当なし (PE の読取りのみ。lift・IR の変換は行っていない。`docs/DEFECTS.md`・`tools/icall/REPORT.md` の類型とは照合していない)

## 結論

- 3 件 (`processMapItem`・`releaseMapItem`・`checkMapForHiddenItem`) の**呼出し契約** (引数の書式・型・既定・戻り型・失敗経路の code) は PE から確定した。VA は下の各節。
- **作用先は未確定**。3 件とも、実際の状態変更は engine の `obj.+0x50` (mgr) の vtable 経由で行われ、その slot (`+0x10`・`+0x18`・`+0x30`) の実体を読んでいない。mgr の class と vtable は未同定。作用先が決まらないため、**mock・C の実装は見送った** (根拠のない値を入れない。PY-87・PY-120 と同じ方針)。
- 受入 2 (mock と C の差分 0)・受入 3 (`provider_check` の期待値) は未達。残りは子 issue に移した (下の未解決表)。
- 受入 4 (`all_tools` 48/48) は HEAD で維持を確認した (コードを変えていないため、main と同じ結果)。
- 共通ディスパッチャ `0xd843d0` は、引数 6 個とコールバックを要求オブジェクトに格納する経路まで確定した。投入・待機・status の書き戻しは未読。

## 手段

- 入口: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_launchmap_entries.py --disasm` (12/12 OK。3 件の fn VA・flags)。逆アセンブル: `analysis/flapi/pe_disasm.py <VA> <命令数>`。
- 書式文字列: fn 内の `lea rdx,[rip+X]` の参照先の bytes を読み、`analysis/flapi/flapi_table.json` の `kwsig.fmt` と照合した (別経路の検算)。
- 型記述子・`call` 先の注記 (RIP 相対の参照先) は一時スクリプトで出した。commit していない。上の pe_disasm.py で同じ命令列が出る。
- 展開: `fl-win64` の `block00031_PE.bin` と DATA block 4 件 (`fetch_inputs.sh` 用) を `$RUNNER_TEMP/fl-win64-3030` へ展開 (`tar --zstd -xf --wildcards`、2.8 秒)。
- 表記: 下の `[rbp+0xNN]` は各関数のフレーム。`obj` は `0xd7a6d0(self)` が返す `[rax]` (Python 側の所有オブジェクト)。`mgr` は `obj+0x50`。

## 共通: 外側の呼出し規約 (3 件とも同じ形)

- 出力の型記述子 `0xd81740` (`PyCallSynchronizedResult`) の `0x415610` 初期化 → `obj = [0xd7a6d0(self)]` → PyArg 解析 (`call qword ptr [rax]` の slot) → 失敗 (rc ≤ 0) は rc をそのまま `0xd82c20(rc)` に渡して返す。
- `0xd82c20(status)` の code 表は `REPORT_PY120.md` §参考 (本付録で再掲しない)。本付録で使う行は `-2` (Operation unsafe at current time) と `-7` (Device not assigned)。
- 型記述子 `0xfd5518` (releaseMapItem と `0xd79970` が参照) と `0xd81740` (それ以外) の区別は、PE 上の参照先の違いとして確定。

### 0xd843d0 (共通ディスパッチャ) — 確定した範囲

`0xd843d0(rcx=obj, rdx=out, r8=cb, r9=arg4, [rbp+0x80..0xa8]=arg5..10, [rbp+0xb0]=arg11)` (引数は 11 個。arg5 以降は stack)。

| VA | 命令の意味 (PE から言えること) |
|---|---|
| 0xd843dd〜0xd843e6 | `rbx=obj`・`rsi=out`・`rdi=cb`・`r13=r9` |
| 0xd843e9 | `*out = -2` (`out+0` qword)。既定は「実行不可」 |
| 0xd843f0〜0xd84403 | `mgr=[obj+0x50]` が非 0 かつ `0xd84f30(mgr)` が真なら 0xd84500 へ (**未読**)。`0xd84f30` は `mgr` の `+0x2d8`・`+0x3b8`・`+0x2da`・`+0x2d9`・`+0x410` の各 byte フラグを読む述語 (未同定) |
| 0xd84409〜0xd84415 | `0xd841e0(…, dl=1, r8=obj)` で要求オブジェクトを得て `rbx` に入れる (`0xd841e0` の中身は未読) |
| 0xd8441d〜0xd84446 | `[rbx+0x48]=r13` (0x4133f0 経由)、`[rbx+0x18..0x40]` = arg5..arg10 (6 個の qword) |
| 0xd8446b | `[rbx+0x58]=cb` (コールバック登録) |
| 0xd84471〜0xd8447a | arg11 (byte) が 1 なら `call [0x15e3ef8]` (スロットの実体は未同定) |
| 以降 | 投入・待機・`out+0` への書き戻しは**未読** (保留) |

- 要求オブジェクトの `+0x8` に `obj` が入るかは未確認 (0xd84412 で `r8=obj` を `0xd841e0` に渡すだけ)。下のコールバックは `ctx+0x8` を obj として読む。

## 1. processMapItem (entry 0x151e138・fn 0xd79bc0・flags 1)

- **書式 `Oiii`** (参照先 VA 0xd79d04)。PyArg の出力: `eventData=[rbp+0x98]` (O)・`index=[rbp+0xac]`・`itemIndex=[rbp+0xa8]`・`velocity=[rbp+0xa4]` (i)。flapi の `kwsig.fmt` も `Oiii` で一致 (検算)。
- 外側の流れ: `0xd843d0(rcx=obj(rbx), rdx=&out[rbp+0x80], r8=0xd79970, r9=0, arg5=eventData, arg6=index, arg7=itemIndex, arg8=velocity, arg9=0, arg10=0, arg11=1)` (0xd79c48〜0xd79ca3)。戻り後 `ecx = out+0` → `0xd82c20(status)` (0xd79ca8〜0xd79cb1)。PyArg 失敗 (rc ≤ 0, 0xd79c46) は `0xd82c20(rc)` (0xd79caf)。
- **コールバック `0xd79970` (ctx = 要求オブジェクト)**:
  - `ctx.status (+0x60) = -2` (0xd79996)。
  - 述語 `[0x15e4790]→[+8]→vt[+0x98]` (0xd7999e〜0xd799b2)。偽なら 0xd79b77 (status は -2 のまま)。
  - 真の経路: `mgr=[obj+0x50]` (0xd799d0)。`index<0` は `mgr+0x3d4` (固定記録)、それ以外は `mgr+0x3c0` の配列の `index×32` 番目 (0xd799dd〜0xd79a23)。`0x416750` で要素を holder へ写す (**引数の意味は未確定**。REPORT_PY120_2984 の `getMapItemColor` と同じ要素取得)。
  - `0xd87a90(mgr, eventData)` → `eventData+0x10` (0xd79a34。0xd87a90 は `lea rax,[rdx+0x10]; ret` だけの関数で、rcx は使わない)。その先頭 word を `cmp` (0xd79a3c)。
  - `mgr` の vtable の slot `+0x10` を呼ぶ (0xd79af3)。**呼出し先の vtable・引数・後処理は未読**。mgr 0 の経路 (0xd79b6a) の status は未確認。

## 2. releaseMapItem (entry 0x151e158・fn 0xd79d10・flags 1)

- **書式 `Oi`** (参照先 VA 0xd79f74)。PyArg の出力: `eventData=[rbp+0xa0]` (O)・`index=[rbp+0xcc]` (i)。flapi の `kwsig.fmt` も `Oi` で一致 (検算)。
- **`0xd843d0` を使わない** (fn 全体で `call` 先は 0x415610・0xd7a6d0・PyArg slot・0x416750・0xd87a90・vtable・0xd82c20・0x415c30 のみ)。直接 mgr の slot を呼ぶ。
- 流れ:
  1. `holder=[rbp+0xac]` を型記述子 `0xfd5518` で初期化 (0xd79d26〜0xd79d34)。`obj=[0xd7a6d0(self)]` → `rsi` (0xd79d3e〜0xd79d43)。
  2. PyArg (0xd79d83〜0xd79d8a)。`rc` は `rbx` へ。`rc ≤ 0` は `0xd82c20(rc)` (0xd79f1f)。
  3. `mgr=[rsi+0x50]` が 0 なら `rbx=-7` (0xd79f18) → `0xd82c20(-7)`。
  4. `index<0` は `mgr+0x3d4`、それ以外は `[mgr+0x3c0] + index×32` (0xd79db0〜0xd79dc9)。**件数 (配列の `[arr-8]`) と比較する命令は無い** (範囲外の index は無検査で読まれる。PY-120 の `length` の件数との関係は未確定)。`0x416750(&holder, elem, type)` で holder へ写す (0xd79dd4・0xd79df0)。
  5. `0xd87a90(mgr, eventData)` → `payload=eventData+0x10` (0xd79e00)。
  6. ローカル `[rbp+0x6c..0x9c]` へ payload の値を写す: `flag=(word[payload] != 0)` (0xd79e08〜0xd79e13)、他に dword・double・byte・word の各フィールド (0xd79e16〜0xd79e92)。
  7. `vt+0x18` を呼ぶ: `mgr->vt[+0x18](mgr, &local, &holder)` (0xd79e98〜0xd79ead、`rsi=[mgr]`)。**slot の実体は未同定**。
  8. 戻り後 `local` を payload へ書き戻す (0xd79eb0〜0xd79f0d)。`word[payload+8] = 0x20` (0xd79f10)。
  9. 成功時 `rbx` は PyArg の rc = 1 のまま → `0xd82c20(1)` (0xd79f1f〜0xd79f21)。**正の code の経路 (0xd82c20 の戻り値) は未読**。`None` の根拠はこの経路の確定に依存する (PY-120 の未解決 #3034 と同じ)。

## 3. checkMapForHiddenItem (entry 0x151e178・fn 0xd79fe0・flags 4 NOARGS)

- `out=[rbp+0x78]` (型 `0xd81740`) → `obj=[0xd7a6d0(self)]` (0xd79ff3〜0xd7a009)。
- `0xd843d0(rcx=obj, rdx=&out, r8=0xd79f80, r9=0, arg5..arg10=0, arg11=1)` (0xd7a013〜0xd7a058)。コールバックは `lea r8,[rip-0x9a]` で `0xd79f80` (0xd7a013+7−0x9a = 0xd79f80)。
- 戻り後 `ecx = out+0` → `0xd82c20(status)` → 戻り値を返す (0xd7a05d〜0xd7a068)。後始末 `0x415c30` (0xd7a078)。
- **コールバック `0xd79f80` (ctx = 要求オブジェクト)** (全命令を読んだ):
  - `ctx.status = -2` (0xd79f88)。
  - 述語 `[0x15e4790]→[+8]→vt[+0x98]` (0xd79f90〜0xd79fa4)。偽なら 0xd79fd6 (status -2)。
  - 真なら `status=0` (0xd79fae)。`mgr=[ctx+8]+0x50` (0xd79fb6〜0xd79fba)。
  - mgr が 0 → `status=-7` (0xd79fce)。非 0 → `rbx=[mgr]` (vtable)、`call [vt+0x30](mgr)` (0xd79fc3〜0xd79fc9)。**戻り値は使わない**。
- 結論: 外から見える戻り値は `0xd82c20(status)` のみ。`status` が -2 (述語が偽) と -7 (mgr 無し) は PE から確定。`status=0` の戻り (None か) と、`vt+0x30` の作用は未確定。

## 同定した事実 (3 件の共通)

- mgr (`obj+0x50`) の配列: `+0x3c0` (要素 32 バイト、件数は `[arr-8]`)、`+0x3d4` (固定記録)。`REPORT_PY120_2984.md` の `getMapItemColor` と同じ形。
- 作用先の slot: `vt+0x10` (processMapItem のコールバック)、`vt+0x18` (releaseMapItem。ローカルと holder を受け取る)、`vt+0x30` (checkMapForHiddenItem。引数なし)。3 件とも slot の実体は未確定。
- 述語 `[0x15e4790]→[+8]→vt[+0x98]` は 3 件のコールバックに共通。`REPORT_PY120.md` の `0x11d1430` (`[vtbl+0x88]` の前提判定) と offset が異なる。同一の述語かは未確認。

## 検証

### 測定 commit と差分の証跡

- 測定 commit: `1cb3ac477` (origin/main)。本 PR はコードを変えない (`tools/python/` の `.md` と `docs/DOC_MAP.md` のみ)。
- 差分 0 の証跡 (`docs/WORKFLOW.md` §6): 下の出力を最終 HEAD で取る (コミット後に記入)。

```
$ git diff 1cb3ac477 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis/flapi
(空)   ← コミット後に再取得
```

### 実行結果 (HEAD = 測定 commit、素材 fl-win64 の展開先 `$RUNNER_TEMP/fl-win64-3030`)

| コマンド | 結果 | wall |
|---|---|---|
| `bash fetch_inputs.sh` と `bash provider/build.sh` | rc 0・rc 0 (fl_table.c: 435 関数) | 2.4 秒 (2 本の合計) |
| `bash build_cpython_wasm.sh` (32 bit・emsdk は `[EMSDK]`) | rc 0 | 260.9 秒 (4 分 20.9 秒)・load avg 3.5 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 | 未計測 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 162 / 未実装 273 / MCP 静的 60) | 未計測 |
| `node tests/launchmap_diff.mjs` | calls 3・diffs 0・PASS | 未計測 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true | 未計測 |
| `python3 analysis/flapi/pe_launchmap_entries.py --disasm` | 12/12 OK | 未計測 |

- `provider_check` の実装数 162 は、main が前回測定 (`565ee264`・141) から進んだ分を含む現 HEAD の値。本 PR で変わらない。

### ネガティブコントロール

- 書式の検算 (PE 読取り ↔ flapi): processMapItem の参照先を 1 バイトずらす (VA 0xd79d05) と `'iii'` になり、flapi の `'Oiii'` と**不一致** (`match False`)。ずらさない 0xd79d04 は `'Oiii'` で一致 (`match True`)。releaseMapItem (0xd79f74) は `'Oi'` で一致。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| mgr の class と vtable の同定 (`obj+0x50` の生成側。`vt+0x10`・`vt+0x18`・`vt+0x30` の実体) | 3 件の作用先が決まらない。mock・C の実装 (受入 2) が不可 | #3772 (`[PY-250]`・`親: #3030`)。#3746 (`[PY-244]`) と mgr の vtable を共有する |
| `0xd843d0` の投入・待機経路 (`0xd84500` 側・`0xd841e0`・`[0x15e3ef8]`・要求の `+0x8`) | コールバックが実際にいつ・どの thread で動くか。`out+0` の最終値 | #3772 |
| `0xd82c20` の正の code 経路 (releaseMapItem の成功 status=1) と `0xc38bc0` の同定 | 3 件の戻り値 (None) の根拠。REPORT_PY120 の未解決 #3034 と同じ | #3034 (`[PY-141]`) |
| 述語 `[0x15e4790]→[+8]→vt[+0x98]` の同定 | 3 件の失敗経路 (-2) の発生条件 | #3772。#3746 (`[PY-244]`) は同じ述語を safeToEdit と同じとして扱う (未確認) |
| releaseMapItem の index 範囲検査の無さ (`[arr-8]` と比較しない) | 範囲外 index の読出し (C 実装時の安全性) | #3772 (C 実装時の要件) |
| `checkMapForHiddenItem` の `vt+0x30` 作用・processMapItem の `vt+0x10` の引数 | 作用の有無 | #3772 |

- 起票: 子 issue 1 件 `#3772` (`[PY-250]`・親 `#3030`)。本 PR の範囲は受入 1 (PE の VA 付き記録) のみ。受入 2・3 は子へ移した。
- 関連: #3029 (`[PY-138]`) と #3746 (`[PY-244]`) も `0xd843d0` の経路と mgr を使う (同一関数・同一 vtable かの確認は未実施)。
