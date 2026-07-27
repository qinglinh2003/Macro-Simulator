cmake_minimum_required(VERSION 3.26)

project(macro_sim_installed_c_consumer LANGUAGES C)

include(CTest)
find_package(macro_sim CONFIG REQUIRED)

add_executable(
    macro_sim_installed_c_smoke
    "${CMAKE_CURRENT_LIST_DIR}/../installed_c_smoke.c"
)
target_compile_features(macro_sim_installed_c_smoke PRIVATE c_std_11)
target_link_libraries(macro_sim_installed_c_smoke PRIVATE macro_sim::c)
# Derive the expected version from the installed package so the smoke test
# cannot go stale when a milestone bumps the engine version suffix.
target_compile_definitions(
    macro_sim_installed_c_smoke
    PRIVATE "MACRO_SIM_EXPECTED_VERSION_PREFIX=\"${macro_sim_VERSION}\""
)

if(WIN32)
    add_custom_command(
        TARGET macro_sim_installed_c_smoke
        POST_BUILD
        COMMAND
            "${CMAKE_COMMAND}" -E copy_if_different
            "$<TARGET_FILE:macro_sim::c>"
            "$<TARGET_FILE_DIR:macro_sim_installed_c_smoke>"
    )
endif()

add_test(
    NAME macro_sim.installed_c_abi
    COMMAND macro_sim_installed_c_smoke
)
