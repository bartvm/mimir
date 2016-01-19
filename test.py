from memir import *

log = Log()
log.add_handler(SimpleHandler())

json_log = open('log.json', 'w')
log.add_handler(JSONHandler(json_log))

log.add_handler(GzipJSONHandler('log.json'))

for i in range(25):
    log.log({'this': 'is', 'a': 'test'})
