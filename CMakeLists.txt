cmake_minimum_required(VERSION 3.26)

project(
    macro_sim
    VERSION 0.6.0
    DESCRIPTION "Native foundation for the macro simulator"
    LANGUAGES C CXX
)

include(CTest)

add_subdirectory(native)
