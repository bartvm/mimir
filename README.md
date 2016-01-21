# Mímir

JSON-based logging framework that allows [streaming to a gzipped
log](https://github.com/madler/zlib/blob/master/examples/gzlog.c) and
publishing log updates over TCP sockets using ZeroMQ (both persistent
and streaming).

To use it, simply open a logger object:

```python
import mimir
import time

logger = mimir.Logger('log.json.gz', stream=True)
for i in range(2500):
    logger.log({'iteration': i, 'training_error': 1. / (i + 1)})
    time.sleep(1)
```

To see a live plot of your log, open up a Jupyter notebook and type
(requires Bokeh):

```python
import mimir
mimir.plot.notebook_plot('iteration', 'training_error')
```

To analyze the training logs [jq](https://stedolan.github.io/jq/) is
recommended. For example, to get the minimum training error:

```bash
zcat log.json.gz | jq -s 'min_by(.training_error)'
```
