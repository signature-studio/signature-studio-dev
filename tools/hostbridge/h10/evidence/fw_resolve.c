=== decomp 871fe0 -> FUN_00871fe0 @00871fe0 size=1766

undefined8 * FUN_00871fe0(longlong param_1,undefined8 *param_2,int *param_3,int *param_4)

{
  bool bVar1;
  char cVar2;
  int iVar3;
  int iVar4;
  undefined8 uVar5;
  undefined8 uVar6;
  longlong lVar7;
  int iVar8;
  undefined4 uVar9;
  ulonglong in_stack_ffffffffffffff18;
  undefined4 uVar10;
  undefined8 local_b0;
  undefined8 local_a8;
  undefined8 local_a0;
  undefined8 local_98;
  undefined8 local_90;
  longlong local_88;
  undefined8 local_80;
  undefined8 local_78;
  longlong local_70;
  undefined8 local_68;
  undefined8 local_60 [2];
  undefined8 local_50;
  int local_48;
  int local_44;
  undefined8 local_40;
  undefined8 local_38;
  longlong local_30 [2];
  
  local_b0 = 0;
  local_a8 = 0;
  local_98 = 0;
  local_a0 = 0;
  local_90 = 0;
  local_88 = 0;
  local_80 = 0;
  local_78 = 0;
  local_70 = 0;
  local_68 = 0;
  local_60[0] = 0;
  local_30[0] = 0;
  local_38 = 0;
  local_40 = 0;
  local_50 = 0;
  FUN_00411f10(param_2);
  (**(code **)PTR_DAT_008f6868)(param_4,0x1c);
  *param_4 = -1;
  if (((*(longlong *)(param_3 + 1) == 0) && (*(longlong *)(param_3 + 3) == 0)) &&
     (cVar2 = FUN_004378e0(param_3 + 8,PTR_DAT_008f6f28), cVar2 != '\0')) {
    FUN_00411f10(param_2);
    goto LAB_0087268b;
  }
  FUN_00411f10(&local_40);
  iVar3 = *param_3;
  if (5 < iVar3) {
    if (iVar3 - 7U < 2) {
      FUN_00412630(&local_40,L".vst3");
    }
    else if (iVar3 - 9U < 2) {
      FUN_00412630(&local_40,L".component");
    }
    else if (iVar3 - 0xbU < 2) {
      FUN_00412630(&local_40,L".clap");
    }
    goto LAB_008721d4;
  }
  if (iVar3 == 5) {
LAB_00872182:
    FUN_00412630(&local_40,L".dll");
  }
  else if (iVar3 == 0) {
LAB_00872158:
    FUN_00412630(&local_40,L".dll");
  }
  else {
    if (iVar3 == 1) goto LAB_00872182;
    if (iVar3 - 2U < 2) {
      FUN_00412630(&local_40,L".dll");
    }
    else if (iVar3 == 4) goto LAB_00872158;
  }
LAB_008721d4:
  FUN_005d4a40(local_30,*(undefined8 *)(param_3 + 1));
  if (local_30[0] == 0) {
    FUN_00412630(local_30,*(undefined8 *)(param_3 + 3));
  }
  FUN_00413ba0(local_30,local_40);
  uVar10 = (undefined4)(in_stack_ffffffffffffff18 >> 0x20);
  if (*(char *)((longlong)param_3 + 0x31) == '\0') {
    in_stack_ffffffffffffff18 = in_stack_ffffffffffffff18 & 0xffffffff00000000;
    iVar8 = FUN_00773340(0x17,iVar3,*(undefined8 *)(param_3 + 3),param_3 + 8,
                         in_stack_ffffffffffffff18);
    uVar10 = (undefined4)(in_stack_ffffffffffffff18 >> 0x20);
    if (iVar8 == 0x20) {
      local_48 = 0;
      local_44 = 0x10;
    }
    else if (iVar8 == 0x40) {
      local_48 = 0x10;
      local_44 = 0;
    }
    else {
      cVar2 = *(char *)(*(longlong *)(param_1 + 0x5064) + 0x2d);
      if (cVar2 == '\x02') {
        local_48 = 0;
        local_44 = 0x10;
      }
      else if (cVar2 == '\x03') {
        local_48 = 0x10;
        local_44 = 0;
      }
    }
  }
  else if ((char)param_3[0xc] == '\0') {
    local_48 = 0;
    local_44 = 0x10;
  }
  else {
    local_48 = 0x10;
    local_44 = 0;
  }
  iVar8 = local_48;
  FUN_0079e540(local_60,local_30[0],*(undefined8 *)(param_3 + 3),iVar3,CONCAT44(uVar10,param_3[7]),
               param_3 + 8,*(undefined8 *)(param_3 + 0xd));
  FUN_0041b300(&local_50,local_60[0]);
  uVar5 = FUN_00413080(local_50);
  uVar6 = (**(code **)**(undefined8 **)(param_1 + 0xbc))
                    (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),7,(longlong)iVar8
                     ,uVar5);
  FUN_0041b5c0(&local_68,uVar6);
  FUN_0079e850(param_2,local_68,param_4);
  FUN_0043a1f0(&local_70,*param_2);
  iVar3 = local_44;
  if ((local_70 == 0) && (*param_4 == -1)) {
    bVar1 = false;
  }
  else {
    bVar1 = true;
  }
  if (!bVar1) {
    FUN_0079e540(&local_78,local_30[0],*(undefined8 *)(param_3 + 3),*param_3,param_3[7],param_3 + 8,
                 *(undefined8 *)(param_3 + 0xd));
    FUN_0041b300(&local_50,local_78);
    uVar5 = FUN_00413080(local_50);
    uVar6 = (**(code **)**(undefined8 **)(param_1 + 0xbc))
                      (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),7,
                       (longlong)iVar3,uVar5);
    FUN_0041b5c0(&local_80,uVar6);
    FUN_0079e850(param_2,local_80,param_4);
    FUN_0043a1f0(&local_88,*param_2);
    if ((local_88 == 0) && (*param_4 == -1)) {
      bVar1 = false;
    }
    else {
      bVar1 = true;
    }
  }
  uVar10 = (undefined4)((ulonglong)uVar5 >> 0x20);
  if (!bVar1) {
    if (param_3[7] != 0) {
      FUN_005d4a40(&local_90,*(undefined8 *)(param_3 + 3));
      FUN_00437ab0(&local_38,local_90);
      iVar3 = FUN_00796670();
      uVar10 = (undefined4)((ulonglong)uVar5 >> 0x20);
      iVar8 = 0;
      if (-1 < iVar3 + -1) {
        do {
          lVar7 = FUN_00796690(*(undefined8 *)(*(longlong *)PTR_DAT_008f67d8 + 0x148),iVar8);
          FUN_005d4a40(&local_a0,*(undefined8 *)(lVar7 + 0x10));
          FUN_00437ab0(&local_98,local_a0);
          iVar4 = FUN_00413e60(local_98,local_38);
          if (iVar4 != 0) {
            iVar4 = FUN_00746800(lVar7,param_3[7]);
            uVar10 = (undefined4)((ulonglong)uVar5 >> 0x20);
            if (-1 < iVar4) {
              FUN_0043a480(local_30,*(undefined8 *)(lVar7 + 0x10));
              break;
            }
          }
          uVar10 = (undefined4)((ulonglong)uVar5 >> 0x20);
          iVar8 = iVar8 + 1;
          iVar3 = iVar3 + -1;
        } while (iVar3 != 0);
      }
    }
    uVar9 = 1;
    if ((char)param_3[0xc] != '\0') {
      uVar9 = 0x11;
    }
    FUN_0079e540(&local_a8,local_30[0],*(undefined8 *)(param_3 + 3),*param_3,
                 CONCAT44(uVar10,param_3[7]),param_3 + 8,*(undefined8 *)(param_3 + 0xd));
    FUN_0041b300(&local_50,local_a8);
    uVar5 = FUN_00413080(local_50);
    uVar5 = (**(code **)**(undefined8 **)(param_1 + 0xbc))
                      (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),7,uVar9,uVar5);
    FUN_0041b5c0(&local_b0,uVar5);
    FUN_0079e850(param_2,local_b0,param_4);
  }
LAB_0087268b:
  FUN_00411ff0(&local_b0,0xb);
  FUN_00411f60(&local_50);
  FUN_00411ff0(&local_40,3);
  return param_2;
}


=== decomp 79e540 -> FUN_0079e540 @0079e540 size=560

undefined8 *
FUN_0079e540(undefined8 *param_1,undefined8 param_2,longlong param_3,int param_4,int param_5,
            undefined8 param_6,longlong param_7)

{
  char cVar1;
  undefined8 local_58;
  longlong local_50;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  undefined8 local_30;
  undefined1 local_28;
  longlong local_20;
  undefined1 local_18;
  undefined8 local_10;
  
  local_58 = 0;
  local_48 = 0;
  local_50 = 0;
  local_40 = 0;
  local_38 = 0;
  local_10 = 0;
  FUN_004125a0(param_1,param_2);
  if (param_4 != -1) {
    local_30 = *param_1;
    local_28 = 0x11;
    local_20 = CONCAT44(local_20._4_4_,param_4);
    local_18 = 0;
    FUN_0043ad90(&local_10,L"%s|class=%d",&local_30,1);
    FUN_004125a0(param_1,local_10);
  }
  if (param_3 != 0) {
    local_30 = *param_1;
    local_28 = 0x11;
    local_18 = 0x11;
    local_20 = param_3;
    FUN_0043ad90(&local_38,L"%s|name=%s",&local_30,1);
    FUN_004125a0(param_1,local_38);
  }
  if (param_5 != 0) {
    local_30 = *param_1;
    local_28 = 0x11;
    local_20 = CONCAT44(local_20._4_4_,param_5);
    local_18 = 0;
    FUN_0043ad90(&local_40,L"%s|vstid=%d",&local_30,1);
    FUN_004125a0(param_1,local_40);
  }
  cVar1 = IsEqualGUID(param_6,PTR_DAT_008f6f18);
  if (cVar1 == '\0') {
    local_30 = *param_1;
    local_28 = 0x11;
    FUN_00437860(&local_50,param_6);
    local_20 = local_50;
    local_18 = 0x11;
    FUN_0043ad90(&local_48,L"%s|guid=%s",&local_30,1);
    FUN_004125a0(param_1,local_48);
  }
  if (param_7 != 0) {
    local_30 = *param_1;
    local_28 = 0x11;
    local_20 = param_7;
    local_18 = 0x11;
    FUN_0043ad90(&local_58,L"%s|id=%s",&local_30,1);
    FUN_004125a0(param_1,local_58);
  }
  FUN_00411ff0(&local_58,5);
  FUN_00411f10(&local_10);
  return param_1;
}


=== decomp 79e850 -> FUN_0079e850 @0079e850 size=897

undefined8 FUN_0079e850(undefined8 param_1,undefined8 param_2,undefined4 *param_3)

{
  int iVar1;
  undefined4 uVar2;
  undefined8 local_98;
  undefined8 local_90;
  undefined8 local_88;
  undefined8 local_80;
  undefined8 local_78;
  undefined8 local_70 [2];
  undefined8 local_60;
  undefined8 uStack_58;
  undefined8 local_50;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  longlong local_30 [2];
  
  local_90 = 0;
  local_98 = 0;
  local_80 = 0;
  local_88 = 0;
  local_70[0] = 0;
  local_78 = 0;
  local_30[0] = 0;
  local_38 = 0;
  local_40 = 0;
  local_48 = 0;
  local_50 = 0;
  FUN_00411f10(param_1);
  (**(code **)PTR_DAT_008f6868)(param_3,0x1c);
  *param_3 = 0xffffffff;
  FUN_00412630(local_30,param_2);
  iVar1 = FUN_004140c0(&DAT_0079ec1c,local_30[0],1);
  if (iVar1 == 0) {
    FUN_004125a0(param_1,local_30[0]);
    FUN_00411f10(local_30);
  }
  else {
    FUN_00413eb0(param_1,local_30[0],1,iVar1 + -1);
    FUN_00413eb0(&local_78,local_30[0],iVar1 + 1,0x7fffffff);
    FUN_004381f0(local_70,local_78);
    FUN_00412630(local_30,local_70[0]);
  }
  while (local_30[0] != 0) {
    iVar1 = FUN_004140c0(&DAT_0079ec1c,local_30[0],1);
    if (iVar1 == 0) {
      FUN_00412630(&local_38,local_30[0]);
      FUN_00411f10(local_30);
    }
    else {
      FUN_00413eb0(&local_38,local_30[0],1,iVar1 + -1);
      FUN_00413eb0(&local_88,local_30[0],iVar1 + 1,0x7fffffff);
      FUN_004381f0(&local_80,local_88);
      FUN_00412630(local_30,local_80);
    }
    iVar1 = FUN_004140c0(&DAT_0079ec2c,local_38,1);
    if (iVar1 == 0) {
      FUN_00412630(&local_50,local_38);
      FUN_00411f10(&local_38);
    }
    else {
      FUN_00413eb0(&local_50,local_38,1,iVar1 + -1);
      FUN_00413eb0(&local_98,local_38,iVar1 + 1,0x7fffffff);
      FUN_004381f0(&local_90,local_98);
      FUN_00412630(&local_38,local_90);
    }
    FUN_00437ab0(&local_40,local_50);
    FUN_00412630(&local_48,local_38);
    iVar1 = FUN_00413e60(local_40,L"class");
    if (iVar1 == 0) {
      uVar2 = FUN_00438fe0(local_48,0xffffffff);
      *param_3 = uVar2;
    }
    else {
      iVar1 = FUN_00413e60(local_40,L"magic");
      if (iVar1 == 0) {
        uVar2 = FUN_00438fe0(local_48,0);
        param_3[1] = uVar2;
      }
      else {
        iVar1 = FUN_00413e60(local_40,L"guid");
        if (iVar1 == 0) {
          FUN_00437720(&local_60,local_48);
          *(undefined8 *)(param_3 + 2) = local_60;
          *(undefined8 *)(param_3 + 4) = uStack_58;
        }
      }
    }
  }
  FUN_00411ff0(&local_98,6);
  FUN_00411ff0(&local_50,5);
  return param_1;
}


