"""Run the KYC API, optionally with TLS 1.3.

    python run.py            # plain HTTP (local demo)
    python run.py --tls      # TLS 1.3 using SSL_CERTFILE / SSL_KEYFILE from .env
"""
import ssl
import sys

import uvicorn

from app.config import settings

HOST = "0.0.0.0"
PORT = 8000


def main() -> None:
    use_tls = "--tls" in sys.argv or bool(settings.SSL_CERTFILE)

    if not use_tls:
        uvicorn.run("app.main:app", host=HOST, port=PORT)
        return

    if not (settings.SSL_CERTFILE and settings.SSL_KEYFILE):
        raise SystemExit(
            "TLS requested but SSL_CERTFILE / SSL_KEYFILE are not configured"
        )

    config = uvicorn.Config("app.main:app", host=HOST, port=PORT)
    config.load()

    # Build a hardened context and enforce TLS 1.3 minimum.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(settings.SSL_CERTFILE, settings.SSL_KEYFILE)
    config.ssl = context

    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
