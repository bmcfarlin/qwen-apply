import os
import math
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import db
from datetime import datetime
import uvicorn
from contextlib import asynccontextmanager

# 1. Ensure the 'out' directory exists for resumes and 'templates' for HTML
os.makedirs("out", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# 2. Define the HTML Template (Jinja2 syntax)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Board</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background-color: #f4f7f6; color: #333; }
        .container { max-width: 100%; width: 98%; margin: 0 auto; background: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        h1 { text-align: center; color: #2c3e50; margin-top: 0; }
        
        /* Filters Form */
        .filters { display: flex; gap: 20px; margin-bottom: 30px; align-items: flex-end; flex-wrap: wrap; background: #f8f9fa; padding: 20px; border-radius: 8px; border: 1px solid #e9ecef; }
        .filters label { font-weight: 600; display: flex; flex-direction: column; font-size: 0.9em; color: #495057; }
        .filters input, .filters select { padding: 8px 12px; border-radius: 6px; border: 1px solid #ced4da; margin-top: 6px; font-size: 1em; }
        .filters button { padding: 9px 20px; background-color: #0d6efd; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; transition: background 0.2s; }
        .filters button:hover { background-color: #0b5ed7; }
        .checkbox-label { align-items: center; flex-direction: row; gap: 8px; margin-top: 20px; }
        .checkbox-label input { width: 18px; height: 18px; cursor: pointer; margin: 0; }
        
        /* Table Styling */
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 14px 16px; border-bottom: 1px solid #dee2e6; text-align: left; }
        th { background-color: #2c3e50; color: white; position: sticky; top: 0; font-weight: 600; }
        tr:hover { background-color: #f1f3f5; }
        a { color: #0d6efd; text-decoration: none; font-weight: 500; }
        a:hover { text-decoration: underline; }
        
        /* Specific Elements */
        .job-id { font-family: monospace; font-size: 0.85em; color: #6c757d; white-space: nowrap; }
        .resume-link { background-color: #198754; color: white !important; padding: 6px 12px; border-radius: 5px; font-size: 0.85em; font-weight: normal; display: inline-block; }
        .resume-link:hover { background-color: #157347; text-decoration: none !important; color: white !important; }
        .no-resume { color: #adb5bd; font-style: italic; }
        
        /* Score Colors */
        .score-high { color: #198754; font-weight: bold; }
        .score-med { color: #fd7e14; font-weight: bold; }
        .score-low { color: #dc3545; font-weight: bold; }
        
        /* Action Buttons */
        .actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .btn-action { padding: 5px 10px; border-radius: 4px; font-size: 0.8em; text-decoration: none !important; font-weight: 500; cursor: pointer; border: 1px solid transparent; white-space: nowrap; }
        .btn-save { background-color: #ffc107; color: #000 !important; }
        .btn-save.saved { background-color: #fff3cd; color: #856404 !important; border-color: #ffe69c; }
        .btn-apply { background-color: #0dcaf0; color: #000 !important; }
        .btn-apply.applied { background-color: #cff4fc; color: #055160 !important; border-color: #b6effb; }
        .btn-archive { background-color: #6c757d; color: white !important; }
        .btn-archive.archived { background-color: #f8d7da; color: #842029 !important; border-color: #f5c2c7; }
        .btn-action:hover { opacity: 0.8; text-decoration: none !important; }

        /* Pagination */
        .pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin-top: 30px; flex-wrap: wrap; }
        .pagination a, .pagination span { padding: 8px 12px; border: 1px solid #dee2e6; border-radius: 4px; text-decoration: none; color: #0d6efd; }
        .pagination a:hover { background-color: #e9ecef; }
        .pagination .current { background-color: #0d6efd; color: white; border-color: #0d6efd; font-weight: bold; }
        .pagination .disabled { color: #adb5bd; pointer-events: none; background-color: #f8f9fa; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Job Application Board</h1>
        
        <form method="get" action="/" class="filters">
            <label>Min Score
                <input type="number" name="min_score" value="{{ min_score }}" min="0" max="10">
            </label>
            <label>Max Score
                <input type="number" name="max_score" value="{{ max_score }}" min="0" max="10">
            </label>
            <label>Source
                <input type="text" name="source" value="{{ source }}" placeholder="e.g., bwtt, workday">
            </label>
            <label>Sort By
                <select name="sort_by">
                    <option value="dtm" {% if sort_by == 'dtm' %}selected{% endif %}>Date Published</option>
                    <option value="score" {% if sort_by == 'score' %}selected{% endif %}>Match Score</option>
                    <option value="title" {% if sort_by == 'title' %}selected{% endif %}>Job Title</option>
                </select>
            </label>
            <label>Order
                <select name="sort_order">
                    <option value="desc" {% if sort_order == 'desc' %}selected{% endif %}>Descending</option>
                    <option value="asc" {% if sort_order == 'asc' %}selected{% endif %}>Ascending</option>
                </select>
            </label>
            <label class="checkbox-label">
                <input type="checkbox" name="remote" value="true" {% if remote %}checked{% endif %}>
                Remote Only
            </label>
            <label class="checkbox-label">
                <input type="checkbox" name="saved" value="true" {% if saved %}checked{% endif %}>
                Saved Only
            </label>
            <label class="checkbox-label">
                <input type="checkbox" name="applied" value="true" {% if applied %}checked{% endif %}>
                Applied Only
            </label>
            <label class="checkbox-label">
                <input type="checkbox" name="include_archived" value="true" {% if include_archived %}checked{% endif %}>
                Include Archived
            </label>
            <button type="submit">Apply Filters</button>
        </form>
        
        <table>
            <thead>
                <tr>
                    <th>Job ID</th>
                    <th>Job Title</th>
                    <th>Source</th>
                    <th>Date</th>
                    <th>Score</th>
                    <th>Resume</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for job in jobs %}
                <tr>
                    <td class="job-id">{{ job.job_id }}</td>
                    <td><a href="{{ job.link }}" target="_blank">{{ job.title }}</a></td>
                    <td>{{ job.source }}</td>
                    <td>{{ job.dtm_str }}</td>
                    <td>
                        {% if job.score != 'N/A' %}
                            <span class="{% if job.score >= 8 %}score-high{% elif job.score >= 5 %}score-med{% else %}score-low{% endif %}">
                                {{ job.score }} / 10
                            </span>
                        {% else %}
                            <span class="no-resume">Pending</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if job.resume %}
                            <a href="/out/{{ job.resume }}" target="_blank" class="resume-link">View Resume</a>
                        {% else %}
                            <span class="no-resume">Not Generated</span>
                        {% endif %}
                    </td>
                    <td class="actions">
                        {% set qs = request.url.query %}
                        <a href="/save/{{ job.job_id }}{% if qs %}?{{ qs }}{% endif %}" class="btn-action btn-save {% if job.saved %}saved{% endif %}">
                            {% if job.saved %}★ Saved{% else %}☆ Save{% endif %}
                        </a>
                        <a href="/apply/{{ job.job_id }}{% if qs %}?{{ qs }}{% endif %}" class="btn-action btn-apply {% if job.applied %}applied{% endif %}">
                            {% if job.applied %}✓ Applied{% else %}Apply{% endif %}
                        </a>
                        <a href="/archive/{{ job.job_id }}{% if qs %}?{{ qs }}{% endif %}" class="btn-action btn-archive {% if job.archived %}archived{% endif %}">
                            {% if job.archived %}Archived{% else %}Archive{% endif %}
                        </a>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="7" style="text-align: center; padding: 30px; color: #6c757d;">No jobs found matching your criteria.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        {% if total_pages > 1 %}
        <div class="pagination">
            <a href="{{ request.url.include_query_params(page=1) }}" class="{% if page == 1 %}disabled{% endif %}">« First</a>
            <a href="{{ request.url.include_query_params(page=page-1) }}" class="{% if page == 1 %}disabled{% endif %}">‹ Prev</a>
            
            {% for p in range(1, total_pages + 1) %}
                {% if p == page %}
                    <span class="current">{{ p }}</span>
                {% elif p <= 3 or p > total_pages - 3 or (p >= page - 2 and p <= page + 2) %}
                    <a href="{{ request.url.include_query_params(page=p) }}">{{ p }}</a>
                {% elif p == 4 or p == total_pages - 3 %}
                    <span>...</span>
                {% endif %}
            {% endfor %}

            <a href="{{ request.url.include_query_params(page=page+1) }}" class="{% if page == total_pages %}disabled{% endif %}">Next ›</a>
            <a href="{{ request.url.include_query_params(page=total_pages) }}" class="{% if page == total_pages %}disabled{% endif %}">Last »</a>
        </div>
        <p style="text-align: center; color: #6c757d; font-size: 0.9em;">
            Showing {{ (page - 1) * page_size + 1 }} to {{ end_item }} of {{ total_count }} jobs
        </p>
        {% endif %}
    </div>
</body>
</html>
"""

# Write the template to the templates directory
with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write(HTML_TEMPLATE)

templates = Jinja2Templates(directory="templates")

# 3. FastAPI App Setup
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.get_db()
    yield
    await db.close()

app = FastAPI(lifespan=lifespan)

# Mount the 'out' directory so resume files can be accessed via URL
app.mount("/out", StaticFiles(directory="out", html=False), name="out")

@app.get("/", response_class=HTMLResponse)
async def read_jobs(
    request: Request,
    min_score: int = Query(0, ge=0, le=10),
    max_score: int = Query(10, ge=0, le=10),
    sort_by: str = Query("dtm", pattern="^(dtm|score|title)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    source: str = Query(""),
    remote: bool = Query(False),
    saved: bool = Query(False),
    applied: bool = Query(False),
    include_archived: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    filters = {}

    if min_score > 0 or max_score < 10:
        filters["score"] = {"$gte": min_score, "$lte": max_score}

    if source:
        filters["source"] = source

    if remote:
        filters["description"] = {"$regex": r"\bremote\b", "$options": "i"}

    if saved:
        filters["saved"] = True

    if applied:
        filters["applied"] = True

    if not include_archived:
        filters["archived"] = {"$ne": True}

    # Get total count for pagination
    total_count = await db.count_jobs(filters)
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

    # Adjust page if it's out of bounds
    if page > total_pages:
        page = total_pages

    # Fetch jobs from SQLite
    jobs = await db.find_jobs(
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=(page - 1) * page_size,
        limit=page_size,
    )

    for job in jobs:
        # Format datetime safely
        dtm = job.get("dtm")
        if isinstance(dtm, datetime):
            job["dtm_str"] = dtm.strftime("%Y-%m-%d")
        else:
            job["dtm_str"] = "N/A"

        # Format score safely
        score = job.get("score")
        if isinstance(score, (int, float)):
            job["score"] = int(score)
        else:
            job["score"] = "N/A"

        # Set defaults for missing fields to prevent template errors
        job.setdefault("link", "#")
        job.setdefault("title", "No Title")
        job.setdefault("source", "N/A")
        job.setdefault("resume", None)
        job.setdefault("saved", False)
        job.setdefault("applied", False)
        job.setdefault("archived", False)

    end_item = min(page * page_size, total_count)

    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "jobs": jobs,
            "min_score": min_score,
            "max_score": max_score,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "source": source,
            "remote": remote,
            "saved": saved,
            "applied": applied,
            "include_archived": include_archived,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_count": total_count,
            "end_item": end_item
        }
    )

@app.get("/save/{job_id}")
async def save_job(job_id: str, request: Request):
    job = await db.find_one(job_id)
    if job:
        new_status = not job.get("saved", False)
        await db.update_job(job_id, {"saved": new_status})

    qs = request.url.query
    redirect_url = f"/?{qs}" if qs else "/"
    return RedirectResponse(url=redirect_url, status_code=303)

@app.get("/apply/{job_id}")
async def apply_job(job_id: str, request: Request):
    job = await db.find_one(job_id)
    if job:
        new_status = not job.get("applied", False)
        await db.update_job(job_id, {"applied": new_status})

    qs = request.url.query
    redirect_url = f"/?{qs}" if qs else "/"
    return RedirectResponse(url=redirect_url, status_code=303)

@app.get("/archive/{job_id}")
async def archive_job(job_id: str, request: Request):
    job = await db.find_one(job_id)
    if job:
        new_status = not job.get("archived", False)
        await db.update_job(job_id, {"archived": new_status})

    qs = request.url.query
    redirect_url = f"/?{qs}" if qs else "/"
    return RedirectResponse(url=redirect_url, status_code=303)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)