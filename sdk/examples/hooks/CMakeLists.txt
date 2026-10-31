# bmashup-sdk example (f): coordinated hooks, owner + rival from one source. Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_hooks LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_sdk_hooks_demo
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_sdk_hooks_demo.c
    MOD_DIR bmashup-sdk-hooks-demo
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/demo/mod.toml)
bmsdk_add_plugin(bm_sdk_hooks_rival
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_sdk_hooks_demo.c
    DEFINES BM_HOOKS_DEMO_RIVAL
    MOD_DIR bmashup-sdk-hooks-rival
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/rival/mod.toml)
