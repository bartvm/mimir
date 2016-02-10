import time
from mimir import (Logger, PrintHandler, JSONHandler,
                   GzipJSONHandler, PersistentServerHandler)

logger = Logger()

json_log = open('log.json', 'w')
logger.handlers = [PrintHandler(),
                   JSONHandler(json_log),
                   GzipJSONHandler('log.json'),
                   PersistentServerHandler(maxlen=10)]

for i in range(2500):
    logger.log({'iteration': i, 'training_error': 1. / (i + 1)})
    time.sleep(1)
