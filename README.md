# Mímir

JSON-based logging framework that allows [streaming to a gzipped
log](https://github.com/madler/zlib/blob/master/examples/gzlog.c) and publishing
log updates over TCP sockets using ZeroMQ.

## Quickstart

To use Mímir, simply create a logger object:

```python
import mimir
import time

logger = mimir.Logger()
for i in range(100):
    logger.log({'iteration': i, 'training_error': 1. / (i + 1)})
    time.sleep(1)
```

By default the log will just print the entry to standard output and then discard
it.  If you don't want to print anything, pass `formatter=None`, or pass a
custom `formatter` to change the way the data is printed.

### Memory

If you want to keep entries in memory so that you can access past entries, pass
a nonzero `maxlen` argument, which determines the maximum number of entries kept
in memory. This is done so that long-running experiments don't run out of
memory.

```python
logger = mimir.Logger(maxlen=10)
logger.log({'iteration': 0, 'training_error': 10})
assert logger[-1]['training_error'] == 10
```

If you're sure that you won't run out of memory you can use
`maxlen=sys.maxsize`.

### Streaming

Mímir can stream log entries over a TCP socket which clients can connect to,
both locally as well as over a network. This allows you to do things like
live-plotting your experiments. To enable this, pass `stream=True`. By default
the data is streamed, which means that clients only get the entries from after
when they joined. If you want clients to receive past log entries as well, there
is a `stream_maxlen` argument similar to the `maxlen` argument.

```python
logger = mimir.Logger(stream=True, stream_maxlen=50)
for i in range(100):
    logger.log({'iteration': i, 'training_error': 1. / (i + 1)})
    time.sleep(1)
```

To see a live plot of your log, open up a Jupyter notebook and type the
following (requires Bokeh). It will plot the last 50 datapoints, and then live
plot every entry as it comes in.

```python
import mimir
mimir.plot.notebook_plot('iteration', 'training_error')
```

### Saving to disk

We often want to analyze the log entries afterwards. Mímir allows you to save
the log to disk as line-delimited JSON files.

```python
logger = mimir.Logger(filename='log.jsonl.gz')
for i in range(100):
    logger.log({'iteration': i, 'training_error': 1. / (i + 1)})
    time.sleep(1)
```

If the filename ends with `.gz` the log will be compressed in a streaming manner
using [gzlog](https://github.com/madler/zlib/blob/master/examples/gzlog.c).

To analyze the training logs [jq](https://stedolan.github.io/jq/) is
recommended. For example, to get the minimum training error:

```bash
zcat log.json.gz | jq -s 'min_by(.training_error)'
```
