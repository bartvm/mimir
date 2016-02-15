import binascii
import codecs
import gzip
import io
import os
from contextlib import contextmanager

import zmq

from .serialization import loads


# Taken from github.com/imatix/zguide/blob/master/examples/Python/zhelpers.py
def zpipe(ctx):
    """Sets up IPC between two threads."""
    a = ctx.socket(zmq.PAIR)
    b = ctx.socket(zmq.PAIR)
    a.linger = b.linger = 0
    a.hwm = b.hwm = 1
    iface = 'inproc://{}'.format(binascii.hexlify(os.urandom(8)))
    a.bind(iface)
    b.connect(iface)
    return a, b


@contextmanager
def open(filename, raw_text=False, **kwargs):
    """Generator over log entries loaded from a file.

    Parameters
    ----------
    filename : str
        The file to read. Assumed to be gzipped if it has extension
        ``.gz``.
    raw_text : bool, optional
        If true then the generator returns the JSON strings, if false it
        deserializes the JSON strings and returns Python objects instead.
        Defaults to false.

    """
    def read(f):
        for line in f:
            if raw_text:
                yield line
            else:
                yield loads(line, **kwargs)
    root, ext = os.path.splitext(filename)
    if ext == '.gz':
        with codecs.getreader('utf-8')(gzip.open(filename)) as f:
            yield read(f)
    else:
        with io.open(filename) as f:
            yield read(f)
