# Plus One design site

This branch contains the full local Django prototype for the Plus One design site.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/` to view the site.

Main routes:

- `/discover/`
- `/create/`
- `/dashboard/`
- `/chat/<match_id>/`
