# coding: utf-8
from __future__ import absolute_import, print_function, unicode_literals

import itertools

from .query import LIBERTY

__all__ = ['MySqlShim']


class MySqlShim(object):
    batch_size = 100
    limit = 1000

    def __init__(self, **connect_args):
        # lazy load so to avoid installing the Python
        # package which also requires the MySQL headers...
        import MySQLdb

        self.db = MySQLdb.connect(**connect_args)
        self.cursor = self.db.cursor()
        self.version = LIBERTY

    def columns(self):
        return [cd[0] for cd in self.cursor.description]

    def query(self, *cargs, **ckwargs):
        limit = ckwargs.pop('limit', self.limit)

        if ckwargs.pop('immediate', False):
            return list(itertools.islice(self._query(*cargs, **ckwargs), limit))
        else:
            return itertools.islice(self._query(*cargs, **ckwargs), limit)

    def _query(self, *cargs, **ckwargs):
        modified_rows = self.cursor.execute(*cargs, **ckwargs)

        if self.cursor.description is None:
            # UPDATE's and INSERT's don't have a description
            yield {'updated_rows': modified_rows}
            return

        fields = self.columns()
        rows = self.cursor.fetchmany(self.batch_size)
        while rows:
            for row in rows:
                yield dict(zip(fields, row))
            rows = self.cursor.fetchmany(self.batch_size)
