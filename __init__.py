from __future__ import print_function

import gzip
import sys
from collections import Callable

import simplejson as json
from cytoolz.dicttoolz import keyfilter
from six import iteritems


class Log(object):
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)

    def log(self, entry):
        for handler in self.handlers:
            handler.log(entry)


class Handler(object):
    pass


class SimpleHandler(Handler):
    """Prints keys and their values with an optional filter."""
    def __init__(self, key_predicate=None, file=sys.stdout, padding='  '):
        if key_predicate and not isinstance(key_predicate, Callable):
            raise ValueError('key_predicate is not callable')
        self.key_predicate = key_predicate
        self.file = file
        self.padding = padding

    def log(self, entry):
        def pretty(d, indent=0):
            if self.key_predicate:
                d = keyfilter(self.key_predicate, d)
            for key, value in iteritems(d):
                print('{0}{1}'.format(self.padding * indent, key),
                      file=self.file)
                if isinstance(value, dict):
                    pretty(value, indent + 1)
                else:
                    print('{0}{1}'.format(self.padding * (indent + 1), value),
                          file=self.file)
        pretty(entry)
        return entry


class JSONHandler(Handler):
    """Writes entries as JSON objects to a file"""
    def __init__(self, fp):
        self.fp = fp

    def log(self, entry):
        json.dump(entry, self.fp)


class GzipJSONHandler(Handler):
    """Writes entries to a GZipped JSON file"""
    # NB: https://github.com/madler/zlib/blob/master/examples/gzlog.c
    def __init__(self, fp):
        # Use an existing file object
        self.fp = gzip.GzipFile(fileobj=fp)

    def log(self, entry):
        json.dump(entry, self.fp)


class ServerHandler(Handler):
    # http://zguide.zeromq.org/py:clonesrv1
    def __init__(self, port=5557):
        pass


class PersistentServerHandler(ServerHandler):
    # http://zguide.zeromq.org/py:clonesrv2
    def __init__(self, port=5557):
        pass
