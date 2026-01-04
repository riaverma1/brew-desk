# Deployment Guide: Vercel + Render

This guide explains how to deploy the Coffee App to Vercel (frontend) and Render (backend).

## Architecture

- **Frontend**: Next.js app deployed on Vercel
- **Backend**: FastAPI app deployed on Render
- **Database**: Supabase PostgreSQL (cloud-hosted)

## Prerequisites

1. GitHub repository with your code
2. Vercel account (free tier)
3. Render account (free tier)
4. Supabase project with database
5. API keys:
   - Google Places API key
   - Google Maps JavaScript API key
   - Tavily API key
   - OpenAI API key

## Step 1: Deploy Backend to Render

### 1.1 Connect Repository to Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Select the repository

### 1.2 Configure Render Service

**Basic Settings:**
- **Name**: `coffee-app-backend` (or your preferred name)
- **Region**: Choose closest region (e.g., Oregon)
- **Branch**: `main` (or your default branch)
- **Root Directory**: Leave empty (repository root)
- **Environment**: `Python 3`
- **Build Command**: `pip install -r backend/requirements.txt`
- **Start Command**: `python -m uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`

**Alternative**: Use `render.yaml` file (already created in repository root)

### 1.3 Deploy and Get Backend URL

1. Click "Create Web Service"
2. Wait for deployment to complete
3. Note your backend URL: `https://your-app.onrender.com`
4. Test the backend:
   - Visit: `https://your-app.onrender.com`
   - Should see: `{"message":"Coffee App API","version":"1.0.0"}`
   - Visit: `https://your-app.onrender.com/docs` for API documentation

## Step 2: Deploy Frontend to Vercel

### 2.1 Connect Repository to Vercel

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Click "Add New..." → "Project"
3. Import your GitHub repository
4. Select the repository

### 2.2 Configure Vercel Project

**Framework Preset:**
- **Framework Preset**: Next.js (auto-detected)

**Root Directory:**
- **Root Directory**: `coffee-map`

**Build Settings:**
- Vercel auto-detects Next.js - no additional configuration needed

### 2.3 Deploy and Get Frontend URL

1. Click "Deploy"
2. Wait for deployment to complete
3. Note your frontend URL: `https://your-app.vercel.app`
4. Test the frontend - it should load (but may show errors until environment variables are set)

## Step 3: Configure Environment Variables

### 3.1 Render Environment Variables

Go to Render Dashboard → Your Service → Environment

**Required Variables:**

```bash
# API Keys
GOOGLE_PLACES_API_KEY=your_google_places_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Database - Use Supabase Connection Pooler (port 6543)
# Get from Supabase Dashboard -> Project Settings -> Database -> Connection pooling
# Format: postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
DATABASE_URL=postgresql://postgres.ufxbobwrkbeahhvhbjug:PASSWORD@aws-0-us-west-2.pooler.supabase.com:6543/postgres

# CORS - Set after Vercel deployment (your Vercel frontend URL)
ALLOWED_ORIGINS=https://your-app.vercel.app
```

**Important Notes:**
- Use **connection pooler** URL (port 6543), not direct connection (port 5432)
- Get the exact pooler URL from Supabase Dashboard → Project Settings → Database → Connection pooling
- Set `ALLOWED_ORIGINS` after deploying to Vercel (get the URL from Vercel dashboard)

### 3.2 Vercel Environment Variables

Go to Vercel Dashboard → Your Project → Settings → Environment Variables

**Required Variables:**

```bash
# Backend API URL (your Render backend URL)
FASTAPI_BASE_URL=https://your-app.onrender.com

# Google Maps JavaScript API Key
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
```

**Important Notes:**
- `FASTAPI_BASE_URL` should be your Render backend URL (this is used server-side only in Next.js API routes)
- `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is different from `GOOGLE_PLACES_API_KEY`
  - Maps JavaScript API key is for displaying the map in the frontend
  - Places API key is for searching places in the backend
- Note: The frontend no longer needs `NEXT_PUBLIC_FASTAPI_BASE_URL` because all backend calls are proxied through Next.js API routes

## Step 4: Redeploy Services

After setting environment variables:

1. **Render**: Click "Manual Deploy" → "Deploy latest commit" (or push a new commit)
2. **Vercel**: Changes are automatically deployed, or manually trigger redeploy

## Step 5: Verify Deployment

### 5.1 Test Backend

1. Visit `https://your-app.onrender.com`
   - Should see: `{"message":"Coffee App API","version":"1.0.0"}`
2. Visit `https://your-app.onrender.com/docs`
   - Should see API documentation
3. Visit `https://your-app.onrender.com/health`
   - Should see: `{"status":"healthy"}`

### 5.2 Test Frontend

1. Visit `https://your-app.vercel.app`
   - Should load the map interface
   - Should be able to search for places
   - Should display results on the map

### 5.3 Test Integration

1. Open browser DevTools → Network tab
2. Interact with the map (pan, zoom)
3. Check for requests to `/api/places`
4. Should see successful responses (200 status)
5. Check for any CORS errors in console

## Local Development

### Backend (Local)

1. Create `backend/.env.local`:
   ```bash
   GOOGLE_PLACES_API_KEY=your_key_here
   TAVILY_API_KEY=your_key_here
   OPENAI_API_KEY=your_key_here
   DATABASE_URL=your_supabase_connection_string
   # ALLOWED_ORIGINS not needed for local development
   ```

2. Start backend:
   ```bash
   python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. Backend runs at: `http://localhost:8000`

### Frontend (Local)

1. Create `coffee-map/.env.local`:
   ```bash
   FASTAPI_BASE_URL=http://localhost:8000
   NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_key_here
   ```

2. Start frontend:
   ```bash
   cd coffee-map
   npm install  # First time only
   npm run dev
   ```

3. Frontend runs at: `http://localhost:3000`

## Troubleshooting

### Backend Issues

**Connection to database fails:**
- Use connection pooler URL (port 6543), not direct connection (port 5432)
- Get exact URL from Supabase Dashboard → Project Settings → Database → Connection pooling
- Verify `DATABASE_URL` is set correctly in Render environment variables

**CORS errors:**
- Verify `ALLOWED_ORIGINS` includes your Vercel URL
- Check Render logs for CORS configuration
- Ensure URL matches exactly (including https://)

**Module not found errors:**
- Verify `Root Directory` is empty (repository root)
- Verify `Build Command` is: `pip install -r backend/requirements.txt`
- Verify `Start Command` is: `python -m uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`

### Frontend Issues

**Google Maps API error:**
- Verify `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is set in Vercel
- Ensure Maps JavaScript API is enabled in Google Cloud Console
- Verify API key restrictions allow your Vercel domain

**Backend connection fails:**
- Verify `FASTAPI_BASE_URL` is set to your Render backend URL
- Check Vercel function logs for connection errors
- Ensure Render backend is running (check Render logs)

**500 errors from API:**
- Check Vercel function logs
- Check Render logs for backend errors
- Verify all environment variables are set correctly

### Render Free Tier Notes

- Services spin down after 15 minutes of inactivity
- First request after spin-down takes ~30 seconds to wake up
- Free tier includes 750 hours/month
- Consider upgrading for always-on service

## Environment Variables Summary

### Render (Backend)

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_PLACES_API_KEY` | Yes | Google Places API key |
| `TAVILY_API_KEY` | Yes | Tavily API key for web searches |
| `OPENAI_API_KEY` | Yes | OpenAI API key for LLM features |
| `DATABASE_URL` | Yes | Supabase PostgreSQL connection pooler URL |
| `ALLOWED_ORIGINS` | Yes (production) | Comma-separated list of allowed CORS origins |

### Vercel (Frontend)

| Variable | Required | Description |
|----------|----------|-------------|
| `FASTAPI_BASE_URL` | Yes | Render backend URL (used server-side in Next.js API routes) |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | Yes | Google Maps JavaScript API key |

## Additional Resources

- [Render Documentation](https://render.com/docs)
- [Vercel Documentation](https://vercel.com/docs)
- [Supabase Documentation](https://supabase.com/docs)
- [Next.js Documentation](https://nextjs.org/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

