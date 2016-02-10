import argparse
from functools import partial

import zmq
from bokeh.client import push_session
from bokeh.plotting import figure, curdoc, output_notebook, show
from bokeh.io import push_notebook
from zmq.utils.jsonapi import jsonmod as json


def connect(x_key, y_key, push_port=5557, router_port=5556, persistent=True):
    """Connect to a socket.

    If connected to a persistent server, a snapshot of data will be
    requested.

    Parameters
    ----------
    x_key : str
        The key in the serialized JSON object that contains the x-axis
        value.
    y_key : str
        See `x_key`.
    push_port : int
        The port over which entries are pushed by the server.
    router_port : int
        THe port over which requests for snapshots are sent and snapshots
        received.
    persistent : bool
        If True, the server is assumed to have a snapshot of the data and
        will be asked for it i.e. the `stream_maxlen` argument was
        non-zero. If False, only new data will come in.

    Returns
    -------
    subscriber : ZMQ socket
        The socket over which log entries are streamed.
    sequence : int
        The sequence number of the last log entry that was received (always
        0 in case `persistent` is set to `False`.
    x : list
        A list of the x values received as part of the snapshot. If
        `persistent` is `False` this is an empty list.
    y : list
        See `x`.

    """
    ctx = zmq.Context()

    subscriber = ctx.socket(zmq.SUB)
    subscriber.linger = 0
    subscriber.setsockopt(zmq.SUBSCRIBE, b'')
    subscriber.connect("tcp://localhost:{}".format(push_port))

    sequence = 0
    x, y = [], []

    if persistent:
        snapshot = ctx.socket(zmq.DEALER)
        snapshot.linger = 0
        snapshot.connect("tcp://localhost:{}".format(router_port))

        snapshot.send(b'ICANHAZ?')
        while True:
            sequence = int(snapshot.recv())
            entry = json.loads(snapshot.recv_string())
            if sequence < 0:
                break
            if x_key in entry and y_key in entry:
                x.append(entry[x_key])
                y.append(entry[y_key])

    return subscriber, sequence, x, y


def update(x_key, y_key, init_sequence, subscriber, plot):
    """Add a data point to a given plot.

    Parameters
    ----------
    x_key : str
        The key in the serialized JSON object that contains the x-axis
        value.
    y_key : str
        See `x_key`.
    init_sequence : int
        The sequence number to start plotting with; entries with lower
        sequence numbers will be ignored (they were probably already
        plotted when receiving the snapshot).
    subscriber : ZMQ socket
        The ZMQ socket to receive the sequence number and JSON data over.
    plot : Bokeh plot
        The Bokeh plot whose data source will be updated.

    """
    sequence = int(subscriber.recv())
    entry = json.loads(subscriber.recv_string())
    if sequence > init_sequence and x_key in entry and y_key in entry:
        # Mutating data source in place doesn't work
        x = plot.data_source.data['x'] + [entry[x_key]]
        y = plot.data_source.data['y'] + [entry[y_key]]
        plot.data_source.data['x'] = x
        plot.data_source.data['y'] = y


def serve_plot(x_key, y_key, **kwargs):
    r"""Live plot log entries on the current Bokeh server.

    Parameters
    ----------
    x_key : str
        The key in the serialized JSON object that contains the x-axis
        value.
    y_key : str
        See `x_key`.
    \*\*kwargs
        Connection parameters passed to the `connect` function.

    """
    subscriber, sequence, x, y = connect(x_key, y_key, **kwargs)
    session = push_session(curdoc())

    fig = figure()
    plot = fig.line(x, y)

    serve_update = partial(update, x_key, y_key, sequence, subscriber, plot)
    curdoc().add_periodic_callback(serve_update, 50)
    return session


def notebook_plot(x_key, y_key, **kwargs):
    r"""Live plot log entries in the current notebook.

    Parameters
    ----------
    x_key : str
        The key in the serialized JSON object that contains the x-axis
        value.
    y_key : str
        See `x_key`.
    \*\*kwargs
        Connection parameters passed to the `connect` function.

    """
    subscriber, sequence, x, y = connect(x_key, y_key, **kwargs)
    session = push_session(curdoc())
    output_notebook()

    fig = figure()
    plot = fig.line(x, y)

    show(fig)

    def notebook_update():
        update(x_key, y_key, sequence, subscriber, plot)
        push_notebook()

    curdoc().add_periodic_callback(notebook_update, 50)

    session.loop_until_closed()

if __name__ == "__main__":
    # Assuming a Bokeh server is running, this will create a live plot
    parser = argparse.ArgumentParser(description='Live stream plot')
    parser.add_argument('x_key')
    parser.add_argument('y_key')
    args = parser.parse_args()
    session = serve_plot(args.x_key, args.y_key)
    session.show()
    session.loop_until_closed()
