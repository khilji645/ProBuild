# ProBuild Engineering — Updated App

## What changed in this update

**1. Public marketing website (no login):**
- `/` Home, `/about`, `/services`, `/portfolio`, `/contact`
- Portfolio only shows projects a manager/admin has explicitly marked "Show on public portfolio" when adding/editing a project — budgets and client details are never exposed publicly.
- The contact form saves every submission to a new `Lead` database table AND attempts to email it to you via SMTP (if configured) — it never blocks on the email step.

**2. Role-based internal system (login required), four roles:**
| Role | View everything (incl. financials) | Add / Edit | Delete | Manage users |
|---|---|---|---|---|
| **Admin** | ✅ | ✅ | ✅ | ✅ |
| **Manager** | ✅ | ✅ | ✅ | ❌ |
| **Data Entry Operator** | ✅ | ✅ | ❌ | ❌ |
| **Viewer** | ✅ | ❌ | ❌ | ❌ |

This is enforced at the route level (`app.py`), not just hidden buttons — so even a viewer typing the delete URL directly gets blocked.

**3. Leads inbox** — `/leads`, visible to Admin/Manager, to triage public contact-form submissions.

**4. Production-ready DB config** — reads `DATABASE_URL` from the environment (Postgres in production), falls back to local SQLite for dev.

## ⚠️ Important — templates I didn't have

Only 19 of your templates were uploaded to this conversation. These referenced templates **still exist in your real project** but I couldn't apply the "hide buttons from Viewer" styling to them since I never saw their code:

`projects.html`, `tasks.html`, `salaries.html`, `suppliers.html`, `users.html`, `project_detail.html`, `edit_project.html`, `edit_client.html`, `edit_employee.html`, `edit_expense.html`, `edit_equipment.html`, `reports.html`, `profile.html`, `settings.html`

**The backend already blocks the actions correctly regardless** — a Viewer cannot actually add/edit/delete even on these pages. It's purely cosmetic: their Add/Edit/Delete buttons will still be visible until you add this one-line guard around them:

```jinja
{% if current_user.role != 'viewer' %}
  <a href="...">Add / Edit</a>
{% endif %}

{% if current_user.role in ['admin', 'manager'] %}
  <a href="...">Delete</a>
{% endif %}
```

Send me any of those files and I'll finish them the same way.

## Local setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then edit SECRET_KEY, MAIL_* as needed
python app.py
```
Visit `http://127.0.0.1:5000` — public site is now the homepage. Staff log in via "Staff Login" (top right) with `admin` / `admin123`, then create Manager/Data Entry/Viewer accounts under **User Management → Add User**.

## Deploying to Vercel with a persistent database

SQLite will NOT persist on Vercel (serverless filesystem resets between requests). You need external Postgres:

1. **Create a free Postgres database** — easiest options: [neon.tech](https://neon.tech) or [supabase.com](https://supabase.com). Copy the connection string (starts with `postgresql://` or `postgres://`).
2. **Push this project to a GitHub repo.**
3. **Import the repo into Vercel** (vercel.com → New Project).
4. **Set environment variables** in Vercel Project Settings → Environment Variables:
   - `DATABASE_URL` = your Postgres connection string
   - `SECRET_KEY` = a long random string
   - `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_TO` (optional, for lead email notifications)
5. **Deploy.** On first request, `init_db()` runs automatically and creates all tables + the default `admin`/`admin123` account in your Postgres database — **change that password immediately** after first login.
6. **File uploads**: the `Document` model stores a `file_path` — if you use that feature, point it at S3/Cloudflare R2 rather than local disk, since Vercel's filesystem is also ephemeral for file writes.

### A more honest alternative to Vercel
Vercel is built for short-lived serverless functions, not long-running stateful apps. For an internal company system like this — sessions, file uploads, background-friendly — **Railway, Render, or Fly.io** will get you persistent SQLite/Postgres and file storage with far less friction, typically for a similar or lower cost. Worth a look before you commit to the Vercel path.

## Files in this package
- `app.py` — full backend
- `templates/` — all pages, including new public site templates
- `vercel.json` + `api/index.py` — Vercel serverless entrypoint
- `requirements.txt` — pinned dependencies
- `.env.example` — copy to `.env` for local dev / reference for Vercel env vars
