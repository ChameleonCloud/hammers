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

.. note::

    Because the hammers repo was installed with ``-e``, some updates in the
    future can be done by ``cd``-ing into the directory and ``git pull``-ing.
    Updates that change script entrypoints in ``setup.py`` will require a
    quick ``pip install...``

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

Running
=============

You can either ``source venv/bin/activate`` the virtualenv to put the scripts
into the path, or directly execute them out of the directory,
``venv/bin/neutron-reaper``

Common Options:

* ``--slack <json-options>`` - if provided, used to post notifications to Slack
* ``--osrc <rc-file>`` - alternate way to feed in the OS authentication vars


Script Descriptions
=======================

Neutron Resource "Reaper"
------------------------------

.. automodule:: hammers.scripts.neutron_reaper

Conflicting Ironic/Neutron MACs
-----------------------------------

.. automodule:: hammers.scripts.conflict_macs

Undead Instances
-----------------------

.. automodule:: hammers.scripts.undead_instances

Ironic Node Error Resetter
------------------------------

.. automodule:: hammers.scripts.ironic_error_resetter

Dirty Ports
-------------

.. automodule:: hammers.scripts.dirty_ports

Orphan Resource Providers
-------------------------

.. automodule:: hammers.scripts.orphan_resource_providers

Curiouser
--------------

.. automodule:: hammers.scripts.curiouser

Metadata Sync
---------------

.. automodule:: hammers.scripts.metadata_sync

GPU Resource "Lease Stacking"
---------------

.. automodule:: hammers.scripts.gpu_lease_stacking

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
    cron { 'hammers-ironicerrorresetter':
        command => "$venv_bin/ironic-error-resetter info --slack $slack_json_loc --osrc $osrc_loc 2>&1 | /usr/bin/logger -t hammers-ironicerrorresetter",
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
    cron { 'hammers-orphanresourceproviders':
      command => "$venv_bin/orphan-resource-providers info --slack $slack_json_loc 2>&1 | /usr/bin/logger -t hammers-orphanresourceproviders",
      user => 'root',
      hour => 5,
      minute => 40,
    }
    cron { 'hammers-gpuleasestacking':
      command => "$venv_bin/lease-stack-reaper delete --slack $slack_json_loc 2>&1 | /usr/bin/logger -t hammers-leasestacking",
      user => 'root',
      hour => 5,
      minute => 40,
    }
