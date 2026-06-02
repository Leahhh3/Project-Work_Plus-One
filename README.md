# Plus One

Plus One is a Django-native campus activity matcher. Students create temporary activity posts, swipe on nearby plans, match with interested users, and enter a five-minute anonymous chat before deciding to meet.

## Requirements Covered

- Local Django webpage with multiple pages and interactions.
- SQLite database driven by user input: posts, swipes, matches, chats, and AI logs.
- AI integration for post parsing, icebreakers, and safety moderation.
- No npm, React, ReAct, Celery, or extra frontend/server stack.

## Main Pages

- `/` and `/profile/setup/` campus avatar/profile setup.
- `/discover/` discovery queue with filters, swipe actions, and match modal.
- `/create/` LLM-assisted post creation with live card preview.
- `/posts/<id>/edit/` owner-only post editing and cancellation.
- `/dashboard/` dashboard for active, matched, expired, and cancelled posts.
- `/chat/<match_id>/` five-minute anonymous chat.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo --reset
.venv/bin/python manage.py runserver
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo --reset
.\.venv\Scripts\python.exe manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Demo users:

```text
demo_alex / plusone123
demo_blair / plusone123
```

The app includes one-click demo user switching in the top bar.

## AI Behavior

If `OPENAI_API_KEY` is set, the app uses OpenAI for:

- natural-language activity parsing,
- icebreaker generation,
- safety moderation.

If no API key is set, the app automatically uses a deterministic rule-based fallback. All AI and fallback calls are stored in `LLMLog`.

Run the baseline evaluation:

```bash
.venv/bin/python manage.py evaluate_ai
```

## Demo Flow

1. Open the site root and set or review the campus avatar profile.
2. Continue to Discover.
3. Create a post from casual text.
4. Review the AI-generated structured card and live preview.
5. Publish.
6. Switch demo user.
7. Swipe interested.
8. Confirm the match modal.
9. Enter the five-minute anonymous chat.
10. Send a message and agree to meet.
11. View My Plus Ones dashboard.

## Tests

```bash
.venv/bin/python manage.py test
```

Current test coverage includes post creation, profile setup, unsafe post blocking, editing/cancelling posts, discovery filtering rules, swipe/match behavior, chat permissions, chat expiry, moderation logging, and dashboard status separation.
