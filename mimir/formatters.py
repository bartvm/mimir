from __future__ import print_function

import six


def simple_formatter(entry, fp, indent=0):
    """Called with the entry and the file to write to."""
    for key, value in six.iteritems(entry):
        if isinstance(value, dict):
            print('{}{}:'.format('  ' * indent, key))
            simple_formatter(value, fp, indent + 1)
        else:
            print('{}{}: {}'.format('  ' * indent, key, value), file=fp)
