# InterviewRunway

A local-first technical interview practice app. It records code mutations and optional microphone audio on one monotonic session clock, aligns transcript words with edits, scores a domain rubric, and creates a downloadable review card.

## Run with Docker

Prerequisites: Docker Desktop, Node.js/npm for local frontend builds, and Ollama installed on the host if you want LLM-based feedback.

```powershell
ollama pull qwen3:8b
docker compose up --build
```

Open <http://localhost:5173> and allow microphone access. API health is at <http://localhost:8000/api/health>. Docker Compose provides Redis, the FastAPI manager, the processing worker (FFmpeg + faster-whisper), and the frontend. The worker downloads its Whisper model on its first audio transcription. To use a different local Ollama model, set `OLLAMA_MODEL` in `.env` before starting Compose.

If Ollama is unavailable, the worker completes with a clearly labeled local heuristic report. Audio transcription is optional; when faster-whisper cannot load, code events and the rest of the report still process.

## Run locally without Docker

Open two PowerShell terminals in the project directory. Install the backend requirements once:

```powershell
python -m pip install -r backend/requirements.txt
```

For local audio transcription, install `backend/requirements-worker.txt` instead; it includes the optional faster-whisper runtime and can require native wheels/model downloads for your Python version.

In terminal one, use the in-memory store and run the manager. This mode processes submitted sessions in a FastAPI background task; it is for local development, not multi-process deployment.

```powershell
$env:PYTHONPATH = "backend"
$env:STORAGE_BACKEND = "memory"
$env:AUDIO_DIR = "data/sessions"
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

In terminal two:

```powershell
npm install
npm run dev
```

Open the Vite URL printed in the terminal. Use `ollama pull qwen3:8b` first for local LLM feedback; the API otherwise uses its disclosed heuristic fallback. Local Whisper may download model weights the first time audio is processed.

## Tests and build

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s backend/tests -v
npm run build
```

## What is included

- Four structured tracks: backend core system design, high-throughput data infrastructure, high-performance frontend architecture, and distributed ML platform design.
- Per-track phase rubrics, evidence vocabulary, preparation notes, and question banks are exported through `backend/domain_knowledge.py` and injected into the Ollama system context.
- Original company-round-style labels, topic tags, and progressive hint ladders are included as metadata; the app does not scrape or reproduce third-party problem descriptions.
- Contest simulation uses a 90-minute clock, records complexity/speech cadence, and applies a separate five-point adjustment for each revealed hint.
- Hints unlock after 12 seconds without detected voice energy or editor changes. Voice detection is a local audio-energy heuristic, not speech recognition.
- CodeGuru-style static checks review structural abstractions, resource/exception signals, and language idioms; Python drafts also receive an AST parse. Findings are coaching signals, not correctness verdicts.
- Evaluation flags include `STRUCTURAL_PREMATURE_IMPLEMENTATION` for actual code edits before the five-minute scope window, plus transcript-backed unmet rubric expectations.
- Monaco editor mutation capture, a shared `performance.now()` session clock, microphone activity visualization, and one-second browser audio chunks.
- IndexedDB outbox for code/audio events during connection loss; queued events retry in timestamp order when connectivity returns.
- Redis-backed manager/worker pipeline, optional local word-timestamp transcription with faster-whisper, Ollama JSON evaluation, language-aware static review, timeline alignment, interaction metrics, and PNG review card.
- Interactive timeline, clickable code and hint events, domain rubric, CodeGuru-style review, contest cadence metrics, evaluation flags, assumption flag, preparation masterclass, and share-card download.

## Local-first scope

This is a runnable portfolio MVP, not a hardened public service. API sessions currently have no user authentication or retention policy; do not expose the compose ports to an untrusted network. Browser microphone capture requires localhost or HTTPS. The audio container is browser WebM/Opus; the worker uses FFmpeg through faster-whisper rather than assuming that MediaRecorder emits PCM WAV.