#ifndef MACRO_SIM_EXPORT_H
#define MACRO_SIM_EXPORT_H

#if defined(_WIN32)
#  if defined(MACRO_SIM_C_BUILDING_LIBRARY)
#    define MACRO_SIM_C_API __declspec(dllexport)
#  else
#    define MACRO_SIM_C_API __declspec(dllimport)
#  endif
#else
#  define MACRO_SIM_C_API __attribute__((visibility("default")))
#endif

#endif
