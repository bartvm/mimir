import base64

import numpy
import simplejson as json
from numpy.lib.format import header_data_from_array_1_0


def serialize_numpy(obj):
    """Serializes NumPy arrays and scalars.

    Note that ``numpy.generic`` objects are converted to Python types,
    which means that on deserialization they won't be the same object e.g.
    ``numpy.float32`` will be deserialized as a ``float``.

    """
    if isinstance(obj, numpy.ndarray):
        if not obj.flags.c_contiguous and not obj.flags.f_contiguous:
            obj = numpy.ascontiguousarray(obj)
        dct = header_data_from_array_1_0(obj)
        data = base64.b64encode(obj.data)
        dct['__ndarray__'] = data
        return dct
    if isinstance(obj, numpy.generic):
        return obj.item()
    raise TypeError


def deserialize_numpy(dct):
    """Deserialize NumPy arrays encoded as base64 data."""
    if '__ndarray__' in dct:
        data = base64.b64decode(dct['__ndarray__'])
        obj = numpy.frombuffer(data, dtype=dct['descr'])
        if dct['fortran_order']:
            obj.shape = dct['shape'][::-1]
            obj = obj.transpose()
        else:
            obj.shape = dct['shape']
        return obj
    return dct


def loads(entry, **kwargs):
    """Wrapper of ``json.loads`` with sensible defaults"""
    kwargs.setdefault('object_hook', deserialize_numpy)
    return json.loads(entry, **kwargs)
