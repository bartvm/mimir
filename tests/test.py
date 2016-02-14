import time
from mimir import Logger
from mimir.handlers import (PrintHandler, JSONHandler, GzipJSONHandler,
                            PersistentServerHandler)
from mimir.formatters import simple_formatter

logger = Logger()

json_log = open('log.json', 'w')
logger.handlers = [PrintHandler(simple_formatter),
                   JSONHandler(json_log),
                   GzipJSONHandler('log.json'),
                   PersistentServerHandler(maxlen=10)]

for i in range(2500):
    logger.log({'iteration': i, 'training_error': 1. / (i + 1)})
    time.sleep(0.2)
