'''
Check and notify users about their reservation
'''
from __future__ import absolute_import, print_function, unicode_literals

import argparse
import configparser
import json
import logging
import smtplib
import sys
from datetime import datetime, timedelta
from dateutil import tz
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, select_autoescape

from hammers import MySqlArgs, osapi, query

logging.basicConfig()

EMAIL_TEMPLATE = '''
<style type="text/css">
@font-face {{
  font-family: 'Open Sans';
  font-style: normal;
  font-weight: 300;
  src: local('Open Sans Light'), local('OpenSans-Light'), url(http://fonts.gstatic.com/s/opensans/v13/DXI1ORHCpsQm3Vp6mXoaTa-j2U0lmluP9RWlSytm3ho.woff2) format('woff2');
  unicode-range: U+0460-052F, U+20B4, U+2DE0-2DFF, U+A640-A69F;
}}
.body {{
    width: 90%;
    margin: auto;
    font-family: 'Open Sans', 'Helvetica', sans-serif; 
    font-size: 11pt;
    color: #000000;
}}
a:link {{ color: #B40057; text-decoration: underline }}
a:visited {{ color: #542A95; text-decoration: none }}
a:hover {{ color: #B40057; background-color:#C4FFF9; text-decoration: underline }}
</style>

<div class="body">
<p>Dear {{{{ vars['username'] }}}},</p>
<br>

{email_body}

<br>
<p><i>
This is an automatic email, please <b>DO NOT</b> reply! 
If you have any question or issue, please submit a ticket on our <a href='https://www.chameleoncloud.org/user/help/' target='_blank'>help desk</a>.
</i></p>

<br><br>
<p>Thanks,</p>
<p>Chameleon Team</p>

</div>
<br><br>
'''

RESERVATION_START_EMAIL_BODY = '''
<p>We're sending this email to remind you that your lease {{ vars['leasename'] }} (ID: {{ vars['leaseid'] }}) under project {{ vars['projectname'] }} on {{ vars['site'] }} 
will start on {{ vars['startdatetime_utc'] }} UTC / {{ vars['startdatetime_ct'] }} Central Time.</p>
'''

IDLE_RESERVATION_EMAIL_BODY = '''
<p>We're sending this email to inform you that your lease {{ vars['leasename'] }} (ID: {{ vars['leaseid'] }}) under project {{ vars['projectname'] }} on {{ vars['site'] }} 
has been idle for more than {{ vars['idlehours_threshold'] }} hours.</p>

<p>If you don't need the reservation anymore, please delete the lease using 
either the Chameleon <a href='https://chameleoncloud.readthedocs.io/en/latest/technical/gui.html#reservations' target='_blank'>web interface</a> 
or <a href='https://chameleoncloud.readthedocs.io/en/latest/technical/cli.html' target='_blank'>command line interface</a> to release the resources.</p>
'''

IDLE_HOUR_THRESHOLD = 24

def render_template(email_body, **kwargs):
    ''' renders a Jinja template into HTML '''
    templ = Environment(autoescape=select_autoescape(default_for_string=True)).from_string(EMAIL_TEMPLATE.format(email_body=email_body))
    return templ.render(**kwargs)
 
def send_email(email_host, to, sender, subject=None, body=None):
    # convert TO into list if string
    if type(to) is not list:
        to = to.split()
    to_list = filter(None, to) # remove null emails
    
    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['Subject'] = subject
    msg['To'] = ','.join(to)
    msg.attach(MIMEText(body, 'html'))

    # send email
    server = smtplib.SMTP(email_host, timeout=30)
    server.sendmail(sender, to_list, msg.as_string())
    server.quit()
    
def get_reservations_start_next_day(db):
    advance_reservations = query.get_advance_reservations(db)
    results = []
    for obj in advance_reservations:
        start_date = obj['start_date'].replace(tzinfo=tz.gettz('UTC'))
        nextday = datetime.today().replace(tzinfo=tz.gettz('UTC')) + timedelta(days=1)
        nextday_start = nextday.replace(hour=0, minute=0, second=0).replace(tzinfo=tz.gettz('UTC'))
        nextday_end = nextday.replace(hour=23, minute=59, second=59).replace(tzinfo=tz.gettz('UTC'))
        if start_date >= nextday_start and start_date <= nextday_end:
            email_pack = {
                'address': json.loads(obj['user_extra'])['email'],
                'content_vars' : {
                    'username': obj['user_name'],
                    'projectname': obj['project_name'],
                    'leasename': obj['lease_name'],
                    'leaseid': obj['lease_id'],
                    'startdatetime_utc': start_date.strftime("%Y-%m-%d %H:%M:%S"),
                    'startdatetime_ct': start_date.astimezone(tz.gettz('America/Chicago')).strftime("%Y-%m-%d %H:%M:%S")
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
                'content_vars' : {
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

    parser = argparse.ArgumentParser(description='Check and notify users about their reservation')
    parser.add_argument('--sender', type=str, help='Email address of sender', default='noreply@chameleoncloud.org')
    
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
    db.version = query.OCATA
    
    auth = osapi.Auth.from_env_or_args(args=args)
    
    email_host = '127.0.0.1'        
    blazar_config = configparser.ConfigParser()
    try:
        blazar_config.read('/etc/blazar/blazar.conf')
        email_host = blazar_config['physical:host']['email_relay']
    except Exception:
        logging.warn('Can not read email relay from config file. Default email host will be used.')
        pass
    
    # get all future reservations start next day in UTC
    for email_pack in get_reservations_start_next_day(db):
        email_pack['content_vars']['site'] = auth.region
        html = render_template(RESERVATION_START_EMAIL_BODY, vars=email_pack['content_vars'])
        subject = 'Chameleon lease {} starts tomorrow'.format(email_pack['content_vars']['leasename'])
        send_email(email_host, email_pack['address'], args.sender, subject, html.encode("utf8"))
        
    # get idle leases
    for email_pack in get_idle_leases(db):
        email_pack['content_vars']['site'] = auth.region
        html = render_template(IDLE_RESERVATION_EMAIL_BODY, vars=email_pack['content_vars'])
        subject = 'You have an idle Chameleon lease {}'.format(email_pack['content_vars']['leasename'])
        send_email(email_host, email_pack['address'], args.sender, subject, html.encode("utf8"))


if __name__ == '__main__':
    sys.exit(main(sys.argv))
