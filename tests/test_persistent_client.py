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
    sequence, entry = int(snapshot.recv_string()), snapshot.recv_json()
    if sequence < 0:
        break
    store[sequence] = entry
    print('{}: {}'.format(sequence, entry))

while True:
    sequence, entry = int(subscriber.recv_string()), subscriber.recv_json()
    if sequence not in store:
        store[sequence] = entry
        print('{}: {}'.format(sequence, entry))
