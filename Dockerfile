FROM python:3.11-slim

WORKDIR /app

# Nur die Laufzeit-Abhängigkeiten – kein pystray/pillow, kein PyInstaller.
RUN pip install --no-cache-dir flask waitress werkzeug

COPY src/ ./src/
COPY templates/ ./templates/
COPY static/ ./static/
COPY main.py .

# Datenbank liegt im gemounteten Volume, nicht im Image.
ENV PRAXIS_DB_PATH=/data/contacts.db

EXPOSE 5000

CMD ["python", "main.py"]
