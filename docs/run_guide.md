# Setup and Run Guide

This document explains how to set up the FoodVision application locally for development or portfolio demonstration purposes.

## Requirements
- Python 3.10+ (for `backend`)
- Node.js 18+ (for `frontend`)
- API Keys for **OpenRouter** and **USDA**

## 1. Backend Setup

The FastAPI backend executes asynchronous data ingestion, internal caching, OpenRouter & USDA API calls, and remote segmentation calls.

### Installation

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   # source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Create a `.env` file in the `backend/` directory (you can copy `.env.example` as a template). Ensure to add:

- **OPENROUTER_API_KEY**: Sign up at [OpenRouter](https://openrouter.ai/) for vision/LLM classification models.
- **USDA_API_KEY**: Sign up at [USDA FDC](https://fdc.nal.usda.gov/api-key-signup.html) for exact nutritional mappings.
- *(Optional)* **FAST_SCAN_MODEL**: Override the default fast scan model (e.g., `openai/gpt-4o`).
- *(Optional)* **DEEP_SCAN_MODEL**: Override the model used to classify deep scan segments (e.g., `qwen/qwen-vl-plus`).

### Start the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
The API should now be accessible at `http://localhost:8000`.

## 2. Frontend Setup

The frontend is a Vite + React application, updated with Lottie animations and responsive dashboards, configured to proxy `/api` calls directly to `localhost:8000`.

### Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```

### Start the Server

```bash
npm run dev
```

The frontend application will start up, usually on **http://localhost:5173**. Open this URL in your browser to test the full stack app.

## 3. Testing the Application

- Ensure both the backend terminal (`uvicorn`) and the frontend terminal (`npm run dev`) are running.
- Drop or upload a food photo into the application UI.
- Use the toggle to switch between **Fast Scan** (~3s) and **Deep Scan** (~60s).
  - *Note: Deep Scan utilizes an external Hugging Face Space for generation, which may be slower on cold boot.*
- Track the real-time progress bar powered by Server-Sent Events (SSE).
- The UI will display the raw or segmented image, followed by a detailed per-item macro breakdown and interactive nutrition charts.
