"""Einstiegspunkt für Praxis Helper im Serverbetrieb.

Startet die Flask-App über den produktionstauglichen WSGI-Server waitress.
Host, Port und Datenbankpfad kommen aus Umgebungsvariablen (siehe README).
"""

import os

from waitress import serve

from src.app import app


def main() -> None:
    """Startet den waitress-Server, gebunden an alle Interfaces."""
    port = int(os.environ.get("PRAXIS_PORT", "5000"))
    serve(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
