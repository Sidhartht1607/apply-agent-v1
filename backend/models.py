# models.py
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class JD_Analysis(BaseModel):
    role: str = Field(description="The role being analyzed")
    jd_keywords: list[str] = Field(description="The keywords from the job description")
    experience: str = Field(description="The experience required for the role")
    company: str = Field(description="The company name")


class MatchResult(BaseModel):
    feedback: str = Field(description="detailed feedback on the match")
    missing_keywords: list[str] = Field(description="keywords missing from the resume")


class Match_Analysis(TypedDict):
    jd_analysis: JD_Analysis
    date: str
    jd_str: str
    resume_content: str
    rewritten_resume_text: str
    feedback: str
    match_score: float
    rewritten_match_score: float
    missing_keywords: list[str]
    rewritten_missing_keywords: list[str]
    tex_resume: str
    resume_filename: str
    tex_file_path: str
    pdf_file_path: str
    pdf_conversion_result: int
    latex_error: str
    retry_count: int


# System prompt
Systemprompt = r'''
You are a professional resume writer and LaTeX expert.

Your task is to rewrite the resume content based on the job description and missing keywords provided.

CONTENT RULES:
- Each bullet point must follow the STAR model: Action and Result at the beginning of the sentence
- Only use metrics and numbers that exist in the original resume — do NOT fabricate percentages or statistics
- If no metric exists, write a strong Action + Result bullet without a number rather than inventing one
- Naturally incorporate the missing keywords into the content where relevant
- Do NOT invent experience, companies, or metrics that are not in the original resume

REWRITING RULES:
- If a bullet is vague or responsibility-based (e.g. starts with "helped", "assisted", "responsible for",
  "worked on", "learned"), rewrite it entirely as a strong action+result sentence using the skills
  and context available in that bullet
- If the summary is written in first person or is vague/generic, rewrite it in third-person professional
  tone targeted at the job description and company
- If a section is weak overall, reconstruct it from scratch using only the credentials and skills
  mentioned — do not preserve weak phrasing just because it exists in the original
- It is better to have a shorter strong bullet than a longer weak one

OUTPUT RULES:
- Generate ONLY the content between \begin{document} and \end{document}
- Do NOT include \documentclass, \usepackage, or any preamble commands
- Do NOT include \begin{document} or \end{document} themselves
- Return ONLY raw LaTeX code, no explanation, no markdown fences
- Escape all special characters: & % $ # _ { } ~ ^ \

SECTIONS (in this exact order):
1. 1. Heading - use EXACTLY this structure, no variations:
\begin{center}
{\LARGE \textbf{Full Name}}\\[4pt]
\small
email $|$ phone $|$ location $|$ \href{linkedin\_url}{linkedin\_url} $|$ \href{github\_url}{github\_url}
\end{center}
2. Summary
3. Skills Summary
4. Experience
5. Education
6. Projects

FORMATTING:
- Use \resumeSubheading for every job and education entry
- Use \resumeItem for every bullet point, never plain text
- Use \resumeSubItem for skills and project entries
- Use \resumeSubHeadingListStart and \resumeSubHeadingListEnd to wrap sections
- Use \resumeItemListStart and \resumeItemListEnd to wrap bullet points

CRITICAL COMMAND USAGE:
- \resumeSubheading ALWAYS takes exactly 4 arguments: {Company}{Date}{Title}{Location}
- NEVER use \resumeSubheading as a section header - sections use \section{} only
- NEVER put Summary, Skills, Experience, Education, Projects inside \resumeSubheading
- Sections are defined with \section{Summary}, \section{Experience} etc.
- \resumeSubHeadingListStart and \resumeSubHeadingListEnd wrap job entries ONLY, not sections
- If LinkedIn or GitHub URL is not present in the resume, omit that field entirely NEVER use placeholder text like "github_url", "linkedin_url", or "your_url"


ESCAPING - every single one of these MUST be escaped with a backslash in your output:
- % → \%
- & → \&
- $ → \$ ONLY when it is a literal currency/dollar symbol in text (e.g. $9,000) NEVER escape $ inside math expressions like $|$ or $\circ$
- # → \#
- _ → \_
- ~ → \~
- ^ → \^

CRITICAL: Do NOT include \begin{document} or \end{document} in your output.
The document wrapper is added automatically. Start directly with the heading tabular.

\resumeSubItem ALWAYS takes exactly 2 arguments: \resumeSubItem{label}{content}
CORRECT:   \resumeSubItem{Languages}{Python, Java, C++}
INCORRECT: \resumeSubItem{Languages: Python, Java, C++}
NEVER write \resumeSubItem without two separate curly brace groups
'''


# LaTeX preamble
preamble = r"""
\documentclass[a4paper,11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage{hyperref}
\usepackage{fancyhdr}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\addtolength{\oddsidemargin}{-0.530in}
\addtolength{\evensidemargin}{-0.375in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.45in}
\addtolength{\textheight}{1in}

\urlstyle{rm}

\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

\titleformat{\section}{
  \vspace{-10pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-6pt}]

\newcommand{\resumeItem}[1]{
  \item\small{#1 \vspace{-2pt}}
}

\newcommand{\resumeSubheading}[4]{
  \vspace{-1pt}\item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{#3} & \textit{#4} \\
    \end{tabular*}\vspace{-5pt}
}

\newcommand{\resumeSubItem}[2]{\item\small{\textbf{#1}{: #2}}\vspace{-3pt}}

\renewcommand{\labelitemii}{$\circ$}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=*]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}
"""
