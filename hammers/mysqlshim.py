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
        '''
        Parameters not listed are passed into the :py:func:`cursor.execute`
        function. One notable one would be ``args`` for parameterized queries.

        Keyword Parameters
        -------------------
        no_rows : bool
            Executes the query and returns the number of rows updated.

        immediate : bool
            If true, immediately runs the query and puts it into a list.
            Otherwise, an iterator is returned.
        '''
        limit = ckwargs.pop('limit', self.limit)

        if ckwargs.pop('no_rows', False):
            return self._query_no_rows(*cargs, **ckwargs)

        if ckwargs.pop('immediate', False):
            return list(itertools.islice(self._query(*cargs, **ckwargs), limit))
        else:
            return itertools.islice(self._query(*cargs, **ckwargs), limit)

    def _query(self, *cargs, **ckwargs):
        self.cursor.execute(*cargs, **ckwargs)

        fields = self.columns()
        rows = self.cursor.fetchmany(self.batch_size)
        while rows:
            for row in rows:
                yield dict(zip(fields, row))
            rows = self.cursor.fetchmany(self.batch_size)

    def _query_no_rows(self, *cargs, **ckwargs):
        # split function as _query is a generator, this isn't, so doesn't
        # need to be consumed
        return self.cursor.execute(*cargs, **ckwargs)
