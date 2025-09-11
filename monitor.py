
"""Program: Monitorowanie usług (REST API i SSH) z powiadomieniami Pushover

Opis:
    Ten program służy do monitorowania dostępności wybranych usług REST API oraz portów SSH na wskazanych hostach.
    W przypadku zmiany statusu (np. usługa przestaje odpowiadać lub ponownie staje się dostępna), program zapisuje
    aktualny stan do pliku oraz wysyła powiadomienie przez usługę Pushover.

Funkcjonalności:
    - Sprawdza dostępność portu SSH (22) na zadanych hostach.
    - Sprawdza odpowiedź HTTP (status 200) wybranych endpointów REST API.
    - Zmiany statusu są zapisywane do plików w katalogu STATUS_DIR.
    - W przypadku zmiany statusu wysyłane jest powiadomienie przez Pushover (jeśli skonfigurowano token i user key).

Konfiguracja:
    - STATUS_DIR: Katalog, w którym zapisywane są pliki statusów.
    - DEFAULT_TIMEOUT_MS: Domyślny timeout dla sprawdzeń (w milisekundach).
    - CLIENT_NAME: Nazwa klienta lub aplikacji, która monitoruje usługi.
    - PUSHOVER_API_TOKEN: Token aplikacji Pushover.
    - PUSHOVER_USER_KEY: Klucz użytkownika Pushover.

Główne funkcje:
    - check_ssh(host, timeout_ms): Sprawdza dostępność portu SSH na hoście.
    - check_api(url): Sprawdza dostępność endpointu REST API.
    - send_pushover_message(token, user, title, message): Wysyła powiadomienie przez Pushover.
    - sendMessage(name, url, code, message): Obsługuje zapis statusu i wysyłkę powiadomień.
    - main(): Główna funkcja uruchamiająca sprawdzenia.

Użycie:
    Uruchom program. Wyniki sprawdzeń oraz ewentualne powiadomienia pojawią się w konsoli oraz (w przypadku zmiany statusu) w aplikacji Pushover.

Autor: Grzegorz Skorupa
Data: 2025-08-12

Aby uruchamiać program cyklicznie, np. co 5 minut, można użyć harmonogramu zadań crontab w systemie Linux.
W tym celu należy dodać odpowiedni wpis do pliku crontab użytkownika, np.:

    */5 * * * * /usr/bin/python3 /ścieżka/do/skryptu/monitoring.py /ścieżka/do/konfiguracji.yaml

Powyższy wpis spowoduje automatyczne uruchamianie programu co 5 minut.
Upewnij się, że ścieżka do interpretera Python oraz do pliku programu jest poprawna.
Wyniki działania oraz powiadomienia będą generowane zgodnie z konfiguracją programu.
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

# Pobierz ścieżkę do pliku konfiguracyjnego z argumentu wywołania
if len(sys.argv) < 2:
    print("Podaj ścieżkę do pliku konfiguracyjnego YAML jako pierwszy argument!")
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
        CLIENT_NAME = "phoenix3"
        STATUS_DIR = "/tmp/status_files/"
        DEFAULT_TIMEOUT_MS = 5000
        PUSHOVER_API_TOKEN = ""
        PUSHOVER_USER_KEY = ""
except Exception as e:
    print(f"Error loading config: {e}")
    sys.exit(1)

def check_ssh(host, timeout_ms=DEFAULT_TIMEOUT_MS):
    """
    Sprawdza dostępność portu SSH (22) na danym hoście.
    Zwraca (200, "OK") jeśli port otwarty, w przeciwnym razie (kod, opis).
    """
    timeout_sec = timeout_ms / 1000.0
    try:
        # Najpierw sprawdź czy port 22 jest otwarty
        with socket.create_connection((host, 22), timeout=timeout_sec):
            pass
    except (socket.timeout, TimeoutError):
        return timeout_ms, "Timeout"
    except Exception as e:
        return -1, f"Port 22 error: {e}"

    # Opcjonalnie: sprawdź czy można się zalogować (np. przez ssh-keyscan lub próbę połączenia bez hasła)
    # Tu tylko sprawdzenie baneru ssh (nie wymaga klucza)
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
    Wysyła powiadomienie przez Pushover API.
    :param token: API token aplikacji Pushover
    :param user: User key Pushover
    :param title: Tytuł powiadomienia
    :param message: Treść powiadomienia
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
            print("Pushover: Powiadomienie wysłane.")
        else:
            print(f"Pushover: Błąd wysyłania powiadomienia: {response.status_code} {response.text}")
    except Exception as e:
        print(f"Pushover: Wyjątek podczas wysyłania powiadomienia: {e}")

def check_api(url, checkJson, checkText):
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
                # find "500" in response text
                if "500" in response.text:
                    return response.status_code, f"500 found in response text: {response.text }"
            return 200, "OK"
        else:
            return response.status_code, f"Unexpected status: {response.status_code}"
    except requests.exceptions.Timeout:
        return DEFAULT_TIMEOUT_MS, "Timeout"
    except Exception as e:
        return -1, f"Error: {e}"

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
        # jeśli nie są puste zmienne PUSHOVER_API_TOKEN i PUSHOVER_USER_KEY
        # to wyślij powiadomienie przez Pushover
        if PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
            send_pushover_message(PUSHOVER_API_TOKEN, PUSHOVER_USER_KEY, f"{name} error", f"{code} {message} ({CLIENT_NAME})")

def main():
    # Ensure config is loaded and is a dict before accessing its attributes
    if config is None or not isinstance(config, dict):
        print("Błąd: Konfiguracja nie została poprawnie załadowana lub jest nieprawidłowa.")
        sys.exit(1)

    urls = config.get("urls", [])
    hosts = config.get("hosts-ssh", [])

    for entry in urls:
        code, message = check_api(entry["url"], entry.get("checkJson", False), entry.get("checkText", False))
        sendMessage(entry["name"], entry["url"], code, message)

    for host in hosts:
        code, message = check_ssh(host)
        sendMessage(host, host, code, message)

if __name__ == "__main__":
    main()
