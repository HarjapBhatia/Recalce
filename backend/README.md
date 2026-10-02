# Recalce backend

The backend contains the FastAPI application, Background tasks, database
migrations, ML pipeline, tests, and integration scripts.

Run backend commands from this directory so the existing `app.*` and `ml.*`
package imports resolve consistently:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\python.exe -m pytest tests -v
```
