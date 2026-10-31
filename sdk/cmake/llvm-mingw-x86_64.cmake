# llvm-mingw-x86_64.cmake - bmashup-sdk 0.3.0 toolchain file: Windows x64 plugins with llvm-mingw clang (the compiler the
# host itself is built with). The toolchain root, first match wins:
#   -DLLVM_MINGW_ROOT=<dir>   or   env LLVM_MINGW_ROOT=<dir>     (<dir>/bin/x86_64-w64-mingw32-clang[.exe])
#   x86_64-w64-mingw32-clang on PATH
# build.ps1 passes -DLLVM_MINGW_ROOT from -LlvmMingw / BMKIT_LLVM_MINGW / the clang on PATH (mod kit 0.4.1: no fixed path).
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)

if(NOT LLVM_MINGW_ROOT AND DEFINED ENV{LLVM_MINGW_ROOT})
    set(LLVM_MINGW_ROOT "$ENV{LLVM_MINGW_ROOT}")
endif()
set(LLVM_MINGW_ROOT "${LLVM_MINGW_ROOT}" CACHE PATH "llvm-mingw install root (empty: search PATH)")
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES LLVM_MINGW_ROOT)
if(LLVM_MINGW_ROOT)
    set(_bmsdk_hints HINTS "${LLVM_MINGW_ROOT}/bin" NO_DEFAULT_PATH)
endif()
find_program(_bmsdk_cc x86_64-w64-mingw32-clang ${_bmsdk_hints} REQUIRED)
set(CMAKE_C_COMPILER "${_bmsdk_cc}")
get_filename_component(_bmsdk_bin "${_bmsdk_cc}" DIRECTORY)
set(CMAKE_FIND_ROOT_PATH "${_bmsdk_bin}/../x86_64-w64-mingw32")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
