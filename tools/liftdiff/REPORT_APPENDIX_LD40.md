# LD-40 (#1199): fvm の VMT slot 解決 (#975 残り)

親: #975 (LD-23) の REPORT_APPENDIX §12.1。本節は設計の事前確認と、このラン時点の未達を記録する。

## 1. 現状 (測定済み)

- 基準 (origin/main `481eb2d7`・`liftdiff_e2e.sh --m11-only`): PASS・exit 0。
  sample:800 で 一致 360 / 不一致 230 / 実行不能 210。batch 95s (`--shards 12`・4 vCPU・load は未採取)。
- fvm 追加 (`0596772f`) の既存 REPORT §12.1 の実測 (fvm 437 件 = native_fault 193 / both_fault 243 / hang 1) は
  1 件も equal/diff/wasm_trap にならない。受入条件 (2) は未達のまま。

## 2. 既存コードで確認した事実 (設計の入力)

- native (`rt/ld_native.c` `ld_fake_ptr`): `LD_FAKEPROC_BASE` (0x50010000) に実行可能 thunk を mmap し、
  `mov r10, MARK|i; mov r11, ld_stub_common; jmp r11` で `ld_stub` へ戻す。
- wasm (`rt/ld_wasm.c`・`rt/fle_ldbridge.c`): `ld_fake_ptr` は値 (`LD_FAKEPROC_BASE + i*SZ`) のみ。
  `ott_dispatch` (fle_ldbridge.c) が同じ番地への dispatch を `ld_stub` に振り向ける。
  未登録 index は `ott_unlifted` (ret 0) に落ちる。
- つまり「VMT slot に仮 proc (`ld_fakeproc_get` 由来の番地) を置く」は、native・wasm 両側で同じ解決先を指せる。
  ただし fvm の VMT 本体は現在 0 埋め (`cases.make_blob_vm`) で、slot の内容は未設定。

## 3. 未達 (このランで実装しなかった理由)

- VMT slot への書き込みは `cases.make_blob_vm` / `fvm_line` と、case 生成時の仮 proc 登録
  (`ld_fakeproc_get` は native 側の `ld_stub` 名解決を要する) の両方に入る。
  両ランナ (native/wasm) の再ビルドと sample:800 の再測定 (1 回約 3 分) を伴い、
  この run の 60 分上限内で設計・実装・実測・記録を完結させる見込みが立たなかった。
- 受入条件 (1)(2)(3) は未達。残りは子 issue として分割起票する (§4)。

## 4. 残り (子 issue)

- 子 issue: #1398 ([LD-48])。
- 受入条件: VMT slot に仮 proc を置く実装、fvm case の outcome 件数を sample:800 で実測し REPORT_APPENDIX §12.1 に記録、既存 pattern の増減の理由記録。
- 必要素材: `oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff`
