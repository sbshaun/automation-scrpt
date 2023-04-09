import requests
from sendgrid.helpers.mail import Mail
from configparser import ConfigParser
import os

# Get the absolute path to the config.ini file
current_dir = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(current_dir, '..', 'config', 'config.ini')

config_parser = ConfigParser()
config_parser.read(config_file)

SENDGRID_API_KEY = config_parser.get('SENDGRID', 'SENDGRID_API_KEY')
PUSH_TOKEN = config_parser.get('PUSHOVER', 'PUSH_TOKEN')
PUSH_USER = config_parser.get('PUSHOVER', 'PUSH_USER')
MAILGUN_BASE_API_URL = config_parser.get('MAILGUN', 'BASE_API_URL')
FROM_EMAIL = config_parser.get('MAILGUN', 'FROM_EMAIL')
TO_EMAILS = config_parser.get('MAILGUN', 'TO_EMAILS').split(',')

def send_notification(msg):
    print(f"Sending notification: {msg}")

    if SENDGRID_API_KEY:
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=TO_EMAILS,
            subject=msg,
            html_content=msg)
        try:
            response = requests.post(
                MAILGUN_BASE_API_URL,
                auth=("api", SENDGRID_API_KEY),
                data={"from": FROM_EMAIL,
                        "to": TO_EMAILS,
                        "subject": msg,
                        "text": f'https://ais.usvisa-info.com/en-ca/niv/groups/33978368 \n {msg}'})
            print(response.status_code)
        except Exception as e:
            print(e.message)

    if PUSH_TOKEN:
        url = "https://api.pushover.net/1/messages.json"
        data = {
            "token": PUSH_TOKEN,
            "user": PUSH_USER,
            "message": msg
        }
        requests.post(url, data)

# Test notification
if __name__ == "__main__":
    test_message = "Test notification: US VISA appointment reschedule alert!"
    send_notification(test_message)
