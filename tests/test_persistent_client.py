import simplejson as json
import zmq

ctx = zmq.Context()

snapshot = ctx.socket(zmq.DEALER)
snapshot.linger = 0
snapshot.connect("tcp://localhost:5556")

subscriber = ctx.socket(zmq.SUB)
subscriber.linger = 0
subscriber.setsockopt(zmq.SUBSCRIBE, b'')
subscriber.connect("tcp://localhost:5557")

store = {}

sequence = 0
snapshot.send(b'ICANHAZ?')
while True:
    sequence = int(snapshot.recv())
    entry = json.loads(snapshot.recv_string())
    if sequence < 0:
        break
    store[sequence] = entry
    print('{}: {}'.format(sequence, entry))

while True:
    sequence = int(subscriber.recv())
    entry = json.loads(subscriber.recv_string())
    if sequence not in store:
        store[sequence] = entry
        print('{}: {}'.format(sequence, entry))
