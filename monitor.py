"""
Program: Service Monitoring (web content, REST API and SSH)

Description:
    This program is used to monitor the availability of selected web pages content, REST API services and SSH ports on specified hosts.
    If the status changes (e.g. the service stops responding or becomes available again), the program saves
    the current state to a file and sends a notification via the Pushover service.

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

To run the program cyclically, e.g. every 5 minutes, you can use the crontab scheduler in Linux.
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

config = None

def load_config(config_path):
    global config
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

# Get the path to the configuration file from the command-line argument
if len(sys.argv) < 2:
    print("Please provide the path to the YAML configuration file as the first argument!")
    sys.exit(1)
config_path = sys.argv[1]
load_config(config_path)

try:
    if config is not None and isinstance(config, dict):
        CLIENT_NAME = config.get("CLIENT_NAME", "phoenix3")
        STATUS_DIR = config.get("STATUS_DIR", "/tmp/status_files/")
        DEFAULT_TIMEOUT_MS = config.get("DEFAULT_TIMEOUT_MS", 5000)
        PUSHOVER_API_TOKEN = config.get("PUSHOVER_API_TOKEN", "")
        PUSHOVER_USER_KEY = config.get("PUSHOVER_USER_KEY", "")
    else:
        CLIENT_NAME = "myhost"
        STATUS_DIR = "/tmp/status_files/"
        DEFAULT_TIMEOUT_MS = 5000
        PUSHOVER_API_TOKEN = ""
        PUSHOVER_USER_KEY = ""
except Exception as e:
    print(f"Error loading config: {e}")
    sys.exit(1)

def check_ssh(host, timeout_ms=DEFAULT_TIMEOUT_MS):
    """
    Checks the availability of the SSH port (22) on the given host.
    Returns (200, "OK") if the port is open, otherwise (code, description).
    """
    timeout_sec = timeout_ms / 1000.0
    try:
        # First, check if port 22 is open
        with socket.create_connection((host, 22), timeout=timeout_sec):
            pass
    except (socket.timeout, TimeoutError):
        return timeout_ms, "Timeout"
    except Exception as e:
        return -1, f"Port 22 error: {e}"

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

def send_pushover_message(token, user, title, message):
    """
    Sends a notification via the Pushover API.
    :param token: Pushover application API token
    :param user: Pushover user key
    :param title: Notification title
    :param message: Notification content
    """
    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": token,
        "user": user,
        "title": title,
        "message": message
    }
    try:
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            print("Pushover: Notification sent.")
        else:
            print(f"Pushover: Error sending notification: {response.status_code} {response.text}")
    except Exception as e:
        print(f"Pushover: Exception while sending notification: {e}")

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

def sendMessage(name, url, code, message):
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

    if prev_code != str(code):
        print(f"[{name}] Status changed: {code} {message} ({CLIENT_NAME})")
        # if PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY are not empty
        # then send a notification via Pushover
        if PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
            send_pushover_message(PUSHOVER_API_TOKEN, PUSHOVER_USER_KEY, f"{name} error", f"{code} {message} ({CLIENT_NAME})")

def main():
    # Ensure config is loaded and is a dict before accessing its attributes
    if config is None or not isinstance(config, dict):
        print("Error: Configuration was not loaded correctly or is invalid.")
        sys.exit(1)

    urls = config.get("urls", [])
    hosts = config.get("hosts-ssh", [])

    # if urls is iterable
    if urls:
        for entry in urls:
            code, message = check_api(entry["url"], entry.get("checkJson", False), entry.get("checkText", False), entry.get("okText", None), entry.get("errorText", None))
            sendMessage(entry["name"], entry["url"], code, message)

    # if hosts is iterable
    if hosts:
        for host in hosts:
            code, message = check_ssh(host)
            sendMessage(host, host, code, message)

if __name__ == "__main__":
    main()
