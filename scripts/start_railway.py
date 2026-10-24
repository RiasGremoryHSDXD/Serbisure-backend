"""Start Railway with the configured PostgreSQL database without applying migrations."""
import os
import subprocess
import sys
from urllib.parse import unquote, urlsplit


def validate_environment(env):
    database = urlsplit(env.get('DATABASE_URL', ''))
    # DATABASE_URL selects the database; do not hardcode a staging database name.
    if database.scheme not in ('postgres', 'postgresql') or not unquote(database.path.lstrip('/')).strip():
        raise ValueError('Set DATABASE_URL to a PostgreSQL URL with an explicit database name.')
    if not database.hostname or database.hostname in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Railway requires an external PostgreSQL database host.')
    redis = urlsplit(env.get('REDIS_URL', ''))
    if redis.scheme not in ('redis', 'rediss') or not redis.hostname or redis.hostname in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Set REDIS_URL to the Railway Redis service.')
    if not env.get('SECRET_KEY') or env.get('DJANGO_DEBUG', '').lower() != 'false':
        raise ValueError('Set SECRET_KEY and DJANGO_DEBUG=false in Railway Variables.')
    if not env.get('REALTIME_ALLOWED_ORIGINS', '').strip():
        raise ValueError('Set REALTIME_ALLOWED_ORIGINS to the allowed admin origin(s).')
    port = int(env.get('PORT', '8000'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535.')
    return port


def main():
    try:
        port = validate_environment(os.environ)
    except ValueError as error:
        # Messages describe the missing setting; never print connection strings.
        raise SystemExit(str(error)) from None
    subprocess.run([sys.executable, 'manage.py', 'check'], check=True)
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--check', '--noinput'], check=True)
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'Serbisure.asgi:application',
                            '--host', '0.0.0.0', '--port', str(port), '--workers', '1',
                            '--proxy-headers', '--ws-max-size', '4096',
                            '--ws-ping-interval', '25', '--ws-ping-timeout', '25'])


if __name__ == '__main__':
    main()
