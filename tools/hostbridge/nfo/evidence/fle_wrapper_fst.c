=== decomp aba880 -> FUN_00aba880 @00aba880 size=1163

void FUN_00aba880(longlong param_1,longlong param_2,uint param_3)

{
  
  local_70 = auStack_128;
  local_d0 = 0;
  local_a8 = 0;
  local_a0 = 0;
  local_88 = 0;
  local_80 = 0;
  local_78 = 0;
  local_38 = 0;
  FUN_00415610(local_60,PTR_DAT_00aa9a58);
  FUN_00414c70(&local_38,*(undefined8 *)(param_2 + 0x18),L".FST");
  FUN_00414c70(&local_78,*(undefined8 *)(param_1 + 0x38),local_38);
  cVar2 = FUN_00819110(local_78);
  if (cVar2 != '\0') {
    FUN_00414c70(&local_80,*(undefined8 *)(param_1 + 0x38));
    lpExistingFileName = (LPCWSTR)FUN_00414850(local_80);
    lpNewFileName = (LPCWSTR)FUN_00414850(*(undefined8 *)(param_2 + 0x2c));
    CopyFileW(lpExistingFileName,lpNewFileName,0);
    local_98 = *(undefined8 *)(param_2 + 0x18);
    local_90 = 0x11;
    FUN_0043dd60(&local_88,L"Save \"%s\" - copied default preset",&local_98,0);
    FUN_00ab81f0(param_1,local_88,0,0);
    goto LAB_00abad31;
  }
  local_30 = FUN_0040f9e0(PTR_PTR_004d4618,1);
  local_28 = FUN_0040f9e0(PTR_PTR_004d4618,1);
  uVar4 = *(undefined8 *)(param_2 + 0x18);
  FUN_00413480(local_60,uVar4);
  if (*(uint *)(param_2 + 0x34) < 8) {
    bVar6 = ((byte)((int)CONCAT71((int7)((ulonglong)uVar4 >> 8),1) <<
                   ((byte)*(uint *)(param_2 + 0x34) & 0x1f)) & DAT_00abaea8) != 0;
  }
  else {
    bVar6 = false;
  }
  if (bVar6) {
    local_68 = 0;
    cVar2 = FUN_008f5cd0(param_2,*(undefined4 *)(param_2 + 0x34),3,&local_68);
    if (cVar2 == '\0') {
      FUN_008f5cd0(param_2,*(undefined4 *)(param_2 + 0x34),2,&local_68);
    }
    if (local_68 != 0) {
      FUN_00413480(local_60,*(undefined8 *)(local_68 + 8));
    }
  }
  uVar5 = *(ulonglong *)(param_2 + 0x18);
  FUN_00413480(local_58,uVar5);
  local_4c = 0;
  local_44 = 0;
  local_50 = param_3;
  cVar2 = FUN_008f6380(param_2);
  bVar1 = (byte)param_3;
  if (cVar2 == '\0') {
    local_3c = false;
  }
  else {
    cVar2 = FUN_008f64f0(param_2);
    if (cVar2 == '\0') {
      local_3c = true;
    }
    else if (param_3 < 0x10) {
      uVar3 = (int)CONCAT62((int6)(uVar5 >> 0x10),1) << (bVar1 & 0x1f);
      uVar5 = (ulonglong)uVar3;
      local_3c = ((ushort)uVar3 & DAT_00abaea9) != 0;
    }
    else {
      local_3c = false;
    }
  }
  if (param_3 < 0x10) {
    uVar3 = (int)CONCAT62((int6)(uVar5 >> 0x10),1) << (bVar1 & 0x1f);
    uVar5 = (ulonglong)uVar3;
    bVar6 = ((ushort)uVar3 & DAT_00abaeab) != 0;
  }
  else {
    bVar6 = false;
  }
  if (bVar6) {
LAB_00ababc8:
    FUN_00ab8ae0(param_1,local_60,param_2,local_28);
  }
  else {
    if (param_3 < 0x10) {
      bVar6 = ((ushort)((int)CONCAT62((int6)(uVar5 >> 0x10),1) << (bVar1 & 0x1f)) & DAT_00abaead) !=
              0;
    }
    else {
      bVar6 = false;
    }
    if (bVar6) goto LAB_00ababc8;
  }
  FUN_00aac300(local_30,0x30,local_60,0);
  FUN_0043c5e0(&local_a0,*(undefined8 *)(param_2 + 0x2c));
  FUN_0043bc40(local_a0);
  FUN_00513c20(local_30,*(undefined8 *)(param_2 + 0x2c));
  local_c8 = *(undefined8 *)(param_2 + 0x18);
  local_c0 = 0x11;
  local_b8 = *(undefined8 *)(param_2 + 0x2c);
  local_b0 = 0x11;
  FUN_0043dd60(&local_a8,L"Save \"%s\": created preset file \"%s\"",&local_c8,1);
  FUN_00ab81f0(param_1,local_a8,0,0);
  FUN_0040faa0(local_28);
  FUN_0040faa0(local_30);
LAB_00abad31:
  FUN_00412d60(&local_d0);
  FUN_00412e40(&local_a8,2);
  FUN_00412e40(&local_88,3);
  FUN_00415c30(local_60,PTR_DAT_00aa9a58);
  FUN_00412d60(&local_38);
  return;
}


=== decomp ab8ae0 -> FUN_00ab8ae0 @00ab8ae0 size=571

void FUN_00ab8ae0(undefined8 param_1,longlong param_2,longlong param_3,longlong *param_4)

{
  
  local_678 = 0;
  local_680 = 0;
  lVar5 = FUN_008f5e70(param_3);
  FUN_00413480(&local_678,*(undefined8 *)(param_3 + 0x18));
  uVar6 = *(undefined8 *)(lVar5 + 0x10);
  FUN_00413480(&local_680,uVar6);
  if (local_680 != 0) {
    uVar3 = *(int *)(param_2 + 0x10) - 8;
    if (uVar3 < 8) {
      bVar8 = ((byte)((int)CONCAT71((int7)((ulonglong)uVar6 >> 8),1) << ((byte)uVar3 & 0x1f)) &
              DAT_00ab8d3c) != 0;
    }
    else {
      bVar8 = false;
    }
    if (!bVar8) {
      FUN_00661970(&local_678,local_680);
    }
  }
  iVar4 = FUN_008f5b40(param_3);
  if (1 < iVar4) {
    FUN_00412d60(&local_680);
  }
  (**(code **)PTR_DAT_015e0a48)(&local_66c,0x644);
  local_66c = *(undefined4 *)(param_3 + 0x34);
  FUN_0043d760(local_668,local_678,0x20a);
  FUN_0043d760(local_45e,local_680,0x20a);
  FUN_008f6dc0(lVar5,&local_698);
  local_254 = local_698;
  uStack_24c = uStack_690;
  local_244 = 0;
  local_240 = 0;
  local_238 = *(int *)(lVar5 + 0x20);
  if (local_238 != 0) {
    local_244 = 2;
  }
  FUN_00513cf0(param_4);
  cVar1 = FUN_008f62b0(param_3,2);
  cVar2 = FUN_008f62b0(param_3,3);
  if ((cVar2 != '\0') || (cVar1 == '\0')) {
    uVar7 = 0;
  }
  else {
    uVar7 = (undefined4)CONCAT71((int7)((ulonglong)param_3 >> 8),1);
  }
  FUN_00a9eff0(param_4,&local_66c,uVar7,
               CONCAT71((int7)((ulonglong)auStack_688 >> 8),cVar2 != '\0' || cVar1 != '\0') &
               0xffffffff,*(undefined8 *)(lVar5 + 0x50),0,*(undefined8 *)(lVar5 + 0x60));
  FUN_005123c0(param_4,0);
  FUN_004133f0(param_2,L"Fruity Wrapper");
  *(undefined4 *)(param_2 + 0x10) =
       *(undefined4 *)(&DAT_014e1cdc + (longlong)*(char *)(param_2 + 0x24) * 4);
  *(longlong *)(param_2 + 0x14) = param_4[1];
  uVar6 = (**(code **)(*param_4 + 0x18))(param_4);
  *(undefined8 *)(param_2 + 0x1c) = uVar6;
  FUN_00412e40(&local_680,2);
  return;
}


=== decomp aac300 -> FUN_00aac300 @00aac300 size=405

void FUN_00aac300(undefined8 param_1,int param_2,undefined8 param_3,char param_4)

{
  
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


=== decomp aac1e0 -> FUN_00aac1e0 @00aac1e0 size=270

void FUN_00aac1e0(longlong param_1,undefined8 *param_2)

{
  
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


=== decomp a9eff0 -> FUN_00a9eff0 @00a9eff0 size=935

/* WARNING: Type propagation algorithm not settling */

void FUN_00a9eff0(longlong *param_1,int *param_2,char param_3,char param_4,longlong param_5,
                 longlong *param_6,undefined8 param_7)

{
  
  local_6d8 = 0;
  local_6d0 = 0;
  local_6c8 = 0;
  local_6c0[0] = 0;
  piVar3 = &local_65c;
  for (lVar2 = 200; lVar2 != 0; lVar2 = lVar2 + -1) {
    *(undefined8 *)piVar3 = *(undefined8 *)param_2;
    param_2 = param_2 + 2;
    piVar3 = piVar3 + 2;
  }
  *piVar3 = *param_2;
  local_6a0 = 8;
  (**(code **)(*param_1 + 0x38))(param_1,&local_6a0,4);
  FUN_008e8e10(local_6ac,param_1,DAT_00a9f3bc);
  (**(code **)PTR_DAT_015e0a48)(&local_675,0x19);
  local_674 = 0xffffffff;
  local_670 = 0xffffffff;
  local_675 = 0;
  local_66c = 0x407908;
  if (param_3 != '\0') {
    local_66c = 0x407d08;
  }
  if (param_4 != '\0') {
    local_66c = local_66c | 0x100000;
  }
  local_664 = 1;
  FUN_008e8ed0(local_6ac,2,0x19,&local_675);
  (**(code **)PTR_DAT_015e0a48)(local_699,0x10);
  local_699[0] = local_65c;
  FUN_008e8ed0(local_6ac,0x32,0x10,local_699);
  if ((local_65c == 0) || (local_65c == 4)) {
    (**(code **)PTR_DAT_015e0a48)(&local_679,4);
    local_679 = local_228;
    FUN_008e8ed0(local_6ac,0x33,4,&local_679);
  }
  else if (local_65c - 7U < 2) {
    (**(code **)PTR_DAT_015e0a48)(local_689,0x10);
    FUN_00409c80(local_244,local_689,0x10);
    FUN_008e8ed0(local_6ac,0x34,0x10,local_689);
  }
  else if (local_65c - 0xbU < 2) {
    FUN_008e8fe0(local_6ac,0x3a,param_7);
  }
  else {
    (**(code **)PTR_DAT_015e0a48)(&local_679,4);
    local_679 = local_228;
    FUN_008e8ed0(local_6ac,0x33,4,&local_679);
    (**(code **)PTR_DAT_015e0a48)(local_689,0x10);
    FUN_00409c80(local_244,local_689,0x10);
    FUN_008e8ed0(local_6ac,0x34,0x10,local_689);
  }
  FUN_00414940(local_6c0,local_658,0x105);
  if (local_6c0[0] != 0) {
    FUN_00414940(&local_6c8,local_658,0x105);
    FUN_008e8fe0(local_6ac,0x36,local_6c8);
  }
  FUN_00414940(&local_6d0,local_44e,0x105);
  if (local_6d0 != 0) {
    FUN_00414940(&local_6d8,local_44e,0x105);
    FUN_008e8fe0(local_6ac,0x37,local_6d8);
  }
  if (param_5 != 0) {
    FUN_008e8fe0(local_6ac,0x38,param_5);
  }
  if (param_6 != (longlong *)0x0) {
    lVar2 = (**(code **)(*param_6 + 0x18))(param_6);
    if (0 < lVar2) {
      FUN_005123c0(param_6,0);
      uVar1 = (**(code **)(*param_6 + 0x18))(param_6);
      FUN_008e8ed0(local_6ac,0x35,uVar1,param_6[1]);
    }
  }
  FUN_00412e40(&local_6d8,4);
  return;
}


=== decomp 8e8ed0 -> FUN_008e8ed0 @008e8ed0 size=146

undefined8 FUN_008e8ed0(undefined8 *param_1,undefined4 param_2,longlong param_3,longlong param_4)

{
  
  uVar1 = FUN_005123a0(*param_1);
  local_34 = param_2;
  local_30 = param_3;
  (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,&local_34,0xc);
  for (; 0 < param_3; param_3 = param_3 - iVar2) {
    if (param_3 < 0x80000000) {
      iVar2 = (int)param_3;
    }
    else {
      iVar2 = 0x7fffffff;
    }
    (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,param_4,iVar2);
    param_4 = param_4 + iVar2;
  }
  return uVar1;
}


=== decomp 8e8fe0 -> FUN_008e8fe0 @008e8fe0 size=373

void FUN_008e8fe0(undefined8 *param_1,undefined4 param_2,longlong param_3)

{
  
  local_40 = 0;
  local_34 = param_2;
  if ((*(byte *)(param_1 + 1) & 1) == 0) {
    if ((*(byte *)(param_1 + 1) & 2) == 0) {
      FUN_00414200(&local_40,param_3,0);
    }
    else {
      FUN_0041c420(&local_40,param_3);
    }
    iVar2 = 0;
    if (local_40 != 0) {
      iVar2 = *(int *)(local_40 + -4);
    }
    local_30 = (longlong)iVar2;
    (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,&local_34,0xc);
    iVar1 = 1;
    iVar2 = (int)local_30;
    if (0 < (int)local_30) {
      do {
        lVar3 = FUN_00413770(&local_40);
        (**(code **)(*(longlong *)*param_1 + 0x38))
                  ((longlong *)*param_1,lVar3 + -1 + (longlong)iVar1,1);
        iVar1 = iVar1 + 1;
        iVar2 = iVar2 + -1;
      } while (iVar2 != 0);
    }
  }
  else {
    iVar2 = 0;
    if (param_3 != 0) {
      iVar2 = *(int *)(param_3 + -4);
    }
    local_30 = (longlong)(iVar2 * 2);
    (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,&local_34,0xc);
    for (lVar3 = local_30; 0 < lVar3; lVar3 = lVar3 - iVar2) {
      if (lVar3 < 0x80000000) {
        iVar2 = (int)lVar3;
      }
      else {
        iVar2 = 0x7fffffff;
      }
      (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,param_3,iVar2);
      param_3 = param_3 + iVar2;
    }
  }
  FUN_00412db0(&local_40);
  return;
}


=== decomp 8e8e10 -> FUN_008e8e10 @008e8e10 size=21

void FUN_008e8e10(undefined8 *param_1,undefined8 param_2,undefined1 param_3)

{
  *param_1 = param_2;
  *(undefined1 *)(param_1 + 1) = param_3;
  return;
}


=== decomp 661970 -> FUN_00661970 @00661970 size=74

undefined8 FUN_00661970(undefined8 param_1,undefined8 param_2)

{
  
  local_10 = 0;
  FUN_0043c870(&local_10,param_2);
  FUN_0043c4c0(param_1,local_10,0);
  FUN_00412d60(&local_10);
  return param_1;
}


=== decomp 8ef610 -> FUN_008ef610 @008ef610 size=542

undefined8 FUN_008ef610(undefined8 param_1,undefined8 param_2)

{
  
  local_80 = 0;
  local_30 = 0;
  local_38 = 0;
  local_40 = 0;
  local_48 = 0;
  local_50 = 0;
  local_58 = 0;
  local_60 = 0;
  FUN_004133f0(param_1,param_2);
  FUN_0043c8f0(&local_40,param_2);
  FUN_00661970(&local_38,param_2);
  FUN_0043c5e0(&local_48,param_2);
  FUN_004394e0(&local_30,local_38);
  iVar2 = 0;
  if (local_38 != 0) {
    iVar2 = *(int *)(local_38 + -4);
  }
  bVar1 = false;
  uVar6 = 0;
  do {
    FUN_00413480(&local_50,(&PTR_DAT_01413978)[uVar6]);
    iVar3 = FUN_004150d0(local_50,local_30,1);
    if (iVar3 != 0) {
      uVar7 = 0;
      do {
        FUN_00413480(&local_58,(&PTR_u___s__014139b0)[uVar7]);
        local_78 = local_50;
        local_70 = 0x11;
        FUN_0043dd60(&local_60,local_58,&local_78,0);
        iVar3 = 0;
        if (local_60 != 0) {
          iVar3 = *(int *)(local_60 + -4);
        }
        iVar4 = FUN_004150d0(local_60,local_30,1);
        if (iVar4 == (iVar2 - iVar3) + 1) {
          FUN_00414ec0(&local_80,local_38,1,iVar2 - iVar3);
          FUN_00414da0(param_1,3,local_48,local_80,local_40);
          bVar1 = true;
          break;
        }
        uVar5 = (int)uVar7 + 1;
        uVar7 = (ulonglong)uVar5;
      } while (uVar5 != 9);
      if (bVar1) break;
    }
    uVar5 = (int)uVar6 + 1;
    uVar6 = (ulonglong)uVar5;
  } while (uVar5 != 7);
  FUN_00412d60(&local_80);
  FUN_00412e40(&local_60,7);
  return param_1;
}


