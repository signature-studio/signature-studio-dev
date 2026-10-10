=== decomp d8cab0 -> FUN_00d8cab0 @00d8cab0 size=970

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

longlong FUN_00d8cab0(longlong param_1,undefined8 param_2)

{
  longlong lVar1;
  char cVar2;
  undefined8 uVar3;
  undefined8 local_res10 [3];
  undefined1 auStack_88 [32];
  undefined8 local_68;
  undefined8 local_60;
  undefined8 local_58;
  undefined1 *local_50;
  longlong local_48;
  longlong local_40;
  longlong local_38;
  undefined8 local_30;
  code *local_28;
  longlong local_20;
  
  local_50 = auStack_88;
  local_68 = 0;
  local_60 = 0;
  local_58 = 0;
  local_res10[0] = param_2;
  FUN_00412f30(param_2);
  FUN_00439550(&local_58,local_res10[0]);
  local_30 = local_58;
  cVar2 = FUN_0044f040(&local_30,L"_x64.dll",0);
  if (cVar2 == '\0') {
    FUN_0043c4c0(&local_60,local_res10[0],L"_x64.dll");
    FUN_00413480(local_res10,local_60);
  }
  local_20 = FUN_0040f9e0(PTR_DAT_00d8be40,1);
  uVar3 = FUN_0044db40(local_res10[0],0x8000);
  lVar1 = local_20;
  *(undefined8 *)(local_20 + 8) = uVar3;
  if (*(longlong *)(local_20 + 8) == 0) {
    local_48 = local_20;
    local_20 = 0;
    FUN_0040faa0(lVar1);
  }
  else {
    local_28 = (code *)FUN_004235f0(*(longlong *)(local_20 + 8),L"CreatePlugInstance");
    if (local_28 == (code *)0x0) {
      *(undefined8 *)(local_20 + 0x10) = 0;
    }
    else {
      uVar3 = (*local_28)(param_1,local_20);
      *(undefined8 *)(local_20 + 0x10) = uVar3;
    }
    if (*(longlong *)(local_20 + 0x10) == 0) {
      FreeLibrary(*(HMODULE *)(local_20 + 8));
      lVar1 = local_20;
      local_38 = local_20;
      local_20 = 0;
      FUN_0040faa0(lVar1);
    }
    else {
      (**(code **)(**(longlong **)(param_1 + 0x118) + 0x100))
                (*(longlong **)(param_1 + 0x118),*(undefined8 *)(param_1 + 0x120));
      local_40 = *(longlong *)(param_1 + 0x128);
      if (*(int *)(local_40 + 0x10) == *(int *)(local_40 + 0x14)) {
        FUN_00663aa0(local_40);
      }
      *(longlong *)(*(longlong *)(local_40 + 8) + (longlong)*(int *)(local_40 + 0x10) * 8) =
           local_20;
      *(int *)(local_40 + 0x10) = *(int *)(local_40 + 0x10) + 1;
      if (*(int *)(param_1 + 0x100) != 0x7fffffff) {
        (**(code **)(**(longlong **)(local_20 + 0x10) + 8))
                  (*(longlong **)(local_20 + 0x10),3,0,(longlong)*(int *)(param_1 + 0x100));
      }
      if (*(int *)(param_1 + 0x104) != 0x7fffffff) {
        (**(code **)(**(longlong **)(local_20 + 0x10) + 8))
                  (*(longlong **)(local_20 + 0x10),4,0,(longlong)*(int *)(param_1 + 0x104));
      }
      if (*(int *)(param_1 + 0x108) != 0x7fffffff) {
        (**(code **)(**(longlong **)(local_20 + 0x10) + 8))
                  (*(longlong **)(local_20 + 0x10),1,0,(longlong)*(int *)(param_1 + 0x108));
      }
      if (*(int *)(param_1 + 0x10c) != 0x7fffffff) {
        (**(code **)(**(longlong **)(local_20 + 0x10) + 8))
                  (*(longlong **)(local_20 + 0x10),0x15,0,(longlong)*(int *)(param_1 + 0x10c));
      }
      if (*(int *)(param_1 + 0x110) != 0x7fffffff) {
        (**(code **)(**(longlong **)(local_20 + 0x10) + 8))
                  (*(longlong **)(local_20 + 0x10),0xc,0,(longlong)*(int *)(param_1 + 0x110));
      }
      if (*(float *)(param_1 + 0x114) != _DAT_00d8ce8c) {
        (**(code **)(**(longlong **)(local_20 + 0x10) + 0x28))
                  (*(longlong **)(local_20 + 0x10),0,*(undefined4 *)(param_1 + 0x114),0);
      }
      (**(code **)(**(longlong **)(param_1 + 0x118) + 0x108))
                (*(longlong **)(param_1 + 0x118),*(undefined8 *)(param_1 + 0x120));
    }
  }
  FUN_0063a660();
  FUN_0063a6d0();
  if (local_20 == 0) {
    FUN_00414c70(&local_68,local_res10[0],L" is missing.");
    FUN_00818e00(local_68,1);
  }
  FUN_00412e40(&local_68,3);
  FUN_00412d60(local_res10);
  return local_20;
}


