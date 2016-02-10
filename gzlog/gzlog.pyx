import io

cdef extern from "cgzlog.h":
    ctypedef void* gzlog

    gzlog* gzlog_open(char *path)
    int gzlog_write(gzlog* log, void* data, size_t len)
    int gzlog_compress(gzlog* log)
    int gzlog_close(gzlog* log)

cdef extern from "cgzlog.c":
    struct log:
        int fd

cdef extern from "Python.h":
    bint PyMemoryView_Check(object obj)
    Py_buffer *PyMemoryView_GET_BUFFER(object obj)

cdef class Gzlog:
    """This type extension managed the gzlog object."""
    cdef gzlog* _gzlog  # Pointer to log struct
    cdef bint _dirty  # Data to be compressed/flushed?
    def __cinit__(self, path):
        self._gzlog = gzlog_open(path.encode('utf-8'))
        if self._gzlog == NULL:
            raise IOError
        self._dirty = False

    def fileno(self):
        cdef log* log_ = <log*>self._gzlog
        return log_[0].fd

    def flush(self):
        cdef int rval
        # Only call gzlog_compress if dirty, otherwise returns -1 error
        if self._dirty:
            rval = gzlog_compress(self._gzlog)
            self._raise(rval)
            self._dirty = False

    cdef _raise(self, int rval):
        if rval == -1:
            raise IOError
        elif rval == -2:
            raise MemoryError
        elif rval == -3:
            raise RuntimeError

    def write(self, data):
        cdef char* cdata
        cdef Py_buffer* ddata
        cdef int rval
        # Cython doesn't allow read-only memoryview objects to be
        # cast to typed memoryviews, so we need to treat those differently
        if not PyMemoryView_Check(data):
            cdata = data
            rval = gzlog_write(self._gzlog, cdata, len(data))
        else:
            ddata = PyMemoryView_GET_BUFFER(data)
            rval = gzlog_write(self._gzlog, ddata.buf, len(data))
        self._raise(rval)
        self._dirty = True
        # Return the number of bytes written (blocking I/O)
        return len(data)

    def close(self):
        cdef int rval
        rval = gzlog_close(self._gzlog)
        if rval == -3:
            raise RuntimeError
        self._dirty = False


class GZipLog(io.RawIOBase):
    """A writable bytestream object.

    This can be wrapped in a TextIOWrapper for UTF-8 encoding, and in a
    BufferedWriter for faster (buffered) writing.

    Parameters
    ----------
    path : str
        The path to create the log at. Note that .gz will be appended.

    """
    # We can't do multiple inheritence with Gzlog as well (instance
    # lay-out conflict) so we need to do it in a messier way
    def __init__(self, *args, **kwargs):
        self._gzlog = Gzlog(*args, **kwargs)

    def fileno(self):
        return self._gzlog.fileno()

    def writable(self):
        return not self.closed

    def write(self, *args, **kwargs):
        self._checkClosed()
        return self._gzlog.write(*args, **kwargs)

    def flush(self):
        self._checkClosed()
        self._gzlog.flush()

    def close(self):
        # Closed should be a no op if called repeatedly
        # Note that this gets called by io.RawIOBase's __del__ method
        if not self.closed:
            self._gzlog.close()
        # This call is a no op if self.closed is True
        super(GZipLog, self).close()
