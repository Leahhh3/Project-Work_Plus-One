# Plus One

Plus One is a Django-native campus activity matcher. Students get a temporary anonymous identity, create time-limited activity posts, swipe on nearby plans, match with interested users, and enter a five-minute anonymous chat before deciding to meet.

## Product Capabilities

- Anonymous session identities with no registration or password.
- Time-limited campus activity cards created from structured fields or casual text.
- Discovery filters, swipe actions, instant matches, and five-minute private chats with lightweight polling.
- Meet handoff after both people agree, with place, time, and a short safety reminder.
- AI-assisted post parsing, icebreakers, and safety moderation with deterministic fallback.
- Dashboard for active, matched, expired, and cancelled plans.

## Main Pages

- `/` and `/discover/` discovery queue with filters, swipe actions, and match modal.
- `/session/` session status, visibility rules, and fresh identity reset.
- `/create/` LLM-assisted post creation with live card preview.
- `/posts/<id>/edit/` owner-only post editing and cancellation.
- `/dashboard/` dashboard for active, matched, expired, and cancelled posts.
- `/chat/<match_id>/` five-minute anonymous chat with near-real-time message refresh and meet handoff.

## Project Structure

- `config/` contains the Django settings, URL routing, and deployment entry points.
- `plusone/models.py` defines the main data model: temporary profiles, campus locations, activity posts, swipes, matches, chat messages, and LLM logs.
- `plusone/views.py` handles the page requests and keeps the browser flow together.
- `plusone/templates/plusone/` contains the server-rendered pages for Discover, Create, Chat, Dashboard, and supporting views.
- `plusone/static/plusone/` contains the CSS and JavaScript used by the interface.
- `plusone/services/` contains the core state-changing logic, including anonymous identity reset, post saving, matching, chat agreement, and expiry.
- `plusone/selectors.py` keeps larger database queries for Discover and Dashboard in one place.
- `plusone/presenters.py` prepares form previews and chat payloads for the templates.
- `plusone/ai_services/` contains the provider client, parsing, moderation, icebreaker generation, logging, and rule-based fallbacks.
- `plusone/management/commands/` includes helper commands such as demo data seeding, record expiry, cleanup, and LLM evaluation.
- `docs/` contains supporting documentation, including evaluation notes and the final presentation PDF.
- `DEPLOY_RENDER.md`, `render.yaml`, and `build.sh` describe the hosted Render deployment.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

No registration is required. The first visit creates a temporary anonymous session identity and opens Discover. The session remains available in that browser until cookies/session data are cleared or the user starts fresh.

## AI Behavior

If `DEEPSEEK_API_KEY` is set, the app uses DeepSeek through the OpenAI-compatible API for:

- natural-language activity parsing,
- icebreaker generation,
- safety moderation.

Set the key in your shell before running Django:

```bash
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export PLUSONE_LLM_MODEL="deepseek-v4-flash"
```

Do not commit API keys. If you prefer a local `.env` file, keep it untracked and load it before starting Django:

```bash
set -a
source .env
set +a
```

If `DEEPSEEK_API_KEY` is not set but `OPENAI_API_KEY` is set, the app uses OpenAI. If no API key is set, the app automatically uses deterministic rule-based fallback. All AI and fallback calls are stored in `LLMLog`.

Run the baseline evaluation:

```bash
.venv/bin/python manage.py evaluate_ai
```

## Development Assistance and Quality Control

We used language-model tools during development mainly for debugging help, wording improvements, and interface refinement. The team reviewed the suggested changes before using them, and the project behavior was checked through Django tests, manual end-to-end flows, and the provider benchmark in `docs/ai_evaluation.md`. The application also keeps deterministic fallbacks for parsing, moderation, and icebreakers so the main product flow can still run without external API access.

## Hosted Deployment

To run one hosted instance that keeps `DEEPSEEK_API_KEY` on the server and lets other people use the app through a public URL, follow [DEPLOY_RENDER.md](DEPLOY_RENDER.md).

## Core Flow

1. Open the site root and land in Discover with a generated anonymous session.
2. Create a post from casual text.
3. Review the AI-generated structured card and live preview.
4. Publish.
5. Use another browser session, or choose **Start fresh identity** on Session, to act as a separate temporary identity.
6. Swipe interested.
7. Confirm the match modal.
8. Enter the five-minute anonymous chat.
9. Send a message and agree to meet.
10. When both people agree, review the meet handoff and safety reminder.
11. View My Plus Ones dashboard.

## Tests

```bash
.venv/bin/python manage.py test
```

Current test coverage includes anonymous session identity creation, post creation, identity reset, unsafe post blocking, editing/cancelling posts, discovery filtering rules, swipe/match behavior, chat permissions, chat expiry, moderation logging, and dashboard status separation.
