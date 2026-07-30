import sys
import os
import asyncio
from loguru import logger
import base64
import threading
import time
import json
from dotenv import load_dotenv
import re
from pydantic import BaseModel, Field
import signal
from openai import AsyncOpenAI
from serpapi import GoogleSearch
from playwright.async_api import async_playwright
import uuid
import db
from urllib.parse import urlencode, quote, quote_plus
from datetime import datetime, date
import typer
from typing_extensions import Annotated
from pathlib import Path
import subprocess
import shutil

__version__ = "0.1.1"

load_dotenv()

logger.remove()

_filter={"":"DEBUG"}

logger.add(
    sink=sys.stdout, 
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
    level="DEBUG", 
    colorize=True,
    filter=_filter
)


ALIBABA_API_KEY_US = os.getenv("ALIBABA_API_KEY_US")
if not ALIBABA_API_KEY_US:
    raise EnvironmentError("ALIBABA_API_KEY_US is not set")

ALIBABA_BASE_URL_US = os.getenv("ALIBABA_BASE_URL_US")
if not ALIBABA_BASE_URL_US:
    raise EnvironmentError("ALIBABA_BASE_URL_US is not set")

ALIBABA_MODEL_US = os.getenv("ALIBABA_MODEL_US")
if not ALIBABA_MODEL_US:
    raise EnvironmentError("ALIBABA_MODEL_US is not set")

SERP_API_KEY = os.getenv("SERP_API_KEY")
if not SERP_API_KEY:
    raise EnvironmentError("SERP_API_KEY is not set")

os.makedirs("./out", exist_ok=True)

class App:

    def __init__(self):
        logger.debug("__init__")

        self._llm = AsyncOpenAI(
            api_key=ALIBABA_API_KEY_US,
            base_url=ALIBABA_BASE_URL_US
        )

        self._playwright = None
        self._browser = None
        self._context = None

    async def init_playwright(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

    async def finish(self):
        logger.debug("finish")
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        if self._llm:
            await self._llm.close()
            self._llm = None
        await db.close()

    async def load_bwtt_jobs(self, keywords):
        logger.debug("load_bwtt_jobs")

        for keyword in keywords:

            logger.debug(f"keyword: {keyword}")

            page_no = 1
            while True:

                try:

                    keyword_value = quote_plus(keyword)
                    link = f"https://blackwomentalktechjobs.com/jobs?keywords={keyword_value}&page={page_no}"
                    logger.debug(link)

                    await self._page.goto(link)
                    selector = 'div[data-qa="job-listing"]'
                    await self._page.wait_for_selector(selector)
                    jobs = await self._page.locator(selector).all()
                    if jobs:
                        for job in jobs:
                            a = job.locator('a').first
                            title = await a.inner_text()
                            href = await a.get_attribute('href')
                            job_id = str(uuid.uuid4())
                            d = job.locator('div.gap-3 div.text-base').first
                            dtms = await d.inner_text()
                            dtm = datetime.strptime(dtms, "%b %d, %Y")
                            item = {"job_id":job_id, "source":"bwtt", "title":title, "link":href, "dtm":dtm}
                            logger.debug(item)
                            await db.upsert_job(item)

                        page_no = page_no + 1
                    else:
                        logger.debug("no more jobs. breaking out...")
                        break

                except Exception as e:
                    logger.debug(f"100 {e}")
                    break

            logger.debug("continuing for keyword")

        logger.debug("done with for keyword")

    async def load_nvidia_jobs(self, keywords):
        logger.debug("load_nvidia_jobs")


        for keyword in keywords:

            logger.debug(f"keyword: {keyword}")

            start_no = 0
            while True:

                try:

                    keyword_value = quote_plus(keyword)
                    link = f"https://jobs.nvidia.com/careers?query={keyword_value}&start={start_no}&sort_by=match&filter_job_category=engineering&filter_work_location_option=remote"
                    logger.debug(link)

                    await self._page.goto(link)
                    selector = 'div[data-test-id="job-listing"]'
                    await self._page.wait_for_selector(selector)
                    jobs = await self._page.locator(selector).all()
                    if jobs:
                        for job in jobs:
                            a = job.locator('a').first
                            title = await a.get_attribute('aria-label')
                            title = title.replace('View job: ', '')
                            href = await a.get_attribute('href')
                            href = f"https://jobs.nvidia.com{href}"
                            job_id = str(uuid.uuid4())
                            dtm = datetime.now()
                            item = {"job_id":job_id, "source":"nvidia", "title":title, "link":href, "dtm":dtm}
                            logger.debug(item)
                            await db.upsert_job(item)

                        start_no = start_no + 10
                    else:
                        logger.debug("no more jobs. breaking out...")
                        break

                except Exception as e:
                    logger.debug(f"100 {e}")
                    break

            logger.debug("continuing for keyword")

        logger.debug("done with for keyword")

    async def gen_resume(self, description, resume):
        logger.debug("gen_resume")
        content = None
        prompt = f"""
<role>
You are an expert ATS (Applicant Tracking System) resume optimizer and technical recruiter specializing in Workday systems. Your task is to rewrite and optimize the provided resume specifically for the provided job description. 
</role>

<instructions>
Align the candidate's existing experience as closely as possible to the target role without fabricating degrees, job titles, or completely unrelated skills. The output must pass through Workday ATS parsing with a 90%+ keyword match rate while remaining highly compelling and readable to a human hiring manager.
Extract the critical hard skills, software, methodologies, and specific noun phrases directly from the job description. Seamlessly integrate these exact phrases into the skills section and experience bullet points. Do not use synonyms if the job description uses a specific industry-standard term.
Do not lie or invent fake experience. However, logically translate the candidate's actual past accomplishments into the lexicon of the job description. (For example, if the job asks for "edge deployment" and the candidate built software for IoT/raspberry pi, reframe it using the job's exact phrasing).
Analyze the core responsibilities of the target job. Rewrite the candidate's bullet points to emphasize achievements and duties that directly map to those responsibilities. De-emphasize or remove administrative tasks, pitching, payroll, or unrelated operational duties unless they are specifically requested in the job description. Prioritize metrics and quantifiable results.
Analyze the job description and resume. Determine the top 20 skills required for the job.
Insert a Technical Skills section in the resume just below the Executive Summary section with all 20 skills on one line separated by a | character.
</instructions>

<constraints>
Return only ASCII characters (character codes 0-127).
Do not use smart quotes, em dashes, en dashes, bullets, ellipses, non-breaking spaces, or any Unicode symbols.
Use only plain ASCII equivalents.
Output ONLY plain text. No markdown (no **, no ##), no bolding, no italics, no bullet point symbols (use standard hyphens only), and no tables.
Do not use columns, headers, or footers.
List work experience in reverse cronological order.
Keep the resume length down to 1 to 2 pages.
If older work experience will not fit in 2 pages, create work experience entry that summarizes all older work experience.
</constraints>

<job>
{description}
</job>

<resume>
{resume}
</resume>
        """
        content = await self.chat(prompt)
        return content

    async def gen_html_resume(self, resume, html_resume):
        logger.debug("gen_html_resume")
        content = None
        prompt = f"""
You are an expert resume writer. Your job is to format a plain text resume into HTML.
Do not include any logos or URLs in the Experience section.

CONSTRAINTS
===========
Return only ASCII characters (character codes 0-127).
Do not use smart quotes, em dashes, en dashes, bullets, ellipses, non-breaking spaces, or any Unicode symbols.
Use only plain ASCII equivalents.
Follow the EXAMPLE HTML RESUME structure, style, and class names exactly.
For bulleted list items (li), do not include the hyphen (`-`) at the beginning of the copy.

EXAMPLE HTML RESUME
===================
{html_resume}

TEXT RESUME
===========
{resume}


HTML RESUME
===========
        """

        content = await self.chat(prompt)
        return content

    async def gen_cover(self, description, resume):
        logger.debug("gen_cover")
        content = None
        current_date = date.today().strftime("%B %d, %Y")
        prompt = f"""
ROLE
====
You are a professional cover letter writing expert, with an extensive experience in crafting compelling cover letters.
Your role is now to create a personalized cover letter that effectively showcases my qualifications and potential value I would bring to employers. When I give you my information and the job details, you will:

INSTRUCTIONS
============
Retreive the job title and company name from the job description.
Write an opening paragraph showing enthusiasm and knowledge of the company.
Create clear and concise paragraphs that connect my experience to the job requirements.
Highlight my achievements and skills, using specific examples and metrics when available.
Incorporate industry-specific keywords naturally.
Maintain a professional and engaging tone and style.
Always be focused on the value proposition I can offer to the company.
Close the cover letter with a confident call-to-action and a professional closing

CONTEXT
=======
Today's date is {current_date}.

CONSTRAINTS
===========
The cover letter should be approximately 300-500 words, avoid generic phrases, be tailored specifically to the role and company, balance confidence with humility.
Do not use hyphens in the output.
Return only ASCII characters (character codes 0-127).
Do not use smart quotes, em dashes, en dashes, bullets, ellipses, non-breaking spaces, or any Unicode symbols.
Use only plain ASCII equivalents.

JOB DESCRIPTION
===============
{description}

RESUME
======
{resume}
        """
        content = await self.chat(prompt)
        return content

    async def gen_yc(self, description, resume):
        logger.debug("gen_yc")
        content = None
        prompt = f"""
You are an expert startup operator helping a candidate write a cold pitch for the Y Combinator job board. 

The audience is a startup founder or founding engineer. They are busy, read on their phone, and hate corporate jargon. They value ownership, speed, and specific technical proof over generic soft skills.

Your task is to take the provided RESUME and JOB DESCRIPTION and write a short, punchy pitch message (under 150 words).

RULES FOR THE PITCH:
1. DO NOT start with "Hi, my name is [Name] and I am writing to..." Jump straight into the value.
2. FORMAT: Start with a lowercase "hey [Founder Name]," or "hi [Founder Name]," (Find the founder's name in the JD if possible. If not, use "hi team,").
3. THE HOOK: Connect the candidate's most relevant past achievement directly to the core problem the startup is solving in 1-2 sentences.
4. THE PROOF: Mention 1 specific technology or metric from the resume that perfectly matches the JD's hardest requirement. 
5. ADDRESS DEALBREAKERS IMMEDIATELY: 
   - If the candidate's location doesn't match the JD, explicitly state they are relocating/toeing the office requirement.
   - If the candidate's primary stack is different (e.g., C# vs Node.js) but they have adjacent experience, confidently state they are comfortable cross-training into the required stack based on architectural experience.
6. TONE: Conversational, confident, slightly informal. Use contractions (I'm, don't, we've). 
7. NEGATIVE CONSTRAINTS: Do NOT use words like "delve," "leverage," "tailored," "testament," "synergy," "passionate," or "eager." Do NOT write a standard 3-paragraph cover letter.

JOB DESCRIPTION
===============
{description}

RESUME
======
{resume}

PITCH
====
        """

        content = await self.chat(prompt)
        return content
    
    async def gen_html_cover(self, cover, html_cover):
        logger.debug("gen_html_cover")
        content = None
        prompt = f"""
You are an expert resume writer. Your job is to format a plain text cover letter into HTML that prints on 1 page.

CONSTRAINTS
===========
Return only ASCII characters (character codes 0-127).
Do not use smart quotes, em dashes, en dashes, bullets, ellipses, non-breaking spaces, or any Unicode symbols.
Use only plain ASCII equivalents.

EXAMPLE COVER LETTER
====================
{html_cover}

TEXT COVER LETTER
=================
{cover}

HTML COVER LETTER
=================
        """

        content = await self.chat(prompt)
        return content

    async def get_score(self, description, resume):
        logger.debug("get_score")
        score = None
        prompt = f"""
ROLE
====
You are a tech recuriter. Your job is to match candiates with jobs. You do this by giving each candidate a score based on how well their skills and experience match the job description.
A score of 0 means they are not a fit in any way.  A score of 10 means they are a perfect fit and have everything needed for the job.
Given the following RESUME and JOB_DESCRIPTION, generate a score for this candidate.  
The score just be returned in JSON format.  Example: {{"score":7, "reason":"the candidate has most of the skills but lacks experience"}}

CONSTRAINTS
===========
Return only ASCII characters (character codes 0-127).
Do not use smart quotes, em dashes, en dashes, bullets, ellipses, non-breaking spaces, or any Unicode symbols.
Use only plain ASCII equivalents.

JOB_DESCRIPTION
===============
{description}

RESUME
======
{resume}

SCORE
=====
        """
        result_json = await self.chat(prompt)
        try:
            result = json.loads(result_json)
            score = result["score"]
        except Exception as e:
            logger.error(e)
        return score

    async def get_description(self, link, source):
        logger.debug("get_description")
        content = None
        try:
            await self._page.goto(link)

            if source == "nvidia":
                selector = 'div.container-3Gm1a'
            elif source == "bwtt":
                selector = 'div[x-show="showFullDescription"]'
            elif source == "workday":
                selector = 'div[data-automation-id="jobPostingDescription"]'
            else:
                logger.error("invalid source")
                sys.exit(1)
            await self._page.wait_for_selector(selector, state="attached")
            content = await self._page.locator(selector).text_content()
        except Exception as e:
            logger.debug(f"193 {e}")
        return content

    async def chat(self, content) -> str:
        logger.debug("chat")
        logger.debug(ALIBABA_MODEL_US)
        logger.debug(len(content))
        message = {"role": "user", "content": content}
        messages = [message]
        response = await self._llm.chat.completions.create(
            model=ALIBABA_MODEL_US,
            messages=messages,
            stream=False,
        )
        content = response.choices[0].message.content
        content = content.replace('```html', '')
        content = content.replace('```', '')

        TRANSLATION = str.maketrans({
            "“": '"',
            "”": '"',
            "‘": "'",
            "’": "'",
            "—": "-",
            "–": "-",
            "…": "...",
            "•": "*",
            "\u00A0": " ",   # non-breaking space
        })

        content = content.translate(TRANSLATION)
        content = content.encode("ascii", "ignore").decode("ascii")
        logger.debug(len(content))
        return content

    async def load_workday_jobs(self, keywords):
        logger.debug("load_workday_jobs")
        results = []

        for keyword in keywords:
            term = f"{keyword} site:myworkdayjobs.com"
            search = GoogleSearch({
                "engine":"google",
                "q": term, 
                "google_domain": "google.com",
                "hl": "en",
                "gl": "us",
                "api_key": SERP_API_KEY
              })
            result = search.get_dict()
            organic_results = result.get("organic_results", [])
            for organic_result in organic_results:
                title = organic_result["title"]
                link = organic_result["link"]
                job_id = str(uuid.uuid4())
                item = {"job_id":job_id, "source":"workday", "title":title, "link":link}
                await db.upsert_job(item)
        return results

    async def get_job_description(self):
        logger.debug("get_job_description")
        content = None
        with open('job.txt', 'r', encoding='utf-8') as file:
            content = file.read()
        return content

    async def get_resume(self):
        logger.debug("get_resume")
        content = None
        with open('resume.txt', 'r', encoding='utf-8') as file:
            content = file.read()
        return content

    async def get_html_resume(self):
        logger.debug("get_html_resume")
        content = None
        with open('resume.htm', 'r', encoding='utf-8') as file:
            content = file.read()
        return content

    async def get_html_cover(self):
        logger.debug("get_html_cover")
        content = None
        with open('cover.htm', 'r', encoding='utf-8') as file:
            content = file.read()
        return content

    async def get_keywords(self):
        logger.debug("get_keywords")
        results = []
        with open('keywords.txt', 'r', encoding='utf-8') as file:
            for line in file:
                clean_line = line.strip()
                results.append(clean_line)
        return results

    async def run(self, sources):
        logger.debug("run")
        logger.debug(sources)

        await self.init_playwright()

        resume = await self.get_resume()

        keywords = await self.get_keywords()

        for source in sources:

            logger.debug(f"source: {source}")

            if source == "nvidia":
                await self.load_nvidia_jobs(keywords)
            elif source == "bwtt":
                await self.load_bwtt_jobs(keywords)
            elif source == "workday":
                await self.load_workday_jobs(keywords)
            else:
                logger.error("invalid source")
                sys.exit(1)

            jobs = await db.get_jobs_by_source(source)

            for job in jobs:

                job_id = job["job_id"]
                job_source = job["source"]
                title = job["title"]
                link = job["link"]

                logger.debug("====================")
                logger.debug(f"source: {job_source}")
                logger.debug(f"title: {title}")
                logger.debug(f"link: {link}")

                if job.get("description"):
                    description = job["description"]
                else:
                    description = await self.get_description(link, job_source)
                    if description:
                        await db.upsert_job({"link": link, "description": description})
                    else:
                        logger.error("description is None")
                        continue

                if job.get("score") is not None:
                    score = job["score"]
                else:
                    score = await self.get_score(description, resume)
                    logger.debug(f"score: {score}")
                    if score is not None:
                        await db.upsert_job({"link": link, "score": score})

                        if score > 7:

                            if job.get("resume"):
                                content = job["resume"]
                            else:
                                content = await self.gen_resume(description, resume)

                                file_name = f"resume_{job_id}.txt"
                                file_path = f"./out/{file_name}"
                                with open(file_path, 'w', encoding='ascii') as file:
                                    file.write(content)

                                await db.upsert_job({"link": link, "resume": file_name})
                    else:
                        logger.error("score is None")

                logger.debug(f"score: {score}")

    async def keyword(self, job_id):

        result = None

        job = await db.find_one(job_id)
        if job:

            description = job["description"]

            score = 0
            prompt = f"""
You are a tech recuriter. Your job is to analyze job descriptions.
Analyze the job description below and return a list of the top 20 skills required for the job.
Return the list of skills in JSON format.

CONSTRAINTS
===========
Return only ASCII characters (character codes 0-127).
Do not use smart quotes, em dashes, en dashes, bullets, ellipses, non-breaking spaces, or any Unicode symbols.
Use only plain ASCII equivalents.

EXAMPLE
=======
{{"skills":["Javacript", "LLM", "Artifical Intelligence", "RAG", "Python"]}}

JOB_DESCRIPTION
===============
{description}

SKILLS
=====
            """

            result_json = await self.chat(prompt)
            try:
                result = json.loads(result_json)
                skills = result["skills"]
                result = " | ".join(skills)

            except Exception as e:
                logger.error(e)

        return result

    async def resume(self):

        logger.debug("resume")

        file_path = Path("/tmp/resume.pdf")
        if file_path.exists():
            file_path.unlink()

        resume = await self.get_resume()
        description = await self.get_job_description()
        content = await self.gen_resume(description, resume)

        job_id = str(uuid.uuid4())
        file_name_txt = f"resume_{job_id}.txt"
        file_path_txt = f"./out/{file_name_txt}"
        with open(file_path_txt, 'w', encoding='ascii') as file:
            file.write(content)

        full_path_txt = Path(file_path_txt).resolve()
        logger.debug(full_path_txt)

        # try:
        #     subprocess.Popen(
        #         ['/usr/local/bin/subl', full_path_txt],
        #         stdout=subprocess.DEVNULL,
        #         stderr=subprocess.DEVNULL,
        #         start_new_session=True
        #     )
        # except Exception as e:
        #     logger.error(e)

        html_resume = await self.get_html_resume()
        html_content = await self.gen_html_resume(content, html_resume)
        file_name_htm = f"resume_{job_id}.htm"
        file_path_htm = f"./out/{file_name_htm}"
        with open(file_path_htm, 'w', encoding='ascii') as file:
            file.write(html_content)

        full_path_htm = Path(file_path_htm).resolve()
        logger.debug(full_path_htm)

        # try:
        #     subprocess.Popen(
        #         ['/usr/local/bin/subl', file_path_htm],
        #         stdout=subprocess.DEVNULL,
        #         stderr=subprocess.DEVNULL,
        #         start_new_session=True
        #     )
        # except Exception as e:
        #     logger.error(e)

        file_name_pdf = f"resume_{job_id}.pdf"
        file_path_pdf = f"./out/{file_name_pdf}"

        try:
            subprocess.run(
                ['wkhtmltopdf', '-q', file_path_htm, file_path_pdf],
                check=True,
                capture_output=True,
                text=True
            )
            full_path_pdf = Path(file_path_pdf).resolve()
            logger.debug(full_path_pdf)

            tmp_file_path_pdf = f"/tmp/resume.pdf"
            shutil.copy(full_path_pdf, tmp_file_path_pdf)

            subprocess.Popen(
                ['xdg-open', tmp_file_path_pdf],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

        except Exception as e:
            logger.error(e)

        score = await self.get_score(description, content)
        logger.debug(f"score: {score}")

        # title = "adhoc"
        # link = None
        # dtm = datetime.now()

        # coll = self._mongo["apply"]["job"]

        # item = {"job_id":job_id, "source":"adhoc", "title":title, "link":link, "description":description, "resume":file_name_txt, "dtm":dtm}
        # await coll.insert_one(item)

        # keywords = await self.keyword(job_id)
        # #logger.debug(keywords)

        # file_name_kwd = f"keyword_{job_id}.txt"
        # file_path_kwd = f"./out/{file_name_kwd}"
        # with open(file_path_kwd, 'w', encoding='ascii') as file:
        #     file.write(keywords)

        # full_path_kwd = Path(file_path_kwd).resolve()
        # logger.debug(full_path_kwd)

        # match = {"job_id":job_id}
        # await coll.delete_one(match)

        return content

    async def salary(self, source):
        logger.debug("salary")

        jobs = await db.get_jobs_by_source(source)

        for job in jobs:

            if job.get("min_salary") is not None and job.get("max_salary") is not None:
                continue

            link = job["link"]
            logger.debug(link)

            if job.get("description"):
            
                description = job["description"]

                prompt = f"""
You are a technical recruiter. 
Analyze the following JOB DESCRIPTION to determine the salary range.
If no salary is found set the min_salary and max_salary = 0 (zero).
Always respond in JSON format. 

CONSTRAINTS
===========
Return only ASCII characters (character codes 0-127).
Do not use smart quotes, em dashes, en dashes, bullets, ellipses, non-breaking spaces, or any Unicode symbols.
Use only plain ASCII equivalents.

EXAMPLE
=======
{{"min_salary":200000, "max_salary":320000}}


JOB_DESCRIPTION
===============
{description}

SALARY
======
                """
                result_json = await self.chat(prompt)
                try:
                    result = json.loads(result_json)
                    min_salary = result["min_salary"]
                    max_salary = result["max_salary"]
                    item = {"link": link, "min_salary":min_salary, "max_salary":max_salary}
                    logger.debug(item)
                    await db.upsert_job(item)

                except Exception as e:
                    logger.error(e)

    async def score(self):
        logger.debug("test")

        resume = await self.get_resume()
        description = await self.get_job_description()
        score = await self.get_score(description, resume)
        logger.debug(f"score: {score}")

    async def cover(self, resume: str = None) -> str:
        logger.debug("cover")

        file_path = Path("/tmp/cover.pdf")
        if file_path.exists():
            file_path.unlink()

        if resume is None:
            resume = await self.get_resume()

        description = await self.get_job_description()
        content = await self.gen_cover(description, resume)

        job_id = str(uuid.uuid4())
        file_name_txt = f"cover_{job_id}.txt"
        file_path_txt = f"./out/{file_name_txt}"
        with open(file_path_txt, 'w', encoding='ascii') as file:
            file.write(content)

        full_path_txt = Path(file_path_txt).resolve()
        logger.debug(full_path_txt)

        # try:
        #     subprocess.Popen(
        #         ['/usr/local/bin/subl', full_path_txt],
        #         stdout=subprocess.DEVNULL,
        #         stderr=subprocess.DEVNULL,
        #         start_new_session=True
        #     )
        # except Exception as e:
        #     logger.error(e)

        html_cover = await self.get_html_cover()
        html_content = await self.gen_html_cover(content, html_cover)
        file_name_htm = f"cover_{job_id}.htm"
        file_path_htm = f"./out/{file_name_htm}"
        with open(file_path_htm, 'w', encoding='ascii') as file:
            file.write(html_content)

        full_path_htm = Path(file_path_htm).resolve()
        logger.debug(full_path_htm)

        # try:
        #     subprocess.Popen(
        #         ['/usr/local/bin/subl', full_path_htm],
        #         stdout=subprocess.DEVNULL,
        #         stderr=subprocess.DEVNULL,
        #         start_new_session=True
        #     )
        # except Exception as e:
        #     logger.error(e)

        file_name_pdf = f"cover_{job_id}.pdf"
        file_path_pdf = f"./out/{file_name_pdf}"

        try:
            subprocess.run(
                ['wkhtmltopdf', '-q', file_path_htm, file_path_pdf],
                check=True,
                capture_output=True,
                text=True
            )
            full_path_pdf = Path(file_path_pdf).resolve()
            logger.debug(full_path_pdf)

            tmp_file_path_pdf = f"/tmp/cover.pdf"
            shutil.copy(full_path_pdf, tmp_file_path_pdf)

            subprocess.Popen(
                ['xdg-open', tmp_file_path_pdf],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

        except Exception as e:
            logger.error(e)

        return content

    async def yc(self, resume: str = None) -> str:
        logger.debug("yc")

        file_path = Path("/tmp/yc.txt")
        if file_path.exists():
            file_path.unlink()

        if resume is None:
            resume = await self.get_resume()

        description = await self.get_job_description()
        content = await self.gen_yc(description, resume)

        job_id = str(uuid.uuid4())
        file_name_txt = f"yc_{job_id}.txt"
        file_path_txt = f"./out/{file_name_txt}"
        with open(file_path_txt, 'w', encoding='ascii') as file:
            file.write(content)

        full_path_txt = Path(file_path_txt).resolve()
        logger.debug(full_path_txt)

        tmp_file_path_txt = f"/tmp/yc.txt"
        shutil.copy(full_path_txt, tmp_file_path_txt)

        try:
            subprocess.Popen(
                ['/usr/local/bin/subl', tmp_file_path_txt],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        except Exception as e:
            logger.error(e)

        return content

    async def test(self):
        logger.debug("test")
        prompt = "Hello"
        logger.debug(prompt)
        content = await self.chat(prompt)
        logger.debug(content)

typr = typer.Typer()

def _version_callback(value: bool):
    if value:
        print(f"qwen-apply {__version__}")
        raise typer.Exit()

@typr.command()
def apply():
    logger.debug("apply")

    async def _run():
        try:
            resume = await _app.resume()
            cover = await _app.cover(resume)
        finally:
            await _app.finish()

    _app = App()
    asyncio.run(_run())

@typr.command()
def yc():
    logger.debug("yc")

    async def _run():
        try:
            await _app.yc()
        finally:
            await _app.finish()

    _app = App()
    asyncio.run(_run())

@typr.command()
def cover():
    logger.debug("cover")

    async def _run():
        try:
            await _app.cover()
        finally:
            await _app.finish()

    _app = App()
    asyncio.run(_run())

@typr.command()
def test():
    logger.debug("test")

    async def _run():
        try:
            await _app.test()
        finally:
            await _app.finish()

    _app = App()
    asyncio.run(_run())

@typr.command()
def run(source: str):
    logger.debug("run")

    if source == "nvidia":
        pass
    elif source == "bwtt":
        pass
    elif source == "workday":
        pass
    else:
        logger.error("invalid source")
        sys.exit(1)

    async def _run(sources):
        try:
            await _app.run(sources)
        finally:
            await _app.finish()

    _app = App()
    sources = [source]
    asyncio.run(_run(sources))

@typr.command()
def score():
    logger.debug("score")

    async def _run():
        try:
            await _app.score()
        finally:
            await _app.finish()

    _app = App()
    asyncio.run(_run())

@typr.command()
def resume():
    logger.debug("resume")

    async def _run():
        try:
            await _app.resume()
        finally:
            await _app.finish()

    _app = App()
    asyncio.run(_run())

@typr.command()
def keyword(job_id: str):
    logger.debug("keyword")
    logger.debug(job_id)

    async def _run(job_id):
        try:
            await _app.keyword(job_id)
        finally:
            await _app.finish()

    _app = App()
    asyncio.run(_run(job_id))

@typr.command()
def salary(source: str):
    logger.debug("salary")

    if source == "nvidia":
        pass
    elif source == "bwtt":
        pass
    elif source == "workday":
        pass
    else:
        logger.error("invalid source")
        sys.exit(1)

    async def _run(source):
        try:
            await _app.salary(source)
        finally:
            await _app.finish()

    _app = App()
    asyncio.run(_run(source))

@typr.callback(invoke_without_command=True)
def default_command(ctx: typer.Context, version: Annotated[bool, typer.Option("--version", callback=_version_callback, is_eager=True)] = False):
    if ctx.invoked_subcommand is None:
        async def _run(sources):
            try:
                await _app.run(sources)
            finally:
                await _app.finish()

        _app = App()
        sources = ["workday"]
        asyncio.run(_run(sources))

if __name__ == "__main__":
    typr()

"""
Wellfound (AngelList Talent): Filter by "AI" and "Contract" or "Part-time". Startups hire fast here.
Otta.com: A job board specifically for high-growth tech startups. Much better than LinkedIn.
Keyway.ai: A job board specifically for AI roles.
Fractional Platforms: If you want to be a "Fractional AI Officer" for $5k-$10k/month, list yourself on Fractional.com or MarketerHire (if you are biz-side).
Y Combinator "Work at a Startup": (ycombinator.com/jobs) - These companies are used to hiring founders. They don't care about corporate credentials; they care that you can build.
"""