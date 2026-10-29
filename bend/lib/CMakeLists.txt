# libturboblake with CMake, for packagers and package managers: the
# official BLAKE3 C library (blake3.h, unchanged) with its subtree hook,
# plus the Bend engine that hashes big subtrees on every core. The same
# sources as build.sh (csrc, from gen.sh); this one installs:
#
#   include/turboblake/blake3.h, turboblake.h
#   lib/libturboblake.{a,so,dylib}
#   lib/pkgconfig/libturboblake.pc        pkg-config --cflags --libs libturboblake
#   lib/cmake/turboblake/                 find_package(turboblake), turboblake::turboblake
#
# Programs keep `#include "blake3.h"`: the include path names the directory.
#
#   cmake -S bend/lib -B build -DCMAKE_BUILD_TYPE=Release
#   cmake --build build && cmake --install build --prefix /usr/local
#
# The engine needs clang and a POSIX system; anywhere else (Windows, gcc)
# the library is the official C alone, and says so. TURBOBLAKE_TARGET_CPU
# picks the engine's CPU: "baseline" (default) is each platform's release
# baseline, x86-64-v3 or armv8 (the engine checks the CPU before it runs and
# leaves an older one to the official C, ADR 0020); "native" tunes for this
# machine; anything else is passed to clang as is.
cmake_minimum_required(VERSION 3.16)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/../VERSION" TURBOBLAKE_VERSION)
string(STRIP "${TURBOBLAKE_VERSION}" TURBOBLAKE_VERSION)
project(turboblake VERSION ${TURBOBLAKE_VERSION} LANGUAGES C)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

set(CSRC "${CMAKE_CURRENT_SOURCE_DIR}/csrc")
if(CMAKE_C_COMPILER_ID MATCHES "Clang" AND UNIX)
  set(engine_default ON)
else()
  set(engine_default OFF)
endif()
option(TURBOBLAKE_ENGINE "Build the Bend engine (needs clang, POSIX)" ${engine_default})
option(TURBOBLAKE_GPU "Build the GPU backend (loads Metal or CUDA at run time)" ON)
option(TURBOBLAKE_CLI "Build bin/blake3, the test command line" OFF)
set(TURBOBLAKE_TARGET_CPU "baseline" CACHE STRING "The engine's CPU: baseline, native, or clang flags")

if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|AMD64|amd64)$")
  set(arch x86_64)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64|ARM64)$")
  set(arch aarch64)
else()
  set(arch other)
endif()

add_library(turboblake
  "${CSRC}/blake3.c" "${CSRC}/blake3_dispatch.c" "${CSRC}/blake3_portable.c")
set_target_properties(turboblake PROPERTIES
  C_STANDARD 11
  VERSION ${PROJECT_VERSION}
  SOVERSION 0
  POSITION_INDEPENDENT_CODE ON
  PUBLIC_HEADER "${CSRC}/blake3.h;${CMAKE_CURRENT_SOURCE_DIR}/turboblake.h")
target_include_directories(turboblake PUBLIC
  "$<BUILD_INTERFACE:${CSRC}>"
  "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}/turboblake>")

# The official SIMD code, picked at run time
if(arch STREQUAL "x86_64")
  if(WIN32 AND MSVC)
    enable_language(ASM_MASM)
    foreach(s sse2 sse41 avx2 avx512)
      target_sources(turboblake PRIVATE "${CSRC}/blake3_${s}_x86-64_windows_msvc.asm")
    endforeach()
  else()
    enable_language(ASM)
    set(flavor unix)
    if(WIN32)
      set(flavor windows_gnu)
    endif()
    foreach(s sse2 sse41 avx2 avx512)
      target_sources(turboblake PRIVATE "${CSRC}/blake3_${s}_x86-64_${flavor}.S")
    endforeach()
  endif()
elseif(arch STREQUAL "aarch64")
  target_sources(turboblake PRIVATE "${CSRC}/blake3_neon.c")
  target_compile_definitions(turboblake PRIVATE BLAKE3_USE_NEON=1)
else()
  target_compile_definitions(turboblake PRIVATE
    BLAKE3_NO_SSE2 BLAKE3_NO_SSE41 BLAKE3_NO_AVX2 BLAKE3_NO_AVX512)
endif()

set(pc_libs_private "")
if(TURBOBLAKE_ENGINE)
  if(TURBOBLAKE_TARGET_CPU STREQUAL "baseline")
    if(arch STREQUAL "x86_64")
      set(cpu "-march=x86-64-v3")
    elseif(APPLE AND arch STREQUAL "aarch64")
      set(cpu "-mcpu=apple-m1")
    elseif(arch STREQUAL "aarch64")
      set(cpu "-mcpu=generic")
    else()
      set(cpu "")
    endif()
  elseif(TURBOBLAKE_TARGET_CPU STREQUAL "native")
    if(arch STREQUAL "x86_64")
      set(cpu "-march=native")
    else()
      set(cpu "-mcpu=native")
    endif()
  else()
    set(cpu "${TURBOBLAKE_TARGET_CPU}")
  endif()
  separate_arguments(cpu UNIX_COMMAND "${cpu}")
  # the engine is C as Bend2 emits it, with bend/build.sh's vectorizer flags
  # (ADR 0002); only it gets the CPU flags
  set_source_files_properties("${CSRC}/engine.c" PROPERTIES
    COMPILE_OPTIONS "-O3;-w;${cpu};-mllvm;-slp-max-reg-size=512;-mllvm;-slp-recursion-max-depth=100000;-mllvm;-slp-threshold=-20;-mllvm;-inline-threshold=20000"
    COMPILE_DEFINITIONS "BEND_EMBED;main=b3e_bend_main")
  target_sources(turboblake PRIVATE "${CSRC}/engine.c" "${CSRC}/turboblake.c")
  target_compile_definitions(turboblake PRIVATE TURBOBLAKE)
  find_package(Threads REQUIRED)
  target_link_libraries(turboblake PRIVATE Threads::Threads m)
  set(pc_libs_private "-lpthread -lm")
  if(TURBOBLAKE_GPU AND (APPLE OR CMAKE_SYSTEM_NAME STREQUAL "Linux"))
    target_sources(turboblake PRIVATE "${CSRC}/turboblake_gpu.c")
    target_compile_definitions(turboblake PRIVATE TURBOBLAKE_GPU)
    target_link_libraries(turboblake PRIVATE ${CMAKE_DL_LIBS})
    if(CMAKE_DL_LIBS)
      string(APPEND pc_libs_private " -l${CMAKE_DL_LIBS}")
    endif()
  endif()
  message(STATUS "turboblake ${PROJECT_VERSION}: the Bend engine, for ${TURBOBLAKE_TARGET_CPU} (${cpu})")
else()
  message(STATUS "turboblake ${PROJECT_VERSION}: no engine (it needs clang on a POSIX system): the official C alone")
endif()

if(TURBOBLAKE_CLI)
  add_executable(blake3-cli "${CMAKE_CURRENT_SOURCE_DIR}/cli.c")
  set_target_properties(blake3-cli PROPERTIES OUTPUT_NAME blake3)
  target_link_libraries(blake3-cli PRIVATE turboblake)
  if(TURBOBLAKE_ENGINE AND TURBOBLAKE_GPU AND (APPLE OR CMAKE_SYSTEM_NAME STREQUAL "Linux"))
    target_compile_definitions(blake3-cli PRIVATE TURBOBLAKE_GPU)
  endif()
endif()

install(TARGETS turboblake EXPORT turboblakeTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
  PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/turboblake)
install(EXPORT turboblakeTargets NAMESPACE turboblake::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/turboblake)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/turboblakeConfig.cmake.in" [=[
@PACKAGE_INIT@
include(CMakeFindDependencyMacro)
if(NOT WIN32)
  find_dependency(Threads)
endif()
include("${CMAKE_CURRENT_LIST_DIR}/turboblakeTargets.cmake")
]=])
configure_package_config_file("${CMAKE_CURRENT_BINARY_DIR}/turboblakeConfig.cmake.in"
  "${CMAKE_CURRENT_BINARY_DIR}/turboblakeConfig.cmake"
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/turboblake)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/turboblakeConfigVersion.cmake"
  COMPATIBILITY SameMajorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/turboblakeConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/turboblakeConfigVersion.cmake"
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/turboblake)

# pkg-config: paths relative to the .pc file, so the tree can move
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/libturboblake.pc" "\
prefix=\${pcfiledir}/../..
libdir=\${prefix}/${CMAKE_INSTALL_LIBDIR}
includedir=\${prefix}/${CMAKE_INSTALL_INCLUDEDIR}

Name: libturboblake
Description: BLAKE3 (the official C library, blake3.h) with big inputs hashed on every core by a Bend2 engine
URL: https://gunta.github.io/turboblake/
Version: ${PROJECT_VERSION}
Cflags: -I\${includedir}/turboblake
Libs: -L\${libdir} -lturboblake
Libs.private: ${pc_libs_private}
")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/libturboblake.pc"
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
