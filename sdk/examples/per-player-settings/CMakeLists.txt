# bmashup-sdk 0.5.0 example (per-player-settings). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_player_settings LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_sdk_player_settings
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_sdk_player_settings.c
    MOD_DIR bmashup-sdk-per-player-settings
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)