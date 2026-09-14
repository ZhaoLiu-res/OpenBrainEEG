"""Optional UI locale lookup. No recordings, keys or explicit IP are transmitted."""
from threading import Lock
from time import monotonic
import requests


class LocaleResolver:
    def __init__(self):
        self.lock = Lock()
        self.cached = None
        self.expires = 0

    def resolve(self):
        with self.lock:
            if self.cached is not None and monotonic() < self.expires:
                return dict(self.cached)
            result = {"language": None, "country": None, "source": "browser"}
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    response = session.get("https://ipwho.is/?fields=success,country_code", timeout=(2, 3), allow_redirects=False)
                payload = response.json() if response.status_code == 200 else {}
                country = str(payload.get("country_code", "")).strip().upper() if payload.get("success") is True else ""
                if response.status_code == 200 and len(country) == 2 and country.isascii() and country.isalpha():
                    result = {"language": "zh" if country in {"CN", "HK", "MO", "TW"} else "en", "country": country, "source": "ip"}
            except (requests.RequestException, ValueError, AttributeError):
                pass
            self.cached = result
            self.expires = monotonic() + (86400 if result["source"] == "ip" else 3600)
            return dict(result)
