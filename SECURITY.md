# Security

Agora is built to run on your own machine. The web UI binds to 127.0.0.1, checks the Host header, and requires an `X-Agora` header on every change. Remote model endpoints are refused unless you turn them on in Settings.

## Reporting a vulnerability
Please do not open a public issue. Use GitHub's private vulnerability reporting on this repository ("Security" tab → "Report a vulnerability"). Include the version, steps to reproduce and the impact. We aim to acknowledge within 7 days.

## Secrets
Never commit API keys or tokens. The settings file holding a saved key is created owner-only (0600). Use the `AGORA_API_KEY` environment variable where you can.
