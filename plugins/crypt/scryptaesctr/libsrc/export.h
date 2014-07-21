/*
   Just provides an easy way to define the needed function
   attributes on whatever platform are needed to export the
   function and use the proper calling convention so the
   Python ctypes module can call the procedure.
*/
#ifndef H_EXPORT
#define H_EXPORT
#ifdef _WINDOWS
#define EXPORT __declspec(dllexport) __cdecl
#else
#define EXPORT
#endif
#endif