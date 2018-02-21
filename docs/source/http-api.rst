======================
HTTP Helpers
======================

These are DIY shims that access OpenStack services' APIs without
requiring much more than Python requests. The objects they return
are not intelligent, but are simple lists and dictionaries.


Auth Management
================

.. automodule:: hammers.osapi

    .. autofunction:: hammers.osapi.add_arguments

    .. autofunction:: hammers.osapi.load_osrc

    .. autoclass:: hammers.osapi.Auth
        :members: authenticate, endpoint, token

        .. automethod:: from_env_or_args(*, args=None, env=True)


Service API Wrappers
======================

For the below, the `auth` argument is an instance of
:py:class:`hammers.osapi.Auth`.

Blazar (Reservations)
-----------------------

.. automodule:: hammers.osrest.blazar
    :members: host, hosts, host_update, lease, leases, lease_delete

Glance (Image Store)
-----------------------

.. automodule:: hammers.osrest.glance
    :members: image, images, image_delete,
              image_tag, image_untag, image_upload_curl, image_download_curl

    .. autofunction:: image_properties(auth, image_id, *, add=None, remove=None, replace=None)

    .. autofunction:: image_create(auth, name, *, disk_format='qcow2', container_format='bare', visibility='private', extra=None)

Ironic (Bare Metal)
--------------------

.. automodule:: hammers.osrest.ironic
    :members: node, nodes, node_set_state, ports

    .. autofunction:: node_update(auth, node, * add=None, remove=None, replace=None)

Keystone (Authentication)
----------------------------

.. automodule:: hammers.osrest.keystone
    :members: project, projects, project_lookup, user, users, user_lookup

Neutron (Networking)
-----------------------

.. automodule:: hammers.osrest.neutron
    :members: floatingips, floatingip_delete, network, networks, ports,
              port_delete, subnet, subnets

Nova (Compute)
----------------

.. automodule:: hammers.osrest.nova
    :members:
