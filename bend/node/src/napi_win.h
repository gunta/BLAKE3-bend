// Node-API on Windows, found in the host process. An addon that imports
// node.exe's exports loads only in node.exe (or needs a delay-load hook);
// these calls are looked up in whichever program loaded the addon (node,
// bun, deno, electron all export them), so the addon links to nothing.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#define TB_NAPI(X)                                                             \
  X(napi_create_array_with_length) X(napi_create_arraybuffer)                  \
  X(napi_create_int32) X(napi_create_typedarray) X(napi_define_properties)     \
  X(napi_get_array_length) X(napi_get_arraybuffer_info) X(napi_get_cb_info)    \
  X(napi_get_dataview_info) X(napi_get_element) X(napi_get_null)               \
  X(napi_get_typedarray_info) X(napi_get_value_double)                         \
  X(napi_get_value_string_utf8) X(napi_get_value_uint32) X(napi_is_arraybuffer) \
  X(napi_is_dataview) X(napi_is_typedarray) X(napi_set_element)                \
  X(napi_throw_error) X(napi_throw_range_error) X(napi_throw_type_error)

#define TB_PTR(f) static __typeof__(&f) tb_##f;
TB_NAPI(TB_PTR)

// 1 once every call is found; the module's init asks first.
static int tb_napi_load(void) {
  HMODULE host = GetModuleHandleW(NULL);
#define TB_GET(f)                                               \
  if ((tb_##f = (__typeof__(&f))(void (*)(void))GetProcAddress(host, #f)) == NULL) { \
    return 0;                                                   \
  }
  TB_NAPI(TB_GET)
  return 1;
}

// from here on, each call goes through its pointer
#define napi_create_array_with_length (*tb_napi_create_array_with_length)
#define napi_create_arraybuffer (*tb_napi_create_arraybuffer)
#define napi_create_int32 (*tb_napi_create_int32)
#define napi_create_typedarray (*tb_napi_create_typedarray)
#define napi_define_properties (*tb_napi_define_properties)
#define napi_get_array_length (*tb_napi_get_array_length)
#define napi_get_arraybuffer_info (*tb_napi_get_arraybuffer_info)
#define napi_get_cb_info (*tb_napi_get_cb_info)
#define napi_get_dataview_info (*tb_napi_get_dataview_info)
#define napi_get_element (*tb_napi_get_element)
#define napi_get_null (*tb_napi_get_null)
#define napi_get_typedarray_info (*tb_napi_get_typedarray_info)
#define napi_get_value_double (*tb_napi_get_value_double)
#define napi_get_value_string_utf8 (*tb_napi_get_value_string_utf8)
#define napi_get_value_uint32 (*tb_napi_get_value_uint32)
#define napi_is_arraybuffer (*tb_napi_is_arraybuffer)
#define napi_is_dataview (*tb_napi_is_dataview)
#define napi_is_typedarray (*tb_napi_is_typedarray)
#define napi_set_element (*tb_napi_set_element)
#define napi_throw_error (*tb_napi_throw_error)
#define napi_throw_range_error (*tb_napi_throw_range_error)
#define napi_throw_type_error (*tb_napi_throw_type_error)
