from __future__ import print_function

import binascii
import os
import sys
import threading
from collections import deque, Sequence

import zmq
from six import iteritems
from zmq.utils.jsonapi import jsonmod as json

from . import gzlog


def simple_formatter(entry, file, indent=0):
    """Called with the entry and the file to write to."""
    for key, value in iteritems(entry):
        if isinstance(value, dict):
            print('{}{}:'.format('  ' * indent, key))
            simple_formatter(value, file, indent + 1)
        else:
            print('{}{}: {}'.format('  ' * indent, key, value), file=file)


def Logger(filename=None, maxlen=0, stream=False, stream_maxlen=0,
           formatter=simple_formatter, **kwargs):
    """A pseudo-class for easy initialization of a log.

    .. note::

       Note that the `stream` and `stream_maxlen` arguments are
       independent. In order to respond to requests from streaming clients,
       past entries are stored in a separate thread when `stream_maxlen >
       0`, which is not the case for the entries stored when `maxlen > 0`.

    Parameters
    ----------
    filename : str
        The file to save the log to in newline delimited JSON format. If
        the filename ends in `.gz` it will be compressed on the fly.
    maxlen : int
        The number of entries to store for later retrieval. By default this
        is 0 i.e.  entries are discarded after being fed to the handlers.
        For an effectively unlimited memory use `maxlen=sys.maxsize`. When
        `maxlen > 0` normal list indexing can be used e.g. ``log[-1]`` to
        access the last entry.
    stream : bool
        If `True`, log entries will be published over a ZeroMQ socket.
        Defaults to `False`.
    stream_maxlen : int
        How many entries the log should keep in memory so that clients of
        the streaming interface can request data that they missed. Ignored
        when `stream` is `False`, defaults to `0`.
    formatter : function
        A formatter function that determines how log entries will be
        printed to standard output. If `None`, entries will not be printed
        at all. Defaults to :func:`simple_formatter`.

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
            handlers.append(JSONHandler(open(filename, 'w')))
    if formatter:
        handlers.append(PrintHandler(formatter))
    if stream:
        if stream_maxlen:
            handlers.append(PersistentServerHandler(maxlen=stream_maxlen))
        else:
            handlers.append(ServerHandler())
    return _Logger(handlers, maxlen=maxlen, **kwargs)


class _Logger(Sequence):
    """A logger object.

    Parameters
    ----------
    handlers : list or `None`
        A list of :class:`Handler` objects, each of which will be called in
        the given order. If `None`, the log entry will simply be ignored.
    maxlen : int
        See :func:`Logger`'s `maxlen` argument.

    Attributes
    ----------
    handlers : list
        The list of handlers, which can be appended to and removed from as
        needed.

    """
    def __init__(self, handlers=None, maxlen=0, **kwargs):
        if not handlers:
            handlers = []
        self.handlers = handlers
        self._entries = deque([], maxlen=maxlen)
        self.json_kwargs = kwargs

    def __getitem__(self, key):
        return self._entries[key]

    def __len__(self):
        return len(self._entries)

    def log(self, entry):
        """Log an entry.

        Will check if the handler contains filters and apply them if needed
        (so that if multiple handlers have the same filters, they are only
        applied once). Likewise, it will check if the log entry needs to be
        serialized to JSON data, and make sure that the data is only
        serialized once for each set of filters.

        Parameters
        ----------
        entry : dict
            A log entry is a (JSON-compatible) dict.

        """
        # Store entry for retrieval
        self._entries.append(entry)

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
                    serialized_entries[filters] = json.dumps(
                        filtered_entry, **self.json_kwargs)
                serialized_entry = serialized_entries[filters]
                handler.log(serialized_entry)
            else:
                handler.log(filtered_entry)


class Handler(object):
    """Handlers deal with logging requests.

    Parameters
    ----------
    filters : iterable
        An iterable of functions which will be applied to the incoming
        entry. If the `JSON` attribute of the handler is true, the entry
        will be a serialized JSON object (i.e. a string). If it is false,
        the entry will be a JSON-compatible dictionary.

    Attributes
    ----------
    JSON : bool
        If `True`, this handler will receive JSON-serialized data, if
        `False` the original (but filtered) entry will be received instead.
        This allows JSON serialization to be done only once for all the
        handlers. By default, this is false.

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
        self.fp.write(entry + '\n')

    def __del__(self):
        """Ensure that `.close()` is called on the gzipped log."""
        if hasattr(self, 'fp'):
            self.fp.close()


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
        socket.send(str(self.sequence).encode(), zmq.SNDMORE)
        # ZMQ only sends bytes, and in Python 3 the JSON string will be
        # unicode, so we use the send_string and recv_string methods.
        socket.send_string(entry)

    def log(self, entry):
        self.sequence += 1
        self._log(self.publisher, entry)


class PersistentServerHandler(ServerHandler):
    """Publishes updates over TCP but allows clients to catch up."""
    # http://zguide.zeromq.org/py:clonesrv2
    JSON = True

    def __init__(self, push_port=5557, router_port=5556, maxlen=0, **kwargs):
        super(PersistentServerHandler, self).__init__(port=push_port, **kwargs)

        # Set up IPC and start a thread
        self.updates, peer = zpipe(self.ctx)
        manager_thread = threading.Thread(target=state_manager,
                                          args=(self.ctx, peer,
                                                router_port, maxlen))
        # Daemons are shut down when main process ends
        manager_thread.daemon = True
        manager_thread.start()

    def log(self, entry):
        self.sequence += 1
        self._log(self.publisher, entry)
        # Send the updates to other thread to store
        self._log(self.updates, entry)


def state_manager(ctx, pipe, port, maxlen):
    """Stores log entries and sends them to clients upon request."""
    store = deque([], maxlen=maxlen)

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
            sequence, entry = int(pipe.recv()), pipe.recv_string()
            store.append((sequence, entry))
        if snapshot in items:
            # A client asked for a snapshot
            client, request = snapshot.recv_multipart()
            # NB: client is needed to route messages
            # http://zeromq.org/tutorials:dealer-and-router
            if request != b"ICANHAZ?":
                # TODO Maybe break instead of raise to be more robust?
                raise RuntimeError('strange request: {}'.format(request))

            # Send all the entries to the client
            for k, v in store:
                snapshot.send(client, zmq.SNDMORE)
                snapshot.send(str(k).encode(), zmq.SNDMORE)
                snapshot.send_string(v)

            # Sending a sequence number < 0 means end of snapshot
            snapshot.send(client, zmq.SNDMORE)
            snapshot.send('-1'.encode(), zmq.SNDMORE)
            snapshot.send_string('""')


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
