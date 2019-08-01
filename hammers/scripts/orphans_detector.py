# coding: utf-8
'''
.. code-block:: bash

    orphans_detector

Detects orphan leases and instances.

Optional arguments:

* ``--dbversion rocky`` needed for the Rocky release as the database schema
  changed slightly.
* ``--kvm`` run on kvm site.

'''
from __future__ import absolute_import, print_function, unicode_literals

import sys
import argparse
import os

from hammers import MySqlArgs, osapi, query
from hammers.slack import Slackbot
from hammers.util import prometheus_exporter

from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneauth1 import exceptions
from keystoneclient.v2_0 import client

def get_orphan_info_from_query(query_result):
    orphans = {}
    for obj in query_result:
        orphan_id = obj['id']
        user_enabled = obj['user_enabled'] == 1
        project_enabled = obj['project_enabled'] == 1
        if user_enabled and project_enabled:
            orphans[orphan_id] = 'User {} does not belongs to Project {} anymore'.format(obj['user_name'], obj['project_name'])
        else:
            message = []
            if not user_enabled:
                message.append('User {} is deactivated'.format(obj['user_name']))
            if not project_enabled:
                message.append('Project {} is deactivated'.format(obj['project_name']))
            orphans[orphan_id] = ' and '.join(message)

    return orphans

def get_orphan_leases(db):
    return get_orphan_info_from_query(query.orphans(db, 'lease'))

def get_orphan_instances(db):
    return get_orphan_info_from_query(query.orphans(db, 'instance'))

def get_orphan_instances_kvm(db, kc):
    orphans = {}
    for obj in query.active_instances(db):
        user_id = obj['user_id']
        project_id = obj['project_id']
        instance_id = obj['uuid']

        try:
            user = kc.users.get(user_id)
            user_enabled = user is not None and user.enabled
        except exceptions.http.NotFound:
            user_enabled = False

        try:
            project = kc.tenants.get(project_id)
            project_enabled = project is not None
        except exceptions.http.NotFound:
            project_enabled = False

        if user_enabled and project_enabled:
            project_users = project.list_users()
            if user.id not in [u.id for u in project_users]:
                orphans[instance_id] = 'User {} does not belong to Project {} anymore'.format(user_id, project_id)
        else:
            message = []
            if not user_enabled:
                message.append('User {} is deactivated'.format(user_id))
            if not project_enabled:
                message.append('Project {} is deactivated'.format(project_id))
            orphans[instance_id] = ' and '.join(message)

    return orphans


def generate_report(orphan_dict, title):
    if not orphan_dict:
        return None

    report = []
    report.append(title)
    report.append("{:<45} {:<50}".format('ID','Message'))
    for k, v in orphan_dict.iteritems():
        report.append("{:<45} {:<50}".format(k, v))

    return '\n'.join(report)


@prometheus_exporter(__file__)
def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(description='Detects orphan leases and remove them.')

    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)

    parser.add_argument('-d', '--dbversion', type=str,
        help='Version of the database. Schemas differ, pick the appropriate one.',
        choices=[query.LIBERTY, query.ROCKY], default=query.ROCKY)
    parser.add_argument('--slack', type=str,
        help='JSON file with Slack webhook information to send a notification to')
    parser.add_argument('--kvm', help='Run at KVM site', action='store_true')
    osapi.add_arguments(parser)

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)

    db = mysqlargs.connect()
    db.version = args.dbversion

    kvm = args.kvm

    if args.slack:
        slack = Slackbot(args.slack, script_name='orphan-detector')
    else:
        slack = None

    if kvm:
        # at kvm site
        os_vars = {k: os.environ[k] for k in os.environ if k.startswith('OS_')}
        if args.osrc:
            os_vars.update(osapi.load_osrc(args.osrc))

        auth = v2.Password(username=os_vars['OS_USERNAME'],
                           password=os_vars['OS_PASSWORD'],
                           tenant_name=os_vars['OS_TENANT_NAME'],
                           auth_url=os_vars['OS_AUTH_URL'])
        sess = session.Session(auth=auth)
        keystone = client.Client(session=sess)

        orphan_instances = get_orphan_instances_kvm(db, keystone)
    else:
        orphan_leases_report = generate_report(get_orphan_leases(db), "-" * 45 + "ORPHAN LEASES" + "-" * 45)
        if slack:
            if orphan_leases_report:
                slack.post('orphan-detector', orphan_leases_report, color='#FF0000')
            else:
                slack.post('orphan-detector', 'No orphan leases detected', color='#000000')
        else:
            if orphan_leases_report:
                print(orphan_leases_report)
            else:
                print('No orphan leases detected')

        orphan_instances = get_orphan_instances(db)

    orphan_instances_report = generate_report(orphan_instances, "-" * 45 + "ORPHAN INSTANCES" + "-" * 45)
    if slack:
        if orphan_instances_report:
            slack.post('orphan-detector', orphan_instances_report, color='#FF0000')
        else:
            slack.post('orphan-detector', 'No orphan instances detected', color='#000000')
    else:
        if orphan_instances_report:
            print(orphan_instances_report)
        else:
            print('No orphan instances detected')

if __name__ == '__main__':
    sys.exit(main(sys.argv))
