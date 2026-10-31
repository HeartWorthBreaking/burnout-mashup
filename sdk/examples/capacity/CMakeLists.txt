# bmashup-sdk example (d): engine capacity - the request plugin and the declaration-only (no code) mod.
# Part of the SDK's build, or on its own (BUILD.md). Other values at build time, e.g.
#   -DBMSDK_CAPACITY_DEFINES="CAP_LANES=100u;CAP_LOW_BYTES=0u;CAP_STATIC_BYTES=0u"
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_capacity LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
set(BMSDK_CAPACITY_DEFINES "" CACHE STRING "compile definitions of the capacity example (CAP_*)")
bmsdk_add_plugin(bm_sdk_capacity
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/plugin/bm_sdk_capacity.c
    DEFINES ${BMSDK_CAPACITY_DEFINES}
    MOD_DIR bmashup-sdk-capacity
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/plugin/mod.toml)
bmsdk_add_data_mod(bmsdk_capacity_declaration
    MOD_DIR example-capacity-declaration
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/declaration-only/mod.toml)
