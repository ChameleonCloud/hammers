'''
Check and notify users about their reservation
'''


import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from dateutil import tz

from hammers import MySqlArgs, osapi, query
from hammers.notifications import _email

logging.basicConfig()

IDLE_HOUR_THRESHOLD = 24


def get_reservations_start_next_day(db):
    advance_reservations = query.get_advance_reservations(db)
    results = []
    for obj in advance_reservations:
        start_date = obj['start_date'].replace(tzinfo=tz.gettz('UTC'))
        nextday = datetime.today().replace(tzinfo=tz.gettz('UTC')) + timedelta(
            days=1)
        nextday_start = nextday.replace(hour=0, minute=0, second=0).replace(
            tzinfo=tz.gettz('UTC'))
        nextday_end = nextday.replace(hour=23, minute=59, second=59).replace(
            tzinfo=tz.gettz('UTC'))
        if start_date >= nextday_start and start_date <= nextday_end:
            email_pack = {
                'address': json.loads(obj['user_extra'])['email'],
                'content_vars': {
                    'username': obj['user_name'],
                    'projectname': obj['project_name'],
                    'leasename': obj['lease_name'],
                    'leaseid': obj['lease_id'],
                    'startdatetime_utc': start_date.strftime(
                        "%Y-%m-%d %H:%M:%S"),
                    'startdatetime_ct': start_date.astimezone(tz.gettz(
                        'America/Chicago')).strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            results.append(email_pack)

    return results


def get_idle_leases(db):
    idle_leases = query.get_idle_leases(db, IDLE_HOUR_THRESHOLD)
    results = []
    for obj in idle_leases:
        email_pack = {
                'address': json.loads(obj['user_extra'])['email'],
                'content_vars': {
                    'username': obj['user_name'],
                    'projectname': obj['project_name'],
                    'leasename': obj['lease_name'],
                    'leaseid': obj['lease_id'],
                    'idlehours_threshold': IDLE_HOUR_THRESHOLD
                }
            }
        results.append(email_pack)

    return results


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(
        description='Check and notify users about their reservation')
    parser.add_argument(
        '--sender',
        type=str,
        help='Email address of sender',
        default='noreply@chameleoncloud.org')

    mysqlargs = MySqlArgs({
        'user': 'root',
        'password': '',
        'host': 'localhost',
        'port': 3306,
    })
    mysqlargs.inject(parser)
    osapi.add_arguments(parser)

    args = parser.parse_args(argv[1:])
    mysqlargs.extract(args)

    db = mysqlargs.connect()
    db.version = query.ROCKY

    auth = osapi.Auth.from_env_or_args(args=args)
    email_host = _email.get_host()

    # get all future reservations start next day in UTC
    for email_pack in get_reservations_start_next_day(db):
        email_pack['content_vars']['site'] = auth.region
        html = _email.render_template(
            _email.RESERVATION_START_EMAIL_BODY,
            vars=email_pack['content_vars'])
        subject = 'Chameleon lease {} starts tomorrow'.format(
            email_pack['content_vars']['leasename'])
        _email.send(
            email_host,
            email_pack['address'],
            args.sender, subject,
            html)

    # get idle leases
    for email_pack in get_idle_leases(db):
        email_pack['content_vars']['site'] = auth.region
        html = _email.render_template(
            _email.IDLE_RESERVATION_EMAIL_BODY,
            vars=email_pack['content_vars'])
        subject = 'You have an idle Chameleon lease {}'.format(
            email_pack['content_vars']['leasename'])
        _email.send(
            email_host,
            email_pack['address'],
            args.sender,
            subject,
            html)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
