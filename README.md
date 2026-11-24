# CivicCare – Flask + SQLite

## Setup
1. Install Python 3.
2. In the project directory run: `python -m venv venv`
3. Activate it: Windows PowerShell `venv\Scripts\Activate.ps1` (or CMD `venv\Scripts\activate.bat`).
4. Install: `pip install -r requirements.txt`
5. Run: `python app.py` and open http://127.0.0.1:5000

## Demo accounts
- Admin: `admin@civiccare.local` / `Admin@123`
- Worker: `worker@civiccare.local` / `Worker@123`

Change these demo credentials and SECRET_KEY before deployment. Citizen accounts register through the site.

Features: citizen registration/login, complaint creation and editing, duplicate hints, image upload, priority suggestion, admin status/department/worker management, admin complaint corrections, separate resolved list (no location shown), worker updates and resolution images, feedback, and issue map (coordinate-bearing active reports).
