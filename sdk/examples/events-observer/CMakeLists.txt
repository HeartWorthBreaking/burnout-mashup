# bmashup-sdk example (a): events observer. Part of the SDK's build, or on its own:
#   cmake -S examples/events-observer -B <build> -G Ninja -DCMAKE_TOOLCHAIN_FILE=<sdk>/cmake/llvm-mingw-x86_64.cmake
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_events_observer LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_sdk_events_observer
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_sdk_events_observer.c
    MOD_DIR bmashup-sdk-events-observer
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
