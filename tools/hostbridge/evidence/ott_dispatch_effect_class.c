=== decomp 180126c00 -> FUN_180126c00 @180126c00 size=82

undefined8
FUN_180126c00(longlong param_1,int param_2,undefined8 param_3,undefined8 param_4,undefined8 param_5,
             undefined4 param_6)

{
  longlong *plVar1;
  undefined8 uVar2;
  
  plVar1 = *(longlong **)(param_1 + 0x60);
  if (param_2 == 1) {
    (**(code **)(*plVar1 + 8))();
    (**(code **)*plVar1)(plVar1,1,(undefined8 *)*plVar1,param_4,param_5,param_6);
    return 1;
  }
  uVar2 = (**(code **)(*plVar1 + 8))(plVar1);
  return uVar2;
}


