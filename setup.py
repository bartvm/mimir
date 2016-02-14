# -*- coding: utf-8 -*-
import io
from setuptools import setup, Extension
from Cython.Build import cythonize


def readme():
    with io.open('README.rst') as f:
        return f.read()

setup(
    name='mimir',
    version='0.1.dev1',
    description='A mini-framework for logging JSON-compatible objects',
    long_description=readme(),
    url='https://github.com/bartvm/mimir',
    author='Bart van Merriënboer',
    author_email='bart.vanmerrienboer@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Utilities',
        'Topic :: Scientific/Engineering',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='logging machine learning',
    packages=['mimir'],
    setup_requires=['Cython'],
    install_requires=['pyzmq', 'six'],
    ext_modules=cythonize([
        Extension("mimir.gzlog", ["gzlog/gzlog.pyx"],
                  libraries=['z'])
    ]),
    zip_safe=False
)
