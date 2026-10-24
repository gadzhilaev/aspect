# GigaChat TLS certificates

GigaChat API uses certificates from the Russian Trusted Root CA (Минцифры).
Python/`httpx` does not trust them by default → `CERTIFICATE_VERIFY_FAILED`.

This folder holds a **public** CA bundle (`gigachat_ca_bundle.pem` = certifi + Russian Root + Sub CA).
TLS verification stays **enabled** (`verify=<bundle>`); we never use `verify=False`.

Regen (if needed):

```powershell
# Download public CAs from gu-st.ru, normalize PEM, merge with certifi
```

Set override in root `.env` if desired:

```env
GIGACHAT_CA_BUNDLE=app/certs/gigachat_ca_bundle.pem
```
