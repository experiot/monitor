"""
Program: Service Monitoring (web content, REST API and SSH)

Description:
    This program is used to monitor the availability of selected web pages content, REST API services and SSH ports on specified hosts.
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
            sDir = config.get("STATUS_DIR", "/tmp/status_files/")
            sMode = config.get("SILENT_MODE", False)
            sClient = config.get("CLIENT_NAME", "dev_env")
    except Exception as e:
        print_log(f"Error loading config: {e}")
        sys.exit(1)

    return urls, hosts, webhooks, sDir, sMode, sClient

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
        return timeout_ms, "Timeout"
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

def send_gmail(sender_email, app_password, recipient_email, subject, body):
    # Create the email
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        # Connect to Gmail SMTP server
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

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
                    return response.status_code, f"Required text not found"
                # errorText is not null and not empty
                if errorText and errorText in response.text:
                    return response.status_code, f"Error"
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
    for webhook in webhooks:
        if webhook['name'] == name:
            webhook_def = webhook
            break
    return webhook_def

def main():
    global config, webhooks, hosts, urls, SILENT_MODE, CLIENT_NAME, STATUS_DIR, DEFAULT_TIMEOUT_MS

    config = {}
    urls = []
    webhooks = []
    hosts = []
    DEFAULT_TIMEOUT_MS = 5000
    SILENT_MODE = False
    STATUS_DIR = "/tmp/status_files/"
    CLIENT_NAME = "dev_env"

    # Get the path to the configuration file from the command-line argument
    if len(sys.argv) < 2:
        print_log("Please provide the path to the YAML configuration file as the first argument!")
        sys.exit(1)

    config_path = sys.argv[1]
    urls, hosts, webhooks, STATUS_DIR, SILENT_MODE, CLIENT_NAME = load_config(config_path)

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
            if webhook_def:
                print_log("Webhook found")
                send_webhook_message(webhook_def, code, message, CLIENT_NAME)
            else:
                print_log(f"Webhook not found for {entry['url']}")

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
            if webhook_def:
                print_log("Webhook found")
                send_webhook_message(webhook_def, code, message, CLIENT_NAME)
            else:
                print_log(f"Webhook not found for {entry['url']}")


if __name__ == "__main__":
    main()
