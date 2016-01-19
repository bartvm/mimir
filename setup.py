from distutils.core import setup
from distutils.extension import Extension
from Cython.Build import cythonize

setup(
    ext_modules=cythonize([
        Extension("gzlog", ["gzlog.pyx", "cgzlog.c"],
                  libraries=['z'],
                  define_macros=[('CYTHON_TRACE_NOGIL', '1')])
    ])
)
