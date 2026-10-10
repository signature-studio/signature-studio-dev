# KH-10 — EditorModel 層部分 lift (poll/EventSlot) — スナップイン「編集可能」成立の wasm 実証 (CAB-247 / 親 CAB-59)

- 解析日: 2026-10-10 / 担当 dir: `tools/targets/kilohearts/license/` (本報告は `KH10_REPORT.md`。CAB-59 `REPORT.md` §9 に追記のみ)
- 1 コマンド再現: `bash tools/targets/kilohearts/license/run_all.sh` ([4] 節が本チケット分 / 全体 ≈ 6 分)
- 対象: `work/winpkg/HeartCore.core_64` (76,642,304 B, ImageBase 0x180000000)

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| lift | **25 関数** (module E): EditorModel ctor 0x180051af0 + poll1/poll2 (0x180052830/0x180052a00) + EventSlot/property 機構 8 + 分類 thunk 5 種と状態マージ (**実 IR** — KH-9 module B の検証を本 closure 内で再実証) + **+0x1088 writer 0x18002e850** + 補助 7。wasm **142,363 B** (emcc -O0), undefined import 0 種 (env.exit のみ=標準) |
| wasm 実証 | **47/47 製品が「編集可能」として成立** (`em_check.mjs` ok=50 ng=0): ctor → 不変式 8 項目 → poll2 で [+0x548]=1 (編集可) / [+0x5c8]=1 (dirty) / [+0x550] 更新、poll1 も同一結果 |
| native oracle | **実機機械語との ctx-fuzz bit-exact**: ctor+poll1+poll2+writer **200/200 trial (700/700 call)**、状態注入 sweep **1000/1000 trial (10,000/10,000 call)**。arénna ms_abi 方式 (実 PE を 0x180000000 に敷設, アリーナ 0x04000000, image パッチで stub seam を両系一致) |
| +0x1088 解明 | **書込側 3 系統を特定** (§3): (1) **0x18002e850** — 47 製品の「エディタ文書」ctor 0x18002dc30 が EM+0x1b0 に登録するコールバックで、poll1 冒頭 `FUN_180022be0(EM+0x1b0)` から起火。**thunkB(status) (mask {5,7,8,26}) 成立時に 0 を書く**。(2) 0x1800f6540 — `[+0x1088] = !thunkA(status)`。(3) 0x18068f750/930/a00 — 汎用 property setter。**getStatus≡9 では全系統が 0 を書くか不発 → flag は 0 を保ち編集可が成立** (wasm で (1) の不発と flag=1 消費を含め実証) |
| 回帰 | lic_check **70/70** / license run_all.sh **exit=0** / snapin 6 種 base・lic とも **200/200** (quickeq wasm +4B は §5-6 の shim 改善によるもの) |

## 1. lift 関数表 (module E, 25 関数)

| VA | size | 役割 | 備考 |
|---|--:|---|---|
| 0x180051af0 | 1304 | **EditorModel ctor** (47 製品から呼ばれる共通初期化) | スタック引数 3 個 (param_5/6/7) — kh_lower を拡張して対応 (§4) |
| 0x180052830 | 33 | **poll1**: LicenseManager EventSlot (mgr+0x20) 登録コールバック。冒頭で `0x180022be0(EM+0x1b0)` 起火 | |
| 0x180052a00 | 300 | **poll2**: 47 ctor から直接呼出 (唯一のライセンス消費)。editable = thunkA(status) && [sub+0x1088]==0 → property 更新 | |
| 0x18003d650 / 0x18003d7e0 | 301 / 321 | property set + 変更通知 (observer ループ, 本 closure では空 vector で冷間) | |
| 0x180022be0 | 256 | slot 起火 (0x50/0x58 stride の observer 走査) | |
| 0x1800c6270 / 0x1800c6320 / 0x1800c6530 | 83 / 119 / 279 | property manager (PM+0xd10) の guard begin/end/compact | |
| 0x18001e440 / 0x18000d400 | 328 / 328 | vector compact (dirty flag ゲート, 冷間) | |
| 0x1800b4ac0..b00 | 16..7 | **分類 thunk 5 種 — 実 IR** (stub でない) | getStatus≡9 を入力に実行 |
| 0x1800b4b10 | 157 | **状態マージ — 実 IR** (29 エントリ優先度テーブル) | |
| 0x18002e850 | 229 | **+0x1088 writer** (§3) | |
| 0x1800b20e0 / 0x18001ba90 | 8 / 5 | PM+0xd10 / shared_ptr+8 thunk | |
| 0x180054b90 | 54 | getStatus 束縛 wrapper (尾跳び → stage-0 で call+ret 形に lower) | |
| 0x1800524e0 / 0x18000caf0 | 333 / 239 | 製品 descriptor copy (std::string SSO/heap 両経路) | |
| 0x18006be60 / 0x18006f270 | 89 / 116 | base ctor / sub-object 初期化 | |

stub seam (lift 外, C 実装): getStatus 0x180054bd0 (**retderef** — アリーナ 0x04000008 の status セルを読む = 状態注入点) / key_init 0x180021490 / apply_key 0x1800219b0 (lic_config.json の lic_stub) / getManager 0x180107430 (fake mgr {0x0400F000, NULL}) / **subscribe 0x1800526f0 (no-op — §5-2)** / operator new 0x180f878e0・delete 0x180f8791c (**アリーナ bump** — カーソルはアリーナ先頭 qword, シナリオが trial 冒頭で設定) / memset 0x1813846e0・memcpy 0x181384040 (C 実装)。EH 系 (0x180005c30/c50, 0x180f88468, 0x180fb5f5c) と vector compact 内部 (0x18001e5d0/e730/e840, 0x18000d590/d700/d840) は fail-fast stub (冷間 path のみ)。

## 2. wasm 実証と ctx-fuzz (`em_check.mjs` + `harness/scen_em.h`)

### 2.1 47 製品デモ (`em_check.mjs`, ok=50 / ng=0)
`work/ctors47.json` の 47 呼出元に対応する 47 組の (製品パラメタ 16 u32, descriptor 5 文字列, kind 9 種, apply gate) を合成し、ctor → 不変式検証 (vtable 0x1813af778 生値 / sub=param_3 / kind / PM / desc copy / helper {state,found}) → poll2 → **[+0x548]=1 (編集可)・[+0x5c8]=1** を 47/47 で確認。apply gate=1 の 5 製品は apply_key により状態が 0x17→0x1a になることも検証。poll1 も同一の値に更新。

### 2.2 ctx-fuzz (native oracle)
方式: 実 PE を ImageBase に敷設し (RWX)、アリーナ 0x04000000 に EM/SUB/property manager/desc を構築して ms_abi 直接実行。**stub seam は native 側も image パッチで同一動作**にした (getStatus=`mov eax,[0x04000008]; ret`、key_init/apply_key/getManager は 0x05000000 の code cave へ `movabs r11,addr; jmp r11` で接続、new は同じ bump 式の naked asm)。中間命令レベルで「lift 側 C shim ≡ native パッチ」を保証する。

| scenario | trial | call 内訳 | 結果 |
|---|--:|---|---|
| `em` | 200 | ctor 200 + poll1 200 + poll2 200 + writer 100 | **200/200 bit-exact (700/700 call)** |
| `empoll` | 1000 | ctor 1000 + poll1 1000 + poll2 8000 | **1000/1000 bit-exact (10,000/10,000 call)** |

状態注入: status セル (0x04000008) を {0,5,7,8,9,13,22,25,26,40} から trial 毎に変化 (thunkA/B・マージの真理値表を両系で通過)、[sub+0x1088] = 0/1、[sub+0x548] cache、apply gate、文字列長 (SSO/heap 両経路) を乱数化。writer (0x18002e850) は X オブジェクト {[X+0x100]=EM} をアリーナに構築して直接呼出。

## 3. EditorModel+0x1088 (編集可否 flag) の解明

flag は **[EM+0x270] の sub-object (property bag) の +0x1088** にある。全 .text 走査 (capstone, `.pdata` 111,666 関数) で dword アクセス 72 関数のうち +0x1088 を扱うものを同定した (`scripts/f1088.py`)。

### 3.1 読み出し側 (消費者)
| VA | 意味 |
|---|---|
| 0x180052a00 / 0x180052830 (poll) | editable = **thunkA(status) && ([+0x1088]==0)** → [+0x548] cache / [+0x5c8] dirty / [+0x550] / 0x18003d650(sub+0x388) / 0x18003d7e0(sub+0x3c0) |
| 0x180c194f0 (banner, r15d @0x180c195fd/0x180c1962b) | `status==0x19 && [+0x1088]==0` → "You do not have a license ... can not be edited." + "No license." + padlock (0x180c1976d) |
| 0x180056db0 / 0x180057010 / 0x180057270 / 0x180057510 / 0x18023ad10 / 0x180631000 / 0x18068c8e0 / 0x18068d350 / 0x18068de80 / 0x18068ded0 / 0x1807164f0 / 0x180b6b070 / 0x180ce4230 | その他 UI/Editor 分岐 (lift 範囲外) |

### 3.2 書き込み側 (3 系統)
| VA | トリガ | 書込内容 |
|---|---|---|
| **0x18002e850** (229B) | **EM+0x1b0 callback list** に登録 ({0x18002e850, ctx=0})。登録者は「エディタ文書」オブジェクト ctor **0x18002dc30** (直接呼出 47 = EditorModel ctor 呼出元 47 と同数、機械語で `add rcx, [rdx+0x100]+0x1b0` を確認)。起火点は **poll1 冒頭 `FUN_180022be0(EM+0x1b0)`** | `EM=[X+0x100]` → getStatus wrapper 0x180054b90 → **thunkB (0x1800b4ad0, mask {5,7,8,26}=class 4) 成立時のみ** value=0 ([sub+0x1170] listener の vtbl+0x20 で上書き可能) → 変化あれば [+0x1088]=value, [+0x1108]=1, [+0x1090]=vtbl[0](), 0x18003d7e0(sub+0xf00, sub+0xec0, old, new, 2) |
| 0x1800f6540 (3926B) | editor content setup 系 (wrapper 0x180054b90 を 0x1800f6bea で呼ぶ) | **[+0x1088] = !thunkA(status)** (0x1800f6bfd `xor al,1`)。同じ通知形状 |
| 0x18068f750 / 0x18068f930 / 0x18068fa00 (445/194/263B) | 汎用 property setter ([X+0xc48] の property bag、値は [X+0xa0] 経由の vtable lookup) | [+0x1088] = 任意値 (同一通知形状) |

### 3.3 getStatus≡9 での帰結 (wasm 実証ずみ)
thunkB(9) = (0x40001a0>>9)&1 = **0** → writer (1) は不発、(2) は 0 を書く、(3) は経路外 → **+0x1088 は初期値 0 を保つ** → poll2 の editable = thunkA(9) && 1 = **1**。wasm で (a) writer 不発、(b) +0x1088=1 注入 → 編集不可 ([+0x548]=0)、(c) 0 解除 → 編集可復帰 (+dirty) を実証 (`em_check.mjs` [3])。banner は status 9 経路で "No license" 文面に到達しない (0x180c1976d の分岐は status==0x19 が前提)。

## 4. lift 基盤への追加 (すべて license/ 配下の自家コピーを拡張)
1. **kh_lower.py**: (a) wrapper の**スタック引数対応** (`--abi` の `"stack": [...]` → %sp1+0x28+8j に store。5th/6th/7th 引数 = callee entry rsp+0x28+8k と一致することを機械語で確認後修正)。(b) `--raw-va`: vtable/RTTI/関数ポインタの「値」store を生 VA 定数のまま残し native と byte 一致 (deref のみ窓へ。既定動作は変更なし = DSP closure に無影響)。(c) `--volatile-ret`: 本体末尾 `ret load @rax` を volatile 化 (下記 5 参照)。(d) ret i32 wrapper。
2. **lic_stub.py**: kind `retderef` (アリーナ固定セル i32 を読んで返す) と module 別 `stub_override` / `synth_zeroarg` (lift 済み呼出側は引数なし @rcx.. グローバル規約で呼ぶため synth wrapper をゼロ引数化 — module A/B は従来の 4 引数 wrapper を維持)。
3. **gen_stubs_sigs.py**: shim 種追加 (new/delete/memcpy/ident/getManager/subscribe) + **shim 本体の明示 `return rax;`** (return 省略の C 関数は clang が noreturn 扱いにして呼出側を切り捨てる — module E で発災)。
4. **ctx-fuzz harness**: `Frame` を int 8 引数 (+スタック引数 a4..a7) に拡張、`do_call`/`compare.mjs` を 8+4 形式へ (vec ファイル名は `_v3` に変更)、msx64_call はスタック引数を call 前 rsp+0x20+8k に store (callee entry +0x28+8k と一致)、xmm0-3 は新 Frame オフセット (64..88) から load。
5. **native oracle の image パッチ機構** (`scen_em.h`): `patch_jmp` (movabs r11 + jmp r11, 14B)、code cave @0x05000000 (RWX mmap)、`em_new_entry` (naked asm — **volatile GPR 全保存**。MSVC LTCG のコードは new 越しに rdi/rsi を生存させているため)。

## 5. 制限 / 本チケットで判明した基盤課題
1. **UI 表示系は lift 範囲外** (banner 0x180c194f0 / browser / import)。getStatus≡9 の正しさは KH-9 REPORT §3 の実測に依存。
2. **subscribe (0x1800526f0) と manager 登録は no-op seam**: 登録先は manager ヒープ (アリーナ外) で、functor 経路 (0x180024bd0/0x180025080) に stage-0 で落ちる間接 call (functor vtbl+8 clone @0x180024c26 等) があるため。**「LicenseManager 状態変化 → poll1 起火」の E2E は本チケットでは未解除** (poll1 自体の lift と起火機構 0x180022be0 は実証済み)。
3. **listener/observer ありの property 通知は未検証**: [sub+0x630]/[sub+0x1170] を null に固定 (間接 call が stage-0 で落ちるため)。observer ありの 0x18003d650/0x18003d7e0 ループは tools/icall (CAB-89) の復元 pass との統合が前提。
4. apply_key は stub seam ([rcx]=0x1a, rax=1)。実 0x1800219b0 の鍵検証経路は KH-9 から引き続き未検証。
5. **module E は emcc -O0**: -O1 では LLVM が (a) TailCallElim が `call; …; ret load(@rax)` を tail call 化して中間の副作用 (stub 呼出・property 更新) を削除し、(b) shim の return 省略が noreturn 推論を誘導して呼出側の後続を `unreachable` 化する。結果 wasm 実行が ctor 半ばで trap。`--volatile-ret` だけでは不十分で -O0 を採用 (正しさ優先・142KB)。-O1 復帰は KH-11 課題。
6. quickeq wasm が KH-9 REPORT から **+4B** (186,285→186,289 / 187,641→187,645): shim の明示 return 追加による。bit-exact 200/200 は維持。
7. 編集可否の「表示」(padlock/mute icon) と実際の Editor 起動可否の接続は UI 層 (M7 以降)。

## 6. KH-11 (CAB-248) への引継ぎ
1. **subscribe 経路の解除**: 0x180024bd0/0x180025080/0x18001bf70/0x18001c0b0 の lift + 間接 call 復元 (tools/icall 統合) または functor 経路の shim 設計 → 「LicenseManager 状態変化 → poll1 起火 → +0x548 更新」の通し E2E。
2. **listener/observer ありの通知** ([sub+0x630]/[sub+0x1170] 非 null、observer vector 非空) — 同じく icall 前提。
3. **0x1800f6540 (editor content setup) の lift** — `[+0x1088] = !thunkA(status)` の書込側 (2) を実機相当で実証。
4. module E の -O1 化 (TCE/DSE 対策の精査 — `musttail` 禁止 or副作用秘匿のIR構造)。
5. banner/UI の lift は M7 以降 ( getStatus≡9 → バナー解除 0x180130560 経路の実機確認は CAB-59 §6-6 と合流)。

## 7. 成果物
`lic_config.json` (module E 追加) / `lic_stub.py` (retderef + override + synth_zeroarg) / `lic_build.py` (module E の abi/shims/raw_va/volatile_ret/emcc_opt) / `lift/kh_lower.py` (stack args + raw_va + volatile_ret + ret i32) / `lift/gen_stubs_sigs.py` (shim 追加 + return rax) / `harness/{ctxfuzz.h,native_ref.c,compare.mjs,scen_em.h,scenarios.c,scen_clipper.h}` (8 引数 + EM scenario + image パッチ) / `em_check.mjs` (47 製品デモ) / `em_dbg.mjs` (デバッグ用リプレイ) / `scripts/{f1088.py,xrefscan.py,xrq.py}` (+0x1088 全走査・xref) / `run_all.sh` ([4] 追加) / `REPORT.md` §9 (追記)。`work/` (gitignore): em_stage0.ll / f1088.json / xrefscan*.json / licE / em_200_1.bin / empoll_1000_7.bin / native_ref。
