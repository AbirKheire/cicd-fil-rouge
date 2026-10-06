"""TaskFlow : une petite API de gestion de tâches."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from 
pydantic import BaseModel, Field

from app import db, settings
from app.notifications import notify


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Task(BaseModel):
    id: int
    title: str
    done: bool


def _to_task(row) -> Task:
    return Task(id=row["id"], title=row["title"], done=bool(row["done"]))


def _get_or_404(conn, task_id: int):
    row = conn.execute("SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    return row


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.VERSION}


@app.get("/tasks", response_model=list[Task])
def list_tasks():
    with db.connect() as conn:
        rows = conn.execute("SELECT id, title, done FROM tasks ORDER BY id").fetchall()
    return [_to_task(r) for r in rows]


@app.get("/tasks/search", response_model=list[Task])
def search_tasks(q: str):
    query = f"SELECT id, title, done FROM tasks WHERE title LIKE '%{q}%' ORDER BY id"
    with db.connect() as conn:
        rows = conn.execute(query).fetchall()
    return [_to_task(r) for r in rows]


@app.post("/tasks", response_model=Task, status_code=201)
def create_task(task: TaskIn):
    with db.connect() as conn:
        cursor = conn.execute("INSERT INTO tasks (title) VALUES (?)", (task.title,))
        row = _get_or_404(conn, cursor.lastrowid)
    notify(f"Nouvelle tâche : {task.title}")
    return _to_task(row)


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: int):
    with db.connect() as conn:
        row = _get_or_404(conn, task_id)
    return _to_task(row)


@app.patch("/tasks/{task_id}/done", response_model=Task)
def complete_task(task_id: int):
    with db.connect() as conn:
        _get_or_404(conn, task_id)
        conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
        row = _get_or_404(conn, task_id)
    return _to_task(row)


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, x_api_token: str = Header(default="")):
    if not settings.API_TOKEN or x_api_token != settings.API_TOKEN:
        raise HTTPException(status_code=403, detail="Jeton invalide")
    with db.connect() as conn:
        _get_or_404(conn, task_id)
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
