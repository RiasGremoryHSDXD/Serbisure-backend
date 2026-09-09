import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Serbisure.settings')
django.setup()
from django.db import connection
from accounts.models import tbl_user_profile

with connection.cursor() as c:
    c.execute("SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_name = 'accounts_tbl_user_profile'")
    for row in c.fetchall():
        if row[1] == 'NO':
            print('NOT NULL column:', row[0], 'default:', row[2])
