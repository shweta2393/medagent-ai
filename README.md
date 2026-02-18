# MedAgent AI - GenAI Disease Diagnosis Assistant

A GenAI-powered **Clinical Decision Support System** built with FastAPI and RAG (Retrieval-Augmented Generation) that analyzes patient symptoms, vitals, lab reports, and medical history to provide differential diagnoses with confidence scores.

> **Disclaimer**: This is an AI-assisted tool for educational and research purposes only. It is NOT a substitute for professional medical advice, diagnosis, or treatment.

## Features

- **Symptom Analysis**: Input multiple symptoms with duration and severity context
- **Patient Profiling**: Age, gender, weight, medical history, current medications, lifestyle
- **Vitals Integration**: Blood pressure, heart rate, temperature, respiratory rate, SpO2
- **Lab Report Processing**: Input lab test names and values for analysis
- **Medical Knowledge RAG**: Retrieves relevant medical knowledge from a curated disease database using semantic search
- **Differential Diagnosis**: Provides ranked disease predictions with confidence scores (0-100%)
- **Follow-up Questions**: Asks targeted questions to refine the diagnosis
- **Recommended Tests**: Suggests diagnostic tests with priority levels
- **Specialist Referrals**: Recommends relevant medical specialists
- **Urgency Assessment**: Classifies urgency as Low / Moderate / High / Critical
- **Session Management**: Maintains conversation context for iterative refinement
- **Modern UI**: Beautiful, responsive web interface with multi-step form

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (Python) |
| LLM | Google Gemini (via `google-generativeai`) |
| Embeddings | Sentence-Transformers (`all-MiniLM-L6-v2`) |
| Vector Store | ChromaDB |
| Frontend | Vanilla HTML/CSS/JS |
| Architecture | RAG (Retrieval-Augmented Generation) |

## Architecture

```
Patient Input ──> FastAPI ──> Diagnosis Engine
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼             ▼
              RAG Service    LLM Service   Session Mgr
                    │            │
              ┌─────┘            │
              ▼                  ▼
         ChromaDB          Google Gemini
      (Medical KB)        (Analysis + JSON)
              │                  │
              └──────┬───────────┘
                     ▼
              Diagnosis Response
         (Predictions, Tests, Urgency,
          Specialists, Follow-ups)
```

## Project Structure

```
medagent-ai/
├── app/
│   ├── main.py                     # FastAPI application & lifespan
│   ├── config.py                   # Environment & settings
│   ├── models/
│   │   └── schemas.py              # Pydantic request/response models
│   ├── services/
│   │   ├── rag_service.py          # RAG: embeddings + ChromaDB retrieval
│   │   ├── llm_service.py          # Google Gemini LLM integration
│   │   ├── diagnosis_engine.py     # Core diagnosis pipeline
│   │   └── session_manager.py      # In-memory session store
│   ├── api/
│   │   └── routes.py               # API endpoints
│   └── data/
│       └── medical_knowledge/      # Disease knowledge base files
│           ├── cardiology.txt
│           ├── respiratory.txt
│           ├── endocrinology.txt
│           ├── gastroenterology.txt
│           ├── neurology.txt
│           ├── infectious_disease.txt
│           ├── musculoskeletal.txt
│           ├── mental_health.txt
│           ├── dermatology_allergy.txt
│           └── renal_hematology.txt
├── static/
│   ├── index.html                  # Frontend UI
│   ├── styles.css                  # Styles
│   └── app.js                      # Frontend logic
├── requirements.txt
├── .env.example
└── README.md
```

## Setup & Installation

### 1. Clone and Navigate

```bash
git clone <repository-url>
cd medagent-ai
```

### 2. Create Virtual Environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
copy .env.example .env
```

Edit `.env` and add your Google API key:

```
GOOGLE_API_KEY=your_actual_api_key_here
```

Get a free API key at: https://aistudio.google.com/apikey

### 5. Run the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Open in Browser

- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (Swagger)
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### `POST /api/diagnose`
Submit patient data for AI-powered diagnosis.

**Request Body**:
```json
{
    "symptoms": ["fever", "cough", "fatigue"],
    "symptom_duration": "5 days",
    "patient_info": {
        "age": 45,
        "gender": "male"
    },
    "vitals": {
        "temperature_f": 101.5,
        "heart_rate": 92,
        "blood_pressure_systolic": 130,
        "blood_pressure_diastolic": 85,
        "oxygen_saturation": 96
    },
    "medical_history": ["Diabetes", "Hypertension"],
    "lab_reports": {
        "WBC": "12,500/mcL",
        "CRP": "45 mg/L"
    }
}
```

### `POST /api/followup`
Submit answers to follow-up questions.

```json
{
    "session_id": "uuid-from-diagnosis",
    "answers": {
        "Do you have a productive cough?": "Yes, yellow phlegm",
        "Have you traveled recently?": "No"
    }
}
```

### `GET /api/session/{session_id}`
Get full session history.

### `GET /api/health`
Health check.

## Medical Knowledge Base

The RAG system is powered by a curated knowledge base covering 25+ diseases across 9 medical specialties:

- **Cardiology**: Hypertension, CAD, Heart Failure, Atrial Fibrillation
- **Respiratory**: Pneumonia, Asthma, COPD, Tuberculosis
- **Endocrinology**: Type 2 Diabetes, Hypothyroidism, Hyperthyroidism
- **Gastroenterology**: GERD, Peptic Ulcer, IBS, Appendicitis
- **Neurology**: Migraine, Stroke, Meningitis
- **Infectious Disease**: Influenza, COVID-19, UTI, Dengue
- **Musculoskeletal**: Rheumatoid Arthritis, Osteoarthritis, Gout
- **Mental Health**: Depression, GAD, Panic Disorder
- **Dermatology/Allergy**: Eczema, Allergic Rhinitis, Anaphylaxis
- **Renal/Hematology**: CKD, Iron Deficiency Anemia

Each disease entry includes symptoms, risk factors, diagnostic criteria, vital sign indicators, lab indicators, recommended tests, specialist referrals, urgency levels, treatment overviews, complications, and follow-up questions.

## How It Works

1. **Patient Data Collection**: The UI collects symptoms, demographics, vitals, history, labs, and lifestyle information through a multi-step form.

2. **RAG Retrieval**: Patient symptoms are encoded into embeddings and matched against the medical knowledge base using ChromaDB's vector similarity search. The top-K most relevant disease contexts are retrieved.

3. **LLM Analysis**: The retrieved medical context, along with full patient data, is sent to Google Gemini. The LLM generates a structured JSON response with differential diagnoses, confidence scores, follow-up questions, test recommendations, and urgency assessment.

4. **Iterative Refinement**: Follow-up questions allow the system to gather more information and refine its predictions through subsequent LLM calls with accumulated context.

## License

This project is for educational and research purposes. Not for clinical use.
