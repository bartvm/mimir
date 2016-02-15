import threading

import zmq
from zmq.utils.jsonapi import jsonmod as json

from .logger import Logger, LOG_READY, LOG_ACK, LOG_DONE
from .serialization import loads, serialize_numpy


def _server_logger(port, loads_kwargs, *args, **kwargs):
    """Start a server logger.

    This helper function can be called in the main process or in a separate
    thread.

    """
    logger = Logger(*args, **kwargs)

    ctx = zmq.Context()
    remote_logs = ctx.socket(zmq.ROUTER)
    remote_logs.bind('tcp://*:{}'.format(port))

    # Wait for the first client to connect
    client_id = 1
    clients = {}
    client, _, request = remote_logs.recv_multipart()
    assert request == LOG_READY
    clients[client] = client_id
    remote_logs.send_multipart([client, b'', LOG_READY])

    while clients:
        client, _, request = remote_logs.recv_multipart()
        if request == LOG_READY:
            assert client not in clients
            client_id += 1
            clients[client] = client_id
            remote_logs.send_multipart([client, b'', LOG_READY])
        elif request == LOG_DONE:
            assert client in clients
            del clients[client]
            remote_logs.send_multipart([client, b'', LOG_DONE])
        else:
            assert client in clients
            entry = loads(request.decode(), **(loads_kwargs or {}))
            entry['remote_log'] = client_id
            logger.log(entry)
            remote_logs.send_multipart([client, b'', LOG_ACK])
    return logger


def ServerLogger(port=5555, loads_kwargs=None, threaded=False, *args,
                 **kwargs):
    """A logger object that receives entries from other processes.

    A server logger follows the following protocol:

    * Wait for at least one remote logger to join
    * Wait for one of three actions:
        1. A new remote logger joining
        2. A remote logger terminating
        3. Reciving a log entry from a remote logger
    * If all remote loggers have terminated, the log will be closed.

    Parameters
    ----------
    port : int, optional
        The port to listen on for log entries.
    loads_kwargs : dict, optional
        Keyword arguments to be used for deserializing JSON objects from
        the remote loggers.
    threaded : bool, optional
        Whether the server logger should be started in another thread. If
        false (the default) this constructor will block until all remote
        loggers have sent a termination signal. If true, the logger will be
        started in another thread. Note that this thread is not a daemon,
        so the Python process will be kept alive until all remote loggers
        have terminated.
    \*args
        All other arguments are the same as those of the :func:`Logger`
        constructor.
    \*\*kwargs
        All other keyword arguments are the same as those of the
        :func:`Logger` constructor.

    Returns
    -------
    logger : :class:`_Logger` or None
        The logger object in the case threaded was `false`. If
        `threaded` was true `None` will be returned. Note that the logger
        won't be closed.

    """
    if threaded:
        thread = threading.Thread(
            target=_server_logger,
            args=(port, loads_kwargs) + args,
            kwargs=kwargs
        )
        thread.start()
    else:
        return _server_logger(port, loads_kwargs, *args, **kwargs)


class RemoteLogger(object):
    """A remote logger, which sends its log entries to a server to process.

    Parameters
    ----------
    host : str, optional
        The host to send the entries to. Defaults to `localhost`.
    port : int, optional
        The port to connect to. Defaults to 5555.
    ctx : :class:`zmq.Context`, optional
        The ZMQ context to use. If not given, one will be created.
    \*\*kwargs
        All other keyword arguments will be passed on to ``json.dumps``.

    """
    def __init__(self, host='localhost', port=5555, ctx=None, **kwargs):
        # Connect to server log
        self.closed = True
        if not ctx:
            ctx = zmq.Context()
        server_log = ctx.socket(zmq.REQ)
        server_log.connect('tcp://{}:{}'.format(host, port))
        self.server_log = server_log

        # Handshake with server
        server_log.send(LOG_READY)
        assert server_log.recv() == LOG_READY
        self.closed = False

        # JSON serialization
        kwargs.setdefault('ensure_ascii', False)
        kwargs.setdefault('default', serialize_numpy)
        self.json_kwargs = kwargs

    def log(self, entry):
        """Serialize the log entry and send it to the server logger."""
        self.server_log.send_string(json.dumps(entry, **self.json_kwargs))
        assert self.server_log.recv() == LOG_ACK

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the connection.

        Closing the connection consists of sending a termination signal to
        the server logger, and waiting for an acknowledgement of this
        signal from the server.

        """
        if not self.closed:
            self.server_log.send(LOG_DONE)
            assert self.server_log.recv() == LOG_DONE
            self.closed = True

    def __del__(self):
        self.close()
