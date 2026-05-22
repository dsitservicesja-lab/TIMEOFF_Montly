# TIMEOFF_Montly

Simple Flask-based monthly time-off tracker with:
- 4-hour monthly allocation per user
- Branch-based supervisor approval/decline workflow
- Admin panel and monthly reports
- In-app notifications

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Default demo users

- `admin` (admin)
- `sup_north` (supervisor, North branch)
- `sup_south` (supervisor, South branch)
- `alice` (employee, North branch)
- `bob` (employee, South branch)

Use the login screen to choose a user.

## Tests

```bash
python -m unittest discover -s tests
```

## Deployment

See [`DEPLOY.md`](DEPLOY.md) for production deployment steps.