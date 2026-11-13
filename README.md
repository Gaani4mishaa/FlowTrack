# FlowTrack

FlowTrack is a Django web app for reporting drainage problems and following their status. A resident can submit an issue with an area, optional coordinates, a photo and a description, then review the report history from their account.

## Current features

- Resident registration, sign-in and dashboard
- Drainage reports for blocked drains, flooding, damaged culverts and related issues
- County and area details, optional browser location and photo evidence
- Input checks for issue details, coordinates and image uploads
- Report history and status display
- Edit or delete a report while it is still marked **Submitted**
- Organization manager queue for explicitly assigned reports, priority updates and starting review
- Manager assignment of an under-review report to an active engineer in the same organization
- Engineer work-order queue with `Assigned`, `In Progress` and `Resolved` steps
- Required resolution note before an engineer can complete a work order
- Django admin for managing users, organizations and reports

Reports are assigned to organizations manually by an administrator in Django admin. Organization managers can see only reports linked to their active organization and assign reviewed reports to active engineers from that organization. Engineers can see only work orders assigned to their own account.

To route a report, a staff administrator opens the report in Django admin and selects its organization. Organization manager accounts must be linked to an active organization before they can use the review queue. There is no automatic county-based routing.

An organization manager assigns an engineer from the review queue after marking a report **Under Review**. The engineer can start work and later mark the work order resolved with a summary. One work order is supported per report; reassignment, before/after maintenance photos, a full audit history and work-order notifications are not implemented yet.

The forecasting, sensor, mapping and analytics ideas in the project proposal are not implemented yet. The current prototype records and tracks reports; it does not predict floods or dispatch maintenance crews.

## Requirements

- Python 3.11 or later
- PostgreSQL
- The Python packages listed in `requirements.txt`

## Run locally on Windows

Open PowerShell in the project folder and create an environment:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root. This file is ignored by Git. Set the values for your local PostgreSQL database and a development secret key:

```dotenv
SECRET_KEY=replace-with-a-local-secret-key
DB_NAME=flowtrack
DB_USER=postgres
DB_PASSWORD=your-local-database-password
DB_HOST=localhost
DB_PORT=5432
```

Create the `flowtrack` database in PostgreSQL, then apply the migrations and start Django:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The Django admin is at <http://127.0.0.1:8000/admin/>.

If PowerShell does not allow activating the environment, run the project commands through `venv\Scripts\python.exe`, for example:

```powershell
.\venv\Scripts\python.exe manage.py migrate
```

## Tests

Run the Django test suite with:

```powershell
python manage.py test
```

The report workflow tests cover submission, field validation, ownership, edits and deletion rules.

## Project layout

- `accounts/` - resident accounts and organizations
- `reports/` - drainage report data, validation and resident report workflow
- `core/` - home page, authentication pages and resident dashboard
- `templates/` - Django templates
- `static/` - styles and the homepage flood photograph
- `config/` - Django settings and URL configuration

User-uploaded report photos are stored under `media/` during local development. Keep `.env`, database files and uploaded user data out of source control. The development server and current settings are for local project work, not production deployment.
