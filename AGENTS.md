# Contributor guidance

## Application overview

This repository is a deliberately small Flask task manager. It uses SQLite, Flask sessions with Werkzeug password hashes, and a static vanilla JavaScript frontend. There is no build step or ORM.

## Key files

- `app.py`: database setup, account authentication, session/CSRF checks, database helpers, HTML routes, and REST endpoints.
- `templates/index.html`: page structure and frontend asset loading.
- `static/app.js`: Fetch API requests and DOM rendering.
- `static/style.css`: responsive visual styling.

## Development rules

- Keep dependencies minimal; do not introduce a frontend framework or ORM unless explicitly requested.
- Use parameterized SQLite queries only.
- Keep API responses JSON and preserve the existing REST routes.
- Scope every task query and mutation to the authenticated user's ID.
- Validate task titles and statuses in the backend, and keep import validation atomic.
- Store only password hashes; never log or persist plaintext passwords.
- Retain CSRF checks for every state-changing form and API request.
- Escape task content before injecting it into HTML in the frontend.
- Retain the supported statuses exactly: `Todo`, `In Progress`, and `Done`.
- Avoid adding features outside the single-user task-management scope without approval.

## Verification

Run the app locally with:

```bash
python3 app.py
```

For backend changes, verify registration/login/logout, cross-account task isolation, CRUD, invalid-status handling, password changes, and import/export.
