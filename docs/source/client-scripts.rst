=============================
Client Tools ("ccmanage")
=============================

These are the collection of modules and scripts used to perform common tasks
like launching a single node. They generally use the Python APIs, so are
kept separate in the :py:mod:`ccmanage` package.

Because they use the Python APIs, they may be sensitive to the versions
installed; consult the ``requirements.txt`` file for what's known to work.
Notably, the Blazar client comes from a repo rather than PyPI so may be a bit
volatile.


Authentication
================

.. automodule:: ccmanage.auth
    :members: add_arguments, auth_from_rc, session_from_vars, session_from_args


Leases
========

.. automodule:: ccmanage.lease


Servers
=========

.. automodule:: ccmanage.server


Quick Node
=============

.. automodule:: ccmanage.quicknode
