# KHANNAX Backend

This is the production-ready backend for the KHANNAX chatbot built with FastAPI and Supabase.

## Features
- **FastAPI**: Clean and modern Python API framework.
- **Supabase**: Authentication (Email/Password, Google OAuth), Database, and Row Level Security.
- **Groq API**: Integration for AI chatbot capabilities.
- **Modular Structure**: Simple architecture scalable for production.

## Setup Guide

Follow these steps to connect your Supabase project and get the backend running.

### 1. Supabase Project Setup

1. Create a project at [Supabase](https://supabase.com).
2. Go to your project dashboard -> **SQL Editor** -> **New Query**.
3. Copy the contents of `supabase_schema.sql` from this repository and paste it into the editor.
4. Click **Run** to create the necessary tables (`profiles`, `chat_sessions`, `chat_messages`, `documents`) and enable Row Level Security (RLS) policies.

### 2. Supabase Authentication Setup

1. In Supabase, go to **Authentication** -> **Providers**.
2. **Email Provider**: This is enabled by default. You can disable "Confirm email" if you want users to log in immediately after signing up without email verification.
3. **Google Provider** (Optional - if you need Google Auth in the frontend):
   - Enable the Google provider.
   - Enter your `Client ID` and `Client Secret` obtained from Google Cloud Console.

### 3. Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your keys:
   - `SUPABASE_URL`: From Supabase Project Settings -> API -> Project URL.
   - `SUPABASE_KEY`: From Supabase Project Settings -> API -> Project API Keys (anon public).
   - `GROQ_API_KEY`: Your API key for Groq if you want AI replies in the chat.

### 4. Running the Backend locally

1. Install the requirements (preferably in a virtual environment):
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   python -m pip install -r requirements.txt
   ```
2. Run the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Visit [http://localhost:8000/docs](http://localhost:8000/docs) to view and interact with the Swagger API documentation.

## Modules

- `app/api`: Defines all your API routes (`auth`, `chat`, `documents`).
- `app/core`: Application-wide configurations and security functions.
- `app/models`: Defines Pydantic schemas validating inbound/outbound variables.
- `app/services`: Single instance integrations (e.g. Supabase client setup).
- `supabase_schema.sql`: Raw SQL used for declaring your database schema.
