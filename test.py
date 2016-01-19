import time
from mimir import (Log, SimpleHandler, JSONHandler,
                   GzipJSONHandler, PersistentServerHandler)

log = Log()
log.add_handler(SimpleHandler())

json_log = open('log.json', 'w')
log.add_handler(JSONHandler(json_log))

log.add_handler(GzipJSONHandler('log.json'))

log.add_handler(PersistentServerHandler())

for i in range(25):
    log.log({'this': 'is', 'a': 'test'})
    time.sleep(1)
