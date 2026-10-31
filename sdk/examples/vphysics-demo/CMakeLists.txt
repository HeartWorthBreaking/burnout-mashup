# bmashup-sdk example (k): bmashup.vphysics 1 - player 1 Drag Coef x0.5 in odd races, the game's value in even races.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_vphysics_demo LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
set(BMSDK_VPHYSICS_DEFINES "" CACHE STRING "compile definitions of the vphysics demo (VPHYS_DRAG_SCALE)")
bmsdk_add_plugin(bm_vphysics_demo
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_vphysics_demo.c
    DEFINES ${BMSDK_VPHYSICS_DEFINES}
    MOD_DIR bmashup-sdk-vphysics-demo
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
