import hashlib
import hmac
import json
import logging
import os
import random
import secrets
import socket
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import connections, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import Draft, Alert, Area, AuditLog, Counter, Dept, Note, Permit, Person, ResetCode, Setting, Site

BUILD = '2026-10-28 digital-signoff-handover v37 - floating top panel'   # keep in sync with BUILD in index.html
ROLES = ['Receiver', 'Issuer', 'Area Owner']   # roles that can be created; the Administrator is created at first start
PERMIT_TYPES = {'GW': 'General work', 'EX': 'Excavation', 'HW': 'Hot works', 'WH': 'Work at height', 'HO': 'Hot work', 'WO': 'Work at height', 'CS': 'Confined space entry'}

def escalation_settings():
    defaults = {'approval_reminder_minutes': 30, 'approval_escalation_minutes': 120,
                'approval_urgent_minutes': 240, 'closure_escalation_hours': 4,
                'closure_urgent_hours': 24}
    row = Setting.objects.filter(key='escalation_settings').first()
    if row:
        try:
            raw = json.loads(row.value)
            for key in defaults:
                val = int(raw.get(key, defaults[key]))
                defaults[key] = max(5, min(168 * 60, val)) if 'minutes' in key else max(1, min(168, val))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    return defaults

def rams_enabled():
    row = Setting.objects.filter(key='rams_enabled').first()
    return row.value.lower() in ('1', 'true', 'on', 'yes') if row else False

def toolbox_enabled():
    row = Setting.objects.filter(key='toolbox_enabled').first()
    return row.value.lower() in ('1', 'true', 'on', 'yes') if row else False

def _day_passed(day):
    """True once 19:00 on the given YYYY-MM-DD has passed (site local time)."""
    try:
        end = datetime.strptime(str(day) + ' 19:00', '%Y-%m-%d %H:%M')
    except (TypeError, ValueError):
        return False
    return timezone.localtime().replace(tzinfo=None) > end

def _permit_open(dd):
    """A permit is still open unless it is cancelled, closed, or expired before it was ever approved."""
    if dd.get('cx') or dd.get('closureVerification') or len(dd.get('ret') or []) >= 3:
        return False
    if len(dd.get('sig') or []) < 3 and _day_passed(dd.get('date')):
        return False
    return True

def _permit_overdue(dd):
    return _permit_open(dd) and len(dd.get('sig') or []) >= 3 and _day_passed(dd.get('end') or dd.get('date'))

KIND_NAMES = {'GW': 'General Work', 'EX': 'Excavation', 'HW': 'Hot Works', 'WH': 'Work at Height',
              'HO': 'Hot Work (Operations)', 'WO': 'Work at Height (Operations)', 'CS': 'Confined Space Entry'}

def receiver_block(email, kind):
    """Message explaining why this receiver may not start another permit, or '' when allowed."""
    overdue, same = [], []
    for row in Permit.objects.filter(by=email):
        try:
            dd = json.loads(row.data)
        except ValueError:
            continue
        if _permit_overdue(dd):
            overdue.append(dd.get('no') or str(row.id))
        elif dd.get('kind') == kind and _permit_open(dd):
            same.append(dd.get('no') or str(row.id))
    if overdue:
        return 'You have overdue permits that were not returned (' + ', '.join(overdue) + '). Return them before you start or sign a new permit.'
    if same:
        return 'You already have an open ' + KIND_NAMES.get(kind, 'permit of this kind') + ' permit (' + ', '.join(same) + '). Return and close it, or cancel it, before starting another of the same kind.'
    return ''

def enabled_permit_types():
    row = Setting.objects.filter(key='enabled_permit_types').first()
    if not row:
        return list(PERMIT_TYPES)
    try:
        chosen = json.loads(row.value)
        return [code for code in PERMIT_TYPES if code in chosen]
    except (TypeError, ValueError):
        return list(PERMIT_TYPES)
WRITE_LOCK = threading.Lock()
KEY_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_fails = {}

def new_key():
    return '-'.join(''.join(secrets.choice(KEY_CHARS) for _ in range(4)) for _ in range(4))

def code_hash(email, code):
    return hmac.new(settings.SECRET_KEY.encode(), f'{email}:{code}'.encode(), hashlib.sha256).hexdigest()

def email_mode():
    return 'file' if 'filebased' in settings.EMAIL_BACKEND else 'smtp'

def too_many(key):
    # at most 5 wrong attempts per 15 minutes for each email
    now = time.time()
    _fails[key] = [t for t in _fails.get(key, []) if now - t < 900]
    return len(_fails[key]) >= 5

def fail(key):
    _fails.setdefault(key, []).append(time.time())

# ---------------------------------------------------------------- helpers
def body(request):
    return json.loads(request.body or b'{}')

def err(msg, status=400):
    return JsonResponse({'error': msg}, status=status)

def me(request):
    e = request.session.get('e')
    p = Person.objects.filter(email=e).first() if e else None
    return p if p and p.active else None

def is_admin(request):
    p = me(request)
    return p if p and p.role == 'Administrator' else None

def depts_of(p):
    return [x for x in p.dept.split(',') if x]

def available(p):
    # available = signed in right now (and the page has been in touch in the last 3 minutes)
    return bool(p.online and p.last_seen and timezone.now() - p.last_seen < timedelta(seconds=180))

def touch(p, on=True):
    now = timezone.now()
    if on and p.online and p.last_seen and (now - p.last_seen).total_seconds() < 10:
        return
    with WRITE_LOCK:
        p.online, p.last_seen = on, now
        p.save(update_fields=['online', 'last_seen'])

def pub(p):
    return {'e': p.email, 'n': p.name, 'r': p.role, 'd': depts_of(p), 'site': p.site, 'co': p.company or None,
            'phone': p.phone, 'login': p.login, 'active': p.active, 'available': available(p),
            'last_login': p.last_login.isoformat() if p.last_login else None, 'recovery': bool(p.recovery)}

def audit(actor, action, detail=''):
    AuditLog.objects.create(actor=getattr(actor, 'email', actor) or '', action=action, detail=detail)

def structure():
    out = []
    for s in Site.objects.order_by('order', 'id'):
        out.append({'code': s.code, 'name': s.name, 'depts': [
            {'name': d.name, 'areas': [a.name for a in d.areas.order_by('order', 'id')]}
            for d in s.depts.order_by('order', 'id')]})
    return out

def seed_structure():
    if Site.objects.exists():
        return
    with WRITE_LOCK, transaction.atomic():
        if Site.objects.exists():
            return
        ubl = Site.objects.create(code='UBL', name='Uganda Breweries Limited', order=1)
        Site.objects.create(code='IDU', name='International Distillers Uganda', order=2)
        sample = {'Utilities': ['Water recovery plant', 'Boiler house', 'Effluent treatment plant', 'Compressor house'],
                  'Instrumentation': ['Instrumentation workshop', 'Control room'],
                  'Brewing': ['Brewhouse', 'Fermentation cellar', 'Filtration'],
                  'Packaging': ['Bottle filler', 'Pasteuriser', 'Keg line', 'Palletiser']}
        for i, (dn, areas) in enumerate(sample.items()):
            d = Dept.objects.create(site=ubl, name=dn, order=i)
            for j, an in enumerate(areas):
                Area.objects.create(dept=d, name=an, order=j)

def notice():
    s = Setting.objects.filter(key='notice').first()
    return s.value if s else ''

def tok(pid):
    # unguessable code for each permit, used in the QR link
    return hmac.new(settings.SECRET_KEY.encode(), str(pid).encode(), hashlib.sha256).hexdigest()[:16]

def with_tok(x):
    d = json.loads(x.data)
    d['tok'] = tok(x.id)
    return d

def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def base(request):
    # address that phones can reach; set PUBLIC_URL to override (e.g. https://permits.company.com/)
    if os.environ.get('PUBLIC_URL'):
        return os.environ['PUBLIC_URL'].rstrip('/') + '/'
    host = request.get_host().split(':')[0]
    if host in ('localhost', '127.0.0.1', '[::1]'):
        return f"http://{lan_ip()}:{request.get_port()}/"
    return request.build_absolute_uri('/')

# ---------------------------------------------------------------- clash feed and reminders
def classes(d):
    k = d.get('kind') or 'HW'
    if k == 'GW':
        jr = d.get('jr') or []
        return (['hot'] if 0 in jr else []) + (['wah'] if 3 in jr else []) + (['exc'] if any(o.get('i') == 2 for o in d.get('op') or []) else [])
    return {'HW': ['hot'], 'HO': ['hot'], 'CS': ['cs'], 'EX': ['exc'], 'WH': ['wah'], 'WO': ['wah']}.get(k, [])

def activity():
    # light list of every open permit, used for clash warnings
    rows = []
    for x in Permit.objects.all():
        d = json.loads(x.data)
        if d.get('cx') or len(d.get('ret', [])) >= 3:
            continue
        rows.append({'id': x.id, 'no': d.get('no'), 'kind': d.get('kind') or 'HW', 'site': d.get('site'), 'dept': d.get('dept'), 'loc': d.get('loc'),
                     'date': d.get('date'), 'end': d.get('end') or d.get('date'), 'start': d.get('start'), 'finish': d.get('finish'),
                     'sl': len(d.get('sig', [])), 'cl': classes(d)})
    return rows

_last_alert = [0.0]

def pts(s):
    return datetime.fromisoformat(str(s).replace('Z', '+00:00'))

log = logging.getLogger('permits')

def deliver(sub, body, to):
    """Send one email. Returns '' on success or the reason it failed (also logged and kept for the administrator)."""
    try:
        send_mail(sub, body, None, [to], fail_silently=False)
        return ''
    except Exception as ex:
        msg = (type(ex).__name__ + ': ' + str(ex))[:500]
        log.warning('Email to %s failed: %s', to, msg)
        try:
            Setting.objects.update_or_create(key='last_mail_error', defaults={'value': msg})
        except Exception:
            pass
        return msg

def mail_async(sub, body, to):
    """Notification emails are sent in the background so a slow mail service never delays a permit action."""
    def run():
        try:
            deliver(sub, body, to)
        finally:
            connections.close_all()
    threading.Thread(target=run, daemon=True).start()

def permit_email(sub, to, pid, link=''):
    """Email a notification with the permit's key details and a link to sign in and act on it."""
    d, who = {}, None
    try:
        row = Permit.objects.filter(id=int(pid)).first()
        d = json.loads(row.data) if row else {}
        who = Person.objects.filter(email=to).first()
    except Exception:
        pass
    kind = KIND_NAMES.get(d.get('kind'), '')
    area = ' · '.join(x for x in (d.get('dept'), d.get('loc')) if x)
    when = ' '.join(x for x in (str(d.get('date') or ''), ((d.get('start') or '') + ('-' + d['finish'] if d.get('finish') else '')) if d.get('start') else '') if x)
    lines = ['Hello ' + (who.name if who else 'there') + ',', '', sub + '.', '']
    for label, val in (('Permit', d.get('no')), ('Type', kind), ('Department / area', area), ('Requested by', ' · '.join(x for x in (d.get('name'), d.get('company')) if x)), ('Date and time', when), ('Work', (d.get('desc') or '')[:200])):
        if val:
            lines.append(label + ': ' + str(val))
    lines += ['', 'Open the permit system, sign in and review it:' + ((' ' + link) if link else ''), '', 'This is an automated message from the Permit to Work system.']
    mail_async('[Permit to Work] ' + sub, '\n'.join(lines), to)

def mk_note(to, sub, pid):
    nid = time.time() * 1000 + random.random()
    low = sub.lower()
    priority = 'critical' if any(k in low for k in ('work suspended', 'very high', 'safety incident', 'unsafe', 'overdue', 'not returned', 'urgent escalation')) else 'high' if any(k in low for k in ('returned for correction', 'awaiting closure', 'closure verification', 'needs your confirmation', 'waiting')) else 'normal'
    category = 'lifecycle' if any(k in low for k in ('suspend', 'resum', 'complete', 'closure', 'closed')) else 'approval' if any(k in low for k in ('confirm', 'approve', 'correction', 'clarification')) else 'expiry' if any(k in low for k in ('expire', 'valid window', 'not returned', 'overdue')) else 'general'
    n = {'id': nid, 'to': to, 'sub': sub, 'pid': pid, 'ts': timezone.now().isoformat(), 'rd': False, 'priority': priority, 'category': category}
    Note.objects.create(nid=str(nid), to=to, data=json.dumps(n))
    permit_email(sub, to, pid, (os.environ.get('PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL') or '').rstrip('/'))

def alert_once(key, people, sub, pid):
    if Alert.objects.filter(key=key).exists():
        return
    Alert.objects.create(key=key)
    for e in sorted(set(p for p in people if p)):
        mk_note(e, sub, pid)

def run_alerts(now=None):
    now = timezone.localtime(now or timezone.now())
    today, hm = now.date().isoformat(), now.strftime('%H:%M')
    esc = escalation_settings()
    with WRITE_LOCK:
        for x in Permit.objects.all():
            d = json.loads(x.data)
            if d.get('cx') or len(d.get('ret', [])) >= 3:
                continue
            sig, no, by = d.get('sig', []), d.get('no'), d.get('by')
            iss, own = d.get('issuers') or [], d.get('owners') or []
            start_d = d.get('date') or ''
            end = d.get('end') or start_d
            suspension = d.get('suspension') or {}
            if suspension.get('active'):
                # A suspended job must not be treated as routine active work.
                if suspension.get('since') and (now - pts(suspension['since'])).total_seconds() >= 86400:
                    alert_once(f'{x.id}:suspended24h:{suspension.get("since")}', [by] + iss + own,
                               f'{no} has remained suspended for 24 hours. Review and formally resume or close it.', x.id)
                continue
            completion = d.get('workCompletion') or {}
            if completion and not d.get('closureVerification'):
                completed_at = completion.get('ts', 'unknown')
                alert_once(f'{x.id}:closurepending:{completed_at}', iss + own,
                           f'{no} has been declared complete and is awaiting closure verification.', x.id)
                if completed_at != 'unknown':
                    elapsed = (now - pts(completed_at)).total_seconds() / 3600
                    admins = list(Person.objects.filter(role='Administrator', active=True).values_list('email', flat=True))
                    if elapsed >= esc['closure_escalation_hours']:
                        alert_once(f'{x.id}:closure-escalate4h:{completed_at}', iss + own + admins,
                                   f'ESCALATION: {no} has awaited closure verification for at least 4 hours.', x.id)
                    if elapsed >= esc['closure_urgent_hours']:
                        alert_once(f'{x.id}:closure-escalate24h:{completed_at}', [by] + iss + own + admins,
                                   f'URGENT: {no} has awaited closure verification for 24 hours. Resolve the handback and closure status.', x.id)
            if len(sig) < 3:                       # waiting for the issuer or the area owner
                if not sig:
                    continue
                waited = (now - pts(sig[-1]['ts'])).total_seconds() / 60
                responsible = iss if len(sig) == 1 else own
                if waited >= esc['approval_reminder_minutes']:
                    alert_once(f'{x.id}:wait{len(sig)}:{today}', responsible,
                               f'{no} has been waiting {int(waited)} minutes for your confirmation', x.id)
                admins = list(Person.objects.filter(role='Administrator', active=True).values_list('email', flat=True))
                if waited >= esc['approval_escalation_minutes']:
                    alert_once(f'{x.id}:escalate2h:{len(sig)}:{sig[-1].get("ts", today)}', responsible + admins,
                               f'ESCALATION: {no} has awaited approval for at least 2 hours. Please review and assign action.', x.id)
                if waited >= esc['approval_urgent_minutes']:
                    alert_once(f'{x.id}:escalate4h:{len(sig)}:{sig[-1].get("ts", today)}', [by] + iss + own + admins,
                               f'URGENT ESCALATION: {no} has awaited approval for at least 4 hours. The responsible team and administrator must resolve the delay.', x.id)
                continue
            ret_n = len(d.get('ret', []))
            if end < today or (end == today and hm >= '19:00'):      # window over and not returned
                alert_once(f'{x.id}:overdue:{today}', [by] + iss + own, f'{no} was not returned. Its valid window has ended.', x.id)
            elif start_d <= today <= end and ret_n == 0:
                if '18:30' <= hm < '19:00':
                    alert_once(f'{x.id}:soon:{today}', [by],
                               f"{no}: today's work window ends at 19:00. Leave the area safe." if today < end else f'{no} expires at 19:00. Finish the work and start the return.', x.id)
                if d.get('kind') == 'GW' and start_d < today and hm >= '09:00' and not any(dd.get('date') == today for dd in d.get('days', [])):
                    alert_once(f'{x.id}:daily:{today}', [by], f"{no} needs today's daily update before work continues.", x.id)

def maybe_alerts():
    t = time.time()
    if t - _last_alert[0] < 30:
        return
    _last_alert[0] = t
    try:
        run_alerts()
    except Exception:
        pass

# ---------------------------------------------------------------- pages and session
def index(request, t=None):
    html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8').replace('__BUILD__', BUILD)
    r = HttpResponse(html)
    r['Cache-Control'] = 'no-store'
    return r

def state(request):
    seed_structure()
    p = me(request)
    if not p:
        return JsonResponse({'build': BUILD, 'me': None, 'setup': not Person.objects.filter(role='Administrator').exists(), 'notice': notice(), 'email_mode': email_mode(), 'permit_types': enabled_permit_types(), 'rams_enabled': rams_enabled(), 'toolbox_enabled': toolbox_enabled(), 'demo': os.environ.get('DEMO_MODE') == '1'})
    touch(p)
    maybe_alerts()
    if p.role == 'Administrator':
        qs = Permit.objects.all()
    elif p.role == 'Receiver':
        qs = Permit.objects.filter(by=p.email)
    else:
        qs = Permit.objects.filter(site=p.site, dept__in=depts_of(p))
    return JsonResponse({
        'build': BUILD, 'me': pub(p), 'users': [pub(x) for x in Person.objects.filter(active=True).order_by('id')], 'drafts': drafts_of(p),
        'activity': activity(), 'sites': structure(), 'notice': notice(), 'permit_types': enabled_permit_types(), 'rams_enabled': rams_enabled(), 'toolbox_enabled': toolbox_enabled(), 'demo': os.environ.get('DEMO_MODE') == '1',
        'permits': [with_tok(x) for x in qs.order_by('id')],
        'notes': [json.loads(n.data) for n in Note.objects.filter(to=p.email).order_by('id')], 'base': base(request),
    })

@csrf_exempt
def setup(request):
    if Person.objects.filter(role='Administrator').exists():
        return err('The administrator account already exists.', 403)
    d = body(request)
    e, n, ph, pin = str(d.get('e', '')).strip().lower(), str(d.get('n', '')).strip(), str(d.get('phone', '')).strip(), str(d.get('pin', ''))
    if '@' not in e or not n or not ph or len(pin) < 4:
        return err('Enter a name, a valid email, a phone number and a PIN of at least 4 characters.')
    with WRITE_LOCK:
        key = new_key()
        p = Person.objects.create(email=e, name=n, role='Administrator', phone=ph, pin=make_password(pin), login=True, recovery=make_password(key))
    audit(p, 'Administrator created', e)
    request.session['e'] = p.email
    touch(p)
    return JsonResponse({'ok': True, 'key': key})

@csrf_exempt
def login(request):
    d = body(request)
    p = Person.objects.filter(email=str(d.get('e', '')).strip().lower()).first()
    if p and p.login and not p.active and check_password(d.get('p', ''), p.pin):
        admins = [{'n': a.name, 'e': a.email, 'phone': a.phone} for a in Person.objects.filter(role='Administrator', active=True)]
        return JsonResponse({'ok': False, 'deactivated': True, 'contacts': admins}, status=403)
    if p and p.login and p.active and check_password(d.get('p', ''), p.pin):
        request.session['e'] = p.email
        with WRITE_LOCK:
            p.last_login = timezone.now()
            p.save(update_fields=['last_login'])
        touch(p)
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=401)

@csrf_exempt
def logout(request):
    p = me(request)
    if p:
        touch(p, on=False)
    request.session.flush()
    return JsonResponse({'ok': True})

@csrf_exempt
def forgot(request):
    # emails a 6 digit code; the answer is always the same so nobody can test which emails have accounts
    e = str(body(request).get('e', '')).strip().lower()
    p = Person.objects.filter(email=e).first()
    if p and p.login and p.active:
        now = timezone.now()
        rc = ResetCode.objects.filter(email=e).first()
        if not rc or (now - rc.sent).total_seconds() >= 60:
            code = f'{secrets.randbelow(10 ** 6):06d}'
            with WRITE_LOCK:
                ResetCode.objects.update_or_create(email=e, defaults={'code': code_hash(e, code), 'expires': now + timedelta(minutes=15), 'sent': now, 'tries': 0})
            deliver('Your permit system sign-in code', f'Your code is {code}\n\nIt works for 15 minutes. Enter it on the sign-in page to choose a new PIN. If you did not ask for it, ignore this email.', e)
    return JsonResponse({'ok': True, 'mode': email_mode()})

@csrf_exempt
def reset_pin(request):
    d = body(request)
    e, code, pin = str(d.get('e', '')).strip().lower(), str(d.get('code', '')).strip(), str(d.get('pin', ''))
    if len(pin) < 4:
        return err('The new PIN must be at least 4 characters.')
    rc, p = ResetCode.objects.filter(email=e).first(), Person.objects.filter(email=e).first()
    if not rc or not p or not p.active or rc.expires < timezone.now() or rc.tries >= 5:
        return err('That code is not valid or has expired. Ask for a new one.')
    if not hmac.compare_digest(rc.code, code_hash(e, code)):
        with WRITE_LOCK:
            rc.tries += 1
            rc.save()
        return err('That code is not correct.')
    with WRITE_LOCK:
        p.pin = make_password(pin)
        p.save(update_fields=['pin'])
        rc.delete()
    audit(p, 'PIN reset with email code', e)
    return JsonResponse({'ok': True})

@csrf_exempt
def recover(request):
    # administrator only: reset the PIN with the recovery key saved at set-up
    d = body(request)
    e, key, pin = str(d.get('e', '')).strip().lower(), str(d.get('key', '')).strip().upper(), str(d.get('pin', ''))
    if len(pin) < 4:
        return err('The new PIN must be at least 4 characters.')
    if too_many(e):
        return err('Too many attempts. Wait 15 minutes and try again.', 429)
    p = Person.objects.filter(email=e, role='Administrator').first()
    if not p or not p.active or not p.recovery or not check_password(key, p.recovery):
        fail(e)
        return err('The email or the recovery key is not correct.')
    newkey = new_key()
    with WRITE_LOCK:
        p.pin, p.recovery = make_password(pin), make_password(newkey)
        p.save(update_fields=['pin', 'recovery'])
    audit(p, 'PIN reset with recovery key', e)
    return JsonResponse({'ok': True, 'key': newkey})

@csrf_exempt
def my_pin(request):
    p = me(request)
    if not p:
        return err('auth', 401)
    d = body(request)
    if not check_password(str(d.get('old', '')), p.pin):
        return err('The current PIN is not correct.')
    if len(str(d.get('new', ''))) < 4:
        return err('The new PIN must be at least 4 characters.')
    with WRITE_LOCK:
        p.pin = make_password(str(d['new']))
        p.save(update_fields=['pin'])
    audit(p, 'PIN changed', p.email)
    return JsonResponse({'ok': True})

# ---------------------------------------------------------------- permits and notes
@csrf_exempt
def serial(request):
    p = me(request)
    if not p:
        return err('auth', 401)
    d = body(request)
    site, kind = str(d.get('site', '')), str(d.get('kind', ''))
    with WRITE_LOCK, transaction.atomic():
        c, _ = Counter.objects.get_or_create(key=f'{site}:{kind}')
        c.n += 1
        c.save()
    return JsonResponse({'no': f'{site}-{kind}-{c.n:04d}'})

def drafts_of(p):
    if p.role != 'Receiver':
        return []
    return [{'kind': d.kind, 'updated': d.updated.isoformat()} for d in Draft.objects.filter(email=p.email).order_by('-updated')]

@csrf_exempt
def draft(request):
    """Receivers' auto-saved permit drafts: GET ?kind=HW, POST {kind, data} or POST {kind, delete: true}."""
    p = me(request)
    if not p or p.role != 'Receiver':
        return err('Only receivers have permit drafts.', 403)
    if request.method == 'GET':
        row = Draft.objects.filter(email=p.email, kind=request.GET.get('kind', '')).first()
        if not row:
            return JsonResponse({'draft': None})
        try:
            data = json.loads(row.data)
        except ValueError:
            data = {}
        return JsonResponse({'draft': {'data': data, 'updated': row.updated.isoformat()}})
    d = body(request)
    kind = str(d.get('kind', ''))
    if kind not in KIND_NAMES:
        return err('Unknown permit kind.')
    if d.get('delete'):
        Draft.objects.filter(email=p.email, kind=kind).delete()
        return JsonResponse({'ok': True})
    raw = json.dumps(d.get('data') or {})
    if len(raw) > 400000:
        return err('This draft is too large to save.')
    with WRITE_LOCK:
        row, _ = Draft.objects.update_or_create(email=p.email, kind=kind, defaults={'data': raw})
    return JsonResponse({'ok': True, 'updated': row.updated.isoformat()})

@csrf_exempt
def permit(request):
    p = me(request)
    if not p:
        return err('auth', 401)
    d = body(request)
    if not isinstance(d, dict) or 'id' not in d:
        return err('A valid permit ID is required.')
    with WRITE_LOCK:
        old = Permit.objects.filter(id=d['id']).first()
        old_data = json.loads(old.data) if old else {}
        # Authorize against the stored record, never identity/location values supplied by the browser.
        if old:
            ok = (p.role == 'Administrator' or old.by == p.email or
                  (p.role in ('Issuer', 'Area Owner') and old.site == p.site and old.dept in depts_of(p)))
        else:
            ok = (p.role == 'Administrator' or (p.role == 'Receiver' and d.get('by') == p.email))
        if not ok:
            return err('Not allowed to create or edit this permit.', 403)
        if not old and p.role == 'Receiver':
            blocked = receiver_block(p.email, d.get('kind'))
            if blocked:
                return err(blocked, 409)
        if old and d.get('by') != old.by:
            return err('The original Receiver/creator cannot be changed.', 403)
        # Do not allow an approved permit's safety-critical scope to change while retaining its approvals.
        material_fields = ('kind', 'site', 'dept', 'loc', 'date', 'end', 'start', 'finish', 'desc', 'eq', 'ty', 'jr', 'op', 'pp', 'pr', 'gs', 'fw', 'em', 'team', 'name', 'company')
        if old and len(old_data.get('sig') or []) >= 3 and not old_data.get('cx'):
            changed = [key for key in material_fields if old_data.get(key) != d.get(key)]
            if changed:
                return err('This permit is already approved. Safety-critical changes cannot retain the existing approvals; use the formal return-for-correction workflow or create a new permit.', 409)
        # Lifecycle changes are validated on the server as well as in the UI.
        old_susp = old_data.get('suspension') or {}
        new_susp = d.get('suspension') or {}
        is_authority = p.role == 'Administrator' or (p.role in ('Issuer', 'Area Owner') and p.email in ((old_data.get('issuers') or []) + (old_data.get('owners') or [])))
        # Approval/return history is append-only through the authorized actor's own action.
        for field, allowed_roles in (('sig', ('Issuer', 'Area Owner', 'Administrator')), ('ret', ('Receiver', 'Issuer', 'Area Owner', 'Administrator'))):
            old_rows = old_data.get(field) or []
            new_rows = d.get(field) or []
            if old and old_rows != new_rows:
                if len(new_rows) < len(old_rows) or new_rows[:len(old_rows)] != old_rows:
                    return err('Workflow history cannot be removed or rewritten.', 403)
                added = new_rows[len(old_rows):]
                if len(added) != 1 or str((added[0] or {}).get('e', '')).lower() != p.email.lower():
                    return err('Each workflow action must be recorded by the signed-in user.', 403)
                if p.role not in allowed_roles:
                    return err('Your role cannot perform this workflow action.', 403)
                if field == 'sig' and p.role != 'Administrator' and p.email not in ((old_data.get('issuers') or []) + (old_data.get('owners') or [])):
                    return err('Only an assigned reviewer can approve this permit.', 403)
                if field == 'ret' and p.role == 'Receiver' and old.by != p.email:
                    return err('Only the original Receiver can update this return history.', 403)
        if d.get('cx') and not old_data.get('cx') and not is_authority:
            return err('Only an assigned Issuer, Area Owner or Administrator can cancel this permit.', 403)
        if old_data.get('cx') and d.get('cx') != old_data.get('cx'):
            return err('A cancelled permit cannot be altered or uncancelled.', 409)
        if new_susp.get('active') and not old_susp.get('active'):
            if not is_authority:
                return err('Only an assigned Issuer, Area Owner or Administrator can suspend work.', 403)
            if not str(new_susp.get('reason', '')).strip():
                return err('A reason is required to suspend work.')
        if old_susp.get('active') and not new_susp.get('active') and not is_authority:
            return err('Only an assigned Issuer, Area Owner or Administrator can authorize resumption.', 403)
        # Digital handover acknowledgements are append-only and validated against the session actor.
        old_handover = old_data.get('handoverSignoffs') or []
        new_handover = d.get('handoverSignoffs') or []
        if old and old_handover != new_handover:
            if len(new_handover) < len(old_handover) or new_handover[:len(old_handover)] != old_handover:
                return err('Handover sign-offs cannot be removed or rewritten.', 403)
            added = new_handover[len(old_handover):]
            if len(added) != 1:
                return err('Record one handover sign-off at a time.', 400)
            signoff = added[0] if isinstance(added[0], dict) else {}
            stage = signoff.get('stage')
            if str(signoff.get('by', '')).lower() != p.email.lower() or str(signoff.get('name', '')).strip() != p.name:
                return err('A handover sign-off must identify the signed-in account.', 403)
            if not str(signoff.get('note', '')).strip():
                return err('A handover acknowledgement note is required.')
            if len(old_data.get('sig') or []) < 3 or old_data.get('cx'):
                return err('Handover sign-off requires an approved, active permit.', 409)
            if stage == 'pre_work':
                if p.role != 'Receiver' or (old and old.by != p.email):
                    return err('Only the assigned Receiver can acknowledge the pre-work handover.', 403)
                if old_data.get('workCompletion') or old_susp.get('active'):
                    return err('Pre-work handover is unavailable after completion or while work is suspended.', 409)
            elif stage == 'site_handback':
                if not is_authority:
                    return err('Only an assigned Issuer, Area Owner or Administrator can acknowledge site handback.', 403)
                if not old_data.get('workCompletion'):
                    return err('The Receiver must declare work complete before site handback.', 409)
            else:
                return err('Unknown handover stage.', 400)
            if any((x or {}).get('stage') == stage for x in old_handover):
                return err('This handover stage has already been signed off.', 409)
        old_completion = old_data.get('workCompletion')
        new_completion = d.get('workCompletion')
        if new_completion and not old_completion and p.role != 'Receiver' and p.role != 'Administrator':
            return err('Only the assigned Receiver can declare work complete.', 403)
        if d.get('closureVerification') and not old_data.get('closureVerification'):
            if not is_authority:
                return err('Only an assigned Issuer, Area Owner or Administrator can verify closure.', 403)
            if not new_completion:
                return err('The Receiver must declare work complete before closure can be verified.')
        if old is None and d.get('kind') not in enabled_permit_types():
            return err('This permit type is currently disabled by the administrator. Refresh the page or contact the administrator.', 403)
        # Risk assessment / safety-control add-on panels were removed by request.
        was_cx = bool(old and json.loads(old.data).get('cx'))
        Permit.objects.update_or_create(id=d['id'], defaults={'by': d['by'], 'site': d.get('site', ''), 'dept': d.get('dept', ''), 'data': json.dumps(d)})
        if not old and d.get('kind') in KIND_NAMES:
            Draft.objects.filter(email=d['by'], kind=d['kind']).delete()   # the finished permit replaces its draft
        if old is None:
            audit(p, 'Permit created', f"{d.get('no')}: {d.get('kind')} · risk assessment recorded")
        else:
            changed = [k for k in sorted(set(old_data) | set(d)) if old_data.get(k) != d.get(k)]
            # Exclude volatile edit metadata from the audit summary.
            changed = [k for k in changed if k not in ('editedAt', 'editedBy')]
            if changed:
                audit(p, 'Permit updated', f"{d.get('no')}: changed fields: {', '.join(changed[:30])}")
            if old_data.get('sig') != d.get('sig'):
                audit(p, 'Approval recorded', f"{d.get('no')}: approval history appended by {p.email}")
            if old_data.get('ret') != d.get('ret'):
                audit(p, 'Return/resubmission recorded', f"{d.get('no')}: return history appended/updated by {p.email}")
            if old_data.get('suspension') != d.get('suspension'):
                audit(p, 'Suspension/resumption recorded', f"{d.get('no')}: {json.dumps(d.get('suspension') or {}, ensure_ascii=False)[:500]}")
            if old_data.get('workCompletion') != d.get('workCompletion'):
                audit(p, 'Work completion declared', f"{d.get('no')}: declared by {p.email}")
            if old_data.get('closureVerification') != d.get('closureVerification'):
                audit(p, 'Closure verification changed', f"{d.get('no')}: verified/updated by {p.email}")
            if old_data.get('handoverSignoffs') != d.get('handoverSignoffs'):
                latest = (d.get('handoverSignoffs') or [])[-1]
                audit(p, 'Digital handover sign-off', f"{d.get('no')}: {latest.get('stage', 'unknown')} by {p.email}; {str(latest.get('note', ''))[:300]}")
        if d.get('cx') and not was_cx:
            audit(p, 'Permit cancelled', f"{d.get('no')}: {d['cx'].get('reason', '')}")
    return JsonResponse({'ok': True})

@csrf_exempt
def notes(request):
    p = me(request)
    if not p:
        return err('auth', 401)
    payload = body(request)
    if not isinstance(payload, list):
        return err('Notifications must be submitted as a list.')
    with WRITE_LOCK:
        for n in payload:
            if not isinstance(n, dict) or 'id' not in n:
                continue
            obj = Note.objects.filter(nid=str(n['id'])).first()
            if obj is not None:
                # Recipients may mark their own notification read, but cannot rewrite its sender,
                # text, permit association, timestamp, category or priority.
                if obj.to == p.email:
                    try:
                        stored = json.loads(obj.data)
                    except (TypeError, ValueError):
                        stored = {}
                    stored['rd'] = bool(n.get('rd', stored.get('rd', False)))
                    obj.data = json.dumps(stored)
                    obj.save(update_fields=['data'])
                continue
            to = str(n.get('to', '')).strip().lower()
            sub = str(n.get('sub', '')).strip()[:300]
            try:
                pid = int(n.get('pid'))
            except (TypeError, ValueError):
                continue
            permit_obj = Permit.objects.filter(id=pid).first()
            recipient = Person.objects.filter(email=to, active=True).first()
            if not permit_obj or not recipient or not sub:
                continue
            pd = json.loads(permit_obj.data)
            participants = {str(pd.get('by', '')).lower()}
            participants.update(str(e).lower() for e in (pd.get('issuers') or []) + (pd.get('owners') or []))
            participants.update(str((sg or {}).get('e', '')).lower() for sg in (pd.get('sig') or []) + (pd.get('ret') or []))
            if p.role != 'Administrator' and p.email.lower() not in participants:
                continue
            if to not in participants:
                continue
            # Normalize trusted fields server-side; do not accept forged priority/category metadata.
            nid = str(n['id'])
            if Note.objects.filter(nid=nid).exists():
                continue
            sub_low = sub.lower()
            priority = 'critical' if any(k in sub_low for k in ('work suspended', 'very high', 'safety incident', 'unsafe', 'overdue', 'urgent escalation')) else 'high' if any(k in sub_low for k in ('returned for correction', 'awaiting closure', 'closure verification', 'needs your confirmation', 'waiting', 'escalation')) else 'normal'
            category = 'lifecycle' if any(k in sub_low for k in ('suspend', 'resum', 'complete', 'closure', 'closed')) else 'approval' if any(k in sub_low for k in ('confirm', 'approve', 'correction', 'clarification')) else 'expiry' if any(k in sub_low for k in ('expire', 'valid window', 'not returned', 'overdue')) else 'general'
            clean = {'id': n['id'], 'to': to, 'sub': sub, 'pid': pid, 'ts': timezone.now().isoformat(), 'rd': False, 'priority': priority, 'category': category}
            Note.objects.create(nid=nid, to=to, data=json.dumps(clean))
            permit_email(sub, to, pid, base(request).rstrip('/'))
    return JsonResponse({'ok': True})

def verify(request, t):
    # public, read-only view of one permit for anyone who scans its QR code
    for x in Permit.objects.all():
        if hmac.compare_digest(tok(x.id), t):
            return JsonResponse({'permit': with_tok(x), 'base': base(request), 'sites': structure(), 'rams_enabled': rams_enabled(),
                                 'users': [{'e': u.email, 'n': u.name, 'r': u.role, 'd': depts_of(u), 'site': u.site, 'co': u.company or None, 'phone': u.phone}
                                           for u in Person.objects.filter(active=True).order_by('id')]})
    return err('not found', 404)

# ---------------------------------------------------------------- administrator console
def admin_only(request):
    a = is_admin(request)
    return a if a else None

@csrf_exempt
def admin_accounts(request):
    if not admin_only(request):
        return err('Administrator only.', 403)
    return JsonResponse({'people': [pub(x) for x in Person.objects.order_by('role', 'name')]})

@csrf_exempt
def admin_save(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    d = body(request)
    e, n, r, pin = str(d.get('e', '')).strip().lower(), str(d.get('n', '')).strip(), d.get('r'), str(d.get('pin', ''))
    site = str(d.get('site', '')).strip()
    o = Person.objects.filter(email=e).first()
    if '@' not in e or '.' not in e:
        return err('Enter a valid email address.')
    if not n or (r not in ROLES and not (o and o.role == 'Administrator' and r == 'Administrator')):
        return err('Enter a name and choose a role.')
    if not str(d.get('phone', '')).strip():
        return err('Enter a phone number, it is shown on permits.')
    if r != 'Receiver' and r != 'Administrator':
        if not Site.objects.filter(code=site).exists():
            return err('Choose the site this issuer or area owner works at.')
        valid = set(Dept.objects.filter(site__code=site).values_list('name', flat=True))
        dl = [x for x in (d.get('d') or []) if x in valid]
        if not dl:
            return err('Assign at least one department of that site to this issuer or area owner.')
    else:
        dl = []
        if r == 'Receiver' and site and not Site.objects.filter(code=site).exists():
            return err('Unknown site.')
    if o is None and len(pin) < 4:
        return err('The PIN / password must be at least 4 characters.')
    with WRITE_LOCK:
        creating = o is None
        if creating:
            o = Person(email=e, login=True, pin=make_password(pin))
        elif pin:
            o.pin = make_password(pin)
        o.name, o.role, o.site, o.dept = n, r, (site if r != 'Administrator' else ''), ','.join(dl)
        o.company, o.phone = str(d.get('co', '')).strip(), str(d.get('phone', '')).strip()
        o.save()
    audit(a, 'Account created' if creating else ('PIN reset' if pin else 'Account edited'), f'{e} ({r}, {site or "all sites"}, {", ".join(dl)})')
    return JsonResponse({'ok': True})

@csrf_exempt
def admin_active(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    d = body(request)
    o = Person.objects.filter(email=str(d.get('e', '')).lower()).first()
    if o is None or o.email == a.email:
        return err('You cannot deactivate your own account.')
    with WRITE_LOCK:
        o.active = bool(d.get('active'))
        if not o.active:
            o.online = False
        o.save()
    audit(a, 'Account activated' if o.active else 'Account deactivated', o.email)
    return JsonResponse({'ok': True})

@csrf_exempt
def admin_delete(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    o = Person.objects.filter(email=str(body(request).get('e', '')).lower()).first()
    if o is None or o.email == a.email:
        return err('You cannot delete your own account.')
    with WRITE_LOCK:
        o.delete()
    audit(a, 'Account deleted', o.email)
    return JsonResponse({'ok': True})

@csrf_exempt
def admin_struct(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    d = body(request)
    op, name = d.get('op'), str(d.get('name', '')).strip()
    site = Site.objects.filter(code=d.get('site')).first()
    dept = Dept.objects.filter(site=site, name=d.get('dept')).first() if site else None
    with WRITE_LOCK, transaction.atomic():
        if op == 'addSite':
            code = str(d.get('code', '')).strip().upper()
            if not code or not name or Site.objects.filter(code=code).exists():
                return err('Enter a new short code and a name for the site.')
            Site.objects.create(code=code[:10], name=name, order=Site.objects.count() + 1)
        elif op == 'renameSite' and site and name:
            site.name = name
            site.save()
        elif op == 'addDept' and site and name:
            if Dept.objects.filter(site=site, name=name).exists():
                return err('That department already exists at this site.')
            Dept.objects.create(site=site, name=name, order=site.depts.count())
        elif op == 'renameDept' and dept and name:
            old = dept.name
            dept.name = name
            dept.save()
            for p in Person.objects.filter(site=site.code):
                p.dept = ','.join(name if x == old else x for x in depts_of(p))
                p.save(update_fields=['dept'])
        elif op == 'delDept' and dept:
            dept.delete()
        elif op == 'addArea' and dept and name:
            Area.objects.create(dept=dept, name=name, order=dept.areas.count())
        elif op == 'renameArea' and dept and name:
            ar = Area.objects.filter(dept=dept, name=d.get('area')).first()
            if ar:
                ar.name = name
                ar.save()
        elif op == 'delArea' and dept:
            Area.objects.filter(dept=dept, name=d.get('area')).delete()
        else:
            return err('Nothing to change.')
    audit(a, 'Structure changed', f'{op} {d.get("site", "")} {d.get("dept", "")} {d.get("area", "")} {name}'.strip())
    return JsonResponse({'ok': True, 'sites': structure()})

@csrf_exempt
def admin_permit_types(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    if request.method != 'POST':
        return JsonResponse({'types': enabled_permit_types(), 'available': [{'code': k, 'name': v} for k, v in PERMIT_TYPES.items()]})
    d = body(request)
    selected = d.get('types')
    if not isinstance(selected, list) or any(code not in PERMIT_TYPES for code in selected):
        return err('Choose valid permit types.')
    if not selected:
        return err('At least one permit type must remain enabled.')
    # Preserve the catalogue order and avoid duplicates. Existing permits remain visible even if their type is disabled.
    selected = [code for code in PERMIT_TYPES if code in selected]
    with WRITE_LOCK:
        Setting.objects.update_or_create(key='enabled_permit_types', defaults={'value': json.dumps(selected)})
    audit(a, 'Permit types configured', ', '.join(selected))
    return JsonResponse({'ok': True, 'types': selected})


@csrf_exempt
def admin_log(request):
    if not admin_only(request):
        return err('Administrator only.', 403)
    return JsonResponse({'log': [{'ts': x.ts.isoformat(), 'actor': x.actor, 'action': x.action, 'detail': x.detail}
                                 for x in AuditLog.objects.order_by('-id')[:300]]})

@csrf_exempt
def admin_escalation(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    if request.method != 'POST':
        return JsonResponse({'settings': escalation_settings()})
    d = body(request)
    if d.get('read'):
        return JsonResponse({'settings': escalation_settings()})
    limits = {'approval_reminder_minutes': (5, 10080), 'approval_escalation_minutes': (5, 10080),
              'approval_urgent_minutes': (5, 10080), 'closure_escalation_hours': (1, 168),
              'closure_urgent_hours': (1, 168)}
    out = {}
    try:
        for key, (lo, hi) in limits.items():
            value = int(d.get(key))
            if not lo <= value <= hi:
                return err(f'{key} must be between {lo} and {hi}.')
            out[key] = value
    except (TypeError, ValueError):
        return err('Enter valid whole-number escalation thresholds.')
    if not out['approval_reminder_minutes'] < out['approval_escalation_minutes'] < out['approval_urgent_minutes']:
        return err('Approval thresholds must increase: reminder, escalation, then urgent escalation.')
    if out['closure_escalation_hours'] >= out['closure_urgent_hours']:
        return err('Urgent closure escalation must be later than the first closure escalation.')
    with WRITE_LOCK:
        Setting.objects.update_or_create(key='escalation_settings', defaults={'value': json.dumps(out)})
    audit(a, 'Escalation policy changed', json.dumps(out))
    return JsonResponse({'ok': True, 'settings': out})


@csrf_exempt
def admin_rams(request):
    if not admin_only(request):
        return err('Administrator only.', 403)
    d = body(request)
    enabled = bool(d.get('enabled', True))
    Setting.objects.update_or_create(key='rams_enabled', defaults={'value': 'true' if enabled else 'false'})
    audit(me(request), 'RAMS module setting changed', 'enabled' if enabled else 'disabled')
    return JsonResponse({'ok': True, 'enabled': enabled})

@csrf_exempt
def admin_toolbox(request):
    if not admin_only(request):
        return err('Administrator only.', 403)
    d = body(request)
    enabled = bool(d.get('enabled', True))
    Setting.objects.update_or_create(key='toolbox_enabled', defaults={'value': 'true' if enabled else 'false'})
    audit(me(request), 'Toolbox Talk capture setting changed', 'enabled' if enabled else 'disabled')
    return JsonResponse({'ok': True, 'enabled': enabled})

@csrf_exempt
def admin_notice(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    text = str(body(request).get('text', '')).strip()[:400]
    with WRITE_LOCK:
        Setting.objects.update_or_create(key='notice', defaults={'value': text})
    audit(a, 'Notice changed', text or '(cleared)')
    return JsonResponse({'ok': True})

@csrf_exempt
def admin_reset(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    with WRITE_LOCK:
        Permit.objects.all().delete()
        Note.objects.all().delete()
        Alert.objects.all().delete()
        Counter.objects.all().delete()
    audit(a, 'All permits cleared', 'permits, notifications, reminders and serial numbers')
    return JsonResponse({'ok': True})


@csrf_exempt
def admin_recovery(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    if not check_password(str(body(request).get('pin', '')), a.pin):
        return err('The PIN is not correct.')
    key = new_key()
    with WRITE_LOCK:
        a.recovery = make_password(key)
        a.save(update_fields=['recovery'])
    audit(a, 'Recovery key created', a.email)
    return JsonResponse({'ok': True, 'key': key})

@csrf_exempt
def admin_testmail(request):
    a = admin_only(request)
    if not a:
        return err('Administrator only.', 403)
    failure = deliver('Test email from the permit system', 'If you can read this, the permit system can send email.', a.email)
    return JsonResponse({'ok': True, 'mode': email_mode(), 'to': a.email, 'error': failure})
