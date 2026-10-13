=== decomp aac1e0 -> FUN_00aac1e0 @00aac1e0 size=270

void FUN_00aac1e0(longlong param_1,undefined8 *param_2)

{
  uint uVar1;
  int iVar2;
  undefined8 uVar3;
  bool bVar4;
  undefined1 local_4c [8];
  undefined4 local_44;
  uint local_3c;
  
  FUN_00a9eb60(*(undefined8 *)(param_1 + 0x38),0xc9,*param_2);
  uVar3 = 0;
  (**(code **)PTR_DAT_015e0a48)(local_4c,0x34);
  if (*(char *)(param_1 + 0x88) != '\0') {
    local_3c = local_3c | 0x80;
  }
  if (*(char *)((longlong)param_2 + 0x24) != '\0') {
    local_3c = local_3c | 0x10;
  }
  uVar1 = *(uint *)(param_2 + 2);
  if (uVar1 < 0x10) {
    bVar4 = ((ushort)((int)CONCAT62((int6)((ulonglong)uVar3 >> 0x10),1) << ((byte)uVar1 & 0x1f)) &
            DAT_00aac2f0) != 0;
  }
  else {
    bVar4 = false;
  }
  if (bVar4) {
    local_44 = *(undefined4 *)(&DAT_014e11d0 + (longlong)(int)uVar1 * 4);
  }
  FUN_00a9ea80(*(undefined8 *)(param_1 + 0x38),0xd4,local_4c,0x34,0x40000000,0);
  iVar2 = FUN_00414e70(param_2[1],*param_2);
  if (iVar2 != 0) {
    FUN_00a9eb60(*(undefined8 *)(param_1 + 0x38),0xcb,param_2[1]);
  }
  if (*(int *)(param_2 + 2) - 2U < 2) {
    FUN_00a9ea80(*(undefined8 *)(param_1 + 0x38),0xd5,*(undefined8 *)((longlong)param_2 + 0x14),
                 *(undefined8 *)((longlong)param_2 + 0x1c),0x40000000,0);
  }
  return;
}


=== decomp aac300 -> FUN_00aac300 @00aac300 size=405

void FUN_00aac300(undefined8 param_1,int param_2,undefined8 param_3,char param_4)

{
  int iVar1;
  undefined4 uVar2;
  int iVar3;
  undefined1 auStack_68 [33];
  undefined1 local_47;
  undefined4 local_46;
  int local_42;
  undefined4 local_3e;
  undefined4 local_3a;
  undefined2 local_36;
  undefined2 local_34;
  undefined2 local_32;
  longlong local_30;
  
  local_30 = FUN_00a9e980(PTR_DAT_00a9dd98,1,param_1);
  local_3e = DAT_00aac498;
  local_3a = 6;
  local_34 = 2;
  local_32 = 0x30;
  local_36 = (short)param_2;
  (**(code **)(**(longlong **)(local_30 + 8) + 0x38))(*(longlong **)(local_30 + 8),&local_3e,0xe);
  iVar1 = FUN_005123a0(*(undefined8 *)(local_30 + 8));
  (**(code **)(**(longlong **)(local_30 + 8) + 0x38))(*(longlong **)(local_30 + 8),&local_46,8);
  FUN_00a9eb60(local_30,199,L"11.5.5");
  *(undefined1 *)(local_30 + 0x10) = 1;
  local_47 = (&DAT_014e11c8)[param_4];
  FUN_00a9ec60(local_30,0x1c);
  if (*(char *)(local_30 + 0x11) != '\0') {
    uVar2 = FUN_005123a0(*(undefined8 *)(local_30 + 8));
    FUN_00a9ece0(local_30,&local_47,1,uVar2);
  }
  (**(code **)(**(longlong **)(local_30 + 8) + 0x38))(*(longlong **)(local_30 + 8),&local_47,1);
  if (param_2 == 0x30) {
    FUN_00aac1e0(auStack_68,param_3);
  }
  local_46 = DAT_00aac4b6;
  iVar3 = FUN_005123a0(*(undefined8 *)(local_30 + 8));
  local_42 = (iVar3 - iVar1) + -8;
  (**(code **)(**(longlong **)(local_30 + 8) + 0x80))(*(longlong **)(local_30 + 8),iVar1,0);
  (**(code **)(**(longlong **)(local_30 + 8) + 0x38))(*(longlong **)(local_30 + 8),&local_46,8);
  FUN_0040faa0(local_30);
  return;
}


=== decomp f54900 -> FUN_00f54900 @00f54900 size=860

bool FUN_00f54900(undefined8 param_1,uint param_2,byte param_3)

{
  int iVar1;
  longlong lVar2;
  longlong lVar3;
  uint uVar4;
  undefined8 uVar5;
  uint uVar6;
  bool bVar8;
  bool local_89;
  undefined8 local_88;
  undefined8 local_80;
  undefined1 local_74 [8];
  undefined1 local_6c [16];
  uint local_5c;
  undefined8 local_38;
  undefined1 local_2e [8];
  ushort local_26;
  longlong local_20;
  ulonglong uVar7;
  
  local_88 = 0;
  local_80 = 0;
  uVar5 = 0;
  FUN_005123c0(param_1,0);
  FUN_0063a660();
  FUN_0063a6d0();
  local_89 = false;
  if (param_3 != 0) {
    if (param_2 - 0x30 < 8) {
      bVar8 = ((byte)((int)CONCAT71((int7)((ulonglong)uVar5 >> 8),1) <<
                     ((byte)(param_2 - 0x30) & 0x1f)) & DAT_00f54c7c) != 0;
    }
    else {
      bVar8 = false;
    }
    if (!bVar8) goto LAB_00f54c3f;
  }
  local_20 = FUN_00a9e1b0(PTR_DAT_00a9dac0,1,param_1,0x40000000,0);
  lVar2 = (**(code **)(**(longlong **)(local_20 + 8) + 0x18))(*(longlong **)(local_20 + 8));
  if (0x15 < lVar2) {
    (**(code **)(**(longlong **)(local_20 + 8) + 0x30))(*(longlong **)(local_20 + 8),local_2e,0xe);
    uVar7 = 0;
    FUN_00414910(&local_80,local_2e,4);
    iVar1 = FUN_00414e70(local_80,L"FLhd");
    if (iVar1 == 0) {
      uVar6 = (uint)local_26;
      DAT_016bac68 = (uint)local_26;
      uVar4 = param_2;
      if (param_3 != 0) {
        if (DAT_016bac68 - 0x30 < 8) {
          uVar6 = (int)CONCAT71((int7)(uVar7 >> 8),1) << ((byte)(DAT_016bac68 - 0x30) & 0x1f);
          uVar7 = (ulonglong)uVar6;
          bVar8 = ((byte)uVar6 & DAT_00f54c96) != 0;
        }
        else {
          bVar8 = false;
        }
        uVar6 = (uint)local_26;
        if (bVar8) {
          uVar6 = 0x30;
        }
        if (param_2 - 0x30 < 8) {
          bVar8 = ((byte)((int)CONCAT71((int7)(uVar7 >> 8),1) << ((byte)(param_2 - 0x30) & 0x1f)) &
                  DAT_00f54c96) != 0;
        }
        else {
          bVar8 = false;
        }
        if (bVar8) {
          uVar4 = 0x30;
        }
      }
      local_89 = uVar6 == uVar4;
    }
  }
  if ((local_89 & param_3) != 0) {
    local_89 = false;
    (**(code **)(**(longlong **)(local_20 + 8) + 0x30))(*(longlong **)(local_20 + 8),local_74,8);
    FUN_00414910(&local_88,local_74,4);
    iVar1 = FUN_00414e70(local_88,L"FLdt");
    lVar2 = local_20;
    if (iVar1 != 0) {
      local_20 = 0;
      FUN_0040faa0(lVar2);
      goto LAB_00f54c3f;
    }
    local_38 = FUN_005123a0(*(undefined8 *)(local_20 + 8));
    while( true ) {
      lVar2 = FUN_005123a0(*(undefined8 *)(local_20 + 8));
      lVar3 = (**(code **)(**(longlong **)(local_20 + 8) + 0x18))(*(longlong **)(local_20 + 8));
      if (lVar3 + -1 <= lVar2) break;
      FUN_00a9e7a0(local_20,&local_38);
      if ((*(int *)(local_20 + 0x100020) == 0xd4) && (*(longlong *)(local_20 + 0x100024) == 0x34)) {
        (**(code **)PTR_DAT_015e0a48)(local_6c,0x34);
        (**(code **)PTR_DAT_015e0030)
                  (*(undefined8 *)(local_20 + 0x10002c),local_6c,
                   *(undefined4 *)(local_20 + 0x100024));
        if (0x14 < *(longlong *)(local_20 + 0x100024)) {
          if ((local_5c & 0x10) == 0) {
            DAT_016bac68 = 0x32;
          }
          else {
            DAT_016bac68 = 0x31;
          }
          local_89 = DAT_016bac68 == param_2;
        }
        break;
      }
      FUN_005123c0(*(undefined8 *)(local_20 + 8),local_38);
    }
  }
  lVar2 = local_20;
  local_20 = 0;
  FUN_0040faa0(lVar2);
LAB_00f54c3f:
  FUN_00412e40(&local_88,2);
  return local_89;
}


=== decomp f3c870 -> FUN_00f3c870 @00f3c870 size=2045

/* WARNING: Restarted to delay deadcode elimination for space: stack */

void FUN_00f3c870(longlong param_1,longlong param_2)

{
  char cVar1;
  undefined4 uVar2;
  longlong lVar3;
  ulonglong uVar4;
  longlong *plVar5;
  undefined8 uVar6;
  undefined1 auStack_1b8 [32];
  undefined8 local_198;
  code *local_190;
  undefined8 local_140;
  undefined8 local_138;
  undefined8 local_130;
  undefined8 local_128;
  undefined8 local_120;
  undefined8 local_108;
  undefined8 local_100;
  undefined8 local_f8;
  longlong *local_f0;
  undefined8 local_e8;
  undefined1 *local_e0;
  char local_d3;
  undefined1 local_d2;
  undefined1 local_d1;
  longlong local_d0;
  undefined4 local_c4;
  longlong local_c0;
  undefined4 local_b4;
  longlong local_b0;
  undefined1 *local_a8;
  float local_9c;
  undefined8 *local_98;
  bool local_89;
  longlong *local_88;
  undefined8 local_80;
  undefined8 local_78;
  longlong *local_70;
  undefined4 local_64;
  undefined4 local_60;
  undefined4 local_5c;
  undefined4 local_58;
  uint local_54;
  undefined1 local_50;
  undefined1 local_4f [15];
  undefined8 local_40;
  undefined8 local_38;
  
  local_e0 = auStack_1b8;
  local_f8 = 0;
  local_100 = 0;
  local_128 = 0;
  local_130 = 0;
  local_138 = 0;
  local_140 = 0;
  local_108 = 0;
  local_120 = 0;
  local_f0 = (longlong *)0x0;
  local_e8 = 0;
  local_78 = 0;
  local_80 = 0;
  lVar3 = FUN_0041d110();
  FUN_00413480(param_1 + 0x4658,*(undefined8 *)(lVar3 + 0x290));
  FUN_00413480(&local_80,*(undefined8 *)(param_2 + 0x58));
  FUN_00a9eb60(*(undefined8 *)(param_1 + 18000),0xc9,local_80);
  FUN_0132e8e0(param_2);
  local_50 = *(undefined1 *)(*(longlong *)(param_2 + 0xb8) + 0x38);
  local_54 = *(uint *)(*(longlong *)(param_2 + 0xb8) + 0x34) & 0x30d;
  cVar1 = FUN_0040fe90(param_2,PTR_PTR_012b0718);
  if (cVar1 == '\0') {
    local_64 = 0;
    local_60 = 0;
    local_54 = local_54 | 0x10;
  }
  else {
    local_64 = *(undefined4 *)(param_2 + 0x130);
    local_60 = *(undefined4 *)(param_2 + 0x134);
  }
  if (*(char *)(param_2 + 0xa4) != '\0') {
    local_54 = local_54 | 0x20;
  }
  if (*(char *)(param_2 + 0xfb) != '\0') {
    local_54 = local_54 | 0x40;
  }
  local_89 = false;
  if (*(int *)(param_2 + 100) == 2) {
    uVar4 = FUN_01330830(param_2);
    local_89 = (uVar4 & 0x8000) != 0;
  }
  if ((local_89 != false) && ((*(byte *)(param_1 + 0x4698) & 4) == 0)) {
    local_54 = local_54 | 0x80;
  }
  local_40 = *(undefined8 *)(*(longlong *)(param_2 + 0xb8) + 0x20);
  local_38 = *(undefined8 *)(*(longlong *)(param_2 + 0xb8) + 0x28);
  cVar1 = FUN_012b57b0(param_2);
  if ((cVar1 == '\0') || (*(int *)(param_2 + 0xdc) == 0)) {
    local_98 = &local_40;
    local_9c = *(float *)(*(longlong *)PTR_DAT_015e0e28 + 0x10);
    uVar2 = FUN_0040c660((double)((float)(int)local_40 * local_9c));
    *(undefined4 *)local_98 = uVar2;
    uVar2 = FUN_0040c660((double)((float)*(int *)((longlong)local_98 + 4) * local_9c));
    *(undefined4 *)((longlong)local_98 + 4) = uVar2;
    uVar2 = FUN_0040c660((double)((float)*(int *)(local_98 + 1) * local_9c));
    *(undefined4 *)(local_98 + 1) = uVar2;
    uVar2 = FUN_0040c660((double)((float)*(int *)((longlong)local_98 + 0xc) * local_9c));
    *(undefined4 *)((longlong)local_98 + 0xc) = uVar2;
  }
  else {
    FUN_012b5bb0(param_2,&local_40);
  }
  local_5c = *(undefined4 *)(param_2 + 100);
  local_58 = 0;
  local_a8 = local_4f;
  (**(code **)PTR_DAT_015e0a48)(local_a8,0xf);
  local_198 = 0x40000000;
  local_190 = (code *)0x0;
  FUN_00a9ea80(*(undefined8 *)(param_1 + 18000),0xd4,&local_64,0x34);
  if (*(longlong *)(param_2 + 0x50) != 0) {
    FUN_00a9eb60(*(undefined8 *)(param_1 + 18000),0xcb,*(undefined8 *)(param_2 + 0x50));
    local_198 = *(undefined8 *)(param_2 + 0x50);
    local_190 = (code *)&DAT_00f3d294;
    FUN_00414da0(&local_e8,4,*(undefined8 *)(param_1 + 0x4658),&DAT_00f3d280);
    FUN_00661bc0(0,local_e8,0,0);
  }
  local_b0 = *(longlong *)(param_1 + 18000);
  local_b4 = *(undefined4 *)(param_2 + 0x7c);
  FUN_00a9ec60(local_b0,0x9b);
  if (*(char *)(local_b0 + 0x11) != '\0') {
    uVar2 = FUN_005123a0(*(undefined8 *)(local_b0 + 8));
    FUN_00a9ece0(local_b0,&local_b4,4,uVar2);
  }
  (**(code **)(**(longlong **)(local_b0 + 8) + 0x38))(*(longlong **)(local_b0 + 8),&local_b4,4);
  local_c0 = *(longlong *)(param_1 + 18000);
  local_c4 = *(undefined4 *)(param_2 + 0x78);
  FUN_00a9ec60(local_c0,0x80);
  if (*(char *)(local_c0 + 0x11) != '\0') {
    uVar2 = FUN_005123a0(*(undefined8 *)(local_c0 + 8));
    FUN_00a9ece0(local_c0,&local_c4,4,uVar2);
  }
  (**(code **)(**(longlong **)(local_c0 + 8) + 0x38))(*(longlong **)(local_c0 + 8),&local_c4,4);
  local_d0 = *(longlong *)(param_1 + 18000);
  local_d1 = *(undefined1 *)(param_2 + 0xf9);
  FUN_00a9ec60(local_d0,0x29);
  if (*(char *)(local_d0 + 0x11) != '\0') {
    uVar2 = FUN_005123a0(*(undefined8 *)(local_d0 + 8));
    FUN_00a9ece0(local_d0,&local_d1,1,uVar2);
  }
  (**(code **)(**(longlong **)(local_d0 + 8) + 0x38))(*(longlong **)(local_d0 + 8),&local_d1,1);
  if (*(int *)(param_2 + 100) == 2) {
    if ((*(byte *)(param_1 + 0x4698) & 4) == 0) {
      local_d3 = '\x01';
    }
    else {
      local_d2 = 0;
      uVar4 = FUN_01330830(param_2);
      local_d2 = (uVar4 & 0x8000) != 0;
      if (((bool)local_d2) || (**(byte **)(*(longlong *)PTR_DAT_015e4790 + 0xd0) < 0x41)) {
        local_d3 = '\0';
      }
      else {
        local_d3 = '\x01';
      }
    }
    if (local_d3 != '\0') {
      FUN_01331340(param_2,&local_f0);
      plVar5 = (longlong *)(**(code **)(*local_f0 + 0x20))(local_f0);
      local_88 = plVar5;
      if (plVar5 != (longlong *)0x0) {
        local_70 = (longlong *)FUN_0040f9e0(PTR_PTR_004d4618,1);
        lVar3 = FUN_00529280(PTR_PTR_004d5cf8,1,local_70,0);
        if (lVar3 == 0) {
          lVar3 = 0;
        }
        else {
          lVar3 = lVar3 + 0x28;
        }
        FUN_0041a7b0(&local_78,lVar3);
        (**(code **)(*plVar5 + 0x18))(plVar5,local_78,0xffffffff);
        FUN_0041a770(&local_78);
        uVar6 = (**(code **)(*local_70 + 0x18))(local_70);
        local_198 = 0x1000000;
        local_190 = FUN_00f3c210;
        cVar1 = FUN_00a9ea80(*(undefined8 *)(param_1 + 18000),0xd5,local_70[1],uVar6);
        if (cVar1 == '\0') {
          *(undefined4 *)(param_1 + 0x464c) = 3;
        }
        (**(code **)(*local_70 + -0x20))(local_70,1);
      }
    }
  }
  lVar3 = FUN_0041d110();
  FUN_004133f0(lVar3 + 0x290,*(undefined8 *)(param_1 + 0x4658));
  FUN_00412e40(&local_140,5);
  FUN_00412e40(&local_108,3);
  FUN_0041a770(&local_f0);
  FUN_00412d60(&local_e8);
  FUN_00412d60(&local_80);
  FUN_0041a770(&local_78);
  return;
}


