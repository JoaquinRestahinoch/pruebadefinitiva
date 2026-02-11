# Deploy `ai-product-photos` backend (Render / Railway / Fly)

Quick steps to deploy the FastAPI backend to Render (recommended) and make the frontend on Vercel talk to it:

1. Push this repo to GitHub (if not already) and connect it on Render.

2. Create a new **Web Service** on Render:
   - Environment: `Python 3` (runtime from `runtime.txt`)
   - Build Command: leave empty or `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Set the environment variable `GEMINI_API_KEY` in the Render dashboard (do NOT commit `.env` to git).

3. After deployment Render will provide a URL, e.g. `https://your-service.onrender.com`.

4. In your Vercel frontend project (the `photo-wizard` app) set the environment variable that the frontend uses to call the API. Example env names used by this repo:
   - `API_BASE` or `NEXT_PUBLIC_API_BASE` → `https://your-service.onrender.com`

5. Re-deploy the frontend on Vercel. Requests from the frontend to the API should now succeed.

Notes and alternatives:
- If you prefer Railway/Fly, the same `requirements.txt` and `Procfile` work similarly.
- Converting the app into Vercel serverless functions is possible but requires restructuring `main.py` into multiple small handlers and may fail if large native dependencies are required.
- For secure keys, always set them in the host's environment variables, not in `.env` committed to the repo.

If you want, I can:
- Create a small `vercel.json` rewrite to proxy `/api/*` to the Render URL from the frontend repo,
- Or prepare a `Dockerfile` if you prefer a container-based deploy.
