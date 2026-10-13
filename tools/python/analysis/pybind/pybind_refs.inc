/* 生成物: analysis/pybind_extract.py。FL が動的束縛する Py* のうち libpython3.12.a に存在する名前 */
extern void Py_NewInterpreterFromConfig(void);
extern void Py_InitializeEx(void);
extern void PyThreadState_Get(void);
extern void PyThreadState_Swap(void);
extern void PyRun_SimpleString(void);
extern void PyModuleDef_Init(void);
extern void PyImport_AppendInittab(void);
extern void PyModule_AddObject(void);
extern void PyLong_FromLong(void);
extern void Py_EndInterpreter(void);
extern void PyModule_FromDefAndSpec2(void);
extern void PyModule_ExecDef(void);
extern void Py_BuildValue(void);
extern void _PyNamespace_New(void);
extern void PyUnicode_FromString(void);
extern void PyImport_AddModule(void);
extern void _PyImport_SetModuleString(void);
extern void PyType_FromModuleAndSpec(void);
extern char _Py_NoneStruct[];
extern void PyModule_AddType(void);
extern void PyArg_ParseTuple(void);
extern void PyArg_ParseTupleAndKeywords(void);
extern void PyModule_GetState(void);
extern void Py_FinalizeEx(void);
extern void Py_IsInitialized(void);
extern void PyErr_GetRaisedException(void);
extern void PyArg_UnpackTuple(void);
extern void PyObject_Str(void);
extern void PyUnicode_AsUTF8(void);
extern void PyModule_GetDict(void);
extern void PyRun_StringFlags(void);
extern void PyException_GetTraceback(void);
extern void PyList_Append(void);
extern void PyObject_CallObject(void);
extern void PyObject_Call(void);
extern void PySys_AddAuditHook(void);
extern void PyTuple_GetItem(void);
extern void PyModule_AddObjectRef(void);
extern void PyEval_RestoreThread(void);
extern void PyModule_AddIntConstant(void);
extern void PyLong_FromLongLong(void);
extern void PyLong_AsLongLong(void);
extern void PyFloat_FromDouble(void);
extern void PyFloat_AsDouble(void);
extern void PyLong_AsLong(void);
extern void PyType_GetModuleByDef(void);
extern void PySys_GetObject(void);
extern void PyList_New(void);
extern void PyList_AsTuple(void);
extern void PyObject_GetAttrString(void);
extern void PyDict_GetItemString(void);
extern void PyImport_GetModuleDict(void);
extern char PyExc_IndexError[];
extern char PyExc_NameError[];
extern void PyErr_SetString(void);
extern char PyUnicode_Type[];
extern void PyObject_GetIter(void);
extern void PyObject_SelfIter(void);
extern void PyIter_Next(void);
extern void PyObject_HasAttrString(void);
extern void PyList_Size(void);
extern void PyErr_Clear(void);
extern void PyErr_PrintEx(void);
extern void PyCallable_Check(void);
extern void PyBytes_FromStringAndSize(void);
extern char PyExc_Exception[];
extern void PyErr_Occurred(void);
extern char PyLong_Type[];
extern char PyExc_TypeError[];
extern char PyExc_RuntimeError[];
extern char PyExc_SystemExit[];
extern void PyLong_FromSize_t(void);
extern char PyFloat_Type[];
extern char PyBool_Type[];
extern void PyEval_SaveThread(void);
extern void PyModule_AddStringConstant(void);
extern char Py_DontWriteBytecodeFlag[];
extern void PyThreadState_New(void);
extern void PyThreadState_Clear(void);
extern void PyThreadState_DeleteCurrent(void);
extern void Py_IncRef(void);
extern void Py_DecRef(void);
extern void PySys_SetObject(void);
extern void PyNumber_Check(void);
extern void PyInterpreterState_Main(void);
extern void PyInterpreterState_ThreadHead(void);
extern void PyObject_IsTrue(void);
extern void PyBuffer_Release(void);
extern void PyConfig_InitIsolatedConfig(void);
extern void PyConfig_Clear(void);
extern void Py_InitializeFromConfig(void);
extern void Py_DecodeLocale(void);
extern void PyMem_RawFree(void);
extern void PyWideStringList_Append(void);
extern void PyLong_FromVoidPtr(void);
extern void PyLong_AsVoidPtr(void);
extern char PyList_Type[];
extern void PyList_SetItem(void);
extern void PyObject_IsInstance(void);
extern char _Py_TrueStruct[];
extern char _Py_FalseStruct[];
extern void PyInterpreterState_GetDict(void);
extern void PyInterpreterState_Get(void);
extern void PyDict_SetItemString(void);
extern void PyErr_WarnEx(void);
extern char PyExc_UserWarning[];
extern void PyErr_SetRaisedException(void);
extern void PyBool_FromLong(void);
extern void PyDict_New(void);
static const struct { const char *name; const void *addr; } pybind_refs[] = {
    {"Py_NewInterpreterFromConfig", (const void *)&Py_NewInterpreterFromConfig},
    {"Py_InitializeEx", (const void *)&Py_InitializeEx},
    {"PyThreadState_Get", (const void *)&PyThreadState_Get},
    {"PyThreadState_Swap", (const void *)&PyThreadState_Swap},
    {"PyRun_SimpleString", (const void *)&PyRun_SimpleString},
    {"PyModuleDef_Init", (const void *)&PyModuleDef_Init},
    {"PyImport_AppendInittab", (const void *)&PyImport_AppendInittab},
    {"PyModule_AddObject", (const void *)&PyModule_AddObject},
    {"PyLong_FromLong", (const void *)&PyLong_FromLong},
    {"Py_EndInterpreter", (const void *)&Py_EndInterpreter},
    {"PyModule_FromDefAndSpec2", (const void *)&PyModule_FromDefAndSpec2},
    {"PyModule_ExecDef", (const void *)&PyModule_ExecDef},
    {"Py_BuildValue", (const void *)&Py_BuildValue},
    {"_PyNamespace_New", (const void *)&_PyNamespace_New},
    {"PyUnicode_FromString", (const void *)&PyUnicode_FromString},
    {"PyImport_AddModule", (const void *)&PyImport_AddModule},
    {"_PyImport_SetModuleString", (const void *)&_PyImport_SetModuleString},
    {"PyType_FromModuleAndSpec", (const void *)&PyType_FromModuleAndSpec},
    {"_Py_NoneStruct", (const void *)&_Py_NoneStruct},
    {"PyModule_AddType", (const void *)&PyModule_AddType},
    {"PyArg_ParseTuple", (const void *)&PyArg_ParseTuple},
    {"PyArg_ParseTupleAndKeywords", (const void *)&PyArg_ParseTupleAndKeywords},
    {"PyModule_GetState", (const void *)&PyModule_GetState},
    {"Py_FinalizeEx", (const void *)&Py_FinalizeEx},
    {"Py_IsInitialized", (const void *)&Py_IsInitialized},
    {"PyErr_GetRaisedException", (const void *)&PyErr_GetRaisedException},
    {"PyArg_UnpackTuple", (const void *)&PyArg_UnpackTuple},
    {"PyObject_Str", (const void *)&PyObject_Str},
    {"PyUnicode_AsUTF8", (const void *)&PyUnicode_AsUTF8},
    {"PyModule_GetDict", (const void *)&PyModule_GetDict},
    {"PyRun_StringFlags", (const void *)&PyRun_StringFlags},
    {"PyException_GetTraceback", (const void *)&PyException_GetTraceback},
    {"PyList_Append", (const void *)&PyList_Append},
    {"PyObject_CallObject", (const void *)&PyObject_CallObject},
    {"PyObject_Call", (const void *)&PyObject_Call},
    {"PySys_AddAuditHook", (const void *)&PySys_AddAuditHook},
    {"PyTuple_GetItem", (const void *)&PyTuple_GetItem},
    {"PyModule_AddObjectRef", (const void *)&PyModule_AddObjectRef},
    {"PyEval_RestoreThread", (const void *)&PyEval_RestoreThread},
    {"PyModule_AddIntConstant", (const void *)&PyModule_AddIntConstant},
    {"PyLong_FromLongLong", (const void *)&PyLong_FromLongLong},
    {"PyLong_AsLongLong", (const void *)&PyLong_AsLongLong},
    {"PyFloat_FromDouble", (const void *)&PyFloat_FromDouble},
    {"PyFloat_AsDouble", (const void *)&PyFloat_AsDouble},
    {"PyLong_AsLong", (const void *)&PyLong_AsLong},
    {"PyType_GetModuleByDef", (const void *)&PyType_GetModuleByDef},
    {"PySys_GetObject", (const void *)&PySys_GetObject},
    {"PyList_New", (const void *)&PyList_New},
    {"PyList_AsTuple", (const void *)&PyList_AsTuple},
    {"PyObject_GetAttrString", (const void *)&PyObject_GetAttrString},
    {"PyDict_GetItemString", (const void *)&PyDict_GetItemString},
    {"PyImport_GetModuleDict", (const void *)&PyImport_GetModuleDict},
    {"PyExc_IndexError", (const void *)&PyExc_IndexError},
    {"PyExc_NameError", (const void *)&PyExc_NameError},
    {"PyErr_SetString", (const void *)&PyErr_SetString},
    {"PyUnicode_Type", (const void *)&PyUnicode_Type},
    {"PyObject_GetIter", (const void *)&PyObject_GetIter},
    {"PyObject_SelfIter", (const void *)&PyObject_SelfIter},
    {"PyIter_Next", (const void *)&PyIter_Next},
    {"PyObject_HasAttrString", (const void *)&PyObject_HasAttrString},
    {"PyList_Size", (const void *)&PyList_Size},
    {"PyErr_Clear", (const void *)&PyErr_Clear},
    {"PyErr_PrintEx", (const void *)&PyErr_PrintEx},
    {"PyCallable_Check", (const void *)&PyCallable_Check},
    {"PyBytes_FromStringAndSize", (const void *)&PyBytes_FromStringAndSize},
    {"PyExc_Exception", (const void *)&PyExc_Exception},
    {"PyErr_Occurred", (const void *)&PyErr_Occurred},
    {"PyLong_Type", (const void *)&PyLong_Type},
    {"PyExc_TypeError", (const void *)&PyExc_TypeError},
    {"PyExc_RuntimeError", (const void *)&PyExc_RuntimeError},
    {"PyExc_SystemExit", (const void *)&PyExc_SystemExit},
    {"PyLong_FromSize_t", (const void *)&PyLong_FromSize_t},
    {"PyFloat_Type", (const void *)&PyFloat_Type},
    {"PyBool_Type", (const void *)&PyBool_Type},
    {"PyEval_SaveThread", (const void *)&PyEval_SaveThread},
    {"PyModule_AddStringConstant", (const void *)&PyModule_AddStringConstant},
    {"Py_DontWriteBytecodeFlag", (const void *)&Py_DontWriteBytecodeFlag},
    {"PyThreadState_New", (const void *)&PyThreadState_New},
    {"PyThreadState_Clear", (const void *)&PyThreadState_Clear},
    {"PyThreadState_DeleteCurrent", (const void *)&PyThreadState_DeleteCurrent},
    {"Py_IncRef", (const void *)&Py_IncRef},
    {"Py_DecRef", (const void *)&Py_DecRef},
    {"PySys_SetObject", (const void *)&PySys_SetObject},
    {"PyNumber_Check", (const void *)&PyNumber_Check},
    {"PyInterpreterState_Main", (const void *)&PyInterpreterState_Main},
    {"PyInterpreterState_ThreadHead", (const void *)&PyInterpreterState_ThreadHead},
    {"PyObject_IsTrue", (const void *)&PyObject_IsTrue},
    {"PyBuffer_Release", (const void *)&PyBuffer_Release},
    {"PyConfig_InitIsolatedConfig", (const void *)&PyConfig_InitIsolatedConfig},
    {"PyConfig_Clear", (const void *)&PyConfig_Clear},
    {"Py_InitializeFromConfig", (const void *)&Py_InitializeFromConfig},
    {"Py_DecodeLocale", (const void *)&Py_DecodeLocale},
    {"PyMem_RawFree", (const void *)&PyMem_RawFree},
    {"PyWideStringList_Append", (const void *)&PyWideStringList_Append},
    {"PyLong_FromVoidPtr", (const void *)&PyLong_FromVoidPtr},
    {"PyLong_AsVoidPtr", (const void *)&PyLong_AsVoidPtr},
    {"PyList_Type", (const void *)&PyList_Type},
    {"PyList_SetItem", (const void *)&PyList_SetItem},
    {"PyObject_IsInstance", (const void *)&PyObject_IsInstance},
    {"_Py_TrueStruct", (const void *)&_Py_TrueStruct},
    {"_Py_FalseStruct", (const void *)&_Py_FalseStruct},
    {"PyInterpreterState_GetDict", (const void *)&PyInterpreterState_GetDict},
    {"PyInterpreterState_Get", (const void *)&PyInterpreterState_Get},
    {"PyDict_SetItemString", (const void *)&PyDict_SetItemString},
    {"PyErr_WarnEx", (const void *)&PyErr_WarnEx},
    {"PyExc_UserWarning", (const void *)&PyExc_UserWarning},
    {"PyErr_SetRaisedException", (const void *)&PyErr_SetRaisedException},
    {"PyBool_FromLong", (const void *)&PyBool_FromLong},
    {"PyDict_New", (const void *)&PyDict_New},
};
