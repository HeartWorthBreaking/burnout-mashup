# bmsdk.cmake - bmashup-sdk 0.6.0 build helpers (included by the top-level CMakeLists.txt, or by one example on its own).
#   bmsdk_add_plugin(<target> SOURCES <c files> [MOD_DIR <name>] [MOD_TOML <file>] [DEFINES <d>...])
#       a native plugin module <target>.asi (no "lib" prefix, hidden visibility, -Wall -Wextra -Werror) into
#       ${BMSDK_OUT_DIR}/<MOD_DIR>/, with the mod.toml copied beside it: that folder is a drop-in mod.
#   bmsdk_add_data_mod(<name> MOD_TOML <file> [MOD_DIR <name>])
#       a data-only mod: its mod.toml copied to ${BMSDK_OUT_DIR}/<MOD_DIR>/ (no code).
# Only Windows x64 (llvm-mingw clang, or MinGW) is built and tested.
include_guard(GLOBAL)

set(BMSDK_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." CACHE INTERNAL "bmashup-sdk root")
get_filename_component(BMSDK_ROOT "${BMSDK_ROOT}" ABSOLUTE)
set(BMSDK_INCLUDE_DIR "${BMSDK_ROOT}/include" CACHE INTERNAL "bmashup-sdk headers")
if(NOT DEFINED BMSDK_OUT_DIR)
    set(BMSDK_OUT_DIR "${CMAKE_BINARY_DIR}/out")
endif()
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()
if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "bmashup-sdk 0.6.0 builds and tests Windows x64 plugins only (use cmake/llvm-mingw-x86_64.cmake)")
endif()

function(_bmsdk_copy_toml target toml dir)
    get_filename_component(_abs "${toml}" ABSOLUTE)
    add_custom_command(TARGET ${target} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory "${dir}"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different "${_abs}" "${dir}/mod.toml"
        VERBATIM)
endfunction()

function(bmsdk_add_plugin target)
    cmake_parse_arguments(P "" "MOD_DIR;MOD_TOML" "SOURCES;DEFINES" ${ARGN})
    if(NOT P_MOD_DIR)
        set(P_MOD_DIR ${target})
    endif()
    add_library(${target} MODULE ${P_SOURCES})
    target_include_directories(${target} PRIVATE "${BMSDK_INCLUDE_DIR}")
    target_compile_definitions(${target} PRIVATE ${P_DEFINES})
    target_compile_options(${target} PRIVATE -Wall -Wextra -Werror)
    # no link time stamp: the same sources and toolchain give the same bytes, so a player's approval survives a rebuild
    target_link_options(${target} PRIVATE -Wl,--no-insert-timestamp)
    set_target_properties(${target} PROPERTIES
        PREFIX "" SUFFIX ".asi" C_STANDARD 11 C_EXTENSIONS ON C_VISIBILITY_PRESET hidden
        LIBRARY_OUTPUT_DIRECTORY "${BMSDK_OUT_DIR}/${P_MOD_DIR}"
        RUNTIME_OUTPUT_DIRECTORY "${BMSDK_OUT_DIR}/${P_MOD_DIR}")
    foreach(_cfg Debug Release RelWithDebInfo MinSizeRel)
        string(TOUPPER ${_cfg} _u)
        set_target_properties(${target} PROPERTIES LIBRARY_OUTPUT_DIRECTORY_${_u} "${BMSDK_OUT_DIR}/${P_MOD_DIR}")
    endforeach()
    if(P_MOD_TOML)
        _bmsdk_copy_toml(${target} "${P_MOD_TOML}" "${BMSDK_OUT_DIR}/${P_MOD_DIR}")
    endif()
endfunction()

function(bmsdk_add_data_mod name)
    cmake_parse_arguments(P "" "MOD_DIR;MOD_TOML" "" ${ARGN})
    if(NOT P_MOD_DIR)
        set(P_MOD_DIR ${name})
    endif()
    get_filename_component(_abs "${P_MOD_TOML}" ABSOLUTE)
    set(_dst "${BMSDK_OUT_DIR}/${P_MOD_DIR}/mod.toml")
    add_custom_command(OUTPUT "${_dst}"
        COMMAND ${CMAKE_COMMAND} -E make_directory "${BMSDK_OUT_DIR}/${P_MOD_DIR}"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different "${_abs}" "${_dst}"
        DEPENDS "${_abs}" VERBATIM)
    add_custom_target(${name} ALL DEPENDS "${_dst}")
endfunction()
