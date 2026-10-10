=== decomp 7a8f90 -> FUN_007a8f90 @007a8f90 size=121

longlong FUN_007a8f90(longlong param_1)

{
  uint uVar1;
  ulonglong uVar2;
  longlong local_30;
  undefined8 local_20;
  
  local_20 = 0;
  if (param_1 == 0) {
    local_30 = 0;
  }
  else {
    uVar2 = 0;
    do {
      FUN_00412630(&local_20,(&PTR_u_VstPluginMain_008e5d08)[uVar2]);
      local_30 = FUN_007a8f60(param_1,local_20);
      if (local_30 != 0) break;
      uVar1 = (int)uVar2 + 1;
      uVar2 = (ulonglong)uVar1;
    } while (uVar1 != 0x1a);
  }
  FUN_00411f10(&local_20);
  return local_30;
}


=== decomp 7a8f60 -> FUN_007a8f60 @007a8f60 size=42

undefined8 FUN_007a8f60(longlong param_1,undefined8 param_2)

{
  undefined8 uVar1;
  
  if (param_1 == 0) {
    uVar1 = 0;
  }
  else {
    uVar1 = FUN_00413840(param_2);
    uVar1 = FUN_00421dd0(param_1,uVar1);
  }
  return uVar1;
}


=== decomp 449770 -> FUN_00449770 @00449770 size=71

HMODULE FUN_00449770(undefined8 param_1,UINT param_2)

{
  LPCWSTR lpLibFileName;
  undefined1 auStack_48 [40];
  undefined1 *local_20;
  HMODULE local_18;
  UINT local_c;
  
  local_20 = auStack_48;
  local_c = SetErrorMode(param_2);
  lpLibFileName = (LPCWSTR)FUN_00413840(param_1);
  local_18 = LoadLibraryW(lpLibFileName);
  SetErrorMode(local_c);
  return local_18;
}


=== decomp 7ad370 -> FUN_007ad370 @007ad370 size=43

void FUN_007ad370(undefined8 param_1,undefined8 param_2,longlong param_3)

{
  longlong lVar1;
  
  if ((param_3 != 0) && (lVar1 = FUN_007a8f60(param_2,param_3), lVar1 != 0)) {
    return;
  }
  FUN_007a8f90(param_2);
  return;
}


=== decomp 7a9030 -> FUN_007a9030 @007a9030 size=303

undefined1 FUN_007a9030(undefined8 param_1,undefined8 param_2)

{
  int iVar1;
  int iVar2;
  undefined1 auStack_78 [40];
  undefined8 local_50;
  undefined8 local_48;
  undefined1 *local_40;
  undefined8 local_30;
  int local_28;
  undefined1 local_21;
  longlong *local_20;
  
  local_40 = auStack_78;
  local_50 = 0;
  local_48 = 0;
  local_30 = 0;
  local_21 = 0;
  local_20 = (longlong *)FUN_00500f90(PTR_PTR_004c1db0,1);
  FUN_005c0200(param_1,local_20);
  iVar1 = (**(code **)(*local_20 + 0x28))();
  local_28 = 0;
  if (-1 < iVar1 + -1) {
    do {
      (**(code **)(*local_20 + 0x18))(local_20,&local_48,local_28);
      FUN_00437ab0(&local_30,local_48);
      iVar2 = FUN_00413e60(local_30,L"main");
      if ((iVar2 == 0) || (iVar2 = FUN_00413e60(local_30,L"vstpluginmain"), iVar2 == 0)) {
LAB_007a911e:
        local_21 = 1;
        break;
      }
      FUN_00437ab0(&local_50,param_2);
      iVar2 = FUN_00413e60(local_30,local_50);
      if (iVar2 == 0) goto LAB_007a911e;
      local_28 = local_28 + 1;
      iVar1 = iVar1 + -1;
    } while (iVar1 != 0);
  }
  FUN_0040ec50(local_20);
  FUN_00411ff0(&local_50,2);
  FUN_00411f10(&local_30);
  return local_21;
}


=== decomp 437ab0 -> FUN_00437ab0 @00437ab0 size=105

undefined8 * FUN_00437ab0(undefined8 *param_1,ushort *param_2)

{
  int iVar1;
  ushort *puVar2;
  ushort uVar3;
  
  iVar1 = 0;
  if (param_2 != (ushort *)0x0) {
    iVar1 = *(int *)(param_2 + -2);
  }
  FUN_00413ac0(param_1,iVar1);
  if ((0 < iVar1) && (puVar2 = (ushort *)*param_1, 0 < iVar1)) {
    do {
      uVar3 = *param_2;
      if ((ushort)(uVar3 - 0x41) < 0x1a) {
        uVar3 = uVar3 | 0x20;
      }
      *puVar2 = uVar3;
      puVar2 = puVar2 + 1;
      param_2 = param_2 + 1;
      iVar1 = iVar1 + -1;
    } while (iVar1 != 0);
  }
  return param_1;
}


