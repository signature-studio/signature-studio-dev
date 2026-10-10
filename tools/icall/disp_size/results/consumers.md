# capstone disp 依存コード棚卸し (consumers.py, 自動生成)

| 区分 | 意味 | ファイル数 | 補正要否 |
|---|---|--:|---|
| A | `disp_size`/`disp_offset` を読む | 3 | **要** (D9 直接被害) |
| B | `imm_offset`/`imm_size`/`modrm_offset` を読む | 7 | 否 (実測で誤り 0) |
| C | `mem.disp` 値のみ (rip target 等) | 43 | 否 (値は全 case 正) |

## 区分 A (disp_size / disp_offset)

| ファイル | 行 |
|---|---|
| `tools/icall/tests/test_icall.py` | 43 |
| `tools/plugins/framework/fw_prep.py` | 71, 74 |
| `tools/plugins/inventory/win_funcs.py` | 33 |

## 区分 B (imm_* / modrm_offset)

| ファイル | 行 |
|---|---|
| `tools/icall/icall_rewrite.py` | 103, 124, 335, 692 |
| `tools/plugins/framework/fw_prep.py` | 61, 64, 66, 69 |
| `tools/plugins/inventory/fw_overlap.py` | 50, 51 |
| `tools/plugins/inventory/mac_funcs.py` | 102, 105 |
| `tools/plugins/inventory/win_funcs.py` | 119, 122, 127, 130 |
| `tools/plugins/p0c/kernel_matrix.py` | 55, 56 |
| `tools/plugins/p0c/verify_table.py` | 71, 73, 77, 78, 81, 82 |

## 区分 C (mem.disp 値のみ) — ファイル一覧

`tools/flelift/probe_d9_disp.py`, `tools/flelift/x64c.py`, `tools/icall/audit_icall.py`, `tools/icall/icall_rewrite.py`, `tools/icall/landing/gap_fragments.py`, `tools/icall/landing/ott_extract.py`, `tools/ipp/scan_x64.py`, `tools/ipp/shim/sigscan.py`, `tools/liftdiff/ldlib/pe.py`, `tools/liftdiff/ldlib/session.py`, `tools/liftlib/liftlib/mc.py`, `tools/m11/ldfix/ldfix.py`, `tools/m11/ldfix/ldmach.py`, `tools/m2/delphi_scan.py`, `tools/m5/dump_dis.py`, `tools/m5/scan_pure.py`, `tools/m6/ottlib.py`, `tools/ott/lift/x64c.py`, `tools/plugins/framework/fw_prep.py`, `tools/plugins/inventory/host_calls.py`, `tools/plugins/inventory/kernel_table.py`, `tools/plugins/inventory/win_abi.py`, `tools/plugins/inventory/win_funcs.py`, `tools/plugins/lift/plugin_closure.py`, `tools/plugins/p0c/f80_assess.py`, `tools/plugins/p0c/k80abi.py`, `tools/plugins/p0c/kernel_matrix.py`, `tools/shared/scripts/ipp_mac_validate.py`, `tools/shared/scripts/ipp_win_validate.py`, `tools/startup/scripts/pedis.py`, `tools/targets/freshair/closure.py`, `tools/targets/freshair/lift2/dis_annot.py`, `tools/targets/freshair/lift2/mlift/mlift.py`, `tools/targets/freshair/lift2/mlift/mlift_ops.py`, `tools/targets/kilohearts/license/lift/khmach.py`, `tools/targets/kilohearts/license/scripts/f1088.py`, `tools/targets/kilohearts/license/scripts/xrefscan.py`, `tools/targets/kilohearts/snapins/lift/khmach.py`, `tools/targets/serum2/license/scripts/authmap.py`, `tools/targets/serum2/scripts/blob_refs.py`, `tools/targets/serum2/scripts/disasm_fn.py`, `tools/targets/serum2/scripts/dsp_closure.py`, `tools/targets/serum2/scripts/xref_scan.py`
