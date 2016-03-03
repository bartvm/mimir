"""The logger object and user-friendly interface for constructing it."""
import io
import os
from collections import deque, Sequence

import simplejson as json

from . import utils
from .formatters import simple_formatter
from .serialization import serialize_numpy, loads
from .handlers import (GzipJSONHandler, JSONHandler, PrintHandler,
                       PersistentServerHandler, ServerHandler)


def Logger(filename=None, maxlen=0, stream=False, stream_maxlen=0,
           formatter=simple_formatter, push_port=5557, router_port=5556,
           **kwargs):
    r"""A pseudo-class for easy initialization of a log.

    .. note::

       Note that the `stream` and `stream_maxlen` arguments are
       independent. In order to respond to requests from streaming clients,
       past entries are stored in a separate thread when `stream_maxlen >
       0`, which is not the case for the entries stored when `maxlen > 0`.

    Parameters
    ----------
    filename : str, optional
        The file to save the log to in newline delimited JSON format. If
        the filename ends in `.gz` it will be compressed on the fly.
    maxlen : int or None, optional
        The number of entries to store for later retrieval. By default this
        is 0 i.e. entries are discarded after being fed to the handlers.
        For unlimited memory pass ``None``. When `maxlen > 0` normal list
        indexing can be used e.g. ``log[-1]`` to access the last entry. Use
        ``None`` for unlimited memory.
    stream : bool, optional
        If `True`, log entries will be published over a ZeroMQ socket.
        Defaults to `False`.
    stream_maxlen : int or None, optional
        How many entries the log should keep in memory so that clients of
        the streaming interface can request data that they missed. Ignored
        when `stream` is `False`, defaults to `0`. Use ``None`` for
        unlimited memory.
    formatter : function, optional
        A formatter function that determines how log entries will be
        printed to standard output. If `None`, entries will not be printed
        at all. Defaults to :func:`simple_formatter`.
    push_port : int, optional
        The port over which log entries will be published if `stream` is
        true. Defaults to 5557.
    router_port : int, optional
        The port over which snapshots will be sent if `stream_maxlen > 0`.
        Defaults to 5556.
    \*\*kwargs
        Keyword arguments passed on to ``json.dumps``. By default
        ``ensure_ascii=False`` and ``default=serialize_numpy`` are passed.

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
            handlers.append(JSONHandler(io.open(filename, 'w')))
    if formatter:
        handlers.append(PrintHandler(formatter))
    if stream:
        if stream_maxlen != 0:
            handlers.append(PersistentServerHandler(
                push_port=push_port, router_port=router_port,
                maxlen=stream_maxlen
            ))
        else:
            handlers.append(ServerHandler(port=push_port))
    return _Logger(handlers, maxlen=maxlen, **kwargs)


class _Logger(Sequence):
    """A logger object.

    Parameters
    ----------
    handlers : list or None
        A list of :class:`Handler` objects, each of which will be called in
        the given order. If `None`, the log entry will simply be ignored.
    maxlen : int or None, optional
        See :func:`Logger`'s `maxlen` argument.
    \*\*kwargs
        Keyword arguments passed on to ``json.dumps``. By default
        ``ensure_ascii=False`` and ``default=serialize_numpy`` are passed.

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
        # Ensure that json.dumps returns UTF-8 strings on Python 2
        kwargs.setdefault('ensure_ascii', False)
        kwargs.setdefault('default', serialize_numpy)
        self.json_kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getitem__(self, key):
        return self._entries[key]

    def __len__(self):
        return len(self._entries)

    def close(self):
        """Close the handlers."""
        for handler in self.handlers:
            handler.close()

    def load(self, filename, **kwargs):
        """Load log entries from the specified file.

        Parameters
        ----------
        filename : str
            The file to load from. If it ends in ``.gz`` it's assumed to be
            a gzipped file.
        \*\*kwargs
            Arguments passed on ``json.loads``, useful for deserializing
            non-basic objects. By default ``deserialize_numpy`` is passed.

        Returns
        -------
        num_entries : int
            The number of log entries in the file.

        """
        entries = deque([], maxlen=self._entries.maxlen)

        num_entries = 0
        with utils.open(filename, raw_text=True) as f:
            for entry in f:
                num_entries += 1
                entries.append(entry)
        for entry in entries:
            self._entries.append(loads(entry, **kwargs))
        return num_entries

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
