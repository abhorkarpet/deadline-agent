# Deploying to Streamlit Community Cloud

## Prerequisites
1. A GitHub account
2. Your code pushed to a GitHub repository

## Steps to Deploy

### 1. Create GitHub Repository

If you haven't already, create a new repository on GitHub:

1. Go to https://github.com/new
2. Repository name: `deadline-agent` (or your preferred name)
3. Make it **Public** (required for free Streamlit Cloud)
4. Don't initialize with README (we already have one)
5. Click "Create repository"

### 2. Push Your Code to GitHub

Run these commands in your terminal:

```bash
cd /Users/abhaybhorkar/Documents/GitHub/deadline-agent

# Add the remote repository (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/deadline-agent.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

### 3. Deploy on Streamlit Cloud

1. Go to https://share.streamlit.io/
2. Click "New app"
3. Sign in with your GitHub account
4. Select your repository: `YOUR_USERNAME/deadline-agent`
5. Select branch: `main`
6. Main file path: `deadline_agent_app.py`
7. Click "Deploy!"

### 4. Configure Secrets (Optional)

If you want to set default environment variables, go to:
- App settings → Secrets
- Add secrets like:
  ```
  DA_EMAIL_ADDRESS=your-email@example.com
  DA_LLM_API_KEY=your-api-key
  ```

Note: Users can still override these in the UI.

## Important Notes

- The app requires users to provide their own email credentials (app passwords)
- LLM API keys should be entered by users in the UI (not stored in secrets for security)
- The feedback file (`deadline_agent_feedback.jsonl`) is stored locally per session
- All processing happens in the user's browser/session

