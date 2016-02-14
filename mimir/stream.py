"""Helper functions to receive log entries that are streamed."""
import zmq
from zmq.utils.jsonapi import jsonmod as json

from .serialization import deserialize_numpy


def get_snapshot(host='localhost', port=5556, ctx=None, **kwargs):
    r"""Request a snapshot of data from a streaming log.

    Parameters
    ----------
    host : str, optional
        The host to bind to. Defaults to `localhost`.
    port : int, optional
        The port to bind to. Defaults to 5556.
    ctx : :class:`zmq.Context`, optional
        The context to use. If not given a new one will be created.
    \*\*kwargs
        Keyword arguments will be passed on to ``json.loads``. By default
        ``object_hook=deserialize_numpy`` will be passed to support the
        deserialization of NumPy arrays and scalars.

    Returns
    -------
    sequence : int
        The sequence number of the last entry received. If the client wants
        to receive streamed log entries after receiving the snapshot, all
        entries with a sequence number less than this should be discarded
        to avoid duplicates.
    entries : list
        A list of log entries.

    """
    if not ctx:
        ctx = zmq.Context()

    snapshot = ctx.socket(zmq.DEALER)
    snapshot.linger = 0
    snapshot.connect("tcp://{}:{}".format(host, port))
    snapshot.send(b'ICANHAZ?')

    sequence = 0
    entries = []
    while True:
        sequence_, entry = recv(snapshot, **kwargs)
        if sequence_ < 0:
            break
        entries.append(entry)
        sequence = sequence_

    return sequence, entries


def connect(host='localhost', port=5557, ctx=None):
    """Subscribe a socket to log entries being published.

    Parameters
    ----------
    host : str, optional
        The host to bind to. Defaults to `localhost`.
    port : int, optional
        The port to bind to. Defaults to 5557.
    ctx : :class:`zmq.Context`, optional
        The context to use. If not given a new one will be created.

    Returns
    -------
    subscriber : :class:`zmq.Socket`
        A socket on which log entries are received.

    """
    if not ctx:
        ctx = zmq.Context()

    subscriber = ctx.socket(zmq.SUB)
    subscriber.linger = 0
    subscriber.setsockopt(zmq.SUBSCRIBE, b'')
    subscriber.connect("tcp://{}:{}".format(host, port))

    return subscriber


def recv(s, **kwargs):
    """Receive a log entry from the given socket."""
    kwargs.setdefault('object_hook', deserialize_numpy)
    sequence = int(s.recv())
    entry = json.loads(s.recv_string(), **kwargs)
    return sequence, entry


def callback(callback, host='localhost', push_port=5557, router_port=5556,
             get_snapshot=False, ctx=None, **kwargs):
    """Execute a callback for each log entry.

    Parameters
    ----------
    callback : callable
        A callable that will be called with each log entry.
    host : str, optional
        The host to bind to. Defaults to `localhost`.
    push_port : int, optional
        The port over which entries are pushed by the server. Defaults to
        5557.
    router_port : int, optional
        The port over which requests for snapshots are sent and snapshots
        received. Defaults to 5556. Will be ignored if `get_snapshot` is
        false.
    get_snapshot : bool
        If True, the server is assumed to have a snapshot of the data and
        will be asked for it (i.e. the log was given a nonzero
        `stream_maxlen` argument). If False, only new data will come in.
        Defaults to false.
    ctx : :class:`zmq.Context`, optional
        The context to use. If not given a new one will be created.
    \*\*kwargs
        Keyword arguments will be passed on to ``json.loads``. By default
        ``object_hook=deserialize_numpy`` will be passed to support the
        deserialization of NumPy arrays and scalars.

    """
    if not ctx:
        ctx = zmq.Context()

    if get_snapshot:
        init_sequence, entries = get_snapshot(host=host, port=router_port,
                                              ctx=ctx, **kwargs)
    else:
        init_sequence, entries = 0, []

    subscriber = connect(host=host, port=push_port, ctx=ctx)

    for entry in entries:
        callback(entry)

    while True:
        try:
            sequence, entry = recv(subscriber, **kwargs)
        except KeyboardInterrupt:
            break
        if sequence > init_sequence:
            callback(entry)
