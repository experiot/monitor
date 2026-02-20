"""
Program: Service Monitoring (web content, REST API and SSH)

Description:
    This program is used to monitor the availability of selected web pages content,
    REST API services and SSH ports on specified hosts.
    If the status changes (e.g. the service stops responding or becomes available again), the program saves
    the current state to a file and sends a notification via a webhook service.

Features:
    - Checks the availability of the SSH port (22) on specified hosts.
    - Checks for HTTP response from selected web pages or REST API endpoints.
    - Status changes are saved to files in the STATUS_DIR directory.
    - If the status changes, a notification is sent via configured channels.

Configuration: see monitor_config.yaml

Main functions:
    - check_ssh(host, timeout_ms): Checks SSH port availability on a host.
    - check_api(url): Checks REST API endpoint availability.
    - sendMessage(name, url, code, message): Handles status file writing and notification sending.
    - main(): Main function to run checks.

To run the program periodically, e.g. every 5 minutes, you can use the crontab scheduler in Linux.
To do this, add an appropriate entry to the user's crontab file, e.g.:

    */5 * * * * /usr/bin/python3 /path/to/script/monitoring.py /path/to/config.yaml

The above entry will automatically run the program every 5 minutes.
Make sure the path to the Python interpreter and the program file is correct.
The results and notifications will be generated according to the program configuration.
"""
import socket
import requests
import os
import json
import yaml
import sys
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def print_log(message):
    if not SILENT_MODE:
        print(message)

def load_config(config_path):
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            webhooks = config.get("webhooks", [])
            hosts = config.get("hosts", [])
            urls = config.get("urls", [])
            email_config = config.get("email", {})
            # Determine STATUS_DIR: if provided in config use it, otherwise
            # create a 'monitor_status' subfolder next to this script.
            sDir = config.get("STATUS_DIR")
            if not sDir:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                sDir = os.path.join(script_dir, "monitor_status")
            # Ensure the status directory exists
            try:
                os.makedirs(sDir, exist_ok=True)
            except Exception as e:
                print_log(f"Warning: Could not create status directory {sDir}: {e}")

            sMode = config.get("SILENT_MODE", False)
            # Determine CLIENT_NAME: if provided use it, otherwise fall back to hostname
            sClient = config.get("CLIENT_NAME")
            if not sClient:
                try:
                    sClient = socket.gethostname()
                except Exception as e:
                    print_log(f"Warning: Could not retrieve hostname, using default: {e}")
                    sClient = "monitor_client"
    except Exception as e:
        print_log(f"Error loading config: {e}")
        sys.exit(1)

    return urls, hosts, webhooks, email_config, sDir, sMode, sClient

def check_ssh(entry):
    """
    Checks the availability of the SSH port (22) on the given host.
    Returns (200, "OK") if the port is open, otherwise (code, description).
    """
    timeout_sec = DEFAULT_TIMEOUT_MS / 1000.0
    try:
        # First, check if port 22 is open
        with socket.create_connection((entry["host"], 22), timeout=timeout_sec):
            pass
    except (socket.timeout, TimeoutError):
        return timeout_sec, "Timeout"
    except Exception as e:
        return 503, f"Port 22 error: {e}"

    # Optionally: check if you can log in (e.g. via ssh-keyscan or a passwordless connection attempt)
    # Here, only SSH banner check (does not require a key)
    # try:
    #     result = subprocess.run([
    #         "ssh", "-oBatchMode=yes", "-oConnectTimeout=3", f"{host}", "exit"
    #     ], capture_output=True, timeout=timeout_sec)
    #     if result.returncode == 0:
    #         return 200, "SSH OK"
    #     else:
    #         return result.returncode, f"SSH error: {result.stderr.decode().strip()}"
    # except subprocess.TimeoutExpired:
    #     return timeout_ms, "SSH Timeout"
    # except Exception as e:
    #     return -1, f"SSH exception: {e}"
    return 200, "SSH OK"

def print_list(items):
    if items is None:
        print_log("List: 0")
        return
    print_log(f"List: {len(items)}")
    for item in items:
        print_log(f"- {item}")

def getContent(items):
    return items["Content-Type"]

def send_webhook_message(entry, code, message, client_name):
    url = entry["url"]
    method = entry["requestMethod"]
    serviceName = entry["name"]
    contentType = getContent(entry["headers"])
    print_log(f"Sending webhook message to {url} using {method}")
    # Build the data object dynamically based on the 'body' field in the config entry
    body = entry.get("body", {})
    data = {}
    for key, value in body.items():
        if isinstance(value, str):
            # Replace placeholders in string values
            value = value.replace("{code}", str(code)).replace("{message}", str(message))
            value = value.replace("{client}", str(client_name)).replace("{service}", serviceName)
        data[key] = value
    # create the headers object dynamically based on the 'headers' field in the config entry
    headers = {}
    for key, value in entry.get("headers", {}).items():
        headers[key] = value

    try:
        switcher = {
            "POST": requests.post,
            "GET": requests.get,
            "PUT": requests.put
        }
        func = switcher.get(method.upper(), requests.post)
        print_log(f"url:{url}")
        print_log(f"headers:{headers}")
        print_log(f"data:{data}")
        if contentType == "application/x-www-form-urlencoded":
            response = func(url, data=data, headers=headers, timeout=10)
        elif contentType == "application/json":
            response = func(url, json=data, headers=headers, timeout=10)
        else:
            return
        if response.status_code == 200:
            print_log("Webhook: Notification sent.")
            print_log(response)
        else:
            print_log(f"Webhook: Error sending notification: {response.status_code} {response.text}")
    except Exception as e:
        print_log(f"Webhook: Exception while sending notification: {e}")

def send_smtp_email(sender_email, password, recipient_email, subject, body, 
                   smtp_server="smtp.gmail.com", smtp_port=587, use_ssl=False):
    """
    Send email using SMTP (works with Gmail and other SMTP servers)
    
    Args:
        sender_email: Email address of the sender
        password: Email password or app password
        recipient_email: Email address of the recipient
        subject: Email subject
        body: Email body text
        smtp_server: SMTP server address (default: smtp.gmail.com)
        smtp_port: SMTP server port (default: 587)
        use_ssl: Use SSL instead of STARTTLS (default: False)
    """
    # Create the email
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        if use_ssl:
            # Use SSL connection (typically port 465)
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            # Use STARTTLS connection (typically port 587)
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        
        server.login(sender_email, password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print_log("Email sent successfully!")
    except Exception as e:
        print_log(f"Error sending email: {e}")

def send_email_notification(service_name, code, message, client_name):
    """
    Send email notification using SMTP (works with any SMTP server)
    """
    if not email_config:
        print_log("Email configuration not found, skipping email notification")
        return
    
    sender_email = email_config.get("sender_email")
    password = email_config.get("password") or email_config.get("app_password")  # Backward compatibility
    recipient_email = email_config.get("recipient_email")
    subject_template = email_config.get("subject", "Service Monitoring Alert: {service}")
    
    # SMTP server configuration (with defaults for Gmail)
    smtp_server = email_config.get("smtp_server", "smtp.gmail.com")
    smtp_port = email_config.get("smtp_port", 587)
    use_ssl = email_config.get("use_ssl", False)
    
    if not all([sender_email, password, recipient_email]):
        print_log("Email configuration incomplete, skipping email notification")
        return
    
    # Replace placeholders in subject
    subject = subject_template.replace("{service}", service_name)
    subject = subject.replace("{code}", str(code))
    subject = subject.replace("{message}", message)
    subject = subject.replace("{client}", client_name)
    
    # Create email body
    body = f"Service Monitoring Alert\n\n"
    body += f"Service: {service_name}\n"
    body += f"Client: {client_name}\n"
    body += f"Status Code: {code}\n"
    body += f"Message: {message}\n"
    body += f"Timestamp: {datetime.datetime.now()}\n"
    
    send_smtp_email(sender_email, password, recipient_email, subject, body, 
                   smtp_server, smtp_port, use_ssl)

def check_api(url, checkJson, checkText, okText, errorText):
    try:
        response = requests.get(url, timeout=DEFAULT_TIMEOUT_MS / 1000.0)
        if response.status_code == 200:
            # if checkJson is true then check the response content
            if checkJson:
                try:
                    json.loads(response.text)
                except json.JSONDecodeError:
                    return response.status_code, f"Invalid JSON response: {response.status_code}"
            elif checkText:
                # okText is not null and not empty
                if okText and okText not in response.text:
                    return response.status_code, "Required text not found"
                # errorText is not null and not empty
                if errorText and errorText in response.text:
                    return response.status_code, "Error"
            return 200, "OK"
        else:
            return response.status_code, f"Unexpected status: {response.status_code}"
    except requests.exceptions.Timeout:
        return DEFAULT_TIMEOUT_MS, "Timeout"
    except Exception as e:
        return -1, f"Error: {e}"

# Sprawdzanie obecności ciągu znaków w tekście
def check_text_presence(text, substring, required):
    if required:
        return substring in text
    else:
        return substring not in text

def getCodeChanged(entry, code):
    name = entry["name"]
    print_log(f"Status folder location: {STATUS_DIR}")
    if not os.path.exists(STATUS_DIR):
        os.makedirs(STATUS_DIR)

    state_file = os.path.join(STATUS_DIR, f"{name.replace(':', '_').replace('/', '_')}.txt")
    prev_code = None
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            prev_code = f.read().strip()
        with open(state_file, 'w') as f:
            f.write(str(code))
    else:
        with open(state_file, 'w') as f:
            f.write(str(code))

    if prev_code==None or prev_code != str(code):
        print_log(f"[{name}] Status changed: {code}")
        return True
    print_log(f"[{name}] Status unchanged: {code}")
    return False

def get_webhook_definition(name):
    webhook_def = None
    print_log(f"name: {name}")
    print_log(f"webhooks: {webhooks}")
    if webhooks is None:
        return None
    for webhook in webhooks:
        if webhook['name'] == name:
            webhook_def = webhook
            break
    return webhook_def

def main():
    global config, webhooks, hosts, urls, email_config, SILENT_MODE, CLIENT_NAME, STATUS_DIR, DEFAULT_TIMEOUT_MS

    config = {}
    urls = []
    webhooks = []
    hosts = []
    email_config = {}
    DEFAULT_TIMEOUT_MS = 5000
    SILENT_MODE = False
    STATUS_DIR = "/tmp/status_files/"
    CLIENT_NAME = "dev_env"

    # Get the path to the configuration file from the command-line argument
    if len(sys.argv) < 2:
        print_log("Please provide the path to the YAML configuration file as the first argument!")
        sys.exit(1)

    config_path = sys.argv[1]
    urls, hosts, webhooks, email_config, STATUS_DIR, SILENT_MODE, CLIENT_NAME = load_config(config_path)

    # Ensure config is loaded and is a dict before accessing its attributes
    if config is None: # or not isinstance(config, dict):
        print_log("Error: Configuration was not loaded correctly or is invalid.")
        sys.exit(1)

    #urls = config.get("urls", [])
    #hosts = config.get("hosts", [])
    #webhooks = config.get("webhooks", [])
    print_list(urls)
    print_list(hosts)
    print_list(webhooks)

    # if urls is iterable
    if urls:
        for entry in urls:
            code, message = check_api(entry["url"], entry.get("checkJson", False), entry.get("checkText", False), entry.get("textExpected", None), entry.get("textForbidden", None))
            webhook_def = None
            codeChanged = getCodeChanged(entry, code)
            if not codeChanged:
                print_log("URL status not changed")
                continue
            if(code==200):
                okWebhookName =entry.get("okWebhook")
                print_log(f"okWebhookName: {okWebhookName}")
                if okWebhookName:
                    webhook_def = get_webhook_definition(okWebhookName)
            else:
                errorWebhookName = entry.get("errorWebhook")
                print_log(f"errorWebhookName: {errorWebhookName}")
                if errorWebhookName:
                    webhook_def = get_webhook_definition(errorWebhookName)
                elif entry.get("emailConfigName"):
                    # If no webhook defined but emailConfigName exists, this will be handled in email notification section
                    pass
                if webhook_def:
                    print_log("Webhook found")
                    send_webhook_message(webhook_def, code, message, CLIENT_NAME)
                else:
                    print_log(f"Webhook not found for {entry['url']}")
            
            # Send email notification if email configuration is available
            # Always send email if email_config exists (backward compatibility)
            # Additionally, log if emailConfigName is explicitly set when no webhook is defined
            if email_config:
                if not errorWebhookName and entry.get("emailConfigName"):
                    print_log(f"emailConfigName found: {entry.get('emailConfigName')}")
                send_email_notification(entry["name"], code, message, CLIENT_NAME)

    # if hosts is iterable
    if hosts:
        for entry in hosts:
            code, message = check_ssh(entry)
            webhook_def = None
            codeChanged = getCodeChanged(entry, code)
            if not codeChanged:
                print_log("Host status not changed")
                continue
            if(code==200):
                okWebhookName =entry.get("okWebhook")
                print_log(f"okWebhookName: {okWebhookName}")
                if okWebhookName:
                    webhook_def = get_webhook_definition(okWebhookName)
            else:
                errorWebhookName = entry.get("errorWebhook")
                print_log(f"errorWebhookName: {errorWebhookName}")
                if errorWebhookName:
                    webhook_def = get_webhook_definition(errorWebhookName)
                elif entry.get("emailConfigName"):
                    # If no webhook defined but emailConfigName exists, this will be handled in email notification section
                    pass
            if webhook_def:
                print_log("Webhook found")
                send_webhook_message(webhook_def, code, message, CLIENT_NAME)
            else:
                print_log(f"Webhook not found for {entry['url']}")
            
            # Send email notification if email configuration is available
            # Always send email if email_config exists (backward compatibility)
            # Additionally, log if emailConfigName is explicitly set when no webhook is defined
            if email_config:
                if not errorWebhookName and entry.get("emailConfigName"):
                    print_log(f"emailConfigName found: {entry.get('emailConfigName')}")
                send_email_notification(entry["name"], code, message, CLIENT_NAME)


if __name__ == "__main__":
    main()
