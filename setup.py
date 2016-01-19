from setuptools import setup, Extension
from codecs import open
from os import path
from Cython.Build import cythonize

here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='mimir',
    version='0.1.dev1',
    description='A mini-framework for logging JSON-compatible objects',
    long_description=long_description,
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
    install_requires=['pyzmq', 'simplejson', 'six', 'cytoolz'],
    ext_modules=cythonize([
        Extension("mimir.gzlog", ["gzlog/gzlog.pyx", "gzlog/cgzlog.c"],
                  libraries=['z'])
    ])
)
