"""Sends email through Brevo's web API (HTTPS), for hosts that block SMTP ports.
Set BREVO_API_KEY and EMAIL_FROM (an address verified as a sender in Brevo)."""
import json
import urllib.request
from email.utils import parseaddr
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for m in email_messages:
            name, addr = parseaddr(m.from_email or settings.DEFAULT_FROM_EMAIL)
            sender = {'email': addr}
            if name:
                sender['name'] = name
            payload = {'sender': sender, 'to': [{'email': t} for t in m.to], 'subject': m.subject, 'textContent': m.body}
            req = urllib.request.Request('https://api.brevo.com/v3/smtp/email', data=json.dumps(payload).encode('utf-8'), method='POST',
                                         headers={'api-key': settings.BREVO_API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'})
            try:
                urllib.request.urlopen(req, timeout=10).read()
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent
