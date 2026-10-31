# bmashup-sdk example (b): BOOST_AWARD modifier with caps. Part of the SDK's build, or on its own (see BUILD.md).
# Change the rule at build time, e.g. -DBMSDK_BOOST_DEFINES="BONUS_FACTOR=2.0f;BONUS_RACE_BUDGET=20.0f"
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_boost_modifier LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
set(BMSDK_BOOST_DEFINES "" CACHE STRING "compile definitions of the boost modifier (BONUS_*)")
bmsdk_add_plugin(bm_sdk_boost_modifier
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_sdk_boost_modifier.c
    DEFINES ${BMSDK_BOOST_DEFINES}
    MOD_DIR bmashup-sdk-boost-modifier
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
