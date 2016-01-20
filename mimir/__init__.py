from __future__ import print_function

import binascii
import os
import sys
import threading

import simplejson as json
import zmq
from six import iteritems

from . import gzlog


def simple_formatter(entry, file, indent=0):
    """Called with the entry and the file to write to."""
    for key, value in iteritems(entry):
        print('  ' * indent + str(key), file=file)
        if isinstance(value, dict):
            simple_formatter(value, file, indent + 1)
        else:
            print('  ' * (indent + 1) + str(value), file=file)


def Logger(filename=None, stream=False, persistent=True,
           formatter=simple_formatter):
    """A pseudo-class for easy initialization of a log.

    Parameters
    ----------
    filename : str
        The file to save the log to in newline delimited JSON format. If
        the filename ends in `.gz` it will be compressed on the fly.
    stream : bool
        If `True`, log entries will be published over a ZeroMQ socket.
        Defaults to `False`.
    persistent : bool
        Whether the log shoud keep entries in memory so that clients of the
        streaming interface can request all data. Ignored when `stream` is
        `False`, defaults to `True`. Should be disabled for long-running
        experiments or very large logs in order to save memory.
    formatter : function
        A formatter function that determines how log entries will be
        printed. If `None`, entries will not be printed to stdout.
        Defaults to :func:`simple_formatter`.

    Returns
    -------
    :class:`_Logger`
        A logger object with the correct handlers.

    """
    handlers = []
    if filename:
        root, ext = os.path.splitext(filename)
        # If the file ends in .gz then gzip it
        if ext == '.gz':
            handlers.append(GzipJSONHandler(root))
        else:
            # TODO codecs open?
            handlers.append(JSONHandler(open(filename, 'w')))
    if formatter:
        handlers.append(PrintHandler(formatter))
    if stream:
        if persistent:
            handlers.append(PersistentServerHandler())
        else:
            handlers.append(ServerHandler())
    return _Logger(handlers)


class _Logger(object):
    """A logger object.

    Parameters
    ----------
    handlers : list
        A list of :class:`Handler` objects, each of which will be called in
        the given order.

    Attributes
    ----------
    handlers : list
        The list of handlers, which can be appended to and removed from as
        needed.

    """
    def __init__(self, handlers=None):
        if not handlers:
            handlers = []
        self.handlers = handlers

    def log(self, entry):
        """Log an entry.

        Will check if the handler contains filters and apply them if needed
        (so that if multiple handlers have the same filters, they are only
        applied once). Likewise, it will check if the log entry needs to be
        serialized to JSON data.

        Parameters
        ----------
        entry : dict
            A log entry is a (JSON-compatible) dict.

        """
        # For each set of filters, we store the JSON serialized entry
        filtered_entries = {}
        serialized_entries = {}
        for handler in self.handlers:
            filters = frozenset(handler.filters)

            # If the content needs to be filtered, do so
            if filters:
                if filters not in filtered_entries:
                    filtered_entries[filters] = handler.filter(entry)
                filtered_entry = filtered_entries[filters]
            else:
                filtered_entry = entry

            # If the handler wants JSON data, give it
            if handler.JSON:
                if filters not in serialized_entries:
                    serialized_entries[filters] = json.dumps(filtered_entry)
                serialized_entry = serialized_entries[filters]
                handler.log(serialized_entry)
            else:
                handler.log(filtered_entry)


class Handler(object):
    """Handlers deal with logging requests.

    Attributes
    ----------
    JSON : bool
        If `True`, this handler will receive JSON-serialized data, if
        `False` the original (but filtered) entry will be received instead.
        This allows JSON serialization to be done only once.

    """
    JSON = False

    def __init__(self, filters=None):
        if not filters:
            filters = []
        self.filters = filters

    def filter(self, entry):
        for filter in self.filters:
            entry = filter(entry)


class PrintHandler(Handler):
    """Prints entries to a file.

    Parameters
    ----------
    formatter : callable
        A callable that takes two arguments, a log entry (`dict`) and a
        file-like descriptor (object with `.write()` method). The callable
        is expected to write a text-formatted version of the log entry to
        this file.
    file : fileobj
        A file-like object to write to. Defaults to `sys.stdout`.

    """
    def __init__(self, formatter=simple_formatter, file=sys.stdout, **kwargs):
        super(PrintHandler, self).__init__(**kwargs)
        self.file = file
        self.formatter = formatter

    def log(self, entry):
        self.formatter(entry, self.file)


class JSONHandler(Handler):
    """Writes entries as JSON objects to a file.

    Parameters
    ----------
    fp : fileobj
        A file-like object (with the `.write()` method) to write the
        line-delimited JSON formatted log to.

    """
    JSON = True

    def __init__(self, fp, **kwargs):
        super(JSONHandler, self).__init__(**kwargs)
        self.fp = fp

    def log(self, entry):
        self.fp.write(entry)
        self.fp.write('\n')


class GzipJSONHandler(Handler):
    """Writes entries to a GZipped JSON file robustly.

    Uses the `gzlog`_ example from `zlib`.

    Parameters
    ----------
    filename : str
        The filename (without `.gz` extension) to save the compressed log
        to.

    .. _gzlog:
       https://github.com/madler/zlib/blob/master/examples/gzlog.c

    """
    JSON = True

    def __init__(self, filename, **kwargs):
        super(GzipJSONHandler, self).__init__(**kwargs)
        self.fp = gzlog.Gzlog(filename)

    def log(self, entry):
        data = entry + '\n'
        self.fp.write(data)

    def __del__(self):
        """Tries to ensure that `.close()` is called on the gzipped log."""
        fp = getattr(self, 'fp', None)
        if fp:
            fp.close()


class ServerHandler(Handler):
    """Streams updates over TCP."""
    JSON = True

    # http://zguide.zeromq.org/py:clonesrv1
    def __init__(self, port=5557, **kwargs):
        super(ServerHandler, self).__init__(**kwargs)
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
    JSON = True

    def __init__(self, push_port=5557, router_port=5556, **kwargs):
        super(PersistentServerHandler, self).__init__(port=push_port, **kwargs)

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
