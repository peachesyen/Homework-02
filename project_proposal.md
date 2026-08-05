# PetEmotion AI: Real-Time Multimodal Pet Emotion Recognition, Behavioral Analytics, and Social Media Community

**Course:** MGT 575 — Generative AI & Social Media
**Project Title:** PetEmotion AI: Real-Time Multimodal Pet Emotion Recognition, Behavioral Analytics, and Social Media Community
**Repository:** https://github.com/peachesyen/petemotion-ai *(final project app repository — to be created when the app build begins; this document is submitted as part of `peachesyen/Homework-02`, the HW2 video-reel-agent repository)*
**Authors:** Peach

---

## Executive Summary

**PetEmotion AI** is an end-to-end web application that decodes pet emotional states in real time through multi-frame video analysis using Google Gemini 1.5 Flash. By processing 20 sequential images captured across a 4-second camera feed window, the system evaluates micro-expressions (ear angles, eye postures, body language) to classify mood into five primary categories (**Sad, Hungry, Bored, Upset, Happy**). The system connects AI analysis directly to a **reactive 3D pet avatar** built with Three.js, logs longitudinal mood trends on an **analytics dashboard**, and enables users to convert emotional assessments into shareable content on **DogSocial**—an integrated pet community feed.

---

## 1. Introduction & Market Context

### 1.1 Problem Statement
Pet owners often miss subtle non-verbal signals indicating stress, boredom, or early-stage illness in domestic animals. Traditional pet technologies focus almost exclusively on hardware-driven physical activity tracking (e.g., GPS collars, step counting), neglecting real-time emotional and behavioral states.

### 1.2 Generative AI Solution
Static computer vision models fail due to high morphological variation across breeds. Multimodal Generative AI (Gemini 1.5 Flash) solves this by processing temporal sequences of images (20 frames) simultaneously, evaluating contextual cues (e.g., distinguishing a relaxed blink from a fatigue squint or a playful yawn from a stress yawn).

### 1.3 Target Audience & GenAI Value
* **Pet Owners:** Wanting instant, actionable feedback on their pet's emotional state.
* **Social Content Creators & Influencers:** Seeking auto-generated, AI-verified mood posts and story overlays for social channels.
* **Veterinary Professionals:** Utilizing 7-day longitudinal emotional distribution charts during routine checkups.

---

## 2. System Implementation & Architecture

```
                                  [SYSTEM ARCHITECTURE]

 ┌───────────────────┐        ┌───────────────────────┐        ┌─────────────────────────┐
 │ Webcam / Video    │ ─────> │ 20-Frame Capture Engine│ ─────> │ Gemini 1.5 Flash API    │
 │ (Live Feed Input) │        │ (1 frame / 200ms)     │        │ (Multimodal Base64 Array│
 └───────────────────┘        └───────────────────────┘        └────────────┬────────────┘
                                                                            │
 ┌──────────────────────────────────────────────────────────────────────────┴────────────────────────┐
 │                                 STRUCTURED JSON OUTPUT                                           │
 └──────────────┬───────────────────────────────┬────────────────────────────────┬──────────────────┘
                ▼                               ▼                                ▼
 ┌─────────────────────────────┐ ┌─────────────────────────────┐ ┌─────────────────────────────────┐
 │ Reactive 3D Avatar          │ │ 7-Day Mood Analytics        │ │ DogSocial Community             │
 │ (Three.js / R3F Mesh Control│ │ (Recharts Stacked Charts)   │ │ (Auto-Post & Community Timeline)│
 └─────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────────────┘
```

### 2.1 Core Subsystems

1. **Multi-Frame Video Ingestion:** Uses an HTML5 `<canvas>` buffer to capture 20 base64 PNG frames across a 4-second period at 200ms intervals.
2. **Gemini API Pipeline:** Sends the array of 20 images in a single payload to `@google/genai`, enforcing JSON schema output for confidence scores, species detection, care tips, and 3D avatar animation control parameters.
3. **Reactive Three.js Engine:** Direct parametric binding between Gemini JSON output (`headTiltAngle`, `blinkRate`, `primaryColorHex`) and the Three.js mesh render loop via `@react-three/fiber`.
4. **DogSocial Feed & Analytics:** Built-in social network module enabling post generation with AI mood badges, "Woof" engagement metrics, and Recharts 7-day longitudinal emotional tracking graphs.
5. **Emergency Geolocation:** Automated trigger querying nearby veterinary hospitals via Geolocation API + OpenStreetMap whenever distress scores exceed 70%.

---

## 3. Technology Stack & Integration

| Subsystem | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend UI** | React 18 + Vite + Tailwind CSS | Fast SPA rendering and UI layout |
| **AI Processing** | `@google/genai` (Gemini 1.5 Flash) | Multi-frame vision & JSON emotion output |
| **3D Rendering** | Three.js / `@react-three/fiber` | Real-time reactive pet avatar |
| **Data Viz** | Recharts / Chart.js | 7-day emotional trend dashboard |
| **Audio** | Browser Web Audio API | Pitch-modulated synth bark vocalizations |
| **Location** | `navigator.geolocation` + Leaflet | Nearby pet hospital recommendation |

---

## 4. Results, Limitations, & Governance

### 4.1 System Performance
The multimodal approach using 20 temporal frames provides higher context accuracy than single-frame classification by eliminating false positives caused by momentary facial movements (e.g., natural blinks vs. lethargy).

### 4.2 Limitations & Ethics
* **Veterinary Disclaimer:** Clear UI banners state that AI emotion detection provides behavioral approximations and does not substitute for licensed veterinary diagnosis.
* **Privacy & API Hygiene:** All API keys are loaded via client-side `.env` variables excluded from public version control.

---

## 5. Work Plan & Deliverables Checklist

- [x] `project_proposal.md` matching course goals
- [x] Public GitHub Repository with clear setup README
- [ ] Full source code for 20-frame capture, Gemini pipeline, 3D render engine, analytics, and DogSocial feed
- [x] Video Reel submission generated via HW2 Agent
