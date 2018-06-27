=======================
Bag o' Hammers
=======================

    *Percussive maintenance.*

Collection of various tools to keep things ship-shape. Not particularly bright tools, but good for a first-pass.

1. Neutron resource reaper

  ``neutron-reaper {info, delete} {ip, port} <grace-days> [ --dbversion ocata ]``

  Reclaims idle floating IPs and cleans up stale ports.

2. Conflicting Ironic/Neutron MACs

  ``conflict-macs {info, delete} ( --ignore-from-ironic-config <path to ironic.conf> | --ignore-subnet <subnet UUID> )``

  The Ironic subnet must be provided---directly via ID or determined from a config---otherwise the script would think that they are in conflict.

3. Undead Instances clinging to nodes

  ``undead-instances {info, delete}``

  Nova instances that have been put to rest but still cling to Ironic nodes, preventing the next generation from being...ensouled? Checks for the inconsistency and fixed it.

4. Clean up after IPMI errors

  ``ironic-error-resetter {info, reset}``

  Resets Ironic nodes in error state with a known, common error. Records those resets on the node metadata (``extra`` field) and refuses after a magic number of attempts.

5. Update orphaned resource providers

  ``orphan-resource-providers {info, update}``

  Detects and updates resource providers whose UUID has not been updated to match a recreated Nova compute node.

Common options:

* ``--slack <json-options>`` - if provided, used to post notifications to Slack
* ``--osrc <rc-file>`` - alternate way to feed in the OS authentication vars

Setup/Config
============

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

The below cronjob assumes the OS var file is at ``/root/adminrc`` and the Slack vars are in ``/root/scripts/slack.json``. The Slack file is a JSON with a root key ``"webhook"`` that is a URL to post to (keep secret!) and another root key ``"hostname_name"`` that is a mapping of FQDNs to pretty names. Example:

.. code-block:: json

  {
      "webhook": "https://hooks.slack.com/services/...super-seekrit...",
      "hostname_names": {
          "m01-07.chameleon.tacc.utexas.edu": "CHI@TACC",
          "m01-03.chameleon.tacc.utexas.edu": "KVM@TACC",
          "admin01.uc.chameleoncloud.org": "CHI@UC"
      }
  }

4. Add cronjob(s) to Puppet:

.. code-block:: puppet

  $slack_json_loc = '/root/scripts/slack.json'
  $osrc_loc = '/root/adminrc'
  $venv_bin = '/root/scripts/hammers/venv/bin'

  cron { 'hammers-neutronreaper-ip':
    command => "$venv_bin/neutron-reaper delete ip 14 --dbversion ocata --slack $slack_json_loc --osrc $osrc_loc [--kvm if at KVM site] 2>&1 | /usr/bin/logger -t hammers-neutronreaper-ip",
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
