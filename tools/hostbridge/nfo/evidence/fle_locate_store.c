=== decomp 8f05d0 -> FUN_008f05d0 @008f05d0 size=201

undefined8 * FUN_008f05d0(undefined8 *param_1,undefined8 param_2,undefined8 param_3,char param_4)

{
  
  local_10 = 0;
  FUN_004133f0(param_1,param_2);
  FUN_00662680(param_1);
  FUN_00414bb0(param_1,L"Installed\\");
  if (param_4 == '\0') {
    FUN_00414bb0(param_1,L"Generators\\");
    uVar1 = 3;
  }
  else {
    FUN_00414bb0(param_1,L"Effects\\");
    uVar1 = 2;
  }
  FUN_008f0300(&local_10,uVar1);
  FUN_00414da0(param_1,4,*param_1,local_10,param_3,L".FST");
  FUN_00412d60(&local_10);
  return param_1;
}


=== decomp 8f15a0 -> FUN_008f15a0 @008f15a0 size=236

undefined8 FUN_008f15a0(undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  
  local_38 = 0;
  local_30 = 0;
  local_20[0] = 0;
  local_28 = 0;
  FUN_00413480(local_20,param_2);
  FUN_00662680(local_20);
  FUN_00414c70(&local_28,local_20[0],L"Installed\\");
  FUN_004394e0(&local_30,local_28);
  uVar1 = local_30;
  FUN_004394e0(&local_38,param_3);
  iVar2 = FUN_004150d0(uVar1,local_38,1);
  if (iVar2 < 1) {
    FUN_004133f0(param_1,param_3);
  }
  else {
    iVar3 = 0;
    if (local_28 != 0) {
      iVar3 = *(int *)(local_28 + -4);
    }
    FUN_00414ec0(param_1,param_3,iVar2 + iVar3,0x7fffffff);
  }
  FUN_00412e40(&local_38,4);
  return param_1;
}


=== decomp 8f5d00 -> FUN_008f5d00 @008f5d00 size=287

undefined8 FUN_008f5d00(longlong param_1,undefined8 param_2,undefined8 param_3,char param_4)

{
  
  local_30[0] = 0;
  local_10 = 0;
  local_18 = 0;
  local_20 = 0;
  FUN_004133f0(param_2,*(undefined8 *)(param_1 + 0x2c));
  FUN_00439550(&local_10,*(undefined8 *)(param_1 + 0x2c));
  FUN_00439550(&local_18,param_3);
  uVar4 = local_18;
  iVar1 = FUN_004150d0(local_18,local_10,1);
  if (iVar1 != 0) {
    uVar5 = (undefined7)((ulonglong)uVar4 >> 8);
    if (param_4 == '\0') {
      uVar2 = 0;
      uVar3 = (undefined4)CONCAT71(uVar5,1);
    }
    else if (param_4 == '\x01') {
      uVar2 = 1;
      uVar3 = 0;
    }
    else {
      uVar2 = 2;
      uVar3 = (undefined4)CONCAT71(uVar5,2);
    }
    FUN_008f04e0(&local_20,*(undefined4 *)(param_1 + 0x34),uVar2,uVar3);
    FUN_0043c870(local_30,*(undefined8 *)(param_1 + 0x2c));
    FUN_00414da0(param_2,4,param_3,L"Installed\\",local_20,local_30[0]);
  }
  FUN_00412d60(local_30);
  FUN_00412e40(&local_20,3);
  return param_2;
}


=== decomp 9155c0 -> FUN_009155c0 @009155c0 size=253

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_009155c0(longlong param_1,undefined8 param_2)

{
  double dVar3;
  
  local_38 = 0;
  local_30[0] = 0;
  local_20[0] = 0;
  FUN_00414c70(local_20,param_2,L"Installed\\");
  FUN_00414c70(local_30,local_20[0],L"VerifiedIDs.nfo");
  cVar1 = FUN_00819110(local_30[0]);
  if (cVar1 != '\0') {
    dVar3 = (double)FUN_00442c30();
    if (*(longlong *)(param_1 + 0x18) == 0) {
      FUN_00414c70(&local_38,local_20[0],L"VerifiedIDs.nfo");
      uVar2 = FUN_00913450(PTR_DAT_009103e8,1,local_38,1);
      *(undefined8 *)(param_1 + 0x18) = uVar2;
      *(double *)(param_1 + 0x20) = dVar3;
    }
    if (_DAT_009156c0 < dVar3 - *(double *)(param_1 + 0x20)) {
      FUN_00913720(*(undefined8 *)(param_1 + 0x18));
      *(double *)(param_1 + 0x20) = dVar3;
    }
  }
  FUN_00412e40(&local_38,2);
  FUN_00412d60(local_20);
  return;
}


=== decomp 915750 -> FUN_00915750 @00915750 size=2275

/* WARNING: Type propagation algorithm not settling */

longlong *
FUN_00915750(undefined8 *param_1,longlong *param_2,undefined8 param_3,longlong param_4,
            undefined8 param_5,byte param_6,int param_7)

{
  
  local_b0 = auStack_1a8;
  local_160 = 0;
  local_150 = 0;
  local_158 = 0;
  local_148 = 0;
  local_130 = 0;
  local_108 = 0;
  local_100 = 0;
  local_f8 = 0;
  local_f0 = 0;
  local_b8 = 0;
  local_58[1] = 0;
  local_58[0] = 0;
  local_a0 = 0;
  FUN_00412d60(param_2);
  local_e8 = param_5;
  local_e0 = 0x11;
  local_d8 = (uint)param_6;
  local_d0 = 0;
  local_c8 = param_7;
  local_c0 = 0;
  FUN_0043dd60(&local_b8,L"Locate: info=%s bits=%d pc=%d",&local_e8,2);
  (**(code **)*param_1)(param_1,local_b8);
  local_38 = FUN_00511fe0(PTR_PTR_004cf268,1);
  local_28 = FUN_008f6ad0(PTR_DAT_008f1b10,1);
  local_188 = L".Plugins.ini";
  FUN_00414da0(&local_f0,3,param_3,L"Installed\\");
  uVar4 = FUN_005a8880(PTR_PTR_005a2f90,1,local_f0);
  param_1[5] = uVar4;
  if ((param_7 != 2) && (param_7 != 3)) {
    FUN_0090f100(param_4);
  }
  local_178 = FUN_00412d60(&local_a0);
  local_188 = (wchar_t *)(local_28 + 0x20);
  local_180 = local_28 + 0x24;
  FUN_00914ca0(&local_f8,param_5,local_28 + 8,local_28 + 0x18);
  FUN_004133f0(local_28 + 0x10,local_f8);
  if (*(longlong *)(local_28 + 8) == 0) {
    FUN_00661970(&local_100,*(undefined8 *)(local_28 + 0x10));
    FUN_004133f0(local_28 + 8,local_100);
  }
  if ((*(int *)(local_28 + 0x18) == -1) && (param_7 != -1)) {
    *(int *)(local_28 + 0x18) = param_7;
  }
  if (*(int *)(local_28 + 0x18) == -1) {
    uVar3 = FUN_008f0c20(*(undefined8 *)(local_28 + 0x10));
    *(undefined4 *)(local_28 + 0x18) = uVar3;
  }
  FUN_004133f0(local_28 + 0x60,local_a0);
  *(byte *)(local_28 + 0x1e) = param_6;
  local_128 = *(undefined8 *)(local_28 + 0x10);
  local_120 = 0x11;
  local_118 = *(undefined8 *)(local_28 + 8);
  local_110 = 0x11;
  FUN_0043dd60(&local_108,L"FileInfo: fname=%s name=%s",&local_128,1);
  (**(code **)*param_1)(param_1,local_108);
  uVar6 = (ulonglong)*(uint *)(local_28 + 0x18);
  local_68 = FUN_00902770(*(undefined8 *)PTR_DAT_015e3e88,uVar6);
  if ((local_68 == 0) || ((*(ushort *)(local_68 + 0x1c) & 2) == 0)) goto LAB_00915bc4;
  local_91 = DAT_0091621a;
  if (param_7 == -1) {
LAB_00915b5a:
    local_91 = DAT_0091621a | 1;
  }
  else {
    if (*(uint *)(local_28 + 0x18) < 0x10) {
      uVar5 = (int)CONCAT62((int6)(uVar6 >> 0x10),1) << ((byte)*(uint *)(local_28 + 0x18) & 0x1f);
      uVar6 = (ulonglong)uVar5;
      bVar7 = ((ushort)uVar5 & DAT_0091621b) != 0;
    }
    else {
      bVar7 = false;
    }
    if (bVar7) goto LAB_00915b5a;
  }
  if (param_7 == -1) {
LAB_00915b9b:
    local_91 = local_91 | 2;
  }
  else {
    if (*(uint *)(local_28 + 0x18) < 0x10) {
      bVar7 = ((ushort)((int)CONCAT62((int6)(uVar6 >> 0x10),1) <<
                       ((byte)*(uint *)(local_28 + 0x18) & 0x1f)) & DAT_0091621d) != 0;
    }
    else {
      bVar7 = false;
    }
    if (bVar7) goto LAB_00915b9b;
  }
  FUN_0090e5e0(param_4,local_68,local_38,local_91);
LAB_00915bc4:
  local_188 = (wchar_t *)local_68;
  local_180 = local_38;
  local_178 = local_28;
  local_170 = local_84;
  FUN_00916280(param_1,param_2,param_3,*(undefined8 *)(param_4 + 0x18));
  local_140 = *param_2;
  local_138 = 0x11;
  FUN_0043dd60(&local_130,L"LocateByFormat result = %s",&local_140,0);
  (**(code **)*param_1)(param_1,local_130);
  if ((((local_68 == 0) || (*param_2 != 0)) || (local_84[0] == 0xffffffff)) ||
     ((*(ushort *)(local_68 + 0x1c) & 2) != 0)) {
    if (*param_2 == 0) {
      FUN_0043c4c0(&local_150,*(undefined8 *)(local_28 + 0x10),L".NFO");
      FUN_00414c70(&local_158,param_3,L"Installed\\");
      local_188 = (wchar_t *)((ulonglong)local_188 & 0xffffffff00000000);
      FUN_008197f0(local_58,local_150,local_158,FUN_00914a10);
      if (local_58[0] != 0) {
        local_90 = FUN_00910cd0(local_58[0],param_3,*(undefined8 *)(param_4 + 0x18),1);
        cVar2 = FUN_008f5cd0(local_90,*(undefined4 *)(local_28 + 0x18),
                             *(undefined1 *)(local_28 + 0x1e),&local_60);
        if (cVar2 != '\0') {
          cVar2 = FUN_00819110(*(undefined8 *)(local_60 + 0x10));
          if (cVar2 == '\0') {
            FUN_004133f0(local_28 + 0x10,*(undefined8 *)(local_60 + 0x44));
          }
          else {
            FUN_004133f0(param_2,*(undefined8 *)(local_60 + 0x10));
          }
        }
        uVar4 = local_90;
        local_a8 = local_90;
        local_90 = 0;
        FUN_0040faa0(uVar4);
      }
    }
    if (*param_2 == 0) {
      FUN_008ef610(local_58 + 1,*(undefined8 *)(local_28 + 0x10));
      local_188 = (wchar_t *)local_68;
      local_180 = local_38;
      local_178 = local_28;
      local_170 = local_84;
      FUN_00916280(param_1,param_2,param_3,*(undefined8 *)(param_4 + 0x18));
    }
    lVar1 = local_28;
    local_20 = local_28;
    local_28 = 0;
    FUN_0040faa0(lVar1);
    uVar4 = local_38;
    local_30 = local_38;
    local_38 = 0;
    FUN_0040faa0(uVar4);
    local_40 = param_1 + 5;
    local_58[2] = *local_40;
    *local_40 = 0;
    FUN_0040faa0(local_58[2]);
    local_68 = FUN_00902770(*(undefined8 *)PTR_DAT_015e3e88,local_84[0]);
    if ((local_68 != 0) && ((*(ushort *)(local_68 + 0x1c) & 2) != 0)) {
      if ((*(ushort *)(local_68 + 0x1c) & 0x100) == 0) {
        cVar2 = FUN_00819110(*param_2);
        if (cVar2 == '\0') {
          FUN_00412d60(param_2);
          local_84[0] = 0xffffffff;
        }
      }
      else {
        cVar2 = FUN_0043bb50(*param_2,1);
        if (cVar2 == '\0') {
          FUN_00412d60(param_2);
          local_84[0] = 0xffffffff;
        }
      }
    }
    FUN_00915220(&local_160,*param_2,local_84);
    FUN_004133f0(param_2,local_160);
  }
  else {
    FUN_00915220(&local_148,*param_2,local_84);
    FUN_004133f0(param_2,local_148);
    FUN_00916040(0,local_b0);
  }
  FUN_00412e40(&local_160,4);
  FUN_00412d60(&local_130);
  FUN_00412e40(&local_108,4);
  FUN_00412d60(&local_b8);
  FUN_00412d60(&local_a0);
  FUN_00412e40(local_58,2);
  return param_2;
}


=== decomp 916490 -> FUN_00916490 @00916490 size=321

undefined8 FUN_00916490(longlong param_1,undefined8 param_2,undefined4 param_3,undefined1 param_4)

{
  
  local_30 = auStack_68;
  local_38 = 0;
  local_18 = 0;
  FUN_0043c4c0(&local_38,param_2,0);
  local_48 = 1;
  local_10 = FUN_00911e10(*(undefined8 *)(*(longlong *)(param_1 + 0xc0) + 0x28),local_38,
                          *(undefined8 *)(param_1 + 0xd0),*(undefined8 *)(param_1 + 0xd8));
  if (local_10 != 0) {
    cVar1 = FUN_008f5cd0(local_10,param_3,param_4,&local_20);
    if (cVar1 != '\0') {
      local_21 = '\x01';
      if ((*(longlong *)(param_1 + 0xe0) != 0) &&
         ((*(ushort *)(*(longlong *)(param_1 + 0xe0) + 0x1c) & 2) != 0)) {
        if ((*(ushort *)(*(longlong *)(param_1 + 0xe0) + 0x1c) & 0x100) == 0) {
          local_21 = FUN_00819110(*(undefined8 *)(local_20 + 0x10));
        }
        else {
          local_21 = FUN_0043bb50(*(undefined8 *)(local_20 + 0x10),1);
        }
      }
      if (local_21 != '\0') {
        local_18 = FUN_008f6b90(PTR_DAT_008f1b10,1,local_20);
      }
    }
  }
  FUN_0040faa0(local_10);
  FUN_00412d60(&local_38);
  return local_18;
}


=== decomp 916710 -> FUN_00916710 @00916710 size=1471

undefined8
FUN_00916710(longlong param_1,undefined8 param_2,undefined8 ****param_3,undefined8 param_4,
            longlong *param_5,longlong param_6,undefined4 *param_7)

{
  
  local_70 = auStack_b8;
  local_88 = 0;
  local_80 = 0;
  local_78 = 0;
  local_38 = 0;
  local_40 = 0;
  local_48 = (undefined8 ****)0x0;
  local_50 = 0;
  FUN_00412d60(param_2);
  (**(code **)PTR_DAT_015e0a48)(param_7,0x1c);
  *param_7 = 0xffffffff;
  local_68 = 0;
  local_98 = L"Plugin IDs\\";
  FUN_00414da0(&local_38,3,param_3,L"Installed\\");
  FUN_009155c0(param_1,param_3);
  if ((local_68 == 0) && (*(longlong *)(param_1 + 0x18) != 0)) {
    (**(code **)(*param_5 + 0x50))(param_5,&local_78,param_6);
    FUN_008f16d0(&local_50,local_78,*(undefined4 *)(param_6 + 0x18),*(undefined1 *)(param_6 + 0x1e))
    ;
    param_3 = &local_48;
    FUN_00913d40(*(undefined8 *)(param_1 + 0x18),param_3,local_50);
    if ((undefined8 ****)local_48 == (undefined8 ****)0x0) {
      (**(code **)(*param_5 + 0x50))(param_5,&local_80,param_6);
      param_3 = &local_48;
      FUN_00913d40(*(undefined8 *)(param_1 + 0x18),param_3,local_80);
    }
    if ((undefined8 ****)local_48 != (undefined8 ****)0x0) {
      param_3 = (undefined8 ****)local_48;
      local_68 = FUN_00916490(auStack_b8,local_48,*(undefined4 *)(param_6 + 0x18),
                              *(undefined1 *)(param_6 + 0x1e));
    }
  }
  if (local_68 == 0) {
    param_3 = (undefined8 ****)(ulonglong)*(uint *)(param_6 + 0x18);
    local_98 = (wchar_t *)(param_6 + 0x24);
    FUN_00914a20(&local_40,param_3,*(undefined1 *)(param_6 + 0x1e),*(undefined4 *)(param_6 + 0x20));
    if (local_40 != 0) {
      uVar4 = local_38;
      FUN_00414c70(&local_48,local_38,local_40);
      cVar1 = FUN_00819110(local_48);
      if (cVar1 == '\0') {
        if (*(uint *)(param_6 + 0x18) < 0x10) {
          uVar3 = (int)CONCAT62((int6)(uVar4 >> 0x10),1) << ((byte)*(uint *)(param_6 + 0x18) & 0x1f)
          ;
          uVar4 = (ulonglong)uVar3;
          bVar8 = ((ushort)uVar3 & DAT_00916d68) != 0;
        }
        else {
          bVar8 = false;
        }
        if (!bVar8) {
          uVar4 = 0;
          cVar1 = (**(code **)(*param_5 + 0x28))(param_5,7);
          if (cVar1 != '\0') {
            local_60 = *(undefined8 *)(param_6 + 0x24);
            uStack_58 = *(undefined8 *)(param_6 + 0x2c);
            puVar5 = PTR_DAT_015e1f60;
            cVar1 = IsEqualGUID(&local_60,PTR_DAT_015e1f60);
            if (cVar1 != '\0') {
              if (*(uint *)(param_6 + 0x18) < 8) {
                bVar8 = ((byte)((int)CONCAT71((int7)((ulonglong)puVar5 >> 8),1) <<
                               ((byte)*(uint *)(param_6 + 0x18) & 0x1f)) & DAT_00916d6a) != 0;
              }
              else {
                bVar8 = false;
              }
              if (bVar8) {
                FUN_008f1110(*(undefined8 *)(param_6 + 8),*(undefined4 *)(param_6 + 0x20),&local_60,
                             0);
              }
            }
            local_98 = (wchar_t *)&local_60;
            FUN_00914a20(&local_88,7,*(undefined1 *)(param_6 + 0x1e),0);
            uVar4 = local_38;
            FUN_00414c70(&local_48,local_38,local_88);
          }
        }
      }
      if (*(uint *)(param_6 + 0x18) < 0x10) {
        bVar8 = ((ushort)((int)CONCAT62((int6)(uVar4 >> 0x10),1) <<
                         ((byte)*(uint *)(param_6 + 0x18) & 0x1f)) & DAT_00916d6b) != 0;
      }
      else {
        bVar8 = false;
      }
      uVar2 = FUN_008f0ab0(bVar8,8);
      param_3 = (undefined8 ****)local_48;
      local_68 = FUN_00916490(auStack_b8,local_48,uVar2,*(undefined1 *)(param_6 + 0x1e));
    }
  }
  if ((local_68 == 0) && (*(longlong *)(param_1 + 0x18) != 0)) {
    if (*(uint *)(param_6 + 0x18) < 0x10) {
      bVar8 = ((ushort)((int)CONCAT62((int6)((ulonglong)param_3 >> 0x10),1) <<
                       ((byte)*(uint *)(param_6 + 0x18) & 0x1f)) & DAT_00916d68) != 0;
    }
    else {
      bVar8 = false;
    }
    if (!bVar8) {
      uVar6 = 0;
      cVar1 = (**(code **)(*param_5 + 0x28))(param_5,7);
      if (cVar1 != '\0') {
        uVar6 = CONCAT71((int7)((ulonglong)uVar6 >> 8),1);
        local_30 = FUN_008f6b90(PTR_DAT_008f1b10,uVar6,param_6);
        if (*(uint *)(local_30 + 0x18) < 0x10) {
          bVar8 = ((ushort)((int)CONCAT62((int6)((ulonglong)uVar6 >> 0x10),1) <<
                           ((byte)*(uint *)(local_30 + 0x18) & 0x1f)) & DAT_00916d6b) != 0;
        }
        else {
          bVar8 = false;
        }
        uVar2 = FUN_008f0ab0(bVar8,8);
        *(undefined4 *)(local_30 + 0x18) = uVar2;
        lVar7 = local_30;
        local_68 = FUN_00916620(auStack_b8,local_30);
        if (local_68 == 0) {
          if (*(uint *)(param_6 + 0x18) < 8) {
            bVar8 = ((byte)((int)CONCAT71((int7)((ulonglong)lVar7 >> 8),1) <<
                           ((byte)*(uint *)(param_6 + 0x18) & 0x1f)) & DAT_00916d6a) != 0;
          }
          else {
            bVar8 = false;
          }
          if (bVar8) {
            FUN_008f1110(*(undefined8 *)(local_30 + 8),*(undefined4 *)(local_30 + 0x20),
                         local_30 + 0x24,0);
            local_68 = FUN_00916620(auStack_b8,local_30);
          }
        }
        FUN_0040faa0(local_30);
      }
    }
  }
  if (local_68 != 0) {
    *param_7 = *(undefined4 *)(local_68 + 0x18);
    param_7[1] = *(undefined4 *)(local_68 + 0x20);
    *(undefined8 *)(param_7 + 2) = *(undefined8 *)(local_68 + 0x24);
    *(undefined8 *)(param_7 + 4) = *(undefined8 *)(local_68 + 0x2c);
    *(undefined1 *)(param_7 + 6) = *(undefined1 *)(local_68 + 0x1e);
    FUN_004133f0(param_2,*(undefined8 *)(local_68 + 0x10));
    FUN_0040faa0(local_68);
  }
  FUN_00412e40(&local_88,3);
  FUN_00412e40(&local_50,4);
  return param_2;
}


=== decomp 916280 -> FUN_00916280 @00916280 size=454

longlong *
FUN_00916280(undefined8 param_1,longlong *param_2,undefined8 param_3,undefined8 param_4,
            longlong *param_5,undefined8 param_6,longlong param_7,int *param_8)

{
  
  local_20 = 0;
  FUN_00412d60(param_2);
  (**(code **)PTR_DAT_015e0a48)(param_8,0x1c);
  *param_8 = -1;
  if (param_5 != (longlong *)0x0) {
    if ((*(ushort *)((longlong)param_5 + 0x1c) & 0x20) == 0) {
      bVar2 = false;
    }
    else {
      FUN_00439550(&local_20,*(undefined8 *)(param_7 + 0x10));
      iVar1 = FUN_004150d0(L"waveshell",local_20,1);
      bVar2 = iVar1 == 0;
    }
    if (((*param_2 == 0) && (*param_8 == -1)) && (bVar2)) {
      (**(code **)(*param_5 + 0x58))(param_5,param_2,param_6,param_7,param_8);
    }
    if (((*param_2 == 0) && (*param_8 == -1)) &&
       ((*(ushort *)((longlong)param_5 + 0x1c) & 0x10) != 0)) {
      FUN_00916710(param_1,param_2,param_3,param_4,param_5,param_7,param_8);
    }
    if (((*param_2 == 0) && (*param_8 == -1)) && (!bVar2)) {
      (**(code **)(*param_5 + 0x58))(param_5,param_2,param_6,param_7,param_8);
    }
  }
  FUN_00412d60(&local_20);
  return param_2;
}


=== decomp 916620 -> FUN_00916620 @00916620 size=197

undefined8 FUN_00916620(longlong param_1,longlong param_2)

{
  
  local_30 = 0;
  local_20[0] = 0;
  local_28 = 0;
  plVar1 = (longlong *)FUN_00902770(*(undefined8 *)PTR_DAT_015e3e88,8);
  (**(code **)(*plVar1 + 0x50))(plVar1,&local_30,param_2);
  FUN_008f16d0(local_20,local_30,*(undefined4 *)(param_2 + 0x18),*(undefined1 *)(param_2 + 0x1e));
  FUN_00913d40(*(undefined8 *)(*(longlong *)(param_1 + 0xc0) + 0x18),&local_28,local_20[0]);
  uVar2 = FUN_00916490(param_1,local_28,*(undefined4 *)(param_2 + 0x18),
                       *(undefined1 *)(param_2 + 0x1e));
  FUN_00412e40(&local_30,3);
  return uVar2;
}


=== decomp 914a20 -> FUN_00914a20 @00914a20 size=499

undefined8 FUN_00914a20(undefined8 param_1,int param_2,char param_3,int param_4,undefined8 param_5)

{
  
  local_48 = 0;
  local_40 = 0;
  local_38 = 0;
  local_30[0] = 0;
  local_20[0] = 0;
  FUN_00412d60(local_20);
  if ((param_2 == 0) || (param_2 == 4)) {
    if (param_4 != 0) {
      FUN_0043a7e0(local_30,param_4);
      FUN_00414c70(local_20,L"VST\\",local_30[0]);
    }
  }
  else if (param_2 - 7U < 2) {
    cVar3 = IsEqualGUID(param_5,PTR_DAT_015e1f60);
    if (cVar3 == '\0') {
      FUN_00439300(&local_38,param_5);
      FUN_00414c70(local_20,L"VST3\\",local_38);
    }
  }
  if (local_20[0] != 0) {
    if (param_3 == '\x03') {
      FUN_00439550(&local_40,*(undefined8 *)(PTR_DAT_015e1818 + 8));
      uVar2 = local_40;
      FUN_00439550(&local_48,local_20[0]);
      iVar4 = FUN_004150d0(uVar2,local_48,1);
      iVar5 = 0;
      if (local_20[0] != 0) {
        iVar5 = *(int *)(local_20[0] + -4);
      }
      lVar1 = *(longlong *)(PTR_DAT_015e1818 + 8);
      iVar6 = 0;
      if (lVar1 != 0) {
        iVar6 = *(int *)(lVar1 + -4);
      }
      if (iVar4 == iVar5 - iVar6) {
        iVar5 = 0;
        if (local_20[0] != 0) {
          iVar5 = *(int *)(local_20[0] + -4);
        }
        iVar4 = 0;
        if (lVar1 != 0) {
          iVar4 = *(int *)(lVar1 + -4);
        }
        FUN_00414ec0(local_20,local_20[0],1,iVar5 - iVar4);
      }
    }
    FUN_00414da0(local_20,3,local_20[0],
                 *(undefined8 *)(PTR_DAT_015e1818 + (longlong)(param_3 == '\x03') * 8),L".NFO");
  }
  FUN_004133f0(param_1,local_20[0]);
  FUN_00412e40(&local_48,4);
  FUN_00412d60(local_20);
  return param_1;
}


=== decomp 914ca0 -> FUN_00914ca0 @00914ca0 size=1017

undefined8
FUN_00914ca0(undefined8 param_1,undefined8 param_2,undefined8 param_3,undefined4 *param_4,
            undefined4 *param_5,undefined8 *param_6,undefined8 *param_7)

{
  
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
  *param_7 = 0;
  *param_4 = 0xffffffff;
  *param_5 = 0;
  puVar1 = (undefined8 *)(PTR_DAT_015e1f60 + 8);
  *param_6 = *(undefined8 *)PTR_DAT_015e1f60;
  param_6[1] = *puVar1;
  FUN_00412d60(param_3);
  FUN_00413480(local_30,param_2);
  iVar2 = FUN_004150d0(&DAT_009150e0,local_30[0],1);
  if (iVar2 == 0) {
    FUN_004133f0(param_1,local_30[0]);
    FUN_00412d60(local_30);
  }
  else {
    FUN_00414ec0(param_1,local_30[0],1,iVar2 + -1);
    FUN_00414ec0(&local_78,local_30[0],iVar2 + 1,0x7fffffff);
    FUN_00439c90(local_70,local_78);
    FUN_00413480(local_30,local_70[0]);
  }
  while (local_30[0] != 0) {
    iVar2 = FUN_004150d0(&DAT_009150e0,local_30[0],1);
    if (iVar2 == 0) {
      FUN_00413480(&local_38,local_30[0]);
      FUN_00412d60(local_30);
    }
    else {
      FUN_00414ec0(&local_38,local_30[0],1,iVar2 + -1);
      FUN_00414ec0(&local_88,local_30[0],iVar2 + 1,0x7fffffff);
      FUN_00439c90(&local_80,local_88);
      FUN_00413480(local_30,local_80);
    }
    iVar2 = FUN_004150d0(&DAT_009150f0,local_38,1);
    if (iVar2 == 0) {
      FUN_00413480(&local_50,local_38);
      FUN_00412d60(&local_38);
    }
    else {
      FUN_00414ec0(&local_50,local_38,1,iVar2 + -1);
      FUN_00414ec0(&local_98,local_38,iVar2 + 1,0x7fffffff);
      FUN_00439c90(&local_90,local_98);
      FUN_00413480(&local_38,local_90);
    }
    FUN_00439550(&local_40,local_50);
    FUN_00413480(&local_48,local_38);
    iVar2 = FUN_00414e70(local_40,L"class");
    if (iVar2 == 0) {
      uVar3 = FUN_0043aae0(local_48,0xffffffff);
      *param_4 = uVar3;
    }
    else {
      iVar2 = FUN_00414e70(local_40,L"name");
      if (iVar2 == 0) {
        FUN_004133f0(param_3,local_48);
      }
      else {
        iVar2 = FUN_00414e70(local_40,L"guid");
        if (iVar2 == 0) {
          FUN_004391c0(&local_60,local_48);
          *param_6 = local_60;
          param_6[1] = uStack_58;
        }
        else {
          iVar2 = FUN_00414e70(local_40,L"vstid");
          if (iVar2 == 0) {
            uVar3 = FUN_0043aae0(local_48,0);
            *param_5 = uVar3;
          }
          else {
            iVar2 = FUN_00414e70(local_40,&LAB_00915160);
            if (iVar2 == 0) {
              FUN_004133f0(param_7,local_48);
            }
          }
        }
      }
    }
  }
  FUN_00412e40(&local_98,6);
  FUN_00412e40(&local_50,5);
  return param_1;
}


=== decomp 915220 -> FUN_00915220 @00915220 size=390

undefined8 * FUN_00915220(undefined8 *param_1,longlong param_2,int *param_3)

{
  
  local_40 = 0;
  local_48 = 0;
  local_38 = 0;
  local_10 = 0;
  if ((param_2 == 0) && (*param_3 == -1)) {
    FUN_00412d60(param_1);
  }
  else {
    FUN_004133f0(param_1,param_2);
    if (*param_3 != -1) {
      local_30 = *param_1;
      local_28 = 0x11;
      local_20 = CONCAT44(local_20._4_4_,*param_3);
      local_18 = 0;
      FUN_0043dd60(&local_10,L"%s|class=%d",&local_30,1);
      FUN_004133f0(param_1,local_10);
      if (param_3[1] != 0) {
        local_30 = *param_1;
        local_28 = 0x11;
        local_20 = CONCAT44(local_20._4_4_,param_3[1]);
        local_18 = 0;
        FUN_0043dd60(&local_38,L"%s|magic=%d",&local_30,1);
        FUN_004133f0(param_1,local_38);
      }
      cVar1 = IsEqualGUID(param_3 + 2,PTR_DAT_015e1f60);
      if (cVar1 == '\0') {
        local_30 = *param_1;
        local_28 = 0x11;
        FUN_00439300(&local_48,param_3 + 2);
        local_20 = local_48;
        local_18 = 0x11;
        FUN_0043dd60(&local_40,L"%s|guid=%s",&local_30,1);
        FUN_004133f0(param_1,local_40);
      }
    }
  }
  FUN_00412e40(&local_48,3);
  FUN_00412d60(&local_10);
  return param_1;
}


=== decomp 90f100 -> FUN_0090f100 @0090f100 size=1439

void FUN_0090f100(longlong param_1)

{
  
  local_e0 = auStack_128;
  local_e8 = 0;
  local_f0 = 0;
  local_28 = 0;
  local_30 = 0;
  local_38 = 0;
  local_40 = 0;
  local_48 = 0;
  FUN_00415610(&local_80,PTR_DAT_0090b390);
  FUN_00415610(local_90,PTR_DAT_0090b390);
  FUN_00413480(&local_28,L"List");
  FUN_00413480(&local_30,L"path");
  FUN_00413480(&local_38,L"plugclass");
  FUN_00413480(&local_40,L"custom");
  FUN_00413480(&local_48,L"selected");
  local_20 = (longlong *)FUN_0090d9a0(PTR_PTR_0090d698,1);
  (**(code **)(*local_20 + 0x20))(local_20);
  iVar5 = FUN_00907bb0(local_20,L"List");
  if (iVar5 == 0) {
    FUN_0090efb0(auStack_128);
  }
  iVar5 = FUN_00907bb0(local_20,local_28);
  local_f4 = iVar5 + -1;
  local_6c = 0;
  if (-1 < local_f4) {
    do {
      local_f4 = iVar5;
      local_80 = 0;
      _local_78 = 0;
      local_108 = local_6c;
      FUN_00907b60(local_20,&local_f0,local_28,local_30);
      FUN_008f19b0(&local_e8,local_f0,*(undefined8 *)(param_1 + 0x18),L"%FLPath%");
      FUN_00413480(&local_80,local_e8);
      uVar6 = FUN_00907b20(local_20,local_28,local_38,local_6c);
      _local_78 = CONCAT44(stack0xffffffffffffff8c,uVar6);
      uVar3 = FUN_00907ab0(local_20,local_28,local_40,local_6c);
      local_78 = (undefined1  [5])CONCAT14(uVar3,local_78._0_4_);
      uVar3 = FUN_00907ab0(local_20,local_28,local_48,local_6c);
      _local_78 = CONCAT15(uVar3,local_78);
      local_99 = '\0';
      local_9a = '\0';
      uVar7 = (ulonglong)_local_78 & 0xffffffff;
      local_98 = (longlong *)FUN_00902770(*(undefined8 *)PTR_DAT_015e3e88,uVar7);
      if (local_98 != (longlong *)0x0) {
        local_99 = (*(ushort *)((longlong)local_98 + 0x1c) & 0x40) != 0;
        uVar7 = local_80;
        cVar4 = (**(code **)(*local_98 + 0x18))(local_98,local_80);
        local_9a = cVar4 != '\0';
      }
      uVar1 = _local_78;
      if (((local_73 == '\0') || (local_9a != '\0')) && (local_99 != '\0')) {
        uVar3 = 0;
      }
      else {
        uVar3 = 1;
      }
      _local_78 = CONCAT15(uVar3,local_78);
      uVar2 = _local_78;
      local_78._0_4_ = (undefined4)uVar1;
      uVar6 = local_78._0_4_;
      if ((uint)local_78._0_4_ < 8) {
        bVar8 = ((byte)((int)CONCAT71((int7)(uVar7 >> 8),1) << ((byte)uVar1 & 0x1f)) & DAT_0090f816)
                != 0;
      }
      else {
        bVar8 = false;
      }
      _local_78 = uVar2;
      if (bVar8) {
        local_70 = FUN_0090eb80(param_1,uVar6);
        if (-1 < local_70) {
          local_58 = 0;
          uStack_50 = 0;
          local_a8 = *(longlong *)(param_1 + 8);
          uVar7 = (ulonglong)local_70;
          if (*(ulonglong *)(local_a8 + 0x10) <= uVar7) {
            FUN_0047a250(uVar7,*(ulonglong *)(local_a8 + 0x10) - 1,local_a8);
          }
          FUN_00416750(&local_58,*(longlong *)(local_a8 + 8) + uVar7 * 0x10,PTR_DAT_0090b390);
          FUN_00416750(local_90,&local_58,PTR_DAT_0090b390);
          FUN_00415c30(&local_58,PTR_DAT_0090b390);
          local_83 = local_73;
          local_b0 = *(longlong *)(param_1 + 8);
          local_b8 = local_90;
          FUN_0047a5e0(local_b0 + 8,local_b8,(longlong)local_70);
          FUN_00415c30(local_90,PTR_DAT_0090b390);
        }
      }
      else {
        local_70 = FUN_0090ed90(param_1,uVar6,local_80);
        if (local_70 < 0) {
          FUN_0090de30(param_1,&local_80);
        }
        else {
          local_68 = 0;
          uStack_60 = 0;
          local_c0 = *(longlong *)(param_1 + 8);
          uVar7 = (ulonglong)local_70;
          if (*(ulonglong *)(local_c0 + 0x10) <= uVar7) {
            FUN_0047a250(uVar7,*(ulonglong *)(local_c0 + 0x10) - 1,local_c0);
          }
          FUN_00416750(&local_68,*(longlong *)(local_c0 + 8) + uVar7 * 0x10,PTR_DAT_0090b390);
          local_78 = (undefined1  [5])CONCAT14(uStack_60._4_1_,local_78._0_4_);
          FUN_00415c30(&local_68,PTR_DAT_0090b390);
          local_c8 = *(longlong *)(param_1 + 8);
          local_d0 = &local_80;
          FUN_0047a5e0(local_c8 + 8,local_d0,(longlong)local_70);
        }
      }
      FUN_00415c30(&local_80,PTR_DAT_0090b390);
      local_6c = local_6c + 1;
      local_f4 = local_f4 + -1;
      iVar5 = local_f4;
    } while (local_f4 != 0);
  }
  FUN_0040faa0(local_20);
  FUN_0090df00(param_1);
  FUN_00412e40(&local_f0,2);
  FUN_00416230(local_90,PTR_DAT_0090b390,2);
  FUN_00412e40(&local_48,5);
  return;
}


=== decomp ab9f40 -> FUN_00ab9f40 @00ab9f40 size=420

void FUN_00ab9f40(longlong param_1)

{
  
  local_50 = auStack_98;
  local_68 = 0;
  local_58 = 0;
  local_30 = 0;
  local_28 = FUN_00511fe0(PTR_PTR_004cf268,1);
  FUN_00414c70(&local_58,*(undefined8 *)(*(longlong *)(param_1 + 0x60) + 0x30),L"Installed\\");
  local_60 = L".NFO";
  local_78 = DAT_00aba1aa;
  FUN_0081ac40(local_58,&local_60,0,local_28);
  local_20 = (longlong *)0x0;
  local_20 = (longlong *)FUN_0050dfc0(PTR_DAT_004cd0e0,1,local_28);
  while( true ) {
    local_40 = local_20;
    iVar2 = (**(code **)(*(longlong *)local_20[2] + 0x28))((longlong *)local_20[2]);
    local_41 = (int)local_40[1] < iVar2 + -1;
    if (!(bool)local_41) break;
    *(int *)(local_40 + 1) = (int)local_40[1] + 1;
    FUN_0050e080(local_20,&local_30);
    FUN_0043c5e0(&local_68,local_30);
    cVar1 = FUN_00ab9d10(*(undefined8 *)(param_1 + 0x60),local_68);
    if (cVar1 == '\0') {
      local_38 = FUN_00910cd0(local_30,*(undefined8 *)(*(longlong *)(param_1 + 0x60) + 0x30),
                              *(undefined8 *)(*(longlong *)(param_1 + 0x60) + 0x28),1);
      FUN_00ab9f00(param_1,local_38);
    }
  }
  if (local_20 != (longlong *)0x0) {
    (**(code **)(*local_20 + -0x20))(local_20,1);
  }
  FUN_0040faa0(local_28);
  FUN_00412d60(&local_68);
  FUN_00412d60(&local_58);
  FUN_00412d60(&local_30);
  return;
}


=== decomp aba1b0 -> FUN_00aba1b0 @00aba1b0 size=461

undefined1 FUN_00aba1b0(longlong param_1,undefined8 param_2)

{
  
  local_70 = auStack_a8;
  local_50 = 0;
  local_41 = 0;
  cVar2 = FUN_00819110(param_2);
  if (cVar2 != '\0') {
    local_40 = FUN_00511fe0(PTR_PTR_004cf268,1);
    uVar4 = FUN_00452750();
    local_30 = (longlong *)FUN_005a8940(PTR_PTR_005a2f90,1,param_2,uVar4);
    (**(code **)(*local_30 + 0xa8))(local_30,local_40);
    local_20 = (longlong *)0x0;
    local_20 = (longlong *)FUN_0050dfc0(PTR_DAT_004cd0e0,1,local_40);
    while( true ) {
      local_60 = local_20;
      iVar3 = (**(code **)(*(longlong *)local_20[2] + 0x28))((longlong *)local_20[2]);
      local_61 = (int)local_60[1] < iVar3 + -1;
      if (!(bool)local_61) break;
      *(int *)(local_60 + 1) = (int)local_60[1] + 1;
      FUN_0050e080(local_20,&local_50);
      local_88 = 1;
      local_58 = FUN_00911e10(local_30,local_50,
                              *(undefined8 *)(*(longlong *)(param_1 + 0x60) + 0x30),
                              *(undefined8 *)(*(longlong *)(param_1 + 0x60) + 0x28));
      FUN_00ab9f00(param_1,local_58);
    }
    if (local_20 != (longlong *)0x0) {
      (**(code **)(*local_20 + -0x20))(local_20,1);
    }
    plVar1 = local_30;
    local_28 = local_30;
    local_30 = (longlong *)0x0;
    FUN_0040faa0(plVar1);
    uVar4 = local_40;
    local_38 = local_40;
    local_40 = 0;
    FUN_0040faa0(uVar4);
    local_41 = 0 < *(longlong *)(*(longlong *)(param_1 + 0x68) + 0x10);
  }
  FUN_00412d60(&local_50);
  return local_41;
}


=== decomp abb7d0 -> FUN_00abb7d0 @00abb7d0 size=465

void FUN_00abb7d0(longlong param_1)

{
  
  local_70 = auStack_a8;
  local_78 = 0;
  local_38 = 0;
  FUN_0043bc40(*(undefined8 *)(param_1 + 0x40));
  FUN_00414c70(&local_38,*(undefined8 *)(param_1 + 0x40),L"VerifiedIDs.nfo");
  FUN_0043c650(&local_78,local_38);
  FUN_0043bc40(local_78);
  local_28 = FUN_00913450(PTR_DAT_009103e8,1,local_38,0);
  *(undefined1 *)(local_28 + 0x10) = 0;
  local_20 = (longlong *)0x0;
  local_48 = *(undefined8 *)(param_1 + 0x20);
  local_20 = (longlong *)FUN_00abc970(PTR_PTR_00ab3500,1,local_48);
  while( true ) {
    local_50 = local_20;
    local_51 = local_20[2] < *(longlong *)(local_20[1] + 0x10) + -1;
    if (!(bool)local_51) break;
    local_20[2] = local_20[2] + 1;
    local_60 = local_20[1];
    local_30 = *(undefined8 *)(*(longlong *)(local_60 + 8) + local_20[2] * 8);
    local_88 = FUN_00abb620;
    local_80 = param_1;
    FUN_008f53e0(local_30,&local_88,local_28);
  }
  if (local_20 != (longlong *)0x0) {
    (**(code **)(*local_20 + -0x20))(local_20,1);
  }
  FUN_00913e30(local_28);
  FUN_0040faa0(local_28);
  local_3c = FUN_0043bf90(local_38,1);
  FUN_0043c0a0(local_38,local_3c | 2,1);
  FUN_00412d60(&local_78);
  FUN_00412d60(&local_38);
  return;
}


=== decomp abb500 -> FUN_00abb500 @00abb500 size=219

void FUN_00abb500(longlong param_1,longlong param_2)

{
  
  local_20 = 0;
  local_10 = 0;
  local_18 = 0;
  if (param_2 != 0) {
    FUN_008f16d0(&local_10,param_2,*(undefined4 *)(*(longlong *)(param_1 + 0xa8) + 0x18),
                 *(undefined1 *)(*(longlong *)(param_1 + 0xa8) + 0x1e));
    FUN_0043c4c0(&local_20,*(undefined8 *)(*(longlong *)(param_1 + 0x98) + 0x2c),L".NFO");
    FUN_008f15a0(&local_18,*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x30),local_20);
    FUN_00913570(*(undefined8 *)(param_1 + 0x68),local_10);
    FUN_00914880(*(undefined8 *)(param_1 + 0x68),local_10,local_18,0);
  }
  FUN_00412e40(&local_20,3);
  return;
}


=== decomp abb620 -> FUN_00abb620 @00abb620 size=345

void FUN_00abb620(void)

{
  
  local_60 = auStack_88;
  local_38 = 0;
  local_20 = in_stack_00000028;
  local_30 = (longlong *)FUN_00902770(*(undefined8 *)PTR_DAT_015e3e88,*(undefined4 *)(in_R9 + 0x18))
  ;
  if (local_30 != (longlong *)0x0) {
    (**(code **)(*local_30 + 0x50))(local_30,&local_38,in_R9);
    FUN_00abb500(auStack_88,local_38);
    local_28 = (longlong *)0x0;
    local_40 = *(undefined8 *)(in_R9 + 0x68);
    local_28 = (longlong *)FUN_0050dfc0(PTR_DAT_004cd0e0,1,local_40);
    while( true ) {
      local_48 = local_28;
      iVar1 = (**(code **)(*(longlong *)local_28[2] + 0x28))((longlong *)local_28[2]);
      local_49 = (int)local_48[1] < iVar1 + -1;
      if (!(bool)local_49) break;
      *(int *)(local_48 + 1) = (int)local_48[1] + 1;
      FUN_0050e080(local_28,&local_38);
      FUN_00abb500(auStack_88,local_38);
    }
    if (local_28 != (longlong *)0x0) {
      (**(code **)(*local_28 + -0x20))(local_28,1);
    }
  }
  FUN_00412d60(&local_38);
  return;
}


=== decomp abba70 -> FUN_00abba70 @00abba70 size=1334

void FUN_00abba70(longlong param_1,byte param_2)

{
  
  local_c0 = 0;
  local_c8 = 0;
  local_b0 = 0;
  local_b8 = 0;
  local_a8 = 0;
  local_98 = 0;
  local_a0 = 0;
  local_90 = 0;
  local_88 = 0;
  local_80 = 0;
  local_78 = 0;
  local_50 = 0;
  local_20[0] = 0;
  local_28 = 0;
  local_30 = 0;
  local_38 = 0;
  local_40 = 0;
  local_48 = 0;
  local_70 = *(undefined8 *)(*(longlong *)(param_1 + 0x40) + 0x18);
  local_68 = 0x11;
  local_58 = 0;
  local_60 = (uint)param_2;
  FUN_0043dd60(&local_50,L"Store preset \"%s\" - effect=%d",&local_70,1);
  FUN_00ab81f0(*(undefined8 *)(param_1 + 0x30),local_50,0,0);
  cVar1 = FUN_00ab8310(*(undefined8 *)(param_1 + 0x30),*(undefined8 *)(param_1 + 0x40),
                       (*(byte *)(param_1 + 0x50) & 1) != 0,param_2,local_20,&local_30,&local_40);
  if (cVar1 == '\0') {
    local_70 = *(undefined8 *)(*(longlong *)(param_1 + 0x40) + 0x18);
    local_68 = 0x11;
    local_58 = 0;
    local_60 = (uint)param_2;
    FUN_0043dd60(&local_78,L"Can\'t determine filename for \"%s\" - effect=%d",&local_70,1);
    FUN_00ab81f0(*(undefined8 *)(param_1 + 0x30),local_78,0,0);
  }
  else {
    FUN_00414c70(*(longlong *)(param_1 + 0x40) + 0x2c,local_20[0]);
    if ((*(byte *)(param_1 + 0x50) & 1) != 0) {
      FUN_0043c650(&local_80,*(undefined8 *)(*(longlong *)(param_1 + 0x40) + 0x2c));
      FUN_0043bc40(local_80);
      cVar1 = FUN_00819110(*(undefined8 *)(param_1 + 0x48));
      if (cVar1 == '\0') {
        cVar1 = FUN_008f6050(*(undefined8 *)(param_1 + 0x40));
        if (cVar1 != '\0') {
          uVar2 = FUN_008f0ab0(param_2,*(undefined4 *)(*(longlong *)(param_1 + 0x40) + 0x34));
          FUN_00aba880(*(undefined8 *)(param_1 + 0x30),*(undefined8 *)(param_1 + 0x40),uVar2);
        }
      }
      else {
        pWVar3 = (LPCWSTR)FUN_00414850(*(undefined8 *)(param_1 + 0x48));
        pWVar4 = (LPCWSTR)FUN_00414850(*(undefined8 *)(*(longlong *)(param_1 + 0x40) + 0x2c));
        CopyFileW(pWVar3,pWVar4,0);
      }
    }
    if ((*(byte *)(param_1 + 0x50) & 2) != 0) {
      FUN_00413480(&local_48,L".NFO");
      FUN_00450560(&local_48,&local_88,*(undefined4 *)PTR_DAT_015e4f10);
      FUN_0043c4c0(&local_38,local_30,local_88);
      FUN_00414c70(&local_90,local_20[0],local_38);
      FUN_00911940(local_90,*(undefined8 *)(*(longlong *)(param_1 + 0x30) + 0x30),
                   *(undefined8 *)(*(longlong *)(param_1 + 0x30) + 0x28),
                   *(undefined8 *)(param_1 + 0x40));
    }
    if ((*(byte *)(param_1 + 0x50) & 4) != 0) {
      FUN_0043c4c0(&local_a0,local_30,0);
      FUN_00414c70(&local_98,local_40,local_a0);
      FUN_00912d10(*(undefined8 *)(param_1 + 0x38),local_98,
                   *(undefined8 *)(*(longlong *)(param_1 + 0x30) + 0x30),
                   *(undefined8 *)(*(longlong *)(param_1 + 0x30) + 0x28),
                   *(undefined8 *)(param_1 + 0x40));
    }
    if ((*(byte *)(param_1 + 0x50) & 1) != 0) {
      cVar1 = FUN_008f6560(*(undefined8 *)(param_1 + 0x40));
      if (cVar1 != '\0') {
        cVar1 = FUN_00819110(*(undefined8 *)(*(longlong *)(param_1 + 0x40) + 0x2c));
        if (cVar1 != '\0') {
          FUN_00ab9200(*(undefined8 *)(param_1 + 0x30),&local_a8,param_2);
          FUN_00414da0(&local_28,4,*(undefined8 *)(*(longlong *)(param_1 + 0x30) + 0x30),
                       L"Installed\\",local_a8,L"New\\");
          FUN_0043bc40(local_28);
          FUN_00414c70(&local_b0,local_20[0],local_30);
          pWVar3 = (LPCWSTR)FUN_00414850(local_b0);
          FUN_00414c70(&local_b8,local_28);
          pWVar4 = (LPCWSTR)FUN_00414850(local_b8);
          CopyFileW(pWVar3,pWVar4,0);
          FUN_00414c70(&local_c0,local_20[0],local_38);
          pWVar3 = (LPCWSTR)FUN_00414850(local_c0);
          FUN_00414c70(&local_c8,local_28);
          pWVar4 = (LPCWSTR)FUN_00414850(local_c8);
          CopyFileW(pWVar3,pWVar4,0);
        }
      }
    }
  }
  FUN_00412e40(&local_c8,0xb);
  FUN_00412e40(&local_50,7);
  return;
}


=== decomp abaf70 -> FUN_00abaf70 @00abaf70 size=793

void FUN_00abaf70(longlong param_1,byte param_2)

{
  
  local_80 = auStack_e8;
  local_b0 = 0;
  local_88 = 0;
  local_48 = 0;
  local_50 = 0;
  local_a8 = *(longlong *)(param_1 + 0x20) + 0x10;
  local_a0 = 0x10;
  local_98 = *(undefined8 *)(param_1 + 0x30);
  local_90 = 0x11;
  FUN_0043dd60(&local_88,L"Store all presets - count=%d dbpath=\"%s\"",&local_a8,1);
  FUN_00ab81f0(param_1,local_88,1,0);
  if (0 < *(longlong *)(*(longlong *)(param_1 + 0x20) + 0x10)) {
    FUN_00414c70(&local_48,*(undefined8 *)(param_1 + 0x30),L"Installed\\");
    if ((param_2 & 1) != 0) {
      FUN_0081a680(local_48);
    }
    FUN_0043bc40(local_48);
    FUN_00414c70(&local_50,local_48,L".Plugins.ini");
    cVar2 = FUN_00819110(local_50);
    if (cVar2 != '\0') {
      lpFileName = (LPCWSTR)FUN_00414850(local_50);
      DeleteFileW(lpFileName);
    }
    uVar3 = FUN_00452750();
    local_38 = (longlong *)FUN_005a8940(PTR_PTR_005a2f90,1,local_50,uVar3);
    *(undefined1 *)((longlong)local_38 + 0x29) = 0;
    local_20 = (longlong *)0x0;
    local_60 = *(undefined8 *)(param_1 + 0x20);
    local_20 = (longlong *)FUN_00abc970(PTR_PTR_00ab3500,1,local_60);
    while( true ) {
      local_68 = local_20;
      local_69 = local_20[2] < *(longlong *)(local_20[1] + 0x10) + -1;
      if (!(bool)local_69) break;
      local_20[2] = local_20[2] + 1;
      local_78 = local_20[1];
      local_40 = *(undefined8 *)(*(longlong *)(local_78 + 8) + local_20[2] * 8);
      local_c8 = param_2;
      FUN_00abc0f0(param_1,local_38,local_40,0);
    }
    if (local_20 != (longlong *)0x0) {
      (**(code **)(*local_20 + -0x20))(local_20,1);
    }
    (**(code **)(*local_38 + 0xd8))(local_38);
    plVar1 = local_38;
    local_30 = local_38;
    local_38 = (longlong *)0x0;
    FUN_0040faa0(plVar1);
    local_54 = FUN_0043bf90(local_50,1);
    FUN_0043c0a0(local_50,local_54 | 2,1);
  }
  FUN_00ab81f0(param_1,L"Finished (store all presets)",0xffffffff,0);
  FUN_00412d60(&local_b0);
  FUN_00412d60(&local_88);
  FUN_00412e40(&local_50,2);
  return;
}


=== decomp abc0f0 -> FUN_00abc0f0 @00abc0f0 size=87

void FUN_00abc0f0(undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  
  cVar1 = FUN_008f6380(param_3);
  FUN_00abba70(auStack_28,cVar1 != '\x01');
  bVar2 = FUN_008f5ca0(param_3);
  if ((bVar2 & 1) == 0) {
    cVar1 = FUN_008f6380(param_3);
    FUN_00abba70(auStack_28,cVar1 == '\x01');
  }
  return;
}


=== decomp ab8310 -> FUN_00ab8310 @00ab8310 size=283

undefined1
FUN_00ab8310(longlong param_1,undefined8 param_2,undefined1 param_3,undefined1 param_4,
            longlong *param_5,longlong *param_6,undefined8 *param_7)

{
  
  local_18 = 0;
  local_10 = 0;
  local_19 = 0;
  FUN_00412d60(param_5);
  FUN_00412d60(param_6);
  if (*(longlong *)(param_1 + 0x30) != 0) {
    FUN_00ab9150(param_1,&local_10,param_2,param_4);
    FUN_004133f0(param_7,local_10);
    FUN_00414da0(param_5,3,*(undefined8 *)(param_1 + 0x30),L"Installed\\",*param_7);
    FUN_00ab8e60(param_1,&local_18,*param_5,param_2,param_3);
    FUN_004133f0(param_6,local_18);
    if ((*param_5 == 0) || (*param_6 == 0)) {
      local_19 = 0;
    }
    else {
      local_19 = 1;
    }
  }
  FUN_00412e40(&local_18,2);
  return local_19;
}


=== decomp ab9150 -> FUN_00ab9150 @00ab9150 size=142

undefined8 FUN_00ab9150(undefined8 param_1,undefined8 param_2,longlong param_3,undefined1 param_4)

{
  
  local_10 = 0;
  local_18 = 0;
  FUN_00ab9200(param_1,&local_10,param_4);
  FUN_008f0300(&local_18,*(undefined4 *)(param_3 + 0x34));
  if (local_18 != 0) {
    FUN_00414bb0(&local_10,local_18);
  }
  FUN_00662680(&local_10);
  FUN_004133f0(param_2,local_10);
  FUN_00412e40(&local_18,2);
  return param_2;
}


=== decomp ab8e60 -> FUN_00ab8e60 @00ab8e60 size=627

undefined8 *
FUN_00ab8e60(undefined8 param_1,undefined8 *param_2,undefined8 param_3,longlong param_4,char param_5
            )

{
  
  local_70 = 0;
  local_60 = 0;
  local_68 = 0;
  local_48 = 0;
  local_50 = 0;
  local_58 = 0;
  local_30 = 0;
  FUN_00415610(&local_28,PTR_DAT_00ab73d0);
  FUN_00412d60(param_2);
  FUN_008f0740(param_2,*(undefined8 *)(param_4 + 0x18));
  if (param_5 == '\0') {
    FUN_00414bb0(param_2,L".fst");
  }
  else {
    FUN_00414da0(&local_30,3,param_3,*param_2,L".FST");
    cVar1 = FUN_00819110(local_30);
    bVar3 = cVar1 == '\0';
    if (!bVar3) {
      local_28 = 0;
      local_20 = 0;
      FUN_00413480(&local_28,param_3);
      FUN_00413480(&local_20,*param_2);
      local_40 = FUN_00abc150;
      local_38 = param_1;
      lVar2 = FUN_008f5620(param_4,&local_40,&local_28);
      if (lVar2 == 0) {
        FUN_00414da0(&local_58,3,param_3,*param_2,L".FST");
        FUN_00819ca0(&local_50,local_58);
        FUN_00661970(&local_48,local_50);
        FUN_004133f0(param_2,local_48);
      }
      else {
        FUN_004133f0(param_2,local_20);
      }
      bVar3 = true;
      FUN_00415c30(&local_28,PTR_DAT_00ab73d0);
    }
    if (bVar3) {
      FUN_00414da0(&local_68,3,param_3,*param_2,L".fst");
      FUN_00819ca0(&local_60,local_68);
      FUN_004133f0(param_2,local_60);
      FUN_0043c870(&local_70,*param_2);
      FUN_004133f0(param_2,local_70);
    }
    else {
      FUN_00412d60(param_2);
    }
  }
  FUN_00412e40(&local_70,6);
  FUN_00412d60(&local_30);
  FUN_00415c30(&local_28,PTR_DAT_00ab73d0);
  return param_2;
}


=== decomp ab9200 -> FUN_00ab9200 @00ab9200 size=110

undefined8 FUN_00ab9200(undefined8 param_1,undefined8 param_2,char param_3)

{
  
  local_10 = 0;
  if (param_3 == '\0') {
    FUN_00413480(&local_10,L"Generators\\");
  }
  else {
    FUN_00413480(&local_10,L"Effects\\");
  }
  FUN_00662680(&local_10);
  FUN_004133f0(param_2,local_10);
  FUN_00412d60(&local_10);
  return param_2;
}


=== decomp ab9b10 -> FUN_00ab9b10 @00ab9b10 size=335

undefined1 FUN_00ab9b10(longlong param_1,int param_2)

{
  
  local_30[0] = 0;
  local_38 = 0;
  local_20 = 0;
  local_39 = 0;
  if ((param_2 < 0) || (*(longlong *)(*(longlong *)(param_1 + 0x20) + 0x10) <= (longlong)param_2))
  goto LAB_00ab9c3b;
  lVar1 = *(longlong *)(param_1 + 0x20);
  uVar4 = (ulonglong)param_2;
  if (*(ulonglong *)(lVar1 + 0x10) <= uVar4) {
    FUN_0047a250(uVar4,*(ulonglong *)(lVar1 + 0x10) - 1,lVar1);
  }
  lVar1 = *(longlong *)(*(longlong *)(lVar1 + 8) + uVar4 * 8);
  uVar3 = *(undefined8 *)(param_1 + 0x30);
  FUN_00414c70(&local_20,uVar3,L"Installed\\");
  cVar2 = FUN_008f6110(lVar1);
  if (cVar2 == '\0') {
LAB_00ab9bf0:
    FUN_00414bb0(&local_20,L"Effects\\");
  }
  else {
    if (*(uint *)(lVar1 + 0x34) < 0x10) {
      bVar5 = ((ushort)((int)CONCAT62((int6)((ulonglong)uVar3 >> 0x10),1) <<
                       ((byte)*(uint *)(lVar1 + 0x34) & 0x1f)) & DAT_00ab9cae) != 0;
    }
    else {
      bVar5 = false;
    }
    if (!bVar5) goto LAB_00ab9bf0;
    FUN_00414bb0(&local_20,L"Generators\\");
  }
  FUN_00414bb0(&local_20,L"New\\");
  FUN_0043c870(&local_38,*(undefined8 *)(lVar1 + 0x2c));
  FUN_00414c70(local_30,local_20,local_38);
  local_39 = FUN_00819110(local_30[0]);
LAB_00ab9c3b:
  FUN_00412e40(&local_38,2);
  FUN_00412d60(&local_20);
  return local_39;
}


=== decomp aba430 -> FUN_00aba430 @00aba430 size=235

void FUN_00aba430(longlong param_1,longlong param_2)

{
  
  local_18 = 0;
  local_10 = 0;
  if (param_2 != 0) {
    FUN_00ab81f0(param_1,L"LoadExistingPresetsToList",1,0);
    local_38 = L".Plugins.ini";
    FUN_00414da0(&local_10,3,*(undefined8 *)(param_1 + 0x30),L"Installed\\");
    cVar1 = FUN_00aba1b0(auStack_58,local_10);
    if (cVar1 == '\0') {
      FUN_00ab9f40(auStack_58);
      FUN_00abaf70(param_1,DAT_00aba5c6);
    }
    local_28 = param_2 + 0x10;
    local_20 = 0x10;
    FUN_0043dd60(&local_18,L"Finished (LoadExistingPresetsToList) - count=%d",&local_28,0);
    FUN_00ab81f0(param_1,local_18,0xffffffff,0);
  }
  FUN_00412e40(&local_18,2);
  return;
}


=== decomp abf130 -> FUN_00abf130 @00abf130 size=1377

void FUN_00abf130(undefined8 param_1,undefined8 param_2,int param_3,longlong param_4)

{
  
  local_330 = 0;
  local_338 = 0;
  local_340 = 0;
  local_318 = 0;
  local_320 = 0;
  local_328 = 0;
  local_310 = 0;
  local_308 = 0;
  local_300[0] = 0;
  local_30[0] = (wchar_t *)0x0;
  local_38 = 0;
  local_2c0 = 0;
  local_2c8 = 0;
  local_2d0 = 0;
  local_2d8 = 0;
  FUN_00415610(local_2b8,PTR_DAT_0042d8f0);
  FUN_00439c90(local_300,param_2);
  if (local_300[0] != 0) {
    FUN_00414c70(&local_308,param_2,&DAT_00abf704);
    iVar5 = FUN_0043c260(local_308,0x10,local_2b8);
    while (iVar5 == 0) {
      FUN_00413480(local_30,local_2a0);
      cVar2 = FUN_00819440(local_30[0]);
      if (cVar2 != '\0') {
        FUN_00414da0(&local_2d0,5,param_2,local_30[0],&DAT_00abf718,local_30[0],L".dll");
        FUN_00413480(&local_2c0,local_2d0);
        cVar2 = FUN_00819110(local_2c0);
        if (cVar2 == '\0') {
          FUN_00414da0(&local_2c0,5,param_2,local_30[0],&DAT_00abf718,L"FruityPlug",L".dll");
        }
        pwVar9 = L"_x64";
        pwVar10 = L".dll";
        pwVar8 = local_30[0];
        FUN_00414da0(&local_2c8,6,param_2,local_30[0],&DAT_00abf718,local_30[0],L"_x64",L".dll");
        cVar2 = FUN_00819110(local_2c8);
        if (cVar2 == '\0') {
          pwVar8 = L"FruityPlug_x64";
          pwVar9 = L".dll";
          FUN_00414da0(&local_2c8,5,param_2,local_30[0],&DAT_00abf718,L"FruityPlug_x64",L".dll",
                       pwVar10);
        }
        FUN_00413480(&local_38,local_30[0]);
        FUN_00414da0(&local_310,3,param_2,local_2a0,&DAT_00abf718,pwVar8,pwVar9,pwVar10);
        FUN_00abe970(local_310,&local_2d8,&local_2d9);
        cVar2 = FUN_00819110(local_2c0);
        if ((local_2d9 == '\0') && (cVar3 = FUN_00819110(local_2c8), cVar3 != '\0')) {
          bVar1 = true;
        }
        else {
          bVar1 = false;
        }
        uVar7 = 0;
        if (param_3 == 2) {
          uVar7 = 1;
        }
        else if (param_3 == 3) {
          uVar7 = 2;
        }
        if (cVar2 != '\0' || bVar1) {
          if (cVar2 != '\0') {
            lVar6 = FUN_008f6ad0(PTR_DAT_008f1b10,1);
            FUN_004133f0(lVar6 + 8,local_38);
            FUN_004133f0(lVar6 + 0x10,local_2c0);
            *(int *)(lVar6 + 0x18) = param_3;
            *(undefined2 *)(lVar6 + 0x1c) = uVar7;
            *(undefined1 *)(lVar6 + 0x1e) = 2;
            uVar4 = FUN_0063b7f0(local_2c0);
            *(undefined1 *)(lVar6 + 0x1f) = uVar4;
            *(undefined4 *)(lVar6 + 0x20) = 0;
            FUN_0043c870(&local_328,local_2c0);
            FUN_0043c4c0(&local_320,local_328,0);
            FUN_00439550(&local_318,local_320);
            FUN_004133f0(lVar6 + 0x44,local_318);
            *(undefined1 *)(lVar6 + 0x4c) = DAT_00abf79a;
            FUN_004133f0(lVar6 + 0x50,local_2d8);
            *(undefined8 *)(lVar6 + 0x34) = 0;
            *(undefined8 *)(lVar6 + 0x3c) = 0;
            local_2e8 = lVar6;
            FUN_0047b260(param_4 + 8,&local_2e8);
          }
          if (bVar1) {
            lVar6 = FUN_008f6ad0(PTR_DAT_008f1b10,1);
            FUN_004133f0(lVar6 + 8,local_38);
            FUN_004133f0(lVar6 + 0x10,local_2c8);
            *(int *)(lVar6 + 0x18) = param_3;
            *(undefined2 *)(lVar6 + 0x1c) = uVar7;
            *(undefined1 *)(lVar6 + 0x1e) = 3;
            uVar4 = FUN_0063b7f0(local_2c8);
            *(undefined1 *)(lVar6 + 0x1f) = uVar4;
            *(undefined4 *)(lVar6 + 0x20) = 0;
            FUN_0043c870(&local_340,local_2c0);
            FUN_0043c4c0(&local_338,local_340,0);
            FUN_00439550(&local_330,local_338);
            FUN_004133f0(lVar6 + 0x44,local_330);
            *(undefined1 *)(lVar6 + 0x4c) = DAT_00abf79a;
            FUN_004133f0(lVar6 + 0x50,local_2d8);
            *(undefined8 *)(lVar6 + 0x34) = 0;
            *(undefined8 *)(lVar6 + 0x3c) = 0;
            local_2f0 = lVar6;
            FUN_0047b260(param_4 + 8,&local_2f0);
          }
        }
      }
      iVar5 = FUN_0043c2c0(local_2b8);
    }
    FUN_0043c2f0(local_2b8);
  }
  FUN_00412e40(&local_340,9);
  FUN_00412e40(&local_2d8,4);
  FUN_00415c30(local_2b8,PTR_DAT_0042d8f0);
  FUN_00412e40(&local_38,2);
  return;
}


