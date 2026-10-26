// turboblake for Node, Bun and Deno: a Node-API addon over libturboblake, the
// official BLAKE3 C library whose big inputs go to the Bend engine on every
// core. A hasher's state is a blake3_hasher (plain bytes, no pointers) kept
// in a JavaScript ArrayBuffer, so a clone is a copy and nothing needs a
// finalizer. index.js builds the public APIs on these calls:
//
//   init(mode, keyOrContext?) -> ArrayBuffer   mode 0 hash, 1 keyed, 2 derive-key (raw context bytes)
//   update(state, data)                        data: any TypedArray, DataView or ArrayBuffer
//   finalize(state, out, seek)                 fills out (a Uint8Array) from output position seek
//   hash(data, out)                            one-shot default-mode hash into out
//   hashFiles(paths) -> (Uint8Array | number)[] each file's hash, or its errno (-1: not a regular file)
#include <node_api.h>
#include <stdlib.h>
#include <string.h>

#include "blake3.h"

int b3e_files(uint32_t n, const char* const* paths, unsigned char (*out)[32], int* err);

#define CHECK(call)                                   \
  do {                                                \
    if ((call) != napi_ok) {                          \
      napi_throw_error(env, NULL, "turboblake: " #call);  \
      return NULL;                                    \
    }                                                 \
  } while (0)

// The bytes of a TypedArray, DataView or ArrayBuffer argument.
static int bytes_of(napi_env env, napi_value v, void** data, size_t* len) {
  bool is;
  if (napi_is_typedarray(env, v, &is) == napi_ok && is) {
    napi_typedarray_type t;
    size_t n, off;
    napi_value ab;
    if (napi_get_typedarray_info(env, v, &t, &n, data, &ab, &off) != napi_ok) {
      return 0;
    }
    size_t width = t == napi_int8_array || t == napi_uint8_array || t == napi_uint8_clamped_array ? 1
                 : t == napi_int16_array || t == napi_uint16_array ? 2
                 : t == napi_float64_array || t == napi_bigint64_array || t == napi_biguint64_array ? 8 : 4;
    *len = n * width;
    return 1;
  }
  if (napi_is_dataview(env, v, &is) == napi_ok && is) {
    napi_value ab;
    size_t off;
    return napi_get_dataview_info(env, v, len, data, &ab, &off) == napi_ok;
  }
  if (napi_is_arraybuffer(env, v, &is) == napi_ok && is) {
    return napi_get_arraybuffer_info(env, v, data, len) == napi_ok;
  }
  napi_throw_type_error(env, NULL, "turboblake: expected a Uint8Array, another TypedArray, a DataView or an ArrayBuffer");
  return 0;
}

static blake3_hasher* state_of(napi_env env, napi_value v) {
  void* data;
  size_t len;
  if (!bytes_of(env, v, &data, &len)) {
    return NULL;
  }
  if (len != sizeof(blake3_hasher)) {
    napi_throw_type_error(env, NULL, "turboblake: not a hasher state");
    return NULL;
  }
  return (blake3_hasher*)data;
}

static napi_value js_init(napi_env env, napi_callback_info info) {
  size_t argc = 2;
  napi_value argv[2], out;
  CHECK(napi_get_cb_info(env, info, &argc, argv, NULL, NULL));
  uint32_t mode = 0;
  if (argc > 0) {
    CHECK(napi_get_value_uint32(env, argv[0], &mode));
  }
  void* state;
  CHECK(napi_create_arraybuffer(env, sizeof(blake3_hasher), &state, &out));
  void* k = NULL;
  size_t klen = 0;
  if (mode != 0 && (argc < 2 || !bytes_of(env, argv[1], &k, &klen))) {
    return NULL;
  }
  if (mode == 1) {
    if (klen != BLAKE3_KEY_LEN) {
      napi_throw_range_error(env, NULL, "turboblake: a key is 32 bytes");
      return NULL;
    }
    blake3_hasher_init_keyed(state, k);
  } else if (mode == 2) {
    blake3_hasher_init_derive_key_raw(state, k, klen);
  } else {
    blake3_hasher_init(state);
  }
  return out;
}

static napi_value js_update(napi_env env, napi_callback_info info) {
  size_t argc = 2;
  napi_value argv[2];
  CHECK(napi_get_cb_info(env, info, &argc, argv, NULL, NULL));
  blake3_hasher* h = argc == 2 ? state_of(env, argv[0]) : NULL;
  void* data;
  size_t len;
  if (h == NULL || !bytes_of(env, argv[1], &data, &len)) {
    return NULL;
  }
  blake3_hasher_update(h, data, len);
  return NULL;
}

static napi_value js_finalize(napi_env env, napi_callback_info info) {
  size_t argc = 3;
  napi_value argv[3];
  CHECK(napi_get_cb_info(env, info, &argc, argv, NULL, NULL));
  blake3_hasher* h = argc == 3 ? state_of(env, argv[0]) : NULL;
  void* out;
  size_t len;
  double seek = 0;
  if (h == NULL || !bytes_of(env, argv[1], &out, &len)) {
    return NULL;
  }
  CHECK(napi_get_value_double(env, argv[2], &seek));
  blake3_hasher_finalize_seek(h, (uint64_t)seek, out, len);
  return NULL;
}

static napi_value js_hash(napi_env env, napi_callback_info info) {
  size_t argc = 2;
  napi_value argv[2];
  CHECK(napi_get_cb_info(env, info, &argc, argv, NULL, NULL));
  void *data, *out;
  size_t len, olen;
  if (argc != 2 || !bytes_of(env, argv[0], &data, &len) || !bytes_of(env, argv[1], &out, &olen)) {
    return NULL;
  }
  blake3_hasher h;
  blake3_hasher_init(&h);
  blake3_hasher_update(&h, data, len);
  blake3_hasher_finalize(&h, out, olen);
  return NULL;
}

static napi_value js_hash_files(napi_env env, napi_callback_info info) {
  size_t argc = 1;
  napi_value argv[1], result;
  CHECK(napi_get_cb_info(env, info, &argc, argv, NULL, NULL));
  uint32_t n = 0;
  CHECK(napi_get_array_length(env, argv[0], &n));
  char** paths = calloc(n ? n : 1, sizeof(char*));
  unsigned char (*out)[32] = malloc((n ? n : 1) * 32);
  int* err = malloc((n ? n : 1) * sizeof(int));
  for (uint32_t i = 0; i < n; i += 1) {
    napi_value s;
    size_t len = 0;
    napi_get_element(env, argv[0], i, &s);
    if (napi_get_value_string_utf8(env, s, NULL, 0, &len) != napi_ok) {
      napi_throw_type_error(env, NULL, "turboblake: hashFiles takes an array of paths");
      n = i;
      goto fail;
    }
    paths[i] = malloc(len + 1);
    napi_get_value_string_utf8(env, s, paths[i], len + 1, &len);
  }
  if (!b3e_files(n, (const char* const*)paths, out, err)) {
    napi_get_null(env, &result);
  } else {
    napi_create_array_with_length(env, n, &result);
    for (uint32_t i = 0; i < n; i += 1) {
      napi_value v;
      if (err[i] == 0) {
        void* p;
        napi_value ab;
        napi_create_arraybuffer(env, 32, &p, &ab);
        memcpy(p, out[i], 32);
        napi_create_typedarray(env, napi_uint8_array, 32, ab, 0, &v);
      } else {
        napi_create_int32(env, err[i], &v);
      }
      napi_set_element(env, result, i, v);
    }
  }
  for (uint32_t i = 0; i < n; i += 1) {
    free(paths[i]);
  }
  free(paths);
  free(out);
  free(err);
  return result;
fail:
  for (uint32_t i = 0; i < n; i += 1) {
    free(paths[i]);
  }
  free(paths);
  free(out);
  free(err);
  return NULL;
}

static napi_value init(napi_env env, napi_value exports) {
  napi_property_descriptor props[] = {
    { "init", NULL, js_init, NULL, NULL, NULL, napi_default, NULL },
    { "update", NULL, js_update, NULL, NULL, NULL, napi_default, NULL },
    { "finalize", NULL, js_finalize, NULL, NULL, NULL, napi_default, NULL },
    { "hash", NULL, js_hash, NULL, NULL, NULL, napi_default, NULL },
    { "hashFiles", NULL, js_hash_files, NULL, NULL, NULL, napi_default, NULL },
  };
  napi_define_properties(env, exports, sizeof props / sizeof *props, props);
  return exports;
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, init)
