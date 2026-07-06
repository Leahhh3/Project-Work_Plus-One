# Running Plus One for Review

## 1. Create the environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 2. Configure the DeepSeek API key

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and replace `replace_with_your_deepseek_api_key` with the real key:

```bash
DEEPSEEK_API_KEY=replace_with_your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
PLUSONE_LLM_MODEL=deepseek-v4-flash
```

Load the variables before starting Django:

```bash
set -a
source .env
set +a
```

Do not commit or upload `.env`.

## 3. Prepare the local database

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
```

## 4. Start the app

```bash
.venv/bin/python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

## 5. Optional checks

Run the test suite:

```bash
.venv/bin/python manage.py test
```

Run the fallback AI evaluation:

```bash
.venv/bin/python manage.py evaluate_ai
```
