from __future__ import print_function

import binascii
import os
import sys
import threading
from collections import Callable

import simplejson as json
import zmq
from cytoolz.dicttoolz import keyfilter
from six import iteritems

import gzlog


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
    """Writes entries to a GZipped JSON file robustly"""
    # https://github.com/madler/zlib/blob/master/examples/gzlog.c
    def __init__(self, filename):
        self.fp = gzlog.Gzlog(filename)

    def log(self, entry):
        # json.dump makes 9 write calls, which has too much overhead
        # so we construct a single string and write that instead
        data = '{}\n'.format(json.dumps(entry))
        self.fp.write(data)

    def __del__(self):
        fp = getattr(self, 'fp', None)
        if fp:
            fp.close()


class ServerHandler(Handler):
    """Streams updates over TCP."""
    # http://zguide.zeromq.org/py:clonesrv1
    def __init__(self, port=5557):
        self.ctx = zmq.Context()
        self.sequence = 0
        self.publisher = self.ctx.socket(zmq.PUB)
        self.publisher.bind("tcp://*:{}".format(port))
        # No sleep means clients join late and miss the first few messages

    def _log(self, socket, entry):
        # For Python 3 compatibility we use the send_string method
        socket.send_string(str(self.sequence), zmq.SNDMORE)
        socket.send_json(entry)

    def log(self, entry):
        self.sequence += 1
        self._log(self.publisher, entry)


class PersistentServerHandler(ServerHandler):
    """Publishes updates over TCP but allows clients to catch up."""
    # http://zguide.zeromq.org/py:clonesrv2
    def __init__(self, push_port=5557, router_port=5556):
        super(PersistentServerHandler, self).__init__(port=push_port)

        # Set up IPC and start a thread
        self.updates, peer = zpipe(self.ctx)
        manager_thread = threading.Thread(target=state_manager,
                                          args=(self.ctx, peer, router_port))
        # Daemons are shut down when main process ends
        manager_thread.daemon = True
        manager_thread.start()

    def log(self, entry):
        self.sequence += 1
        self._log(self.publisher, entry)
        # Send the updates to other thread to store
        self._log(self.updates, entry)


def state_manager(ctx, pipe, port):
    """Stores log entries and sends them to clients upon request."""
    store = {}

    # Create socket through which snapshots can be sent
    snapshot = ctx.socket(zmq.ROUTER)
    snapshot.bind("tcp://*:{}".format(port))

    # Listen for both updates from main thread, and requests for snapshots
    poller = zmq.Poller()
    poller.register(pipe, zmq.POLLIN)
    poller.register(snapshot, zmq.POLLIN)

    sequence = 0
    while True:
        try:
            items = dict(poller.poll())
        except (zmq.ZMQError, KeyboardInterrupt):
            break

        if pipe in items:
            sequence, entry = int(pipe.recv_string()), pipe.recv_json()
            store[sequence] = entry
        if snapshot in items:
            # A client asked for a snapshot
            client, request = snapshot.recv_multipart()
            # NB: client is needed to route messages
            # http://zeromq.org/tutorials:dealer-and-router
            if request != b"ICANHAZ?":
                # TODO Maybe break instead of raise to be more robust?
                raise RuntimeError('strange request: {}'.format(request))

            # Send all the entries to the client
            for k, v in store.items():
                snapshot.send(client, zmq.SNDMORE)
                snapshot.send_string(str(k), zmq.SNDMORE)
                snapshot.send_json(v)

            # A sequence number < 0 means end of snapshot
            snapshot.send(client, zmq.SNDMORE)
            snapshot.send_string("-1", zmq.SNDMORE)
            snapshot.send_json({})


# Taken from github.com/imatix/zguide/blob/master/examples/Python/zhelpers.py
def zpipe(ctx):
    """Sets up IPC between two threads."""
    a = ctx.socket(zmq.PAIR)
    b = ctx.socket(zmq.PAIR)
    a.linger = b.linger = 0
    a.hwm = b.hwm = 1
    iface = "inproc://%s".format(binascii.hexlify(os.urandom(8)))
    a.bind(iface)
    b.connect(iface)
    return a, b
