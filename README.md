# Digital Work Permit demo (receiver-edit fix)

## Run on Windows
1. Extract the whole folder.
2. Install Python 3.12 if it is not installed.
3. Double-click `run.bat` and allow dependency installation. Keep the server window open.
4. On the laptop open `http://127.0.0.1:8000`. On phones use the IPv4 address printed by `run.bat`, on the same Wi-Fi.

## Returned-for-correction workflow
- Issuer/Area Owner can return a permit with required corrections in a comment.
- The assigned Receiver opens the returned permit and uses **Edit permit details** to update available work details.
- The Receiver then uses **Respond and resubmit**. This records a response and notifies the reviewer/approval team; it does not approve the permit automatically.

## Android APK
The `mobile-wrapper` is a Capacitor Android wrapper. To compile an APK, install Node.js LTS, Android Studio and its Android SDK, then run `BUILD_ANDROID_APK.bat`. Enter the laptop IPv4 address shown by `run.bat`. The phone and laptop must remain on the same Wi-Fi, and the Django server must be running. The APK is not precompiled in this ZIP.

## Note
This is a demo build. Test the complete workflow with test accounts and non-operational permits before using it for real work.


## Version 16 — Configurable foundation
- Administrator can enable or disable the built-in permit types from the new **Permit types** tab.
- Disabled types are hidden from receiver new-permit menus and blocked by the backend for newly created permits.
- Existing permits remain viewable and editable; disabling a type does not delete its records.
- Site, department and area management remains available.
- This version is the first configuration milestone; adding fully custom permit-form builders and site-specific approval workflow designers is planned for later versions.


## Version 18 — Permit lifecycle controls

Version 18 adds a formal work lifecycle layer:

- Assigned Issuers / Area Owners and Administrators can suspend an approved permit with a mandatory reason.
- While suspended, the permit is clearly marked and the normal expiry/overdue monitoring skips it; a reminder is generated if suspension lasts 24 hours.
- Authorized personnel must record checks before authorizing resumption. The reason, checks, names and timestamps are retained in the permit record.
- The assigned Receiver can declare work complete and record handback/housekeeping/isolation notes.
- An assigned Issuer / Area Owner or Administrator must verify closure with a recorded note; pending closure verification generates a notification.
- Lifecycle actions notify the permit team and appear in the permit history panel.
- Backend checks protect suspension, resumption and closure verification, and prevent material safety-critical changes to an already-approved permit from retaining its approvals.
- Existing expiry / overdue reminders remain in place.

Safety note: configure the workflow and risk matrix to your site's approved procedures. This build has passed static Python and JavaScript syntax checks, but should be tested in a staging environment with representative user roles before operational use.


## Version 19 — Advanced notifications and permit control

- Notification centre with unread counts, urgent unread count, category filters (approvals, lifecycle), search and mark-all-as-read.
- Notifications display Normal / High / Urgent priority badges. Urgent events include suspension, overdue/non-returned permits and urgent escalation messages.
- Approval waiting reminders escalate after 2 hours to the assigned reviewer(s) and active administrators, and after 4 hours to the Receiver, assigned reviewers and administrators.
- Closure verification waiting 4 hours and 24 hours triggers escalating reminders to the assigned reviewers and administrators, then the Receiver as well.
- Escalations are deduplicated per permit and workflow event to avoid repeated notification spam.
- Existing notification beep setting, permit workflows, lifecycle controls, risk assessments and mobile layout are retained.

Testing: Python compilation, inline JavaScript syntax, and ZIP integrity checks were run. A live Django/browser/phone workflow test was not run; test escalation timing and notification permissions in a staging environment before operational use.


## Version 20 — Security, audit and configurable escalation

- Permit edits are authorized against the stored permit owner/site/department, not editable identity/location fields sent by the browser. The original permit creator cannot be changed.
- Approval and return history cannot be removed or rewritten through the permit-save API; appended workflow actions must identify the signed-in user, and approvals are restricted to assigned reviewers (or an Administrator).
- New notification creation is checked against the permit participants and active recipient accounts. Recipients can mark their own notifications read, but cannot rewrite the notification's text, recipient, permit link, priority, category or timestamp.
- Server-side audit entries now capture permit updates and key workflow transitions, including approval, return/resubmission, risk assessment, suspension/resumption, completion, closure verification and cancellation. Administrator audit view explains the broader coverage.
- Administrators can configure approval reminder/escalation/urgent thresholds and closure escalation/urgent thresholds from Settings. Values are validated and stored in the database.

Testing: Python compilation, inline JavaScript syntax and ZIP integrity checks were run. A live Django/browser/phone workflow test was not run. Use staging accounts and test permits before operational deployment, and validate the permissions against your site's approved procedures.


## Version 21 — Digital sign-off and handover

Adds server-validated, append-only pre-work handover and post-completion site-handback acknowledgements. Each sign-off records the signed-in account, role, timestamp, typed-name confirmation and required note. Sign-offs are included in the permit card/print view and server audit log. These are application acknowledgements, not a substitute for a legally qualified electronic-signature service or site procedures.

## Version 22 — Permit print, RAMS visibility and Toolbox Talk attachments

- The added Risk Assessment and Safety Control Verification panels have been removed from the permit creation and returned-permit editing screens. Legacy records are not deleted; the old risk panel is no longer displayed on the permit card.
- Printing from a permit card targets the permit contents rather than the surrounding dashboard/navigation. Confirm the output with your browser's print preview before using it as a controlled record.
- Administrator Settings now includes a switch to show/hide the optional RAMS attachment section. The switch is stored server-side and does not delete any existing permit data.
- Issuers, Area Owners and Administrators can attach an operational RAMS PDF/scan and a Toolbox Talk PDF/photo to a permit. On supported phones, the file picker may offer the camera. Attachments are limited to 4 MB each to keep the demo responsive.
- Attachments are stored inside the permit record as data URLs. This is suitable for a small demonstration but is not the recommended long-term storage design for production; use protected file storage and retention/access policies before operational deployment.

Testing: Python source compilation and inline JavaScript syntax checks passed. A live Django/browser/phone workflow test could not be run in this environment because Django is not installed here. Please run `run.bat` and test with non-operational permits before deployment.


## Version 24 — Permit card printing

- **Print permit** now prints only the permit card (logo, QR code, details, checklists, RAMS, handover, issue and return signatures) on A4. The dashboard header, navigation, buttons, upload controls and demo footer are hidden.
- The "Full permit contents" section is expanded automatically for printing and restored afterwards, so PPE and precautions always appear on paper. Browser Ctrl+P gives the same result.
- Printing always uses light colours, and the page title becomes the permit number, so "Save as PDF" suggests a sensible file name.
- A "Printed on ... scan the QR code to confirm this permit is current" line is added at the foot of the printout.

Testing: rendered a sample hot works permit in headless Chromium and printed it to a 3-page A4 PDF; all pages showed only the permit. Not yet tested in Firefox/Safari or on a phone.

## Version 25 — Full RAMS template, Toolbox switch, one open permit per kind, light theme

- **Full RAMS template** (from the IDU RAMS Word template) on every permit form and permit record: 1 General information (client, contractor, competent person), 2 Job / contract details, 3 Site location, 4 People on site and team supervisor, 5 Subcontractors, 6 Frequency of supervision with Note II, 7 Details of work (a sequence of operations and hazards, b tools used and inspection, c emergency procedures, d services isolated, e hazardous materials, f lifting, g confined spaces, h pressure systems, i training, j waste, k risk report, l permits required), IV Risk assessment register with hazard guidance notes and automatic risk rating (L × S, colour-coded), V Approval taken from the digital sign-offs. Rows can be added or removed. It prints with the permit. RAMS saved on older versions still displays.
- **Administrator > Settings**: "Optional RAMS module" switches the whole RAMS section on or off; the new "Toolbox Talk capture" switch hides or shows the toolbox scan/upload section. Switching off never deletes saved data.
- **One open permit per kind**: a receiver cannot start or sign a new permit of a kind while their previous permit of that kind is not closed (or cancelled), and cannot start or sign any new permit while they have an overdue, un-returned permit. A prompt lists the pending permits with an Open button. Enforced on the server as well as in the page.
- **Stat tiles** (Overview): numbers now line up even when a label wraps onto two lines.
- **Light theme**: softer background, cleaner cards, shadows, tabs, tables and buttons. Dark mode is unchanged in character.
- The "Version v15 · Demo system running…" line was removed from the page footer.


## Version 26 — Method statement is a tick only

- The typed "Method statement / JSA reference" field is removed from the General Work, Excavation and Hot Works (projects) forms. Each form now has a required tick that the method statement / JSA is attached. Permits saved earlier keep and still show any reference already typed.


## Version 27 — Defaults

- The RAMS module and Toolbox Talk capture are now **off by default** on a new installation. The administrator switches them on in Settings. A choice already saved on an existing database is kept.

## Version 28 — Online deployment package

- Added `DEPLOY.md` (step-by-step Render guide), `render.yaml`, `build.sh`, `ptw/wsgi.py`, `permits/mailer.py` (email through Brevo's web API for free hosts) and new `requirements.txt` (gunicorn, whitenoise, PostgreSQL support).
- Production mode (`DJANGO_ENV=production`): secret key from environment, allowed hosts, secure cookies, HTTPS-aware links, static files served by WhiteNoise. PostgreSQL when `DATABASE_URL` is set. Local `run.bat` use is unchanged.
- `DEMO_MODE=1` shows a yellow "DEMO SYSTEM" bar; the footer "Reset demo data" link was removed.
- Tested with gunicorn and PostgreSQL 16: sign-up, sign-in, permit rules, parallel serial numbers, static files, secure cookie flags and the browser screens.


## Version 29 — Email errors are reported

- The Settings test-email button now shows the real reason when sending fails (for example an invalid Brevo key or unverified sender) instead of reporting success.
- Notification emails are sent in the background so a slow mail service cannot delay permit actions; failures are written to the server log.


## Version 30 — Detailed permit emails

- Notification emails now name the recipient and include the permit number, type, department/area, requester, date and time, a short work description and a link to sign in, with the subject starting "[Permit to Work]".


## Version 31/32 — Sign-in QR code

- Administrator > Settings > **Sign-in QR code**: one general QR code that opens the sign-in page. Print it as an A4 poster or a sheet of six stickers, or download it as a PNG image. It holds only the web address.


## Version 33 — Disabled buttons and eye icon

- New-permit buttons are now **disabled** (greyed out) for a receiver who already has an open permit of that kind, and all of them are disabled while the receiver has an overdue permit. A note under the buttons names the permit and has an Open button to go and return it.
- Every PIN/password field now has an **eye icon** (show/hide) instead of the word "Show".


## Version 34 — Permit drafts

- While a receiver fills in any permit form, it is saved automatically (a second after the last change, and when the page is hidden or closed) to the server and to the browser. After a browser crash, power cut or switching device, opening the same permit type restores the form, including site, department, area, ticks, team members and the RAMS section. A green bar shows when it was saved and offers "Discard draft". Saved drafts also appear under New permit with Continue and Delete. A draft is removed when the permit is sent. Attached files are not part of a draft. New database table: run migrations (Render does this on deploy).

## Version 35 — New look

- The menu stays on top, as before (a sidebar version was tried and reverted in version 36).
- **Dashboard (administrator Overview, issuer and owner Dashboard):** stat cards with trend chips and a mini chart, a 14-day "Permits raised" bar chart, a status donut, permit types with share bars, and departments with share bars. All figures come from the real permit data.
- **Styling:** pill buttons, larger rounded cards, softer shadows, light and dark themes.

## Version 37 — Floating top panel and open-permit layout

- **Top panel for every account** (administrator, receiver, issuer, area owner): a floating rounded bar with the logo, pill-shaped tabs in the centre, a notification bell with a count, an avatar chip with the person's name and role, Sign out, and a light/dark switch. Below it a "Welcome back" greeting with the date. On phones the bar wraps and the tabs scroll.
- **Open permit page:** on desktop the permit is split into a main column and a sticky side panel holding the status, QR code, sign-off progress (receiver, issuer, area owner) and all action buttons, so the buttons are always in view. On phones the panel comes first. Printing is unchanged.
- The administrator tab "Sites and departments" is now "Sites" so all seven tabs fit.
