"""Gemeinsame Test-Konfiguration.

Setzt die zum Import von src.app nötige Umgebungsvariable, bevor Tests laufen.
Ohne PRAXIS_SECRET_KEY bricht die App beim Import bewusst ab (Produktionsschutz).
"""

import os

os.environ.setdefault("PRAXIS_SECRET_KEY", "test-secret-key")
