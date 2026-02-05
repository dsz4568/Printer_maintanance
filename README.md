# Printer_maintanance
The system was designed to monitor a fleet of printers (simulated by an external application in C++) and automatically detect service needs. It uses the Random Forest model to classify the condition of the device based on telemetry data (drum wear, fuser temperature, number of paper jams, etc.).

. Instrukcja uruchomienia systemu (Deployment Guide)
Aby uruchomić pełne środowisko testowe, należy wykonać poniższe kroki w podanej kolejności.

Krok 1: Przygotowanie środowiska Python
Upewnij się, że masz zainstalowanego Pythona w wersji 3.8 lub nowszej.

Instalacja bibliotek: Otwórz terminal w folderze projektu i zainstaluj wymagane zależności:

Bash
pip install -r requirements.txt
Uruchomienie serwera Flask: Serwer zainicjalizuje bazę danych printer_system.db oraz strukturę folderów dla modeli przy pierwszym starcie.

Bash
python app.py
Serwer będzie dostępny pod adresem: http://localhost:5000.

Krok 2: Kompilacja i uruchomienie symulatora C++
Symulator wymaga biblioteki libcurl do wysyłania danych przez HTTP oraz nagłówka json.hpp.

Kompilacja (Linux/GCC):

Bash
g++ printer_simulator.cpp -o printer_simulator -lcurl
Kompilacja (Windows/Visual Studio):

Otwórz plik Printer_maintanance.sln.

Upewnij się, że biblioteka curl jest podlinkowana w ustawieniach projektu.

Zbuduj projekt w trybie Release.

Uruchomienie: W nowym oknie terminala uruchom skompilowany plik:

Bash
./printer_simulator  # Linux
printer_simulator.exe # Windows
Symulator zacznie generować dane dla 500 drukarek i wysyłać je w paczkach po 50 sztuk do serwera.

Krok 3: Monitoring i Trening ML
Interfejs WWW: Otwórz przeglądarkę i wejdź na http://localhost:5000. Powinieneś zobaczyć napływające dane w tabeli predykcji.

Automatyczny trening: Po odebraniu 500 rekordów telemetrii, system automatycznie uruchomi proces treningu modelu RandomForest w tle.

Weryfikacja: Logi w konsoli serwera Flask poinformują o pomyślnym wytrenowaniu modelu i jego dokładności (Accuracy).
