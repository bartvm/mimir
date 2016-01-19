# Mímir

JSON-based logging framework that allows [streaming to a gzipped
log](https://github.com/madler/zlib/blob/master/examples/gzlog.c) and
publishing log updates over TCP sockets using ZeroMQ (both persistent
and streaming).

To test, run `python setup.py build_ext -i` to build the Cython wrappers
and then run `python test.py`. Run `python test_persistent_client.py`
simultaneously to see updates arrive.
