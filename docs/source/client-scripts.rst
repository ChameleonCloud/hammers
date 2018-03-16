=============================
Client Tools ("ccmanage")
=============================

These are the collection of modules and scripts used to perform common tasks
like launching a single node. They generally use the Python APIs, so are
kept separate in the :py:mod:`ccmanage` package.

Because they use the Python APIs, they may be sensitive to the versions
installed; consult the ``requirements.txt`` file for what's known to work.
Notably, the Blazar client comes from a repo rather than PyPI, so may be a bit
volatile.

These APIs are also used by `Abracadabra
<https://github.com/ChameleonCloud/abracadabra>`_, the automated Chameleon
appliance builder thing.

Quicknode
=============

The quicknode script creates a 24-hour lease, launches an instance on it,
then binds a floating IP to it. One command, a 10 to 15 minute wait, and you
can SSH in to your very own bare metal node.

.. autofunction:: ccmanage.quicknode.main

This script must be run as a module using ``python -m ccmanage.quicknode``. In
the future it could be configured as an entry point in ``setup.py`` and
installed like the hammers scripts.

.. code-block:: bash

    $ python -m ccmanage.quicknode --help
    usage: quicknode.py [-h] [--osrc OSRC] [--node-type NODE_TYPE]
                        [--key-name KEY_NAME] [--image IMAGE] [--no-clean]
                        [--net-name NET_NAME] [--no-floatingip]

    Fire up a single node on Chameleon to do something with.

    optional arguments:
    -h, --help            show this help message and exit
    --osrc OSRC           OpenStack parameters file that overrides envvars.
                            (default: None)
    --node-type NODE_TYPE
                            Node type to launch. May be custom or likely one of:
                            'compute_skylake', 'gpu_p100',
                            'gpu_p100_nvlink', 'gpu_k80', 'gpu_m40',
                            'compute_haswell_ib', 'storage', 'atom',
                            'compute_haswell', 'storage_hierarchy', 'arm64',
                            'fpga', 'lowpower_xeon' (default: compute_haswell)
    --key-name KEY_NAME   SSH keypair name on OS used to create an instance.
                            Must exist in Nova (default: default)
    --image IMAGE         Name or ID of image to launch. (default: CC-CentOS7)
    --no-clean            Do not clean up on failure. (default: False)
    --net-name NET_NAME   Name of network to connect to. (default: sharednet1)
    --no-floatingip       Skip assigning a floating IP. (default: False)

It can either read the environment variables (i.e. you did a ``source
osvars.rc``) or be given a file with them---including the password---in
it (``--osrc``). There must be a key pair loaded into Nova that matches
the option for ``--key-name``. A basic run:

.. code-block:: bash

    $ python -m ccmanage.quicknode --image CC-CentOS7
    Lease: creating...started <Lease 'lease-JTCMZOKMHE' on chi.uc.chameleoncloud.org (ad67ccb1-edeb-462b-a9b3-83727578b937)>
    Server: creating...building...started <Server 'instance-KYJCM5N55A' on chi.uc.chameleoncloud.org (36d52a0d-428d-45a8-88fb-232898aff0cb)>...bound ip 192.5.87.37 to server.

    'ssh cc@192.5.87.37' available.
    Press enter to terminate lease and server.

It attempts to remove the lease after hitting enter, the instance is deleted
along with it.

The main function is also a handy reference for how the other objects in
:py:mod:`ccmanage` work, specifically :py:class:`ccmanage.lease.Lease` and
:py:class:`ccmanage.server.Server` (created in a factory method of
:py:class:`~ccmanage.lease.Lease`)

Authentication
================

.. automodule:: ccmanage.auth
    :members: add_arguments, auth_from_rc, session_from_vars, session_from_args


Leases
========

.. automodule:: ccmanage.lease
    :members: lease_create_args

    .. autoclass:: Lease(keystone_session, *, sequester=False, _no_clean=False, **lease_kwargs)
        :members:

    .. autofunction:: lease_create_nodetype(*args, *, node_type, **kwargs)

Servers
=========

.. automodule:: ccmanage.server

    .. autoclass:: Server(lease, key='default', image='CC-CentOS7', net_ids=None, net_name=None, **extra)
