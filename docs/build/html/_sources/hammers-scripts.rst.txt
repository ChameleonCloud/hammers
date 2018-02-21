==================================
Management Scripts ("Hammers")
==================================

These are the collection of scripts used to fix inconsistencies in the
various OpenStack services. Not particularly bright tools, but good for
a first-pass.

The tools are run in a Python virtualenv to avoid package clashes with the
system Python. On the CHI\@TACC and CHI\@UC controllers, they live at
``/root/scripts/hammers/venv``. The scripts can be called directly without
any path shenanigans by providing the full path, e.g.
``/root/scripts/hammers/venv/bin/conflict-macs info``, and that is how the
cronjobs do it.

Script Descriptions
=======================

Neutron Resource "Reaper"
------------------------------

.. code-block:: bash

    neutron-reaper {info, delete} \
                   {ip, port} \
                   <grace-days> \
                   [ --dbversion ocata ]

Reclaims idle floating IPs and cleans up stale ports.

Required arguments, in order:

* ``info`` to just display what would be cleaned up, or actually clean it up with ``delete``.
* Consider floating ``ip``'s or ``port``'s
* A project needs to be idle for ``grace-days`` days.

Optional arguments:

* ``--dbversion ocata`` needed for the Ocata release as the database schema
  changed slightly.


Conflicting Ironic/Neutron MACs
-----------------------------------

.. automodule:: hammers.scripts.conflict_macs

.. code-block:: bash

    conflict-macs \
        {info, delete} \
        ( --ignore-from-ironic-config <path to ironic.conf> |
          --ignore-subnet <subnet UUID> )

The Ironic subnet must be provided---directly via ID or determined from a
config---otherwise the script would think that they are in conflict.

Undead Instances
-----------------------

Sometimes Nova doesn't seem to tell Ironic the instance went away on a node,
then the next time it deploys to the same node, Ironic fails.

.. code-block:: bash

    undead-instances {info, delete}

Running with ``info`` displays what it thinks is wrong, and with ``delete``
will clear the offending state from the nodes.

IPMI Error Cleanup Retry
------------------------------

.. code-block:: bash

    retry-ipmi {info, reset}

Resets Ironic nodes in error state with a known, common error. Started out
looking for IPMI-related errors, but isn't intrinsically specific to them
over any other error that shows up on the nodes. Records the resets it
performs on the node metadata (``extra`` field) and refuses after some number
(currently 3) of accumulated resets.

Currently watches out for:

.. code-block:: text

    ^Failed to tear down\. Error: Failed to set node power state to power off\.
    ^Failed to tear down\. Error: IPMI call failed: power status\.


Dirty Ports
-------------

.. code-block:: bash

    dirty-ports {info, clean}

There was/is an issue where a non-empty value in an Ironic node's port's
``internal_info`` field would cause a new instance to fail deployment on the
node. This notifies (``info``) or ``clean``\ s up if there is info on said
ports on nodes that are in the "available" state.


Curiouser
--------------

.. note::

    Not well-tested, may be slightly buggy with Chameleon phase 2 updates.

.. code-block:: bash

    curiouser

Displays Ironic nodes that are in an error state, but not in maintenance.


Common Options
=================

* ``--slack <json-options>`` - if provided, used to post notifications to Slack
* ``--osrc <rc-file>`` - alternate way to feed in the OS authentication vars

.. _env_setup:

Setup
===============

As mentioned in the intro, the scripts are run in a virtualenv. Here's how
to set it up:

1. Get code

.. code-block:: bash

    mkdir -p /root/scripts/hammers
    cd /root/scripts/hammers
    git clone https://github.com/ChameleonCloud/hammers.git

2. Create environment

.. code-block:: bash

    virtualenv /root/scripts/hammers/venv
    /root/scripts/hammers/venv/bin/pip install -r /root/scripts/hammers/hammers/requirements.txt
    /root/scripts/hammers/venv/bin/pip install -e /root/scripts/hammers/hammers

3. Set up credentials for OpenStack and Slack

The :ref:`Puppet cronjobs <puppet_jobs>` have a configuration variable that
points to the OS shell var file, for instance ``/root/adminrc``.

There is also a file for Slack vars, e.g. ``/root/scripts/slack.json``. It
is a JSON with a root key ``"webhook"`` that is a URL (keep secret!) to post to
and another root key ``"hostname_name"`` that is a mapping of FQDNs to
pretty names.

Example:

.. code-block:: json

    {
        "webhook": "https://hooks.slack.com/services/...super-seekrit...",
        "hostname_names": {
            "m01-07.chameleon.tacc.utexas.edu": "CHI@TACC",
            "m01-03.chameleon.tacc.utexas.edu": "KVM@TACC",
            "admin01.uc.chameleoncloud.org": "CHI@UC"
        }
    }

.. _puppet_jobs:

Puppet Directives
======================

Add cronjob(s) to Puppet. These expect that the above :ref:`setup <env_setup>`
is already done.

.. code-block:: puppet

    $slack_json_loc = '/root/scripts/slack.json'
    $osrc_loc = '/root/adminrc'
    $venv_bin = '/root/scripts/hammers/venv/bin'

    cron { 'hammers-neutronreaper-ip':
        command => "$venv_bin/neutron-reaper delete ip 14 --dbversion ocata --slack $slack_json_loc --osrc $osrc_loc 2>&1 | /usr/bin/logger -t hammers-neutronreaper-ip",
        user => 'root',
        hour => 5,
        minute => 20,
    }
    cron { 'hammers-retryipmi':
        command => "$venv_bin/retry-ipmi info --slack $slack_json_loc --osrc $osrc_loc 2>&1 | /usr/bin/logger -t hammers-retryipmi",
        user => 'root',
        hour => 5,
        minute => 25,
    }
    cron { 'hammers-conflictmacs':
        command => "$venv_bin/conflict-macs info --slack $slack_json_loc --osrc $osrc_loc --ignore-from-ironic-conf /etc/ironic/ironic.conf 2>&1 | /usr/bin/logger -t hammers-conflictmacs",
        user => 'root',
        hour => 5,
        minute => 30,
    }
    cron { 'hammers-undeadinstances':
        command => "$venv_bin/undead-instances info --slack $slack_json_loc --osrc $osrc_loc 2>&1 | /usr/bin/logger -t hammers-undeadinstances",
        user => 'root',
        hour => 5,
        minute => 35,
    }
