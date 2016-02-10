import zmq
from zmq.utils.jsonapi import jsonmod as json

ctx = zmq.Context()
subscriber = ctx.socket(zmq.SUB)
subscriber.linger = 0
subscriber.setsockopt(zmq.SUBSCRIBE, b'')
subscriber.connect("tcp://localhost:5557")

while True:
    sequence = int(subscriber.recv())
    entry = json.loads(subscriber.recv_string())
    print('{}: {}'.format(sequence, entry))
