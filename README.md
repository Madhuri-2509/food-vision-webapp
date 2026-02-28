# FoodVision

A full-stack asynchronous application for **food recognition and macro estimation** from images. Upload a photo, select a scan mode, and get granular recognized labels (via Vision LLMs) combined with corrected nutrition data (via USDA API).

FoodVision supports advanced Deep Scanning via Hugging Face Space endpoints, bringing real-time progress streaming and precise item bounding boxes to the web application.

## Core Features

- **Dual Scan Modes**: Choose between *Fast Scan* for rapid overall macro estimation, or *Deep Scan* for granular item-by-item bounding box segmentation and classification.
- **Asynchronous Processing**: Non-blocking FastAPI backend delegates work to background threads and streams real-time progress directly to the frontend using Server-Sent Events (SSE).
- **Lottie Animations**: Engaging and varied loading states while computer vision pipelines are running.
- **Manual Corrections**: Intervene when the AI gets it wrong to recalculate macros instantly from the USDA's FoodData Central.

## Structure

```
FoodVision/
├── backend/                  # Python / FastAPI
│   ├── main.py               # API: Upload Jobs, SSE Progress, History, Correct
│   ├── pipeline.py           # Pipeline Logic: Fast/Deep Scan, OpenRouter, USDA
│   ├── segment_client.py     # Deep Scan HF Space Client Logic
│   ├── database.py           # SQLite tables, caching, history
│   ├── requirements.txt      # Python dependencies
│   └── .env                  # OpenRouter & USDA API keys 
├── frontend/                 # React / Vite
│   ├── src/
│   │   ├── components/       # ImageUploader, MacroChart
│   │   ├── Lottie-Animations/# JSON based animations for deep feedback
│   │   ├── App.jsx           # Main layout and SSE logic
│   │   └── main.jsx          # Entry point
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
└── README.md
```

## Documentation

- [Setup & Run Guide](docs/run_guide.md)
- [Architecture & System Overview](docs/architecture.md)
