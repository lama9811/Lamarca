"""Transactional email via SendGrid."""
import requests
from django.conf import settings


def send_email(to_email: str, subject: str, html: str) -> None:
    resp = requests.post(
        'https://api.sendgrid.com/v3/mail/send',
        headers={
            'Authorization': f'Bearer {settings.SENDGRID_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'personalizations': [{'to': [{'email': to_email}]}],
            'from': {'email': settings.SENDGRID_FROM_EMAIL, 'name': 'Lamarca AI'},
            'subject': subject,
            'content': [{'type': 'text/html', 'value': html}],
        },
        timeout=10,
    )
    if resp.status_code not in (200, 201, 202):
        raise Exception(f'SendGrid error {resp.status_code}: {resp.text}')
