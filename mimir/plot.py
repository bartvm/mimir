import argparse
from bokeh.client import push_session
from bokeh.plotting import figure, curdoc, output_notebook, show
import simplejson as json
from bokeh.io import push_notebook
from functools import partial

import zmq


def connect(x_key, y_key, push_port=5557, router_port=5556, persistent=True):
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
            try:
                sequence = int(snapshot.recv_string())
                entry = json.loads(snapshot.recv_json())
                if sequence < 0:
                    break
                x.append(entry[x_key])
                y.append(entry[y_key])
            except:
                break

    return subscriber, sequence, x, y


def update(x_key, y_key, init_sequence, subscriber, plot):
    sequence = int(subscriber.recv_string())
    entry = json.loads(subscriber.recv_json())
    if sequence > init_sequence:
        # Mutating data source in place doesn't work
        x = plot.data_source.data['x'] + [entry[x_key]]
        y = plot.data_source.data['y'] + [entry[y_key]]
        plot.data_source.data['x'] = x
        plot.data_source.data['y'] = y


def serve_plot(x_key, y_key, **kwargs):
    subscriber, sequence, x, y = connect(x_key, y_key, **kwargs)
    session = push_session(curdoc())

    fig = figure()
    plot = fig.line(x, y)

    serve_update = partial(update, x_key, y_key, sequence, subscriber, plot)
    curdoc().add_periodic_callback(serve_update, 50)
    return session


def notebook_plot(x_key, y_key, **kwargs):
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
    parser = argparse.ArgumentParser(description='Live stream plot')
    parser.add_argument('x_key')
    parser.add_argument('y_key')
    args = parser.parse_args()
    session = serve_plot(args.x_key, args.y_key)
    session.show()
    session.loop_until_closed()
