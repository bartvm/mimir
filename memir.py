from __future__ import print_function

import gzip
import sys
from collections import Callable

import simplejson as json
import zmq
from cytoolz.dicttoolz import keyfilter
from six import iteritems

import gzlog
from kvsimple import KVMsg
from zhelpers import zpipe


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
        self.fp.write('\n')


class GzipJSONHandler(Handler):
    """Writes entries to a GZipped JSON file"""
    def __init__(self, filename):
        self.fp = gzlog.Gzlog(filename)

    def log(self, entry):
        json.dump(entry, self.fp)
        self.fp.write('\n')

    def __del__(self):
        fp = getattr(self, 'fp', None)
        if fp:
            fp.close()


class ServerHandler(Handler):
    # http://zguide.zeromq.org/py:clonesrv1
    def __init__(self, port=5557):
        self.ctx = zmq.Context()
        self.sequence = 0
        self.publisher = ctx.socket(zmq.PUB)
        self.publisher.bind("tcp://*:{}".format(port))

    def _log(self, entry):
        self.sequence += 1
        kvmsg = KVMsg(sequence)
        kvmsg.body = json.dumps(entry)
        kvmsg.send(self.publisher)
        return kvmsg

    def log(self, entry):
        self._log(entry)


class PersistentServerHandler(ServerHandler):
    # http://zguide.zeromq.org/py:clonesrv2
    def __init__(self, port=5557):
        super(PersistentServerHandler, self).__init__(port=port)
        self.updates, peer = zpipe(self.ctx)

        manager_thread = threading.Thread(target=state_manager,
                                          args=(self.ctx, peer))
        manager_thread.daemon=True
        manager_thread.start()

    def log(self, entry):
        kvmsg = super(PersistentServerHandler, self)._log(entry)
        kvmsg.send(self.updates)


class Route(object):
    def __init__(self, socket, identity):
        self.socket = socket # ROUTER socket to send to
        self.identity = identity # Identity of peer who requested state


def send_single(key, kvmsg, route):
    """Send one state snapshot key-value pair to a socket

    Hash item data is our kvmsg object, ready to send
    """
    # Send identity of recipient first
    route.socket.send(route.identity, zmq.SNDMORE)
    kvmsg.send(route.socket)
