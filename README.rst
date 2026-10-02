=======================
Bag o' Hammers
=======================

    *Percussive maintenance.*

Collection of various tools to keep things ship-shape. Not particularly bright tools, but good for a first-pass.

1. Neutron resource reaper for KVM

  ``neutron-reaper {info, delete} {ip, port} <grace-days>``

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

6. Detect orphan leases and instances

  ``orphans-detector``

  Detects leases and instances whose user is disabled or project is disabled or the user does not belong to the project.

7. Send notifications about reservation usage

  ``reservation-usage-notification``
  
  Check and notify users about their reservation.
  
 8. Floating IP reaper for CHI
 
   ``floatingip-reaper --grace-days <grace days>``
   
   Reclaim idle floating IPs.

Common options:

* ``--slack <json-options>`` - if provided, used to post notifications to Slack
* ``--osrc <rc-file>`` - alternate way to feed in the OS authentication vars

Building and Deploying
======================

Sites run hammers from the container image ``ghcr.io/chameleoncloud/hammers``.

There are two CI workflows:

* ``.github/workflows/test.yaml`` builds a wheel on pull requests and on pushes to ``master``. There are no tests yet, so this only checks that the package builds.
* ``.github/workflows/build-image.yaml`` builds and pushes the image on pushes to ``master`` and of ``v*`` tags, and when started manually from the Actions tab ("Run workflow"). It does not wait for the wheel build.

Which image tags get pushed depends on the trigger:

=========================  ================================================
Trigger                    Image tags pushed
=========================  ================================================
push to ``master``         ``master``, ``sha-<short commit>``
push of tag ``vX.Y.Z``     ``vX.Y.Z``, ``sha-<short commit>``, ``latest``
manual run on a branch     ``<branch>``, ``sha-<short commit>``
=========================  ================================================

Sites deploy a pinned ``vX.Y.Z`` tag, set in chi-in-a-box.

The release version is the git tag. ``__version__`` in ``hammers/__init__.py`` is not kept up to date. The ``Jenkinsfile``, the ``Makefile`` publish target and ``tasks.py`` (PyPI) are no longer part of the release process.

Releasing
---------

1. Merge your change to ``master``, and check that the Test run on ``master`` passed.
2. Tag the release and push the tag:

   .. code-block:: bash

     git tag v0.3.9
     git push origin v0.3.9

3. Check that the Build image run for the tag passed, and that the new tag appears on the `package page <https://github.com/orgs/ChameleonCloud/packages/container/package/hammers>`_.
4. In `chi-in-a-box <https://github.com/ChameleonCloud/chi-in-a-box>`_, set ``chameleon_hammers_tag: "v0.3.9"`` in ``kolla/defaults.yml``. Open a PR against each release branch that sites deploy from (currently ``chameleoncloud/2025.1``).
5. Deploy at each site, as described below.

Deploying to a site
-------------------

On the site's deploy host, pull the chi-in-a-box change that bumped the tag. Then run the hammers playbook:

.. code-block:: bash

  ./cc-ansible --site /opt/site-config --playbook playbooks/hammers.yml

``./cc-ansible --site /opt/site-config post-deploy`` also runs it. The hammers run from systemd timers on the control node, using ``docker run``. The timers never pull a newer image, so a site keeps running the old version until the playbook runs.

To try an unreleased build on a dev site, start a manual CI run on your branch. Then set ``chameleon_hammers_tag: "sha-<short commit>"`` in that site's ``defaults.yml`` and run the playbook.

Setup/Config
============

These are the original manual install steps. Sites now deploy hammers with chi-in-a-box, as described above.

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

Scripts that send email (``lease-stack-notifier``, ``unutilized-lease-reaper``, ``reservation-usage-notification``) read the SMTP settings from environment variables:

* ``HAMMERS_SMTP_HOST`` - SMTP relay host. If unset, ``email_relay`` from ``/etc/blazar/blazar.conf`` is used, then ``127.0.0.1``.
* ``HAMMERS_SMTP_PORT`` - SMTP port. If unset, 465 when SSL is on, otherwise 25.
* ``HAMMERS_SMTP_SSL`` - ``true`` to connect with SSL.
* ``HAMMERS_SMTP_USER`` and ``HAMMERS_SMTP_PASSWORD`` - login credentials. Login is skipped if either one is unset or empty.

4. Add cronjob(s) to Puppet:

.. code-block:: puppet

  $slack_json_loc = '/root/scripts/slack.json'
  $osrc_loc = '/root/adminrc'
  $venv_bin = '/root/scripts/hammers/venv/bin'

  cron { 'hammers-neutronreaper-ip':
    command => "$venv_bin/neutron-reaper delete ip 14 --slack $slack_json_loc --osrc $osrc_loc 2>&1 | /usr/bin/logger -t hammers-neutronreaper-ip",
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
  # Add the following to bare-metal sites only
  cron { 'hammers-reservationusagenotification':
    command => "$venv_bin/reservation-usage-notification 2>&1 | /usr/bin/logger -t hammers-reservationusagenotification",
    user => 'root',
    hour => 10,
    minute => 0,
  }
  cron { 'hammers-orphansdetector':
    command => "$venv_bin/orphans-detector --slack $slack_json_loc [--kvm if at KVM site] 2>&1 | /usr/bin/logger -t hammers-orphansdetector",
    user => 'root',
    hour => 5,
    minute => 45,
  }
  cron { 'floatingip-reaper':
    command => "$venv_bin/floatingip-reaper --slack $slack_json_loc  --osrc $osrc_loc --grace-days 3 2>&1 | /usr/bin/logger -t hammers-floatingipreaper",
    user => 'root',
    hour => 5,
    minute => 45,
  }
