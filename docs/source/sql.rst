=========================
Direct Database Access
=========================

Some methods, properties are not fully exposed via the APIs, or are extremely
slow or difficult to retrieve. Direct database access can be used with an
abundance of caution and the caveat that it's not guaranteed to work in
future releases without modification.


Credentials and Connecting
==================================

Credential Configuration
---------------------------

.. autoclass:: hammers.mycnf.MyCnf
    :members:

.. autoclass:: hammers.mysqlargs.MySqlArgs
    :members: inject, extract, connect

Connecting
---------------

.. autoclass:: hammers.mysqlshim.MySqlShim
    :members: columns, query

Queries
===========

.. automodule:: hammers.query
    :members: query, project_col, idle_projects, latest_instance_interaction,
              owned_ips, owned_ip_single, projects_with_unowned_ports,
              owned_ports_single, future_reservations,
              clear_ironic_port_internalinfo, remove_extra_capability, main
