#!/bin/bash
# 1. Zdefiniuj zmienne
REPO_URL="https://github.com/experiot/monitor.git"
REPO_DIR="/home/pi/monitor"

# 2. Sprawdź, czy katalog już istnieje
if [ -d "$REPO_DIR" ]; then
  # Jeśli istnieje, wejdź i zaktualizuj (pobierz zmiany)
  echo "Repozytorium istnieje. Aktualizuję..."
  cd "$REPO_DIR"
  git pull
  cd ..
else
  # Jeśli nie istnieje, sklonuj (pobierz)
  echo "Repozytorium nie istnieje. Klonuję..."
  git clone "$REPO_URL"
fi
