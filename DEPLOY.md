# Putting the permit system online (demo) — Render

This puts the app on the internet with a free address like `https://ubl-permit-to-work-demo.onrender.com`, protected by HTTPS, so phones and cameras (QR scan) work anywhere. No server or domain purchase needed. It is for **demonstration only: do not enter real permits or real staff details**.

You need: a GitHub account (free) and a Render account (free; sign in with GitHub). Allow about 30 minutes the first time.

## 1. Put the files on GitHub
1. On github.com click **New repository**. Name it `ubl-permit-to-work`, choose **Private**, click **Create repository**.
2. Unzip the project on your PC. Open the `ptw-demo` folder, select **everything inside it** (not the folder itself) and drag it onto the GitHub page that says "uploading an existing file" (**Add file > Upload files**). Click **Commit changes**.
3. Check that `render.yaml`, `manage.py`, `build.sh` and the `permits` and `ptw` folders appear at the top level of the repository.

## 2. Create the online service
1. On render.com choose **New > Blueprint**, connect your GitHub account and pick the `ubl-permit-to-work` repository.
2. Render reads `render.yaml` and shows a web service and a database. Click **Apply**.
3. Wait about 5 minutes until the service shows **Live**. Click its address at the top.

## 3. First start
1. The first screen asks you to create the administrator. **Save the recovery key it shows you**, because it is the way back in if you forget the PIN.
2. In the Administrator pages create the sites and departments (UBL, IDU) and a few demo accounts (receiver, issuer, area owner).
3. In **Settings** switch the RAMS module and Toolbox Talk capture on if you want to show them (both start off).

## 4. Email notifications (optional)
Free Render services cannot send normal email (SMTP ports are blocked), so this package sends through Brevo's web API instead.
1. Create a free account at brevo.com, add and verify a sender address (a Gmail address is fine for a demo), and create an **API key**.
2. In Render open your service > **Environment** and add `BREVO_API_KEY` (the key) and `EMAIL_FROM` (the verified sender address). Save; the service restarts.
3. Sign in as administrator and use the test email button in Settings.
Without this, notifications still appear inside the app; only the emails are skipped.

## 5. Before every presentation
- A free service **goes to sleep after 15 minutes without visitors** and takes about a minute to wake up. Open the link 5 minutes before you present.
- The free database **expires 30 days after it is created** (with a 14-day grace period to upgrade). Fine for a demo; recreate it, or upgrade, if the demo runs longer.
- Free databases have no backups.
- Prices and limits on the free tier change. Check render.com/pricing. At the time of writing, keeping it always on cost about $7 per month for the web service plus about $6 per month for the database.

## 6. Updating the demo
Upload the changed files to GitHub (**Add file > Upload files**, same names replace the old ones). Render rebuilds automatically.

## What this package changes
- Production settings (secret key, allowed hosts, secure cookies, HTTPS) switch on when `DJANGO_ENV=production`; on a PC with `run.bat` nothing changes.
- PostgreSQL is used when `DATABASE_URL` is set; otherwise the local SQLite file is used.
- The app runs with one worker and several threads, because it serialises saves with an in-process lock.

## Before real use (not part of the demo)
- Replace 4-digit PINs with proper passwords and two-step sign-in, or UBL's own login.
- Add sign-in lockout limits and review the `csrf_exempt` endpoints.
- Move RAMS and toolbox attachments to proper file storage.
- Move the serial-number lock into the database before running more than one server process.
- Daily backups with a tested restore, monitoring, retention policy, and UBL IT security sign-off.
- Host where UBL IT approves, on a company address.
