import binascii
import os

import zmq


# Taken from github.com/imatix/zguide/blob/master/examples/Python/zhelpers.py
def zpipe(ctx):
    """Sets up IPC between two threads."""
    a = ctx.socket(zmq.PAIR)
    b = ctx.socket(zmq.PAIR)
    a.linger = b.linger = 0
    a.hwm = b.hwm = 1
    iface = 'inproc://{}'.format(binascii.hexlify(os.urandom(8)))
    a.bind(iface)
    b.connect(iface)
    return a, b
