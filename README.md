# qwen-apply

![Qwen Open Weight AI](https://aplicar.ai/wp-content/uploads/2026/05/Qwen-the-open-weight-AI-models-1140x760.png)


AI-powered job application toolkit that scrapes job listings, scores them against your resume using an LLM, and generates ATS-optimized resumes, cover letters, and YC-style cold pitches tailored to each role.

## How It Works

1. **Job Discovery** - Scrapes job listings from multiple sources using keywords you define.
2. **Scoring** - Each job description is scored (0-10) by an LLM against your resume for fit.
3. **Resume Generation** - Jobs scoring above 7 get an ATS-optimized plain-text resume, an HTML-formatted resume, and a PDF.
4. **Cover Letters** - Generates tailored cover letters or short YC-style cold pitches.
5. **Dashboard** - A web UI for browsing, filtering, saving, and tracking applications.

All LLM calls go through an OpenAI-compatible API (Alibaba Cloud / Qwen models).

## Prerequisites

- Python 3.10+
- `wkhtmltopdf` (for HTML-to-PDF conversion)
- Playwright Chromium browser

## Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd qwen-apply

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Create a .env file with your API keys
cat > .env << 'EOF'
ALIBABA_API_KEY_US=your_api_key
ALIBABA_BASE_URL_US=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
ALIBABA_MODEL_US=qwen-plus
SERP_API_KEY=your_serpapi_key
EOF

# Copy the resume template and fill in your own details
cp resume.txt.example resume.txt
```

Then open `resume.txt` in your editor and replace the placeholder content with your own resume. Include as much detail as possible — every role, skill, project, certification, and accomplishment. The more comprehensive your resume, the better the LLM can match you to jobs and generate tailored applications.

```bash
# Copy the job description template
cp job.txt.example job.txt
```

Then paste the complete job description into `job.txt`. Include the full posting — title, company, responsibilities, requirements, and any other details. This file is used by `apply`, `resume`, `cover`, `yc`, and `score` commands to generate tailored output for a specific role.

## Configuration

Place your source files in the project root:

| File | Purpose |
|------|---------|
| `resume.txt` | Your base resume in plain text (copy from `resume.txt.example`) |
| `resume.htm` | HTML template for formatted resume output |
| `cover.htm` | HTML template for formatted cover letter output |
| `keywords.txt` | Search keywords, one per line (e.g. "AI Engineer", "ML Platform") |
| `job.txt` | A specific job description — copy from `job.txt.example` and paste the full posting |

## Usage

### CLI Commands

The CLI is built with [Typer](https://typer.tiangolo.com/). Run commands via `python app.py <command>`.

```bash
# Full pipeline: scrape jobs, score, and generate resumes for matches
python app.py

# Generate an ATS-optimized resume + cover letter for the job in job.txt
python app.py apply

# Generate only a resume for the job in job.txt
python app.py resume

# Generate only a cover letter for the job in job.txt
python app.py cover

# Generate a YC-style cold pitch for the job in job.txt
python app.py yc

# Score the job in job.txt against your resume (0-10)
python app.py score

# Extract salary ranges from scraped job descriptions
python app.py salary

# Test the LLM connection
python app.py test
```

### Web Dashboard

```bash
python server.py
```

Opens a job board at `http://localhost:8000` with:
- Filter by match score, source, and remote-only
- Sort by date, score, or title
- Save, apply, and archive actions per job
- Pagination
- Links to generated resumes

## Output

Generated files are written to the `./out/` directory:

```
out/
  resume_<uuid>.txt   # ATS-optimized plain text resume
  resume_<uuid>.htm   # HTML-formatted resume
  resume_<uuid>.pdf   # PDF resume
  cover_<uuid>.txt    # Cover letter (plain text)
  cover_<uuid>.htm    # Cover letter (HTML)
  cover_<uuid>.pdf    # Cover letter (PDF)
  yc_<uuid>.txt       # YC cold pitch
```

## Project Structure

```
app.py           # Core logic: scraping, scoring, generation, CLI
server.py        # FastAPI web dashboard
db.py            # SQLite database helper (aiosqlite)
mcp.py           # MCP server (experimental)
test.py          # LLM connection test
resume.txt       # Your base resume
keywords.txt     # Job search keywords
job.txt           # Target job description (ad-hoc mode)
resume.htm       # HTML resume template
cover.htm        # HTML cover letter template
out/             # Generated output files
```

## Tech Stack

- **LLM**: Alibaba Cloud Qwen models via OpenAI-compatible API
- **Scraping**: Playwright (async, headless Chromium)
- **Search**: SerpAPI (Google Search for Workday job listings)
- **Database**: SQLite via aiosqlite (job storage, scoring state, application tracking)
- **Web UI**: FastAPI + Jinja2
- **PDF**: wkhtmltopdf
- **CLI**: Typer

## License

Private use.
