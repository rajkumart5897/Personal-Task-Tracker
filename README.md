# Task Manager

A local task management app built with Flask, SQLite, and vanilla JavaScript. Each account has its own private task list.

## Features

- Create tasks with a title and optional description
- View saved tasks
- Edit task details
- Set each task to `Todo`, `In Progress`, or `Done`
- Delete tasks
- Register, log in, and log out using locally stored password hashes
- Change passwords and import/export task data as JSON
- Persist account and task data locally in SQLite

## Requirements

- Python 3.10 or newer
- Flask

Install Flask if it is not already available:

```bash
python3 -m pip install flask
```

## Run locally

```bash
python3 app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser.

The application creates `database.db` automatically on its first run.

For stable login sessions across server restarts, set a secret key before starting the app:

```bash
export TASK_MANAGER_SECRET_KEY="replace-with-a-long-random-value"
python3 app.py
```

## Project structure

```text
.
├── app.py                 # Flask app, authentication, and JSON task API
├── database.db            # Local SQLite data (created at runtime)
├── templates/
│   ├── index.html         # Authenticated task manager
│   ├── login.html         # Login page
│   ├── register.html      # Registration page
│   ├── settings.html      # Password and import/export settings
│   ├── privacy.html       # Privacy policy
│   └── terms.html         # Terms and conditions
└── static/
    ├── app.js             # Browser-side API calls and rendering
    └── style.css          # UI styles
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/tasks` | List the logged-in user's tasks |
| `POST` | `/api/tasks` | Create a task |
| `PUT` | `/api/tasks/<id>` | Update one of the user's tasks |
| `DELETE` | `/api/tasks/<id>` | Delete one of the user's tasks |
| `GET` | `/api/tasks/export` | Download the user's tasks as `tasks.json` |
| `POST` | `/api/tasks/import` | Import tasks from a JSON upload |

For create and update requests, send JSON with `title`, `description`, and (for updates) a valid `status`: `Todo`, `In Progress`, or `Done`. Authenticated state-changing API requests also require the CSRF token rendered by the application.
