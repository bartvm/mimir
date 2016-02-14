import abc
import io
import sys
import threading
from collections import deque

import six
import zmq

from . import gzlog
from .utils import zpipe


@six.add_metaclass(abc.ABCMeta)
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

    def close(self):
        pass

    @abc.abstractmethod
    def log(self, entry):
        raise NotImplementedError


class FileHandler(Handler):
    """Handler that owns a file object."""
    def close(self):
        """Close the file object if possible."""
        if (hasattr(self.fp, 'close') and
                self.fp not in (sys.stdout, sys.stdin, sys.stderr)):
            self.fp.close()


class PrintHandler(FileHandler):
    """Prints entries to a file.

    Parameters
    ----------
    formatter : callable
        A callable that takes two arguments, a log entry (`dict`) and a
        file-like descriptor (object with `.write()` method). The callable
        is expected to write a text-formatted version of the log entry to
        this file.
    fp : fileobj
        A file-like object to write to. Defaults to `sys.stdout`.

    """
    def __init__(self, formatter, fp=sys.stdout, **kwargs):
        super(PrintHandler, self).__init__(**kwargs)
        self.fp = fp
        self.formatter = formatter

    def log(self, entry):
        self.formatter(entry, self.fp)


class JSONHandler(FileHandler):
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
        self.fp.write(entry + '\n')


class GzipJSONHandler(FileHandler):
    """Writes entries to a GZipped JSON file robustly.

    Uses the `gzlog`_ example from `zlib`.

    Parameters
    ----------
    filename : str
        The filename (without `.gz` extension) to save the compressed log
        to.
    buffered : bool
        If True, the log is wrapped in a :class:`io.BufferedWriter` stream
        for faster, buffered writing. This means that on system failure
        data can be lost. It is set to true by default since it can give
        significant overhead otherwise for experiments that perform large
        amounts of logging.

    .. _gzlog:
       https://github.com/madler/zlib/blob/master/examples/gzlog.c

    """
    JSON = True

    def __init__(self, filename, buffered=True, **kwargs):
        super(GzipJSONHandler, self).__init__(**kwargs)
        stream = gzlog.GZipLog(filename)
        if buffered:
            stream = io.BufferedWriter(stream)
        self.fp = io.TextIOWrapper(stream)

    def log(self, entry):
        self.fp.write(entry + '\n')

    def __del__(self):
        """Ensure that `.close()` is called on the gzipped log."""
        if hasattr(self, 'fp'):
            self.fp.close()


class ServerHandler(Handler):
    """Streams updates over TCP.

    Parameters
    ----------
    port : int, optional
        The port over which log entries will be published. Defaults to
        5557.

    """
    JSON = True

    # http://zguide.zeromq.org/py:clonesrv1
    def __init__(self, port=5557, **kwargs):
        super(ServerHandler, self).__init__(**kwargs)
        self.ctx = zmq.Context()
        self.sequence = 0
        self.publisher = self.ctx.socket(zmq.PUB)
        self.publisher.bind('tcp://*:{}'.format(port))
        # No sleep means clients join late and miss the first few messages

    def _log(self, socket, entry):
        socket.send(str(self.sequence).encode(), zmq.SNDMORE)
        socket.send_string(entry)

    def log(self, entry):
        self.sequence += 1
        self._log(self.publisher, entry)


class PersistentServerHandler(ServerHandler):
    """Publishes updates over TCP but allows clients to catch up.

    Parameters
    ----------
    push_port : int, optional
        The port over which log entries will be published. Defaults to
        5557.
    router_port : int, optional
        The port over which snapshots will be sent. Defaults to 5556.
    maxlen : int, optional
        The maximum number of log entries to keep in memory i.e. the
        maximum size of the snapshot. Defaults to the effectively unlimited
        ``sys.maxsize``.

    """
    # http://zguide.zeromq.org/py:clonesrv2
    JSON = True

    def __init__(self, push_port=5557, router_port=5556, maxlen=sys.maxsize,
                 **kwargs):
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
        # Publish entry to all clients
        self._log(self.publisher, entry)
        # Send the entry to other thread to store
        self._log(self.updates, entry)


def state_manager(ctx, pipe, port, maxlen):
    """Stores log entries and sends them to clients upon request.

    Parameters
    ----------
    ctx : :class:`zmq.Context` instance
        The ZMQ context used to create the ROUTER socket on which requests
        for snapshots will be listened and replied to.
    pipe : :class:`zmq.Socket` instance
        A PAIR socket used to receive log entries from the main thread.
    port : int
        The port to bind the ROUTER socket to.
    maxlen : int
        The maximum number of entries to keep in memory.

    """
    store = deque([], maxlen=maxlen)

    # Create socket through which snapshots can be sent
    snapshot = ctx.socket(zmq.ROUTER)
    snapshot.bind('tcp://*:{}'.format(port))

    # Listen for both updates from main thread, and requests for snapshots
    poller = zmq.Poller()
    poller.register(pipe, zmq.POLLIN)
    poller.register(snapshot, zmq.POLLIN)

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
            # NB: client is needed to route messages
            # http://zeromq.org/tutorials:dealer-and-router
            client, request = snapshot.recv_multipart()
            assert request == b'ICANHAZ?'

            # Send all the entries to the client
            for k, v in store:
                snapshot.send(client, zmq.SNDMORE)
                snapshot.send(str(k).encode(), zmq.SNDMORE)
                snapshot.send_string(v)

            # Sending a sequence number < 0 means end of snapshot
            snapshot.send_multipart([client, b'-1', b'""'])
