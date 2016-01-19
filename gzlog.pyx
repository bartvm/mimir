cimport cgzlog

cdef class Gzlog:
    cdef cgzlog.gzlog* _gzlog
    def __cinit__(self, path):
        self._gzlog = cgzlog.gzlog_open(path.encode('utf-8'))
        if self._gzlog == NULL:
            raise IOError

    def write(self, data):
        data = data.encode('utf-8')
        cdef char* cdata = data
        cdef int rval
        rval = cgzlog.gzlog_write(self._gzlog, cdata, len(cdata))
        if rval == -1:
            raise IOError
        elif rval == -2:
            raise MemoryError
        elif rval == -3:
            raise RuntimeError

    def close(self):
        cdef int rval
        rval = cgzlog.gzlog_close(self._gzlog)
        if rval == -3:
            raise RuntimeError
