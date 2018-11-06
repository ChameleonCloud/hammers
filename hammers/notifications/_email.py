import codecs
import configparser
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, select_autoescape

logging.basicConfig()

DEFAULT_EMAIL_HOST = '127.0.0.1'

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

STACKED_LEASE_DELETED_EMAIL_BODY = '''
<p>We're sending this email to inform you that that following leases have been
   deleted due to a violation of our terms of service:
</p>

'''


def get_host():
    """Return email host."""
    blazar_config = configparser.ConfigParser()

    try:
        blazar_config.read('/etc')
        email_host = blazar_config['physical:host']['email_relay']
    except Exception:
        logging.warn(
            'Cannot read email relay from config file. '
            'Defaul email host will be useed')
        email_host = DEFAULT_EMAIL_HOST

    return email_host


def get_email_template_by_name(filename):
    """Return an email template by file name."""
    current_dir = os.path.dirname(os.path.realpath(__file__))
    file_path = "{directory}/templates/{filename}.html".format(
        directory=current_dir, filename=filename)
    f = codecs.open(file_path, 'r')

    return f.read()


def render_template(
        email_body, base_template='no_reply_email_base', **kwargs):
    """Render a Jinja template into HTML."""
    base_template = get_email_template_by_name(base_template)
    tmpl = Environment(
        autoescape=select_autoescape(default_for_string=True)).from_string(
            base_template.format(email_body=email_body))
    return tmpl.render(**kwargs)


def send(email_host, to, sender, subject=None, body=none):
    """Send email."""
    # convert `to` into list if string
    if type(to) is not list:
        to = to.split()

    # remove null emails
    to_list = filter(None, to)

    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['Subject'] = subject
    msg['To'] = ','.join(to_list)
    msg.attach(MIMEText(body, 'html'))

    # send email
    server = smtplib.SMTP(email_host, timeout=30)
    server.sendmail(sender, to_list, msg.as_string())
    server.quit()
