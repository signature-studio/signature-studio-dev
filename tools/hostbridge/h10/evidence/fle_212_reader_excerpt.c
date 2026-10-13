=== fle:0xf46490 (.fst/.flp plugin loader) — event 212 (0xd4) case, lines 2062..2322 of the decompile
          else if (iVar3 == 0xd4) {
            cVar2 = FUN_00f463e0(auStack_b38,0x34,0);
            if (cVar2 != '\0') {
              FUN_00415c30(local_b4,PTR_DAT_008ea970);
              (**(code **)PTR_DAT_015e0a48)(local_b4,0x1c);
              (**(code **)PTR_DAT_015e0a48)(&local_244,0x34);
              (**(code **)PTR_DAT_015e0030)
                        (*(undefined8 *)(*(longlong *)(param_1 + 0x4450) + 0x10002c),&local_244);
              if (*(longlong *)(*(longlong *)(param_1 + 0x4450) + 0x100024) < 0x15) {
                local_d8 = 1;
              }
              else {
                local_d8 = local_234;
              }
              if (DAT_016bac50 < 0x1e980a) {
                local_9c = (local_d8 & 0x10000) != 0;
              }
              else {
                local_9c = (char)local_23c;
              }
              local_f4 = local_23c;
              if (*(int *)(param_1 + 0x4488) == 0x30) {
                local_50 = *(longlong **)(param_1 + 0x4490);
              }
              else if (*(int *)(param_1 + 0x4488) == 0x20) {
                local_50 = (longlong *)0x0;
                if ((local_d8 & 0x10) == 0) {
                  *(undefined4 *)(param_1 + 0x445c) = 5;
                  DAT_016bac68 = 0x32;
                  if (((local_1c8 != (undefined1 *)0x0) && (*(longlong *)(param_1 + 0x4490) != 0))
                     && (cVar2 = FUN_0040fe90(*(undefined8 *)(param_1 + 0x4490),PTR_PTR_00fe2c30),
                        cVar2 != '\0')) {
                    local_538 = *(longlong *)(param_1 + 0x4490);
                    if (*(longlong *)(local_538 + 0x30) == 0) {
                      FUN_00414ec0(&local_938,local_1c8,1,4);
                      FUN_004394e0(&local_930,local_938);
                      iVar3 = FUN_00414e70(local_930,L"VFX ");
                      if (iVar3 == 0) {
                        *(undefined4 *)(param_1 + 0x4448) = 6;
                      }
                    }
                    else {
                      local_540 = *(undefined8 *)(param_1 + 0x4490);
                      local_544 = 0;
                      FUN_01331340(local_540,&local_928);
                      local_54c = (**(code **)(*local_928 + 0x20))(local_928);
                      if (local_54c != 0) {
                        local_544 = *(uint *)(*(longlong *)(local_54c + 0x10) + 0x14);
                      }
                      if ((local_544 & 0x4000000) == 0x4000000) {
                        *(undefined4 *)(param_1 + 0x4448) = 6;
                      }
                    }
                  }
                }
                else {
                  if (local_150 == (longlong *)0x0) {
                    local_150 = *(longlong **)(param_1 + 0x4490);
                  }
                  if (local_1c8 != (undefined1 *)0x0) {
                    (**(code **)(*local_150 + 400))(local_150,2);
                    local_b18 = (code *)0x0;
                    local_b10 = DAT_00f50e48;
                    (**(code **)(*local_150 + 0x150))(local_150,0,0,DAT_00f515e2);
                  }
                  local_50 = local_150;
                }
              }
              else if (((local_d8 & 0x10) == 0) || (local_150 == (longlong *)0x0)) {
                if (*(int *)(param_1 + 0x4488) == 0x40) {
                  local_cc = local_e0;
                }
                else {
                  local_cc = local_244;
                  if ((DAT_016bac50 < 0x2dde34) && (0x10 < (int)local_244)) {
                    local_cc = local_244 + 0x30;
                  }
                  if ((DAT_016bac50 < 0x7a2588) && (0x40 < (int)local_cc)) {
                    local_cc = local_cc + 0x23;
                  }
                  if ((DAT_016bac50 < 0xb73e28) && (local_cc == 0x68)) {
                    local_cc = 0x1f5;
                  }
                  if (((DAT_016bac50 < 0x16e3e33) || (*(char *)(param_1 + 0x4447) == '\0')) &&
                     (local_cc == 0x7e)) {
                    local_cc = 0x1f5;
                  }
                }
                local_50 = *(longlong **)
                            (PTR_DAT_015e06a0 +
                            (longlong)local_240 * 8 + (longlong)(int)local_cc * 0x1478 + 0x134c);
              }
              else {
                local_50 = local_150;
              }
              local_158 = local_50;
              if (local_50 != (longlong *)0x0) {
                FUN_0132ff80(local_50,0);
                *(undefined4 *)((longlong)local_158 + 0x7c) = 0;
                (**(code **)(*local_158 + 0x78))(local_158,*(undefined4 *)PTR_DAT_015e2160);
              }
              local_202 = '\0';
              cVar2 = FUN_0040fe90(local_50,PTR_PTR_00fe28b0);
              if ((cVar2 != '\0') &&
                 (cVar2 = FUN_0040fe90(local_50,PTR_PTR_00fe2c30), cVar2 == '\0')) {
                (**(code **)(*local_50 + 0x20))(local_50);
                local_50 = (longlong *)0x0;
              }
              if ((local_50 != (longlong *)0x0) && (-1 < *(int *)((longlong)local_50 + 100))) {
                FUN_0132fb90(local_50,&local_940);
                iVar3 = FUN_00414e70(local_940,L"Patcher");
                if (iVar3 != 0) {
                  uVar11 = *(int *)(param_1 + 0x4488) - 0x20;
                  if (uVar11 < 0x20) {
                    bVar12 = (1 << ((byte)uVar11 & 0x1f) & DAT_00f51600) != 0;
                  }
                  else {
                    bVar12 = false;
                  }
                  if (((bVar12) && (iVar3 = FUN_00414e70(local_1c8,L"Patcher"), iVar3 == 0)) &&
                     (cVar2 = FUN_012b7510(local_50), cVar2 != '\0')) {
                    (**(code **)(*local_50 + 0x20))(local_50);
                    local_50 = (longlong *)0x0;
                    *(undefined4 *)(param_1 + 0x445c) = 5;
                    DAT_016bac68 = 0x50;
                  }
                }
              }
              if (local_50 != (longlong *)0x0) {
                cVar2 = FUN_0132f790(local_50);
                if (((local_d8 & 0x10) == 0) == (cVar2 == '\0')) {
                  (**(code **)(*local_50 + 0x20))(local_50);
                  local_50 = (longlong *)0x0;
                  *(undefined4 *)(param_1 + 0x445c) = 5;
                  if ((local_d8 & 0x10) == 0) {
                    DAT_016bac68 = 0x32;
                  }
                  else {
                    DAT_016bac68 = 0x31;
                  }
                }
                else {
                  (**(code **)*local_50)(local_50,1);
                  if (**(char **)(*(longlong *)PTR_DAT_015e4790 + 0xd0) == '@') {
                    uVar11 = *(int *)(param_1 + 0x4488) - 0x20;
                    if (uVar11 < 0x40) {
                      bVar12 = (1L << ((byte)uVar11 & 0x3f) & DAT_00f51604) != 0;
                    }
                    else {
                      bVar12 = false;
                    }
                    if (bVar12) {
                      (**(code **)(**(longlong **)(*(longlong *)PTR_DAT_015e4790 + 0x40) + 0xf0))
                                (*(longlong **)(*(longlong *)PTR_DAT_015e4790 + 0x40),local_1c8);
                    }
                  }
                  if (local_1c8 != (undefined1 *)0x0) {
                    FUN_00414200(local_b4,local_1c8);
                    FUN_00aa2c00(local_98,local_b4);
                    local_d4 = (**(code **)(*local_50 + 0x28))(local_50,local_b4);
                    if (local_d4 == 0x32) {
                      *(undefined4 *)(param_1 + 0x4448) = 6;
                      (**(code **)*local_50)(local_50,0);
                      (**(code **)(*local_50 + 0x20))(local_50);
                      local_50 = (longlong *)0x0;
                    }
                    else if ((0 < (int)local_d4) || (*(int *)((longlong)local_50 + 100) < 0)) {
                      if ((local_9c != -1) &&
                         (FUN_012b8890(local_1c8,(longlong)local_9c),
                         *(int *)(param_1 + 0x4488) == 0x30)) {
                        *(undefined4 *)(param_1 + 0x445c) = 4;
                      }
                      (**(code **)*local_50)(local_50,0);
                      (**(code **)(*local_50 + 0x20))(local_50);
                      local_50 = (longlong *)0x0;
                    }
                  }
                  if (local_50 != (longlong *)0x0) {
                    if ((local_d8 & 0x80) == 0) {
                      local_54e = false;
                    }
                    else {
                      local_54d = false;
                      if (*(int *)((longlong)local_50 + 100) == 2) {
                        uVar6 = FUN_01330830(local_50);
                        local_54d = (uVar6 & 0x8000) != 0;
                      }
                      local_54e = local_54d;
                    }
                    if (local_54e == false) {
                      uVar11 = *(int *)(param_1 + 0x4488) - 0x20;
                      if (uVar11 < 0x20) {
                        bVar12 = (1 << ((byte)uVar11 & 0x1f) & DAT_00f51600) != 0;
                      }
                      else {
                        bVar12 = false;
                      }
                      if (bVar12) {
                        if (((local_50[6] != 0) && ((*(byte *)(param_1 + 0x4498) & 1) == 0)) &&
                           (DAT_016bac70 < 1)) {
                          (**(code **)(*local_50 + 0xe0))(local_50,1);
                        }
                      }
                      else {
                        (**(code **)(*local_50 + 0x88))(local_50,(local_d8 & 0x20) != 0);
                        if (DAT_016bac50 < 0x5b916e) {
                          local_d8 = local_d8 | 0x40;
                        }
                        (**(code **)(*local_50 + 0xf8))(local_50,(local_d8 & 0x40) != 0);
                        if ((DAT_016bac50 < 0xa7dcaa) || (0xb726b8 < DAT_016bac50)) {
                          local_560 = &local_220;
                          local_564 = *(float *)(*(longlong *)PTR_DAT_015e0e28 + 0xc);
                          uVar4 = FUN_0040c660((double)((float)(int)local_220 * local_564));
                          *(undefined4 *)local_560 = uVar4;
                          uVar4 = FUN_0040c660((double)((float)*(int *)((longlong)local_560 + 4) *
                                                       local_564));
                          *(undefined4 *)((longlong)local_560 + 4) = uVar4;
                          uVar4 = FUN_0040c660((double)((float)*(int *)(local_560 + 1) * local_564))
                          ;
                          *(undefined4 *)(local_560 + 1) = uVar4;
                          uVar4 = FUN_0040c660((double)((float)*(int *)((longlong)local_560 + 0xc) *
                                                       local_564));
                          *(undefined4 *)((longlong)local_560 + 0xc) = uVar4;
                        }
                        if (DAT_016bac50 < 0x1e980a) {
                          lVar7 = local_50[0x17];
                          local_310 = (undefined8 *)(lVar7 + 0x20);
                          *local_310 = CONCAT44(uStack_238,local_23c);
                          if ((local_d8 & 0x20000) != 0) {
                            *(undefined8 *)(lVar7 + 0x28) = local_220;
                          }
                        }
                        else {
                          lVar7 = local_50[0x17];
                          *(undefined8 *)(lVar7 + 0x20) = local_220;
                          *(undefined8 *)(lVar7 + 0x28) = local_218;
                        }
                        *(uint *)(local_50[0x17] + 0x34) = local_d8 & 0x30d;
                        *(uint *)(local_50[0x17] + 0x38) = (uint)local_230;
                        *(undefined1 *)(local_50[0x17] + 0x30) = 1;
                        if (((*(int *)(param_1 + 0x4488) == 0x40) && (*(int *)PTR_DAT_015e3170 == 4)
                            ) && (*(uint *)(local_50[0x17] + 0x34) =
                                       *(uint *)(local_50[0x17] + 0x34) | 4,
                                 *(char *)(*(longlong *)(*(longlong *)PTR_DAT_015e13b8 + 0x1088) +
                                          0x49e) != '\0')) {
                          *(undefined1 *)(local_50[0x17] + 0x30) = 0;
                        }
                      }
                    }
                    else {
                      iVar3 = FUN_00663bf0(local_70,local_50);
                      if (iVar3 < 0) {
                        local_558 = local_70;
                        if (*(int *)(local_70 + 0x10) == *(int *)(local_70 + 0x14)) {
                          FUN_00663aa0(local_70);
                        }
                        *(longlong **)
                         (*(longlong *)(local_558 + 8) + (longlong)*(int *)(local_558 + 0x10) * 8) =
                             local_50;
                        *(int *)(local_558 + 0x10) = *(int *)(local_558 + 0x10) + 1;
                      }
