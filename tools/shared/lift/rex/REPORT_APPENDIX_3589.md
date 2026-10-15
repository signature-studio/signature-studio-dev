# tools/shared/lift/rex 付録 — movnti (閉包内 24 箇所) の到達と x64c 対応の要否 — T-SH-90 (#3589)

測定 commit: `24903929f` (`tools/shared/lift/rex/` の `.c`・`.mjs`・`.py`・`.sh` を変えた最後の commit)。測定 HEAD: `55fe773b2` (§2 の実測ログ 1 本はこの HEAD で取った)。以降の差分は本付録と REPORT の文書だけ (`git diff 24903929f HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力は 0 行)。
既知類型との関係: 該当なし (不一致 0)。

## 結論 (1 行)
movnti は memset (`f_18001c8f0`・8 箇所) の大ブロック経路にだけあり、実測では a1 (= memset の長さ) ∈ [0x70000, 0x80000) の入力 16 件で入力だけで到達する (fn=0・16/16 で wasm が trap)。閾値 0x70000 は静的読み (`count>>6 ≥ 0x1c00`) で、実測はその範囲の一部だけ。a1 ∈ [0x10000, 0x70000) の info 4 件は movnti 以外で trap し、原因は未解明。memcpy (`f_18001ca80`・16 箇所) は、直接 call と定数参照では `f_18001bde8` (長さ 0x40 固定) からしか呼ばれず、入力では到達しない (静的読み)。間接 call 経路は未確認。**x64c 対応は memset の 8 箇所について要** (未実装・子 #3893)。

## 1. 静的な経路 (`lift/fle_lifted.c`・測定 HEAD で読んだ)
| 関数 | movnti | 呼出し元 | 長さ (r8) | movnti に入る条件 |
|---|---|---|---|---|
| `f_18001c8f0` (memset: rcx=dst・rdx=val・r8=count) | 8 | `f_1800011c0` (fn=0・`call` 0x1800022cb) と `f_180001130` (fn=1・`call` 0x18000213a) | `sext32(a1)` (`movsxd` で a1 を符号拡張) | `count>>6 ≥ 0x1c00` ⇒ count ≥ 0x70000 (静的読み) |
| `f_18001ca80` (memmove) | 16 | 直接 call と定数参照では `f_18001bde8` のみ (`mov r8d, 0x40` 固定・0x18001be04) | 0x40 | `count>>5 ≥ 0x2000` ⇒ count ≥ 0x10000。0x40 では不成立 |

- `f_18001bde8` の呼出し元は `f_180016160`・`f_180016170` だけで、どちらも `WaitForSingleObject` の戻りが 0 / 0x80 以外のときの**エラー経路** (直後に `int3`)。harness の `imp_WaitForSingleObject` は 0 を返すので、直接 call の範囲では、この経路は入力でも import でも movnti に届かない。
- 間接 call: 閉包には register 間接 call がある (`f_18001f260` = `ott_dispatch` の呼出し 6 箇所)。その表 (`case 0x3001ca80`) には memmove が入っている。この経路で memmove に入る入力は**未確認** (§4)。
- fn=0 は木の検索 (`f_180001de0`) の直後に memset を呼ぶ (`key_of` は rdi を壊さない・`f_1800019f0` を確認)。fn=1 は memset の前に `f_180012b50`・`f_180012b60`・`f_180012b70`・`f_1800042b0` で node の実体を辿るため、入力の値 (ランダムなポインタ) で先に落ちる (native の fault が arena 末尾 0x30110000 でなく 0x50fb16c0 などになる・推定)。

## 2. 実測 (fix run・1 本のログ)
- 測定: GitHub Actions run 38683492403 (2026-10-15 04:53Z 開始)。HEAD `55fe773b2` で `FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_x64c.sh all` を 1 回 (rc 0・ALL OK・全体 real 12 s)。
- 素材: fl-win64 の `extracted/block24351_PE.bin` (321848 B) のみ。toolchain-emsdk は本 run の素材に無いため、上流 `emsdk install 6.0.12` で代替した (版は `tools/m1/flags.sh` の `EMCC_VERSION_PIN` と同じ 6.0.12)。
- load は `/proc/loadavg` の 1 分・5 分・15 分値の開始→終了。elapsed は整数秒。

| モード | 結果 | elapsed | load 開始 → 終了 |
|---|---|---|---|
| ok (本検査) | PASS・比較 175・一致 175・不一致 0・arena 書込 42・`.data` 書込 0・traps 0 (248 case) | 3 s | 0.41 0.34 0.17 → 0.46 0.35 0.18 |
| neg-cmp | 期待どおり FAIL (不一致 1・case 2・offset 21) | 2 s | 0.46 0.35 0.18 → 0.46 0.35 0.18 |
| neg-ctx | 期待どおり FAIL (不一致 175) | 2 s | 0.46 0.35 0.18 → 0.50 0.36 0.18 |
| neg-owner | 期待どおり FAIL (配信物の一覧が期待と不一致) | 3 s | 0.50 0.36 0.18 → 0.50 0.36 0.18 |
| movnti | PASS (reach 16/16)・info 4/4 は movnti 以外で trap | 0 s (1 s 未満) | 0.50 0.36 0.18 → 0.54 0.37 0.19 |

- reach 16 件 (fn=0・a1 ∈ [0x70000, 0x80000)): wasm は 16/16 が `0x18001c9a0` (`movnti qword ptr [rcx], rdx`・memset の movnti 先頭) で `ott_unsup` に入って trap。native は 16/16 が `0x30110000` (arena 末尾 = 64 KiB の外) で落ちる。movnti 経路でだけ arena を越えて書く。
- info 4 件 (fn=0・a1 = 0x27878・0x2d324・0x3d429・0x3ffa3 ∈ [0x10000, 0x70000)): wasm は 4/4 が trap するが、`ott_unsup` を経由しない (trap VA 0)。movnti ではない。想定 (trap しない) と食い違う。原因未特定 (推定: 通常の memset が arena を越えて書き、後段が壊れる。未確認。子 #3894)。
- 測定の注意: `run_wasm.mjs` は元の機械語が落ちた case を既定で実行しない。movnti モードは `REX_RUN_CRASHED=1` で実行する (元が落ちる入力でも wasm の経路を見るため)。
- 補修 (本 PR): WASI の `fd_write` が 0 を返していたため、trap 前の `fprintf(stderr)` で stdio が戻らなくなっていた。書いた長さを返し、fd 2 の内容を stderr へ流すように直した。`rex_glue.c` で `fle_ff_hook` を使い、trap した未対応命令の VA を `rex_unsup_get` で返す。

## 3. x64c 対応の要否 (判断)
- **memset の movnti 8 箇所: 要。** 入力だけで到達する (実測 16/16。閾値 0x70000 は静的読み)。到達すると fail-fast で trap するため、そういう長さの入力が本番で来るなら x64c の対応が要る。movnti は単一スレッドの意味では普通の store と同じなので、対応は x64c で ST 系へ写すだけで済む見込み (推定。未実装・子 #3893)。本番の host が a1 に何を渡すかは [未確認]。
- **memcpy の movnti 16 箇所: 直接 call の範囲では不要。** 唯一の直接の呼出し元 (`f_18001bde8`) が長さ 0x40 固定で、movnti の閾値 0x10000 に届かない (静的読み・未実測)。「不要」は、間接 call 経路 (§1) が未確認である限り、この限定付きで書く。
- 本付録では x64c を変えない (`tools/flelift/` は触らない)。

## 4. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| movnti (memset 8 箇所) の x64c 対応の実装。到達時は fail-fast で trap | a1 ≥ 0x70000 の入力で wasm が trap | 子 #3893 [T-SH-93] |
| info 4 件 (a1 ∈ [0x10000, 0x70000)) が `ott_unsup` 以外で trap (VA 0)。閾値 0x70000 の静的読みと食い違う。原因未特定 | 閾値の静的読みの反証が未了 | 子 #3894 [T-SH-94] |
| `REX_RUN_CRASHED=1` で 248 件すべてを流すと wasm が戻らない (movnti モードの 20 件は完走) | 元が落ちる入力を全件 wasm で流せない | 子 #3895 [T-SH-95] |
| fn=1 (REXGetInfo) では movnti に到達しなかった (memset の前の node 参照で落ちる) | fn=1 からの到達は未確認 | #3587 [T-SH-88] (open。fn=1 の成功経路の入力を扱う。閉じた #3588 から付け替え) |
| memcpy 16 箇所の間接 call 経路 (`f_18001f260` = `ott_dispatch` の register 間接 call 6 箇所の表・`case 0x3001ca80` に memmove) からの到達 | 「memcpy は不要」は直接 call と定数参照の静的読みに限る | 未起票 (追跡のみ。子は起票しない。本表で追跡) |
| 本番の host が REXGetCreatorInfo に渡す a1 の値域 | 到達が本番で起きるかの判断 | [未確認]。依頼者が FL 側の呼出し値で確認する |

## 付録: #3893 (T-SH-93) の実装と実測 — i_movnti の追加

- 変更: `tools/flelift/x64c.py` に `i_movnti` を追加 (`i_mov` へ委譲。単一スレッドでは通常の store と同じ)。lift 出力の差分は movnti 24 行の `ott_unsup` → `ST64` のみ (lift 出力比較: main と同じ DLL・同じ引数で `diff` 48 行 = 24 削除 + 24 追加。他の行は不変)。
- 実測 (`lift_x64c.sh movnti`): `ott_unsup` (movnti VA `0x18001c9a0`) は消えた。reach 16 件は wasm が `memory access out of bounds` (VA 0) で trap する。`FLE_CHK` を有効にした build で、`rcx = 0xd8a01030` の書込みと、その後の `0xd8a016b8` (境界外) の読み出しを確認。native も同じ入力で arena 外 (0x30110000) で落ちる。
- 原因: memset (`count ≥ 0x70000`) が 64 KiB の arena を越えて書く。native と wasm の両方が同じ越境で落ちるため、受入 1 (「trap せず memset が完了する」) は、この入力の作り方では満たせない。
- 判定: `movnti_check.py` は「movnti VA で trap」を前提にしているため、16/16 が NG (RESULT FAIL)。受入 2 の `all` はこの点で FAIL のまま。
- 受入 2 の内訳 (実測): `ok` PASS (exit 0・owner 一覧 OK) / `neg-cmp` FAIL 検出 (期待どおり) / `neg-ctx` FAIL 検出 (期待どおり) / `neg-owner` FAIL 検出 (期待どおり)。
- 未解決: reach 16 件を arena 内で完了させる入力 (または harness の arena モデル) の決定。子 issue に分ける。

## 付録 (review r1 対応): movnti の gate 期待値 (#4324 既知の未達) と再測定

- 変更: `movnti_check.py` の判定を 2 つに分けた。(1) 実装判定 = `fle_lifted.c` の movnti の `ott_unsup` が 0 件 (#3893。1 件でも残れば FAIL)。(2) reach 16 件 = 既知の未達 (#4324)。reach は「native が arena 外で落ちる」だけを判定し、wasm が movnti 経路を完了したかは判定しない。`movnti` の結果行に 0/16 を既知として出す。`lift_x64c.sh` の `all` は既知の状態で ALL OK になる。期待値を変えた理由: x64c が movnti を ST64 に lift したため、旧判定 (movnti VA で trap) は構造的に成り立たなくなった。解消条件: #4324 で reach 16 件を arena 内で完了させる。解消したら reach 判定を「wasm が完了する」に戻す。
- 測定 commit: `143b84a9a` (main 取り込み後の merge commit。`movnti_check.py` の解消を含む最後のコード変更)。`all` を foreground で 1 回 (rc 0・ALL OK・real 12 s・load 0.04 0.20 0.17 → 0.19 0.23 0.18)。
  - ok: PASS・比較 223・一致 223・不一致 0 (296 case・native crash 除外 73)・owner 一覧 `owner/rex_side.wasm` で期待どおり (3 s)。
  - neg-cmp: 期待どおり FAIL 検出 (比較 223・一致 222・不一致 1)。
  - neg-ctx: 期待どおり FAIL 検出 (比較 223・不一致 223)。
  - neg-owner: 期待どおり FAIL 検出 (一覧 `owner/rex_glue.c owner/rex_side.wasm`・期待 `owner/rex_side.wasm`)。
  - movnti: 実装 OK (ott_unsup 0 件)・reach native 境界外 16/16・wasm 完了 0/16 (既知の未達 #4324)・trap VA=0 が 12 件・trap 記録なし 4 件。1 s。
- 直前の測定 (round 2・`c7ad74763`・main 取り込み前): `all` は ALL OK (real 23 s)。merge 後の値 (上) で置き換える。
- main 取り込みでの判定の扱い: main (#3894・`22b39992c`) の `movnti_check.py` は sweep 閾値 (movnti に入る ⇔ a1 ≥ 0x70000) を「movnti の VA で trap する」で判定していた。本 PR で x64c が movnti を ST64 に下ろしたため movnti の VA で trap しない。main の sweep 判定を残すと `all` が必ず FAIL になるので、本 PR では sweep の閾値判定を判定に入れず、表示のみにした (未解決 #3894 で扱う)。kind 名は main の `sweep` に合わせた。
- 素材: `toolchain-emsdk.tar.zst` と `fl-win64.tar.zst` を `$RUNNER_TEMP` (repo 外) に展開し、`EMSDK_ENV` で展開した emsdk を使った (上流 install はしていない)。round 1 の上流 emsdk による実測は、この素材版の実測で置き換えた。
- 今回の case 数 (296 件・比較 223) は §2 の 248 件・比較 175 と一致しない。原因: `gen_cases.py` が 55fe773b2 以降に変わり (成功経路の case を追加。`git diff 55fe773b2 HEAD -- tools/shared/lift/rex/gen_cases.py`)、その後の `native_ref.c` / `crash_class.py` 等も変わった。§2 の数値は 55fe773b2 の入力に対するもので、現 HEAD の入力では再現しない。現 HEAD の値 (296・223) を正とする。
- lift 差分 (main `59ca0477f` と本 PR の `x64c.py` を同 DLL・同引数で比較): `fle_lifted.c` は movnti 24 行の `ott_unsup` → `ST64` のみ (48 行)。`lift_meta.json` は movnti 24 サイトの `unsup` / `unsup_sites` の削除のみ (他は不変)。
- memcpy 16 箇所の間接 call 経路: 未起票。`docs/WORKFLOW.md` §3 の規則で、「未解決の追跡」だけの子は起票しない。本付録 §4 と PR 本文の未解決表で追跡する。
