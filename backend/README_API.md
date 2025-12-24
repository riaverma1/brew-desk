# FastAPI Backend - Startup Guide

## Prerequisites

1. Python 3.8+ installed
2. Environment variables configured (see below)

## Setup

### 1. Install Dependencies

From the `backend` directory:

```bash
cd backend
pip install -r requirements.txt
```

Or if using a virtual environment (recommended):

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Create a `.env` file in the `backend` directory (or `.env.local` if that's what your code expects):

```bash
# Required
GOOGLE_PLACES_API_KEY=your_google_places_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

**Note**: The code looks for `.env.local` in the parent directory. You can either:
- Create `backend/.env.local` 
- Or modify the code to use `.env` in the backend directory
- Or set environment variables directly in your shell

### 3. Start the Server

From the `backend` directory, run:

```bash
# Option 1: Using uvicorn directly (recommended)
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Option 2: Using Python module
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Option 3: Run the main.py file directly
python backend/api/main.py
```

The `--reload` flag enables auto-reload on code changes (useful for development).

### 4. Verify It's Running

Open your browser and visit:
- http://localhost:8000 - Should show API info
- http://localhost:8000/docs - Interactive API documentation (Swagger UI)
- http://localhost:8000/health - Health check endpoint

## Running from Project Root

If you want to run from the project root directory:

```bash
# From project root
cd /Users/riaverma/Library/Mobile\ Documents/com~apple~CloudDocs/GitHub_Repos/coffee_app

# Make sure you're in the right Python environment
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Troubleshooting

### Import Errors

If you get import errors like `ModuleNotFoundError: No module named 'backend'`, make sure you're running from the project root directory, or add the project root to your Python path:

```bash
export PYTHONPATH="${PYTHONPATH}:/Users/riaverma/Library/Mobile Documents/com~apple~CloudDocs/GitHub_Repos/coffee_app"
```

### Environment Variable Issues

The code looks for `.env.local` in the parent directory. Check:
- `backend/enrichment/google_places.py` line 13: `dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")`

You may need to create `.env.local` in the `backend` directory or adjust the path in the code.

### Port Already in Use

If port 8000 is already in use:
```bash
# Find what's using the port
lsof -i :8000

# Or use a different port
uvicorn backend.api.main:app --reload --port 8001
```

Then update `FASTAPI_BASE_URL` in your Next.js `.env.local` to match.

## Next Steps

Once the FastAPI server is running:
1. Start your Next.js frontend: `cd coffee-map && npm run dev`
2. The frontend will connect to FastAPI at `http://localhost:8000`
3. Make sure `FASTAPI_BASE_URL` in `coffee-map/.env.local` is set to `http://localhost:8000`

