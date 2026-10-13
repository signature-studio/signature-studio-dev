=== decomp 8712b0 -> FUN_008712b0 @008712b0 size=2681

void FUN_008712b0(longlong param_1,undefined8 param_2)

{
  longlong *plVar1;
  char cVar2;
  longlong lVar3;
  undefined8 uVar4;
  int iVar5;
  undefined1 auStack_148 [32];
  undefined1 local_128;
  undefined8 local_118;
  undefined8 local_110;
  undefined8 local_108;
  undefined1 *local_100;
  longlong local_f8;
  longlong local_f0;
  longlong local_e8;
  longlong local_e0;
  longlong local_d8;
  longlong local_d0;
  undefined1 local_c4 [12];
  longlong local_b8;
  undefined1 local_ad;
  int local_ac;
  int local_a8;
  undefined4 local_a4;
  undefined4 local_a0 [4];
  longlong local_90;
  longlong local_88;
  undefined1 local_79 [16];
  undefined4 local_69;
  int local_65;
  int local_61;
  undefined1 local_55 [25];
  undefined4 local_3c;
  undefined4 local_38;
  undefined1 local_34;
  longlong *local_28;
  longlong *local_20;
  
  local_100 = auStack_148;
  local_110 = 0;
  local_118 = 0;
  local_108 = 0;
  local_88 = 0;
  local_90 = 0;
  local_b8 = 0;
  FUN_0074a5b0(local_c4,param_2,DAT_00871dec);
  (**(code **)PTR_DAT_008f6868)(&local_3c,0x14);
  local_3c = *(undefined4 *)(param_1 + 0x854);
  local_38 = *(undefined4 *)(param_1 + 0x858);
  local_34 = *(undefined1 *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x1c);
  FUN_0074a6a0(local_c4,1,0x14,&local_3c);
  FUN_008744d0(param_1,local_55,1);
  FUN_0074a6a0(local_c4,2,0x19,local_55);
  if (*(longlong *)(param_1 + 0x5050) != 0) {
    (**(code **)PTR_DAT_008f6868)(&local_65,0x10);
    if (*(char *)(param_1 + 0x4fae) != '\0') {
      local_65 = *(int *)(*(longlong *)(param_1 + 0x5050) + 0x714);
    }
    local_61 = *(int *)(*(longlong *)(param_1 + 0x5050) + 0x718);
    FUN_0074a6a0(local_c4,0x1e,0x10,&local_65);
    if ((*(char *)(param_1 + 0x4fae) != '\0') && (0 < local_65)) {
      FUN_00416eb0(&local_90,PTR_DAT_00871260,1,(longlong)local_65);
      local_ac = local_65 * 0xc;
      local_d0 = local_90;
      (**(code **)PTR_DAT_008f6868)(local_90,local_ac);
      local_a8 = 0;
      iVar5 = local_65;
      if (-1 < local_65 + -1) {
        do {
          lVar3 = (longlong)local_a8;
          *(undefined4 *)(local_90 + lVar3 * 0xc) =
               *(undefined4 *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x72c) + lVar3 * 8);
          local_ad = *(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x72c) + 4 +
                              lVar3 * 8) != '\0';
          *(undefined1 *)(local_90 + 4 + lVar3 * 0xc) = local_ad;
          local_a8 = local_a8 + 1;
          iVar5 = iVar5 + -1;
        } while (iVar5 != 0);
      }
      FUN_0074a6a0(local_c4,0x1f,(longlong)local_ac,local_90);
    }
    if (0 < local_61) {
      FUN_00416eb0(&local_90,PTR_DAT_00871260,1,(longlong)local_61);
      local_ac = local_61 * 0xc;
      local_d8 = local_90;
      (**(code **)PTR_DAT_008f6868)(local_90,local_ac);
      local_a8 = 0;
      iVar5 = local_61;
      if (-1 < local_61 + -1) {
        do {
          lVar3 = (longlong)local_a8;
          *(undefined4 *)(local_90 + lVar3 * 0xc) =
               *(undefined4 *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x734) + lVar3 * 8);
          local_ad = *(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x734) + 4 +
                              lVar3 * 8) != '\0';
          *(undefined1 *)(local_90 + 4 + lVar3 * 0xc) = local_ad;
          local_a8 = local_a8 + 1;
          iVar5 = iVar5 + -1;
        } while (iVar5 != 0);
      }
      FUN_0074a6a0(local_c4,0x20,(longlong)local_ac,local_90);
    }
  }
  if (*(longlong *)(param_1 + 0x5050) == 0) goto code_r0x00871d04;
  (**(code **)PTR_DAT_008f6868)(local_a0,0x10);
  local_a0[0] = *(undefined4 *)(*(longlong *)(param_1 + 0x5050) + 0x98);
  FUN_0074a6a0(local_c4,0x32,0x10,local_a0);
  FUN_00411f10(&local_88);
  FUN_00411f10(&local_b8);
  lVar3 = *(longlong *)(param_1 + 0x5050);
  iVar5 = *(int *)(lVar3 + 0x98);
  if (iVar5 < 6) {
    if (iVar5 == 5) {
LAB_00871921:
      FUN_00413930(&local_88,lVar3 + 0x9c,0x105);
      (**(code **)PTR_DAT_008f6868)(local_79,0x10);
      local_e8 = *(longlong *)(param_1 + 0x5050) + 0x4b0;
      FUN_00409bb0(local_e8,local_79,0x10);
      FUN_0074a6a0(local_c4,0x34,0x10,local_79);
    }
    else {
      if (iVar5 != 0) {
        if (iVar5 == 1) goto LAB_00871921;
        if (iVar5 != 4) goto LAB_00871ac3;
      }
      FUN_00412630(&local_88,*(undefined8 *)(lVar3 + 0x80));
      if (local_88 == 0) {
        FUN_00413930(&local_108,lVar3 + 0x2a6,0x105);
        FUN_005d4a40(&local_88,local_108);
      }
      FUN_00413930(&local_b8,*(longlong *)(param_1 + 0x5050) + 0x2a6,0x105);
      (**(code **)PTR_DAT_008f6868)(&local_69,4);
      local_69 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x2c0))
                           (*(longlong **)(param_1 + 0x5050));
      FUN_0074a6a0(local_c4,0x33,4,&local_69);
      lVar3 = *(longlong *)(param_1 + 0x5050);
      cVar2 = FUN_0040f040(lVar3,PTR_PTR_007a78a0);
      if (cVar2 != '\0') {
        local_a4 = *(undefined4 *)(lVar3 + 0x9c4);
        FUN_0074a6a0(local_c4,0x39,4,&local_a4);
      }
      cVar2 = FUN_004378e0(*(longlong *)(param_1 + 0x5050) + 0x4b0,PTR_DAT_008f6f28);
      if (cVar2 == '\0') {
        (**(code **)PTR_DAT_008f6868)(local_79,0x10);
        local_e0 = *(longlong *)(param_1 + 0x5050) + 0x4b0;
        FUN_00409bb0(local_e0,local_79,0x10);
        FUN_0074a6a0(local_c4,0x34,0x10,local_79);
      }
    }
  }
  else if (iVar5 - 7U < 2) {
    FUN_00413930(&local_118,lVar3 + 0x2a6,0x105);
    FUN_0043a0d0(&local_110,local_118,0);
    FUN_0043a480(&local_88,local_110);
    FUN_00413930(&local_b8,*(longlong *)(param_1 + 0x5050) + 0x2a6,0x105);
    (**(code **)PTR_DAT_008f6868)(local_79,0x10);
    local_f0 = *(longlong *)(param_1 + 0x5050) + 0x4b0;
    FUN_00409bb0(local_f0,local_79,0x10);
    FUN_0074a6a0(local_c4,0x34,0x10,local_79);
  }
  else if (iVar5 - 0xbU < 2) {
    FUN_00413930(&local_88,lVar3 + 0x9c,0x105);
    FUN_00413930(&local_b8,lVar3 + 0x2a6,0x105);
    lVar3 = FUN_0040f060(lVar3,PTR_PTR_008597f0);
    FUN_0074a740(local_c4,0x3a,*(undefined8 *)(lVar3 + 0x9b4));
  }
  else {
LAB_00871ac3:
    FUN_00412630(&local_88,*(undefined8 *)(lVar3 + 0x80));
    FUN_00413930(&local_b8,lVar3 + 0x2a6,0x105);
    (**(code **)PTR_DAT_008f6868)(&local_69,4);
    local_69 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x2c0))
                         (*(longlong **)(param_1 + 0x5050));
    FUN_0074a6a0(local_c4,0x33,4,&local_69);
    (**(code **)PTR_DAT_008f6868)(local_79,0x10);
    local_f8 = *(longlong *)(param_1 + 0x5050) + 0x4b0;
    FUN_00409bb0(local_f8,local_79,0x10);
    FUN_0074a6a0(local_c4,0x34,0x10,local_79);
  }
  if (local_88 != 0) {
    FUN_0074a740(local_c4,0x36,local_88);
  }
  if (local_b8 != 0) {
    FUN_0074a740(local_c4,0x37,local_b8);
  }
  if (*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x3c) != 0) {
    FUN_0074a740(local_c4,0x38,*(undefined8 *)(*(longlong *)(param_1 + 0x5050) + 0x3c));
  }
  local_20 = (longlong *)FUN_0040eb90(PTR_PTR_004c6c28,1);
  local_128 = 0;
  (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x1a8))
            (*(longlong **)(param_1 + 0x5050),local_20,1,0);
  FUN_00501370(local_20,0);
  lVar3 = (**(code **)(*local_20 + 0x18))(local_20);
  if (0 < lVar3) {
    uVar4 = (**(code **)(*local_20 + 0x18))(local_20);
    FUN_0074a6a0(local_c4,0x35,uVar4,local_20[1]);
  }
  plVar1 = local_20;
  local_28 = local_20;
  local_20 = (longlong *)0x0;
  FUN_0040ec50(plVar1);
code_r0x00871d04:
  FUN_00411ff0(&local_118,3);
  FUN_00411f10(&local_b8);
  FUN_00417080(&local_90,PTR_DAT_00871260);
  FUN_00411f10(&local_88);
  return;
}


