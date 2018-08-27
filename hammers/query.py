# coding: utf-8
from __future__ import absolute_import, print_function, unicode_literals
import functools

LIBERTY = 'liberty'
OCATA = 'ocata'
QUERIES = {}


def query(q):
    '''Decorator to include all the queries into a dictionary'''
    global QUERIES
    QUERIES[q.__name__] = {'f': q}
    return q


def project_col(version):
    '''
    The name of the column changed somewhere between L and O.

    Should be pretty basic to avoid any SQL injection.
    '''
    # might also be sensitive to the component (neutron/nova/etc.)
    return {
        LIBERTY: 'tenant_id',
        OCATA: 'project_id',
    }[version]


@query
def idle_projects(db):
    '''
    Returns rows enumerating all projects that are currently idle (number
    of running instances = 0). Also provides since when the project has been
    idle (when the latest running instance was deleted)

    There may be NULLs emitted for "latest_deletion" if a project hasn't ever
    had an instance (like an admin project...).
    '''
    sql_template = '''
    SELECT project.id
         , project.name
        #  , Count(ip.{projcol})
         , (SELECT deleted_at
            FROM   {novatable}.instances AS instance
            WHERE  instance.project_id = project.id
            ORDER  BY deleted_at DESC
            LIMIT  1)
                AS latest_deletion
    FROM   neutron.floatingips AS ip
       ,   keystone.project AS project
    WHERE  ip.{projcol} = project.id
           AND ip.status = "down"
           AND (SELECT Count(*)
                FROM   {novatable}.instances
                    AS instance
                WHERE  instance.project_id = project.id
                       AND deleted_at IS NULL
                       AND vm_state != "deleted"
                       AND vm_state != "error") = 0
    GROUP  BY {projcol}
    ORDER  BY Count({projcol}) DESC;
    '''

    projcol = project_col(db.version)
    old_sql = sql_template.format(projcol=projcol, novatable='nova')

    if db.version == 'ocata':
        # smash together data from two databases. newer openstack split the database
        # into nova (legacy?) and nova_cell0 (new schema? distributed?)
        new_sql = sql_template.format(projcol=projcol, novatable='nova_cell0')

        merged = list(db.query(old_sql, limit=None)) + list(db.query(new_sql, limit=None))

        latest_for_project = {}
        for row in merged:
            if row['id'] in latest_for_project:
                # no date = ignore
                if latest_for_project[row['id']] is None:
                    # already ignored
                    continue
                if row['latest_deletion'] is None:
                    # ignored from now on
                    latest_for_project[row['id']]['latest_deletion'] = None
                    continue
                latest_for_project[row['id']]['latest_deletion'] = max(
                    # otherwise get latest
                    row['latest_deletion'],
                    latest_for_project[row['id']]['latest_deletion']
                )
            else:
                latest_for_project[row['id']] = row

        results = [row for row in latest_for_project.values() if row['latest_deletion']]
        return results

    else:
        return db.query(old_sql, limit=None)


_LATEST_INSTANCE_DATABASES = {
    'nova',
    'nova_cell0',
}

@query
def latest_instance_interaction(db, kvm, nova_db_name='nova'):
    '''
    Get the latest interaction date with instances on the target database name.
    Combine as you so desire.
    '''
    if nova_db_name not in _LATEST_INSTANCE_DATABASES:
        # can't parameterize a database name
        raise RuntimeError('invalid database selection')
    if kvm:
        table = '{nova_db_name}.instances'.format(nova_db_name=nova_db_name)
        first_col = 'project_id'
        second_col = 'project_id'
    else:
        table = '{nova_db_name}.instances AS inst INNER JOIN keystone.project AS proj ON inst.project_id = proj.id'.format(nova_db_name=nova_db_name)
        first_col = 'proj.name'
        second_col = 'proj.id'
        
    sql = '''\
    SELECT
        {first_col} AS name,
        {second_col} AS id,
        MAX(IFNULL(deleted_at,
            IFNULL(updated_at, created_at))) AS latest_interaction,
        MAX(deleted_at is NULL) > 0 AS active
    FROM
        {table}
    GROUP BY project_id;
    '''.format(first_col=first_col, second_col=second_col,table=table)
    return db.query(sql, limit=None)


@query
def owned_ips(db, project_ids):
    '''
    Return all IPs associated with *project_ids*

    Maria 5.5 in production doesn't seem to like this, but works fine with
    a local MySQL 5.7. Is it Maria? 5.5? Too many? See owned_ip_single for one
    that works, but need to call multiple times.
    '''
    sql = '''
    SELECT id
         , status
         , {projcol} AS project_id
    FROM   neutron.floatingips
    WHERE  {projcol} IN %s;
    '''.format(projcol=project_col(db.version))
    return db.query(sql, args=[project_ids], limit=None)

@query
def floating_ips_to_leases(db, floating_ip_ids):
    '''Return 'active' leases from a tuple of floating ip ids.'''
    floating_ips_varargs = ','.join(['%s'] * len(floating_ip_ids))

    sql = '''
    SELECT bl.id AS lease_id
        , bl.action AS action
        , bl.end_date AS end_date
        , bl.deleted_at AS deleted_at
	    , nfi.id AS ip_id
    FROM neutron.floatingips nfi
    LEFT JOIN neutron.ports np ON nfi.fixed_port_id=np.id
    LEFT JOIN nova.instances ni ON np.device_id=ni.uuid
    LEFT JOIN ironic.nodes ino ON ni.uuid=ino.instance_uuid
    LEFT JOIN blazar.computehosts bc ON ino.uuid = bc.hypervisor_hostname
    LEFT JOIN blazar.computehost_allocations bca ON bca.compute_host_id=bc.id
    LEFT JOIN blazar.reservations br ON bca.reservation_id=br.id
    LEFT JOIN blazar.leases bl ON br.lease_id=bl.id
    WHERE bl.project_id=nfi.project_id
        AND bl.deleted_at is NULL
        AND nfi.id IN ({floating_ips_varargs});
    '''.format(floating_ips_varargs=floating_ips_varargs)

    return db.query(sql, args=floating_ip_ids, limit=None)

@query
def owned_compute_ip_single(db, project_id):
    '''
    Return all IPs associated with *project_id* and if associated with a port,
    whose fixed port is owned by compute
    '''
    sql = '''
    SELECT f.id
         , f.status
         , f.{projcol} AS project_id
    FROM   neutron.floatingips AS f
    LEFT JOIN  neutron.ports AS p
    ON f.fixed_port_id = p.id
    WHERE  
         f.{projcol} = %s
         AND
         ( p.device_owner LIKE 'compute%%' OR p.id is NULL );
    '''.format(projcol=project_col(db.version))
    return db.query(sql, args=[project_id], limit=None)


@query
def projects_with_unowned_ports(db, version='liberty'):
    sql = '''
    SELECT {projcol} AS project_id
         , count({projcol}) AS count_blank_owner
    FROM   neutron.ports
    WHERE  device_owner = ''
    GROUP  BY {projcol};
    '''.format(projcol=project_col(db.version))
    return db.query(sql, limit=None)


@query
def owned_compute_port_single(db, project_id):
    '''
    Return all ports associated with *project_id* and is owned by compute
    '''
    sql = '''
    SELECT id
         , status
         , {projcol} AS project_id
    FROM   neutron.ports
    WHERE  
         {projcol} = %s
         AND
         device_owner LIKE 'compute%%';
    '''.format(projcol=project_col(db.version))
    return db.query(sql, args=[project_id], limit=None)


@query
def future_reservations(db):
    '''
    Get project IDs with lease end dates in the future that haven't
    been deleted. This will also grab *active* leases, but that's erring
    on the safe side.
    '''
    sql = '''
    SELECT DISTINCT project_id
    FROM   blazar.leases
    WHERE  end_date > Now()
           AND deleted_at is NULL;
    '''
    return db.query(sql, limit=None)


@query
def clear_ironic_port_internalinfo(db, port_id):
    """Remove internal_info data from ports. When the data wasn't cleaned up,
    it appeared to block other instances from spawning on the node. Now it
    may not be required? More research needed.
    """
    sql = '''\
    UPDATE ironic.ports
    SET    internal_info = '{}'
    WHERE  uuid = %s;
    '''
    return db.query(sql, args=[port_id], no_rows=True)


@query
def remove_extra_capability(db, host_id, capability_name):
    """
    Remove an extra capability by name from `host_id`. (HTTP API doesn't
    support this as of Feb 2018)
    """
    sql = '''\
    DELETE FROM blazar.computehost_extra_capabilities
    WHERE computehost_id = %s
      AND capability_name = %s
    '''
    return db.query(sql, args=[host_id, capability_name], no_rows=True)


@query
def remove_extra_capability_sentinel(db, sentinel):
    """Remove all extra capabilities with value `sentinel`. The HTTP
    API could be used to mark them."""
    sql = '''\
    DELETE FROM blazar.computehost_extra_capabilities
    WHERE capability_name = %s
    '''
    return db.query(sql, args=[sentinel], no_rows=True)


@query
def count_orphan_resource_providers(db):
    """Count all orphan resource providers in the nova_api database."""
    sql = '''\
    SELECT COUNT(*)
    FROM   nova_api.resource_providers rp JOIN nova.compute_nodes cn
    ON     cn.hypervisor_hostname = rp.name
    WHERE  cn.deleted = 0
       AND rp.uuid != cn.uuid
    '''
    return db.query(sql)


@query
def update_orphan_resource_providers(db):
    """Update all orphan resource providers in the nova_api database."""
    sql = '''\
    UPDATE nova_api.resource_providers rp JOIN nova.compute_nodes cn
        ON cn.hypervisor_hostname = rp.name
       SET rp.uuid = cn.uuid
     WHERE cn.deleted = 0
       AND rp.uuid != cn.uuid
    '''
    return db.query(sql, no_rows=True)


def main(argv):
    """Run queries!"""
    import sys
    import argparse
    import ast

    from .mysqlargs import MySqlArgs

    parser = argparse.ArgumentParser(description=main.__doc__)
    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)

    parser.add_argument('query', type=str, choices=QUERIES,
        help='Query to run.',
    )
    parser.add_argument('qargs', type=str, nargs='*',
        help='Arguments for the query (if needed)'
    )
    parser.add_argument('--commit', action='store_true',
        help='Commit the connection after the query')

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)

    db = mysqlargs.connect()

    # qargs = [ast.literal_eval(a) for a in args.qargs]

    try:
        for row in QUERIES[args.query]['f'](db, *args.qargs):
            print(row)
    except TypeError as e:
        if '{}() takes'.format(args.query) in str(e):
            print('Invalid number of arguments provided to query: {}'.format(str(e)), file=sys.stderr)
            return -1
        elif "'NoneType' object is not iterable" in str(e):
            print('No output from query.')
        else:
            raise

    if args.commit:
        db.db.commit()


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
