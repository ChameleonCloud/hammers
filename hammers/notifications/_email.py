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

NO_REPLY_EMAIL_BASE = '''
<style type="text/css">
@font-face {{
  font-family: 'Open Sans';
  font-style: normal;
  font-weight: 300;
  src: local('Open Sans Light'), local('OpenSans-Light'), url(http://fonts.gstatic.com/s/opensans/v13/DXI1ORHCpsQm3Vp6mXoaTa-j2U0lmluP9RWlSytm3ho.woff2) format('woff2');
  unicode-range: U+0460-052F, U+20B4, U+2DE0-2DFF, U+A640-A69F;
}}
.body {{
    width: 90%;    margin: auto;
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

STACKED_LEASE_DELETED_EMAIL_BODY = '''
<p>
  We're sending this email to inform you that that following leases have been
  deleted due to a violation of our terms of service:
</p>
<blockquote>
  <ul>
  {% for lease in vars['lease_list'] %}
    <li><strong>{{ lease }}</strong></li>
  {% endfor %}
  </ul>
</blockquote>
<p>
  Please do not make multiple consecutive leases on the same node or across
  the same node types. If you require a lease for longer than 1 week then
  please submit a formal request. Likewise, you can also always extend a lease
  within 48 hours of its end date provided that the resources have not been reserved by
  another user. This mechanism is intended to strike a balance between
  convenience and fairness between all our users.
</p>
'''

IDLE_LEASE_WARNING_EMAIL_BODY = '''
<p>
  We're sending this email to inform you that your lease
  {{ vars['lease_name'] }} (ID: {{ vars['lease_id'] }}) has been idle for more
  than {{ vars['warn_period'] }} hours. If your lease is idle for more than
  {{ vars['termination_period'] }} hours it will be terminated to free up
  resources for other users.
</p>
'''

IDLE_LEASE_TERMINATION_EMAIL_BODY = '''
<p>
  We're sending this email to inform you that your lease
  {{ vars['lease_name'] }} (ID: {{ vars['lease_id'] }}) has been terminated.
  In order to promote fair sharing on Chameleon, we terminate unutilized
  leases after a {{ vars['termination_period'] }} hour grace period from the
  start time of the lease so that other users can make use of the resources.
</p>
'''


def get_host():
    """Return email host."""
    blazar_config = configparser.ConfigParser()

    try:
        blazar_config.read('/etc/blazar/blazar.conf')
        email_host = blazar_config['physical:host']['email_relay']
    except Exception:
        logging.warn(
            'Cannot read email relay from config file. '
            'Defaul email host will be useed')
        email_host = DEFAULT_EMAIL_HOST

    return email_host


def render_template(
        email_body, base_template=NO_REPLY_EMAIL_BASE, **kwargs):
    """Render a Jinja template into HTML."""
    tmpl = Environment(
        autoescape=select_autoescape(default_for_string=True)).from_string(
            base_template.format(email_body=email_body))
    return tmpl.render(**kwargs)


def send(email_host, to, sender, subject=None, body=None):
    """Send email."""
    # convert `to` into list if string
    if type(to) is not list:
        to = to.split()

    # remove null emails
    to_list = [_f for _f in to if _f]

    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['Subject'] = subject
    msg['To'] = ','.join(to_list)
    msg.attach(MIMEText(body, 'html'))

    # send email
    server = smtplib.SMTP(email_host, timeout=30)
    server.sendmail(sender, to_list, msg.as_string())
    server.quit()
