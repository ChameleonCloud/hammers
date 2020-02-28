import datetime
import logging
import os
import sys
import traceback

from dateutil import tz

from blazarclient import client as blazar_client
from ironicclient import client as ironic_client
from keystoneauth1 import adapter, loading, session
from keystoneauth1.identity import v3

from hammers import MySqlArgs
from hammers.slack import Slackbot
from hammers.util import base_parser

logging.basicConfig()

MAINT_LEASE_NAME = 'maint-of-{node_name}-by-{operator}-for-{reason}'
DATETIME_STR_FORMAT = "%Y-%m-%d %H:%M:%S"


def valid_date(s):
    if s:
        try:
            return datetime.datetime.strptime(s, DATETIME_STR_FORMAT)
        except ValueError:
            msg = "Not a valid date: '{0}'.".format(s)
            raise argparse.ArgumentTypeError(msg)
    return None


def append_global_identity_args(parser, argv):
    loading.register_auth_argparse_arguments(parser, argv, default='password')

    parser.set_defaults(os_auth_url=os.getenv('OS_AUTH_URL', None))
    parser.set_defaults(os_username=os.getenv('OS_USERNAME', None))
    parser.set_defaults(os_password=os.getenv('OS_PASSWORD', None))
    parser.set_defaults(os_project_name=os.getenv('OS_PROJECT_NAME', None))
    parser.set_defaults(os_project_id=os.getenv('OS_PROJECT_ID', None))
    parser.set_defaults(os_project_domain_id=os.getenv(
        'OS_PROJECT_DOMAIN_ID', 'default'))
    parser.set_defaults(os_project_domain_name=os.getenv(
        'OS_PROJECT_DOMAIN_NAME', 'default'))
    parser.set_defaults(os_user_domain_id=os.getenv(
        'OS_USER_DOMAIN_ID', 'default'))
    parser.set_defaults(os_user_domain_name=os.getenv(
        'OS_USER_DOMAIN_NAME', 'default'))
    parser.set_defaults(os_region_name=os.getenv('OS_REGION_NAME', None))


def get_session(auth_url, username, password, project_name, user_domain_name='default',
                project_domain_name='default', region_name=None, interface=None):
    auth = v3.Password(auth_url=auth_url,
                       username=username,
                       password=password,
                       project_name=project_name,
                       user_domain_name=user_domain_name,
                       project_domain_name=project_domain_name)
    sess = session.Session(auth=auth)

    return adapter.Adapter(sess, region_name=region_name, interface=interface)


def get_nodes(sess, node_id_or_names):
    token = sess.get_token()
    try:
        ironic_url = sess.get_endpoint(
            service_type='baremetal', interface='public')
    except Exception:
        traceback.print_exc(file=sys.stdout)
    ironic = ironic_client.get_client(1, token=token, endpoint=ironic_url)

    nodes = []
    for node_id_or_name in node_id_or_names:
        nodes.append(ironic.node.get(node_id_or_name))

    return nodes


def get_node_earliest_reserve_time(db, node_uuid, requested_hours):
    sql = '''SELECT l.start_date AS start_date, l.end_date AS end_date
               FROM blazar.leases AS l
               JOIN blazar.reservations AS r ON r.lease_id = l.id
               JOIN blazar.computehost_allocations AS ca ON r.id  = ca.reservation_id
               JOIN blazar.computehosts AS ch ON ch.id = ca.compute_host_id
               WHERE ch.hypervisor_hostname=%(node_uuid)s
                 AND l.deleted IS NULL
                 AND l.end_date > UTC_TIMESTAMP()
               ORDER BY l.start_date'''

    current_time = datetime.datetime.utcnow()
    last_end_time = None
    for row in db.query(sql, {'node_uuid': node_uuid}):
        lease_start_time = row['start_date']
        lease_end_time = row['end_date']
        if lease_start_time < current_time:
            lease_start_time = current_time
        if last_end_time:
            if ((lease_start_time - last_end_time).total_seconds() - 600) / 3600.0 > requested_hours:
                # allow 10 minutes break after previous lease
                return last_end_time + datetime.timedelta(minutes=10)
        last_end_time = lease_end_time

    if last_end_time:
        # allow 10 minutes break after previous lease
        return last_end_time + datetime.timedelta(minutes=10)
    else:
        return current_time


def reserve(sess, node, start_time, requested_hours, reason, operator, dryrun):
    end_time = start_time + datetime.timedelta(hours=requested_hours)

    start_time_str_in_ct = start_time.replace(tzinfo=tz.gettz('UTC')).astimezone(
        tz.gettz('America/Chicago')).strftime(DATETIME_STR_FORMAT)
    end_time_str_in_ct = end_time.replace(tzinfo=tz.gettz('UTC')).astimezone(
        tz.gettz('America/Chicago')).strftime(DATETIME_STR_FORMAT)

    print(((
        "Creating maintenance reservation for node {node_name} "
        "(id: {node_uuid}), starting {start} and ending {end} in central time"
    ).format(
        node_name=node.name,
        node_uuid=node.uuid,
        start=start_time_str_in_ct,
        end=end_time_str_in_ct)
    ))

    if not dryrun:
        blazar = blazar_client.Client(
            1, session=sess, service_type='reservation')
        resource_properties = '["=", "$uid", "{node_uuid}"]'.format(
            node_uuid=node.uuid)
        phys_res = {'min': "1", 'max': "1", 'hypervisor_properties': "",
                    'resource_properties': resource_properties, 'resource_type': 'physical:host'}
        lease_name = MAINT_LEASE_NAME.format(node_name=node.name.replace(' ', '_'),
                                             operator=operator.replace(
                                                 ' ', '_'),
                                             reason=reason.replace(' ', '_'))
        lease = blazar.lease.create(name=lease_name,
                                    start=start_time.strftime(
                                        '%Y-%m-%d %H:%M'),
                                    end=end_time.strftime('%Y-%m-%d %H:%M'),
                                    reservations=[phys_res],
                                    events=[])
        print(("Lease {name} (id: {id}) created successfully!".format(
            name=lease['name'], id=lease['id'])))

    return start_time_str_in_ct, end_time_str_in_ct


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = base_parser('Reserve nodes for maintenance')
    append_global_identity_args(parser, argv)

    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)

    parser.add_argument('--operator', type=str, required=True,
                        help='Chameleon account username of the operator')
    parser.add_argument('--nodes', type=str, required=True,
                        help='node ids or node names; comma separated')
    parser.add_argument('--reason', type=str, required=True,
                        help='maintenance reasons')
    parser.add_argument('--dry-run', action="store_true",
                        help='perform a trial run without making reservations')
    parser.add_argument('--start-time', type=valid_date, default=None,
                        help='lease start time (YYYY-mm-DD HH:MM:SS); if not given, start at the earliest possible datetime')
    parser.add_argument('--estimate-hours', type=int, default=168,
                        help='estimated hours required for maintenance; default is 168 hours (1 week)')

    args = parser.parse_args(argv[1:])

    slack = Slackbot(args.slack, script_name='maintenance-reservation') if args.slack else None

    # connect to database
    mysqlargs.extract(args)
    db = mysqlargs.connect()

    # keystone authentication
    auth_args = {'auth_url': args.os_auth_url,
                 'username': args.os_username,
                 'password': args.os_password,
                 'project_name': args.os_project_name,
                 'region_name': args.os_region_name,
                 'interface': 'public'}
    if args.os_user_domain_name:
        auth_args['user_domain_name'] = args.os_user_domain_name
    if args.os_project_domain_name:
        auth_args['project_domain_name'] = args.os_project_domain_name
    # get admin session for node information
    admin_sess = get_session(**auth_args)
    # get maint session for creating lease
    auth_args['project_name'] = 'maintenance'
    maint_sess = get_session(**auth_args)

    try:
        # get node details
        nodes = get_nodes(admin_sess, args.nodes.split(','))

        report_info = {}
        for node in nodes:
            lease_start_time = args.start_time
            if not lease_start_time:
                # find the earliest reservation time for the node
                lease_start_time = get_node_earliest_reserve_time(db, node.uuid, args.estimate_hours)
            else:
                # convert to utc
                lease_start_time = lease_start_time.replace(tzinfo=tz.tzlocal()).astimezone(tz.gettz('UTC'))
            # reserve
            reserve_args = {'sess': maint_sess,
                            'node': node,
                            'start_time': lease_start_time,
                            'requested_hours': args.estimate_hours,
                            'reason': args.reason,
                            'operator': args.operator,
                            'dryrun': args.dry_run}
            start_time_str, end_time_str = reserve(**reserve_args)
            report_info[node.name] = (start_time_str, end_time_str)

        # summary
        report_lines = [
            ('Node {node_name} at {region} is under maintenance '
                'from {start_time} to {end_time}').format(
                node_name=key,
                region=args.os_region_name,
                start_time=value[0],
                end_time=value[1]
            )
            for key, value in report_info.items()
        ]

        if report_lines:
            report = '\n'.join(report_lines)

            print(report)

            if slack:
                slack.message(report)
        else:
            print('nothing reserved!')
    except:
        if slack:
            slack.exception()
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
