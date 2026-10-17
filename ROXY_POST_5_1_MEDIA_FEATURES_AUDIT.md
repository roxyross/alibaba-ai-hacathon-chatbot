# ROXY-AI — POST-PHASE 5.1: MEDIA FEATURES AUDIT (IMAGE & VIDEO)
*(Workstream M Deliverable)*

## 1. Media Generation Architecture Overview

Roxy-AI provides creative media generation capabilities across two studios:
1. **Image Studio:** [ImageStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/ImageStudio/ImageStudio.tsx) and [backend/src/app/images/](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/images/)
2. **Video Studio & Canvas Inpaint:** [VideoStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/VideoStudio/VideoStudio.tsx) and [backend/src/app/media/](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/media/)

```mermaid
graph TD
    User -->|Submit Prompt| UI[Image / Video Studio UI]
    UI -->|POST /api/v1/media/jobs| Gateway[Media API Gateway]
    Gateway --> JobTable[(media_jobs Table)]
    Gateway --> Dispatcher[Asynchronous Job Dispatcher]
    
    Dispatcher -->|Image Request| Imagen[Google Imagen 3 / Flux Engine]
    Dispatcher -->|Video Request| Veo[Google Veo 3.1 Engine]
    
    Imagen --> AssetStorage[Asset Registry & S3/Local Storage]
    Veo --> AssetStorage
    
    UI -->|Poll Status GET /api/v1/media/jobs/{id}| Gateway
    Gateway -->|Status: completed + url| UI
```

---

## 2. Models, Configurations & Parameters

| Studio | Supported Models | Configurable Parameters | Storage Location |
| :--- | :--- | :--- | :--- |
| **Image Studio** | `imagen-3.0-generate-002` (Google), `flux-schnell`, `flux-dev` (Black Forest Labs) | Aspect Ratio (`1:1`, `16:9`, `9:16`, `4:3`, `3:2`), Quality (`standard`, `hd`), Style Preset | `generated_images` table + `/static/images/` |
| **Video Studio** | `veo-3.1-generate-preview` (Google), Canvas Inpaint Engine | Resolution (`720p`, `1080p`), Duration (`5s`, `10s`), Audio generation toggle, Camera Motion | `media_jobs` table + `/static/videos/` |

---

## 3. Asynchronous Job Registry & Canvas Inpainting

- **Job Lifecycle:** Generative media operations dispatch asynchronously to prevent HTTP gateway timeouts. The job transitions through `queued` → `processing` → `completed` (or `failed`).
- **Canvas Inpainting Engine:** [google_engine.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/media/google_engine.py) provides coordinate-bounded inpainting and brush mask blending for localized video edits.
- **Fail-Safe Error Reporting:** If the upstream provider reports quota exhaustion (HTTP 429) or invalid prompt safety filters, the job status updates to `failed` with a clear user explanation.

---

## 4. Test Verification Evidence

- `backend/tests/integration/test_phase10_image_studio.py`: Image generation request validation, style preset injection, and thumbnail gallery listing (**PASS**).
- `backend/tests/integration/test_phase35_media_registry_and_jobs.py`: Media job state machine, polling, retry on transient failure (**PASS (3/3)**).
- `backend/tests/integration/test_phase36_video_studio_and_canvas.py`: Video generation dispatch, canvas inpaint parameter validation, asset library filtering (**PASS (2/2)**).

### Live Generation Caveat
- Real GPU inference against Google Imagen/Veo requires active billing and API tokens (`GEMINI_API_KEY`). Local test execution verified all dispatch schemas and job lifecycles using verified mock engines.
