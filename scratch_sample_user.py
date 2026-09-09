import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Serbisure.settings')
django.setup()
from django.db import connection

with connection.cursor() as c:
    c.execute("SELECT id, username, email, user_about, user_tags, show_contact_number, contact_number FROM accounts_tbl_user_profile LIMIT 2")
    for r in c.fetchall():
        print(r)
