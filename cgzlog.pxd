# Cannot be called gzlog.pxd

cdef extern from "cgzlog.h":
    ctypedef void* gzlog

    gzlog* gzlog_open(char *path)
    int gzlog_write(gzlog* log, void* data, size_t len)
    int gzlog_compress(gzlog* log)
    int gzlog_close(gzlog* log)
