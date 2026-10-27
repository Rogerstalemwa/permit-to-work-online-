from django.db import models

class Site(models.Model):                       # UBL, IDU ... each with its own departments and areas
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    order = models.IntegerField(default=0)

class Dept(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='depts')
    name = models.CharField(max_length=60)
    order = models.IntegerField(default=0)

class Area(models.Model):
    dept = models.ForeignKey(Dept, on_delete=models.CASCADE, related_name='areas')
    name = models.CharField(max_length=80)
    order = models.IntegerField(default=0)

class Person(models.Model):
    email = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=20)          # Receiver, Issuer, Area Owner, Administrator
    site = models.CharField(max_length=10, blank=True, default='')
    dept = models.CharField(max_length=300, blank=True)   # comma separated department names (issuers, owners)
    company = models.CharField(max_length=120, blank=True)
    pin = models.CharField(max_length=128, blank=True)    # stored hashed
    phone = models.CharField(max_length=40, blank=True, default='')
    login = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    online = models.BooleanField(default=False)     # signed in right now
    last_seen = models.DateTimeField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)
    recovery = models.CharField(max_length=128, blank=True, default='')   # hashed recovery key (administrators)

class Permit(models.Model):
    id = models.BigIntegerField(primary_key=True)
    by = models.CharField(max_length=120)
    site = models.CharField(max_length=10, blank=True, default='')
    dept = models.CharField(max_length=60, blank=True)
    data = models.TextField()
    updated = models.DateTimeField(auto_now=True)

class PermitDraft(models.Model):
    owner = models.CharField(max_length=120, db_index=True)
    kind = models.CharField(max_length=10, default="HW")
    title = models.CharField(max_length=180, blank=True, default="")
    data = models.TextField(default="{}")
    updated = models.DateTimeField(auto_now=True)

class Note(models.Model):
    nid = models.CharField(max_length=40, unique=True)
    to = models.CharField(max_length=120)
    data = models.TextField()

class Alert(models.Model):
    key = models.CharField(max_length=80, unique=True)   # one reminder per permit, kind and day

class Counter(models.Model):
    key = models.CharField(max_length=40, unique=True)   # permit serial numbers per site and permit type
    n = models.IntegerField(default=0)

class AuditLog(models.Model):
    ts = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=120)
    action = models.CharField(max_length=60)
    detail = models.TextField(blank=True)

class ResetCode(models.Model):                  # emailed code for a forgotten PIN
    email = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=64)          # stored hashed
    expires = models.DateTimeField()
    sent = models.DateTimeField()
    tries = models.IntegerField(default=0)

class Setting(models.Model):
    key = models.CharField(max_length=40, unique=True)
    value = models.TextField(blank=True)

from django.db.backends.signals import connection_created

def _sqlite_tuning(sender, connection, **kwargs):
    # write-ahead logging and a long busy timeout stop "database is locked" errors when several people save at once
    if connection.vendor == 'sqlite':
        cur = connection.cursor()
        cur.execute('PRAGMA journal_mode=WAL;')
        cur.execute('PRAGMA busy_timeout=30000;')

connection_created.connect(_sqlite_tuning)
