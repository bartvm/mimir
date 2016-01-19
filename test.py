from memir import *

log = Log()
log.add_handler(SimpleHandler())

json_log = open('log.json', 'w')
log.add_handler(JSONHandler(json_log))

log.add_handler(GzipJSONHandler('log.json'))

log.log({'this': 'is', 'a': 'test'})
