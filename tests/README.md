# Tests — mode d'emploi

- Installer : `pip install .[test]` (pytest et httpx ; `httpx` est requis par `TestClient` de FastAPI, sans lui la collecte échoue).
- Lancer : `python scripts/check.py` (porte complète) ou `python -m pytest -q`.
- Encodage : tout accès texte déclare `encoding="utf-8"` ; la porte refuse le contraire (cp1252 par défaut sous Windows).

## Windows : dossier temporaire verrouillé

Si `tmp_path` échoue (`PermissionError` sur `pytest-of-<utilisateur>`), c'est un dossier hérité d'une autre session ou d'un autre compte, à ACL fermée, dans le dossier temporaire du système. Plutôt que de le supprimer, pointer pytest vers un dossier propre :

```
set PYTEST_DEBUG_TEMPROOT=C:\Temp\pytest-gb
python scripts/check.py
```

(PowerShell : `$env:PYTEST_DEBUG_TEMPROOT = "C:\Temp\pytest-gb"`). Le dossier doit exister et appartenir à l'utilisateur courant.
