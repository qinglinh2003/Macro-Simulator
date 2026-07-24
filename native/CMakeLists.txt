include(GNUInstallDirs)
include(CTest)

option(MACRO_SIM_BUILD_BENCHMARKS "Build native benchmark executables" ON)
option(MACRO_SIM_BUILD_PYTHON "Build the nanobind Python extension" ON)
option(MACRO_SIM_BUILD_TESTS "Build native unit and ABI tests" ON)
option(MACRO_SIM_COVERAGE "Enable source coverage instrumentation" OFF)
option(MACRO_SIM_WARNINGS_AS_ERRORS "Treat project warnings as errors" ON)
set(MACRO_SIM_SANITIZERS "" CACHE STRING "Comma-separated sanitizer list")

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)

function(macro_sim_project_options target)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4)
        if(MACRO_SIM_WARNINGS_AS_ERRORS)
            target_compile_options(${target} PRIVATE /WX)
        endif()
    else()
        target_compile_options(
            ${target}
            PRIVATE
                -Wall
                -Wextra
                -Wconversion
                -Wpedantic
                -Wshadow
        )
        if(MACRO_SIM_WARNINGS_AS_ERRORS)
            target_compile_options(${target} PRIVATE -Werror)
        endif()
    endif()

    if(MACRO_SIM_SANITIZERS)
        if(MSVC)
            message(FATAL_ERROR "The requested sanitizers are not configured for MSVC")
        endif()
        string(REPLACE "," ";" sanitizer_items "${MACRO_SIM_SANITIZERS}")
        list(JOIN sanitizer_items "," sanitizer_flags)
        target_compile_options(${target} PRIVATE "-fsanitize=${sanitizer_flags}" -fno-omit-frame-pointer)
        target_link_options(${target} PRIVATE "-fsanitize=${sanitizer_flags}" -fno-omit-frame-pointer)
    endif()

    if(MACRO_SIM_COVERAGE)
        if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
            target_compile_options(${target} PRIVATE -fprofile-instr-generate -fcoverage-mapping)
            target_link_options(${target} PRIVATE -fprofile-instr-generate -fcoverage-mapping)
        elseif(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
            target_compile_options(${target} PRIVATE --coverage)
            target_link_options(${target} PRIVATE --coverage)
        else()
            message(FATAL_ERROR "Coverage is unsupported for ${CMAKE_CXX_COMPILER_ID}")
        endif()
    endif()
endfunction()

add_library(macro_sim_core STATIC src/engine_session.cpp src/version.cpp)
add_library(macro_sim::core ALIAS macro_sim_core)
target_include_directories(
    macro_sim_core
    PUBLIC
        "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
        "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)
macro_sim_project_options(macro_sim_core)

add_library(macro_sim_c SHARED src/c_api.cpp)
add_library(macro_sim::c ALIAS macro_sim_c)
target_link_libraries(macro_sim_c PRIVATE macro_sim_core)
target_include_directories(
    macro_sim_c
    PUBLIC
        "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
        "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)
target_compile_definitions(macro_sim_c PRIVATE MACRO_SIM_C_BUILDING_LIBRARY=1)
set_target_properties(
    macro_sim_c
    PROPERTIES
        OUTPUT_NAME macro_sim_c
        SOVERSION 1
        VERSION 1.0.0
)
macro_sim_project_options(macro_sim_c)

if(MACRO_SIM_BUILD_PYTHON)
    find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
    execute_process(
        COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
        RESULT_VARIABLE nanobind_result
        OUTPUT_VARIABLE nanobind_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(NOT nanobind_result EQUAL 0)
        message(FATAL_ERROR "Unable to locate nanobind through ${Python_EXECUTABLE}")
    endif()
    list(APPEND CMAKE_PREFIX_PATH "${nanobind_dir}")
    find_package(nanobind CONFIG REQUIRED)
    nanobind_add_module(_native STABLE_ABI src/python_bindings.cpp)
    target_link_libraries(_native PRIVATE macro_sim_core)
    macro_sim_project_options(_native)
    install(TARGETS _native LIBRARY DESTINATION macro_sim)
endif()

if(MACRO_SIM_BUILD_TESTS)
    add_executable(macro_sim_native_tests tests/native_tests.cpp)
    target_link_libraries(macro_sim_native_tests PRIVATE macro_sim_core macro_sim_c)
    macro_sim_project_options(macro_sim_native_tests)
    add_test(NAME macro_sim.native COMMAND macro_sim_native_tests)

    add_executable(macro_sim_c_smoke tests/c_smoke.c)
    target_link_libraries(macro_sim_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_c_smoke)
    add_test(NAME macro_sim.c_abi COMMAND macro_sim_c_smoke)
endif()

if(MACRO_SIM_BUILD_BENCHMARKS)
    add_executable(macro_sim_benchmarks benchmarks/foundation_benchmark.cpp)
    target_link_libraries(macro_sim_benchmarks PRIVATE macro_sim_core)
    macro_sim_project_options(macro_sim_benchmarks)
endif()

install(
    TARGETS macro_sim_core macro_sim_c
    EXPORT macro_simTargets
    ARCHIVE DESTINATION "${CMAKE_INSTALL_LIBDIR}"
    LIBRARY DESTINATION "${CMAKE_INSTALL_LIBDIR}"
    RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}"
)
install(DIRECTORY include/ DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}")
install(
    EXPORT macro_simTargets
    FILE macro_simTargets.cmake
    NAMESPACE macro_sim::
    DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/macro_sim"
)
