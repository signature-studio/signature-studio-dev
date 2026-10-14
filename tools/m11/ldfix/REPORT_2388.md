# REPORT #2388 — cf3790 の残り 15 site の IR 消費者追跡と判定 (LD-109)

親: #2312 (LD-105) / #2287 (LD-103) / #2266 / #2244 / #1161 (LD-35)。cf3790 の spill 宛 未判定 15 site を全て判定し、`cf3790` の未判定は 0 件になった。

既知類型との関係: DEFECTS.md の D17 系 (spill 宛の脱落。#1161 の分類と同じ枠)。新規類型なし。

## 1. 結論

- 15 site は全て **OK_LOAD** (当 site の `[rax]` deref が IR に load として存在し、機械語の読み戻しに対応する消費者が IR にある)。TRUE_DROP / NO_CONSUMER / UNDETERMINED は 0 件。
- 判定の根拠 (機械語の命令列・IR の SSA 名と絶対行番号) は `results/candidate_verdicts_1161.jsonl` に site ごとに追記した (15 行)。根拠は `ld109_cf3790_verify.py` が機械語・IR の実物と照合して生成する (§4)。
- `ld105_reg2mem_map.py` の slot 名の式が誤っていた (§3)。突合表の `alloca: no` と `ir_reload_use` は誤った slot を見ていた。同じ訂正が #2389 (LD-110・REPORT_2389.md) で先に main に入ったため、本 PR は main 取り込み時にその版を採用した (再生成した表は一致)。
- cf3790 の 24 site の内訳 (確定のみ): TRUE_DROP 6 (cf387f・cf38be・cf390f・cf3c7a・cf3cbb・cf3d20)・OK_LOAD 17・NO_CONSUMER 1 (cf398c)。

## 2. 測定

- 測定 commit (コードを変えた最後の commit): `584d9cc8` (origin/main `67dffb5d` = #2389 取り込み後の merge commit)。内訳: `73fe9491` (検証スクリプト・判定 15 行)・`27c868ca` (生成物 `results/spill178_1161.tsv` の再生成)・merge で `ld105_reg2mem_map.py` / 突合表 / `candidate_verdicts_1161.jsonl` の 3 行は main 側 (#2389) を採用し、判定 15 行は main 側の末尾に追記し直した。後続の commit は本 REPORT と PR 本文の整合のみで、`git diff 584d9cc8 HEAD -- tools/m11/ldfix ':!tools/m11/ldfix/REPORT_2388.md'` は空 (出力は PR 本文)。
- 素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff`。`work-m11` と `work-liftdiff` は共有の main ワークツリーに展開済みのものを `M11_WORK` / `LD_WORK` で読み取り専用に参照した (worktree には展開していない)。`boot_final3.ll` の sha256 は `010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e` (REPORT_2288 と同一)。
- 実行: `M11_WORK=<work-m11> LD_WORK=<work-liftdiff> bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh`
  - 1 回目 (`73fe9491`・判定追加直後): rc=1・所要 143 s。step 7 の `cmp` が `results/spill178_1161.tsv` の差 (判定 15 行の status 変化) で失敗した。生成物の再生成が未コミットだったためで、想定どおり。
  - 2 回目 (`27c868ca`・#2389 取り込み前): rc=0・所要 142 s (12:26:24〜12:28:46 実測)・7/7 完了・終了時 load average 0.97。
  - 3 回目 (**`584d9cc8`・#2389 取り込み後の測定 commit**): **rc=0・所要 142 s (12:31:58〜12:34:20 実測)・7/7 完了・終了時 load average 0.91**。`drops_510.tsv` と `spill178_1161.tsv` は `results/` と一致 (cmp OK)。step 6 のネガティブコントロール NC0〜NC7 は 8 件とも完了。`ld109_cf3790_verify.py --check` も rc=0。
- step 7 の集計 (基準は origin/main の `spill178_1161.tsv`): status 未判定 117 → **102** / 確定 54 → **69** / 判定不能 7 → 7。増分は本 PR の 15 site のみ。`cf3790` の未判定は 0 件 (`results/spill178_1161.tsv` の cf3790 行 24 件のうち status=未判定 0)。
- 脱落関数の和集合は 69 のまま変わらない (cf3790 は既判定の TRUE_DROP 6 件で既に入っている。`[6] 確定 TRUE_DROP 関数 18 のうち drops_510 に無いもの: 無し`)。

## 3. slot 名の式の訂正 (ld105_reg2mem_map.py)

- 誤: 機械語 `[rbp+disp]` ↔ IR `stack_var_-(disp+8)`。正: **`stack_var_(disp - 0x1d8)`**。
- 根拠: retdec の `stack_var_N` は関数入口 rsp 基準。cf3790 の prologue は `push rbp/rdi/rsi/rbx` (32 B) + `sub rsp,0x1b8` + `mov rbp,rsp` で、`rbp` = 入口 rsp − 0x1d8 (472)。独立確認 (`ld109_cf3790_verify.py` の冒頭): `[rbp+0x48]=0` ↔ IR `store i64 0, ptr %stack_var_-400` / `[rbp+0x188]=0` ↔ `store ptr null, ptr %stack_var_-80`。既判定の cf387f (`[rbp+0x138]`) も `stack_var_-160.0.reg2mem` に対応する。
- 同じ訂正と検証は REPORT_2389.md §1 (`ld110_reg2mem_link.py`・プロローグの 0 初期化 store 8/8 対応) が先に行っている。本 PR の独立確認 (上記 2 点) は同じ式に至った。
- 影響: 旧表の cf3b03 は `stack_var_-280` (正しくは `[rbp+0xc0]` = cf3e08 の slot) を見ており、`ir_reload_use` に別の site の消費者 (`function_43a820` の呼び出し) が出ていた。issue 本文の「cf3b54・cf3c0e・cf3dfa・cf3e7a は alloca が無い」は式の誤りによる見かけで、正しい式では alloca の有無は §4 の表のとおり (alloca が無い 9 site は mem2reg で SSA 値に昇格済みで、phi が無く reg2mem の alloca が作られていないだけ。値は SSA 名で追える)。

## 4. 判定 (15 site・全て OK_LOAD)

IR の SSA 名は `function_cf3790` (`boot_final3.ll` 401631 行〜) のもの。絶対行番号と機械語の命令列は `candidate_verdicts_1161.jsonl` の evidence を参照。

| site | 機械語の store する値 ([rbp+disp] = stack_var) | IR の deref (SSA 名) | reg2mem alloca | 主な IR 消費者 |
|---|---|---|---|---|
| cf3b03 | cf3af5 の値の複製 (0x110 = -200) | `%89 = load %59` | あり | `icmp eq` / `add -8` / SetLength 引数 `%96` |
| cf3b54 | SetLength 後の `*E` (0x108 = -208) | `%.pre11 = load %59` | なし | `icmp eq` / `store → .reg2mem` |
| cf3b62 | cf3b54 の複製 (0x100 = -216) | `%.pre11` | あり | `%99 = add -8` → `%102` / `%103` で E2 を作る |
| cf3baf | `*E2` (0xf8 = -224) | `%106 = load %105` | なし | `icmp eq` / `add -8` |
| cf3bbd | cf3baf の複製 (0xf0 = -232) | `%106` | あり | `%111` → SetLength 引数 |
| cf3c0e | SetLength 後の `*E2` (0xe8 = -240) | `%113 = load %105` | なし | `icmp eq` / `add -8` / `add -4` |
| cf3c1c | cf3c0e の複製 (0xe0 = -248) | `%113` | あり | `%118` → `store i32 %67` |
| cf3dfa | `*E3` (0xc8 = -272) | `%168 = load %167` | なし | `icmp eq` / `add -8` |
| cf3e08 | cf3dfa の複製 (0xc0 = -280) | `%168` | あり | `function_43a820(.., reload, 0)` |
| cf3e7a | 再 `*E3` (0xb8 = -288) | `%179 = load %167` | なし | `icmp eq` / `add -8` |
| cf3e88 | cf3e7a の複製 (0xb0 = -296) | `%179` | なし | `%183` → `add -1` → `icmp slt` |
| cf3f47 | `*E4` (0xa8 = -304) | `%198 = load %197` | なし | `icmp eq` / `add -8` / `.reg2mem24` |
| cf3f55 | cf3f47 の複製 (0xa0 = -312) | `%198` | なし | `%202` → `add -1` / `rdi.0.in` |
| cf3fd3 | 再 `*E4` (0x98 = -320) | `%215 = load %197` | なし | `icmp eq` / `add -8` |
| cf3fe1 | cf3fd3 の複製 (0x90 = -328) | `%215` | あり | `%220 = add reload, -1` → `icmp sgt` |

- E = `[rbp+0x178]`・E2 = `[rbp+0x168]`・E3 = `[rbp+0x160]`・E4 = `[rbp+0x150]` は、機械語では動的配列の要素アドレス (入れ子の配列参照)。cf3b45・cf3bff の `call 417fc0` は引数 (配列変数のアドレス・型情報・次元 1・新しい長さ) から SetLength 相当、cf3e36 の `call 43a820` は引数が Length の整数→文字列化と読める。
- 「複製」の site は、直前の site の値を読み戻して別 slot に写し、その slot を `cmp 0` → `[rax-8]` (Length) で上書きする。このため複製側の slot が phi になり reg2mem の alloca が作られる (表の「あり」の 6 site は全て複製側)。複製側でも cf3e88・cf3f55 は Length が `rsi.0.in`・`rdi.0.in` 名の reg2mem に入り、stack_var 名の alloca は無い。SetLength を跨ぐ再 load (cf3b54・cf3c0e・cf3e7a・cf3fd3) は IR でも call の後に load が置かれている (`ld109_cf3790_verify.py` が行の前後関係を検査)。
- SetLength を通らない経路 (cf3adb→cf3b73) では call が無く、同値の `%89` を `.reg2mem` 経由で使う (IR で確認)。

## 5. 注意: OK_LOAD でも基底は汚染されている (既判定の脱落が上流にある)

- OK_LOAD は「**当 site の deref が IR にある**」ことだけを示す。アドレスの基底は上流で脱落した値から作られている:
  - E 系 7 site (cf3b03〜cf3c1c): `%59` ← `%52 = %51 + %50`・`%51 = %36 - 16`。`%36` は機械語 cf3932〜cf394e の slot 0x15E06F8 の 1 段 deref (cf3939 `mov rax,[rax]`) が無い cf390f の脱落値。
  - E3 系 8 site (cf3dfa〜cf3fe1): `%167` ← `%159` ← `.reload23` ← `%145`。`%145` は cf3d73〜cf3d8b の同じ deref (cf3d7a) が無い cf3d20 の脱落値。
- したがって cf3790 は、15 site の判定とは別に、cf390f・cf3d20 が TRUE_DROP のまま (修復されるまで) 下流の要素アドレスが誤る。これは cf3af5 の既判定 (OK_LOAD・「基底が別途汚染」) と同じ扱い。本 PR の判定で TRUE_DROP の集合は変わらない。汚染が実行時に値を誤らせるかは動的には未確認 (§6)。

## 6. 再現

- `M11_WORK=<work-m11> python3 tools/m11/ldfix/ld109_cf3790_verify.py` → 機械語 15 site の命令列と IR アンカー 70 行を検証して 15 行を出力 (`--check` で `candidate_verdicts_1161.jsonl` と一致検査・一致で rc=0)。
- `M11_WORK=<work-m11> python3 tools/m11/ldfix/ld105_reg2mem_map.py` → `results/ld105_reg2mem_map.tsv` (式の訂正後)。
- ネガティブコントロール (検証スクリプトが改変を検出すること): NC-a `boot_final3.ll` の `%.pre11 = load i64, ptr %59` を `add i64 0, 0` に差し替えた IR → `IR アンカー ... が 0 行に一致` で rc=1。NC-b スクリプトの期待機械語 `cf3b54 mov [rbp+0x108],rax` を `0x109` に変えた版 → `機械語不一致 cf3b54` で rc=1。
- 未実施: 判定は **静的な突合** (機械語と IR の構造) で、動的実行 (liftdiff 等) では確かめていない。15 site とも oracle 列は `-` (cell oracle の対象外)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| c589b0・128f9e0 の未判定 24 site | spill 宛の未判定が残る (全体で 102 site) | #2288 (LD-104) |
