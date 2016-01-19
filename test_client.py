import zmq

ctx = zmq.Context()
subscriber = ctx.socket(zmq.SUB)
subscriber.linger = 0
subscriber.setsockopt(zmq.SUBSCRIBE, b'')
subscriber.connect("tcp://localhost:5557")

while True:
    key, entry = int(subscriber.recv_string()), subscriber.recv_json()
    print('{}: {}'.format(key, entry))
