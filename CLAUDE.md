# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DOCX-to-HTML converter for FDI (Foreign Direct Investment) regulatory documents. Converts Word documents and splits content into four predefined sections based on text markers.

## Architecture

- **Frontend** (`index.html`): Single-page HTML/JS app with drag-and-drop file upload
- **Backend** (`api/index.py`): Python serverless function for Vercel
- **Deployment**: Vercel serverless platform (routes `/api` to the Python handler)

## Key Processing Flow

1. Frontend uploads `.docx` file via `multipart/form-data` POST to `/api`
2. Backend converts DOCX to HTML using `mammoth` library
3. HTML is sanitized (whitelist of allowed tags: br, h1-h6, ul, ol, li, strong, b, em, i, u, a, blockquote, code, pre, font)
4. Content is split into 4 sections based on text markers:
   - **Jurisdiction**: Content before "Foreign investors:"
   - **Thresholds**: Between "Foreign investors:" and "Authority in Charge"
   - **Procedures**: Between "Authority in Charge" and "Standard of Review"
   - **Standard**: After "Standard of Review"
5. Returns JSON with four section keys

## Development

**Local setup:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Deploy:**
```bash
vercel
```

## Dependencies

- `mammoth` - DOCX to HTML conversion
- `beautifulsoup4` - HTML parsing/manipulation
- `legacy-cgi` - Form data handling (cgi module fallback)
