# bmashup-sdk 0.6.0 example (bm-menu-popup). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_menu_popup LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_menu_popup
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_menu_popup.c
    MOD_DIR bm-menu-popup
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)