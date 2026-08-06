# Tailtale
### AI-Powered Facial Emotion & Wellness Monitoring for Dogs

**Project Proposal**

Prepared by: Peach [Team members TBD]
Course: Generative AI and Social Media
Sasin School of Management
August 2026

---

## Executive Summary

Tailtale is a proposed web application, built with React and Vite, that uses generative and computer-vision AI to help dog owners understand what their dog is feeling. Owners record or upload short video clips of their dog through the browser; the system samples frames, analyzes facial and body cues against dog-specific facial action research, and returns a plain-language emotion read-out (e.g. relaxed, anxious, in possible discomfort) rendered as a simple emotional chart over time. When the system flags signs that may indicate pain or illness, it surfaces nearby veterinary clinics on an interactive map with contact details, pulled live from a places API, so the owner can act quickly. This capture-to-chart-to-clinic loop is the MVP. A lighter, more playful layer — a generated "bark reply" and a community feed for sharing a dog's avatar and story — is scoped as a later phase (Section 4 roadmap), not part of the course MVP build, so that engineering effort stays concentrated on the harder, riskier problem: getting the emotion read right and being honest about its limits.

The work responds to two real gaps observed in the current pet-tech market: consumer products either track hardware-based vitals (collars, litter sensors) without any facial or expression-based read of mood, or they offer generic chat-based symptom triage with no visual grounding in the pet itself. Tailtale sits in between: a camera-first, dog-only, emotion-and-wellness lens that is honest about being a screening aid, not a diagnostic tool, and that always routes a genuine concern to a licensed veterinarian rather than trying to replace one.

**GitHub repository** (code, setup instructions, and a demo recording will be published here once development begins): `https://github.com/[team-handle]/tailtale` — to be finalized before submission.

This proposal is written for the Generative AI and Social Media course instructor and teammates as the basis for scoping an MVP build, and secondarily for any future collaborator or advisor (e.g. a veterinary partner) evaluating whether the concept is worth piloting.

---

## 1. Introduction

### 1.1 Why This Matters

Pet ownership in Thailand has shifted from a practical arrangement to something much closer to family. Recent industry research puts Thailand's pet population above 5 million animals in 2025, with roughly 3.45 million dogs, and finds that around half of owners describe their pet as "like a child" and over half consider their pet full family. That emotional closeness is colliding with two frictions: dogs cannot self-report pain, hunger, or distress in words, and convenient, trustworthy veterinary access is uneven, especially outside central Bangkok. Owners are left guessing, often turning to social media or forums for reassurance instead of a clinician.

Thailand's pet care market is growing quickly on the back of this shift — market-research estimates place Thailand pet care value at roughly USD 2 billion in 2026 with high-single-digit to double-digit CAGR forecast through the early 2030s, and pet healthcare/telehealth services are called out as one of the faster-growing sub-segments. Globally, the smart pet-tech category is following the same trajectory, with health-monitoring hardware (collars, litter sensors, feeders) projected to grow from roughly USD 6 billion in 2024 toward the mid-20-billions by the early 2030s. The market opportunity is real, but as detailed in Section 3.4, the current products in this space monitor vitals and activity, not expression — which is the gap Tailtale targets.

### 1.2 What the Project Does

In plain terms: an owner opens the app, points their phone or webcam at their dog (or uploads a short clip), and Tailtale analyzes the footage frame-by-frame to estimate the dog's emotional state. The output is a simple, color-coded emotional chart across a handful of everyday categories (e.g. relaxed, alert/excited, anxious, possible discomfort) rather than a clinical diagnosis. If the pattern looks concerning — repeated "possible discomfort" readings, for instance — the app nudges the owner toward a vet visit and shows nearby animal hospitals and clinics on a map with distance, rating, and contact info pulled from a live places API. That loop — capture, analyze, chart, refer — is the full MVP.

Two lighter features are part of the long-term product vision but are explicitly **not** built in the MVP: a generated "bark reply" the owner could play back to their dog for fun, and a community feed where owners could share a 3D avatar of their dog alongside its story. They are described in Section 4 as Phase 2/3 roadmap items so the proposal is honest about what a course-timeline team can actually ship versus what the concept could grow into.

The MVP deliberately narrows scope to dogs only, rather than pets broadly, because dogs have the largest published body of facial-expression research to build on (see 1.3), and because narrowing the training and prompting problem to one species meaningfully improves how reliable an MVP classifier can be within a course-project timeline.

### 1.3 The Generative AI Angle

Tailtale is a multimodal generative AI application, not a single-model wrapper. Three distinct AI capabilities are combined:

- **Vision-language understanding**: sampled video frames are sent to a large vision-language model (e.g. Gemini or Claude's vision endpoints) prompted with structure drawn from published dog facial-expression research, including DogFACS (the dog-adapted Facial Action Coding System) and recent peer-reviewed work showing that general-purpose vision-language models can already interpret dog emotional cues reasonably well without dog-specific fine-tuning. The model returns a structured emotion estimate rather than free text.
- **Generative audio**: a text-to-audio / voice-synthesis model generates a short, non-human bark-like sound clip in response to owner input, used for the playful talk-to-your-dog feature.
- **Generative image / avatar creation**: an image-generation model helps owners turn a photo of their dog into a stylized avatar for the community feed, using models such as current Imagen- or Nano-Banana-class image generators, then lightly processed into a simple stylized card rather than a full rigged 3D model for the MVP.

Framed as an agentic flow (detailed in Section 2.3), the emotion-detection path is the core agent: it reasons over video input, decides whether a threshold for concern is met, and if so calls a tool (the places/maps API) to retrieve real-world clinic data, rather than a single static prompt-response.

### 1.4 Limitations of the Status Quo

Three limitations motivate the project and also bound what it can honestly promise:

- **Scientific limitation**: dog facial-expression recognition is an active but young research area. Peer-reviewed studies (Mao & Liu, 2023; Martvel et al., 2024/2025) show CNN- and landmark-based classifiers reaching useful but imperfect accuracy, and note that breed morphology — for example floppy- versus pointy-eared dogs — measurably affects detection quality. A 2025 study in *Scientific Reports* specifically evaluated large vision-language models on dog emotion recognition, which supports using a general-purpose multimodal model with research-grounded prompting rather than training a bespoke CNN from scratch within a course timeline, but confirms this remains an emerging, not solved, capability.
- **Trust and cost limitation**: existing clinical-grade options (e.g. smart collars with continuous vitals) are accurate but expensive — industry comparisons put a leading vitals collar's running cost near USD 780 over three years — and existing low-cost options (basic pet cameras) provide raw video and generic bark alerts without any interpretation layer. Neither tier gives an owner a same-day, low-cost, expression-based read they can act on.
- **Access limitation**: even when an owner suspects something is wrong, finding and reaching an appropriate clinic quickly is its own friction point, particularly for renters, first-time owners, or anyone outside a neighborhood they know well.

### 1.5 Ethics, Risk, and Governance

Tailtale is a screening and companionship aid, not a diagnostic device, and the product must say so clearly and repeatedly — on first launch, next to every emotion chart, and next to every clinic recommendation — to avoid an owner delaying real veterinary care because the app read "relaxed." This is the single most important governance decision in the project. Practically, that means conservative language (worth a vet check, never a confident diagnostic claim), a visible confidence indicator rather than false precision, and a bias toward over-referring to a vet rather than under-referring. Other governance items: video of a person's home and pet is sensitive, so clips are processed and then deleted or retained only with explicit, revocable consent, and never used to train external models without opt-in; community-feed content needs lightweight moderation given it is generative-AI-assisted content shared publicly; generated bark audio and avatar images must be labeled as AI-generated; and all third-party model and API usage is bound by each provider's terms of service, with no API keys ever stored client-side or committed to the repository.

---

## 2. Implementation

### 2.1 System Description

Tailtale is composed of five major components:

- **Capture client (React + Vite)**: browser-based camera/live-video capture and short-clip upload, built as a single-page app for fast iteration.
- **Emotion-analysis service**: receives sampled frames, calls the vision-language model with a research-grounded prompt template, and returns a structured emotion payload (category, confidence, short rationale).
- **Chart and history layer**: stores emotion readings per dog profile and renders them as a simple time-series/radar chart so owners can see trends, not just single readings.
- **Clinic-finder tool**: triggered when readings cross a concern threshold; calls a places/maps API to return nearby veterinary clinics and renders them on an interactive map with contact info.
- **Community layer**: authentication, dog profiles, avatar generation, and a simple feed (post, like, comment) for sharing a dog's avatar and story; also hosts the generative bark-reply feature.

**Figure 1. High-level data flow**

```
Core emotion path:
1. Camera / video upload
     -> 2. Frame sampler pulls key frames
     -> 3. Vision-language emotion agent (tool call)
     -> 4. Emotion payload (category + confidence) saved to dog history
     -> 5. Emotion chart UI updates
     -> 6. IF concern threshold met: Clinic-finder tool call (Places API) -> map + clinic list

Community layer (separate, lighter paths):
  Photo -> image-gen avatar -> feed post
  Text/voice prompt -> audio-gen bark reply
```

### 2.2 Stack and Integration

- **Frontend**: React 18 + Vite, deployed as a static site; Tailwind for styling; a lightweight state layer (React Query or Zustand) for async data.
- **Backend**: a thin serverless API layer (Node/Express or Vite's own server functions) that proxies all model and third-party API calls, so the frontend never calls a model or maps API directly and API keys stay server-side.
- **Vision-language model**: a hosted multimodal model API (Gemini or Claude vision endpoints) for frame-level emotion inference; model choice will be finalized based on a small accuracy/cost bake-off during Phase 1.
- **Audio generation**: a text-to-audio / voice model API for the bark-reply feature.
- **Image generation**: an image-generation model API for avatar creation from an uploaded dog photo.
- **Maps / places**: a places API (e.g. Google Places) for the clinic-finder feature, rendered with an interactive map component.
- **Data store**: a managed Postgres instance (e.g. Supabase) for dog profiles, emotion history, and community posts; object storage for uploaded photos/clips.
- **Secrets/config**: all API keys and credentials are stored as environment variables in the deployment platform's secret manager, never committed to the repository or placed in this document; local development uses an untracked `.env` file listed in `.gitignore`.

### 2.3 Agentic Flow

Tailtale uses a light, single-hop agentic pattern rather than a fully autonomous multi-step agent. The emotion-analysis service acts as the decision point: it calls the vision-language model as a tool to produce a structured emotion reading, applies a rule (is this reading in the concern band, and has it repeated?), and conditionally calls a second tool — the places API — only when that rule fires, rather than on every request. This keeps the flow auditable and cheap: the map/clinic lookup, which costs real money per call, is not invoked for every routine relaxed reading. A stretch goal for a later phase is a second agent hop that drafts a short, plain-language note the owner could optionally share with a vet summarizing recent emotion trends before a visit; this is out of scope for the MVP and is not built for the version described here.

### 2.4 Repository and Reproducibility

Repository: `https://github.com/[team-handle]/tailtale` (placeholder, to be created at project kickoff). The repository will include a README with setup steps (clone, `npm install`, copy `.env.example` to `.env` with placeholder key names only, `npm run dev`), a short demo video or GIF, and a CONTRIBUTING note for teammates. No real API keys will ever appear in the repository or in this document; the `.env.example` file will list only variable names such as `VISION_MODEL_API_KEY` and `MAPS_API_KEY`.

### 2.5 Emotion Classification: Prompting and Validation Method

Section 1.4 flags dog facial-expression AI as an emerging, not solved, capability — so the proposal needs a concrete answer for how the prompt is built and checked, not just a citation. The plan has three parts:

- **Structured prompting grounded in DogFACS.** Rather than asking the model an open-ended "how does this dog feel?", the prompt walks it through specific, observable Action Units drawn from DogFACS (e.g. ear position — forward/back/flattened; brow tension; mouth — open/closed/lip retraction; eye whites visible or not; tail carriage if visible) and asks it to score each cue before producing a final category and a confidence value. This mirrors how the peer-reviewed literature itself analyzes dog expressions, rather than relying on the model's unguided intuition.
- **Few-shot calibration using existing labeled datasets.** Two public, labeled datasets identified during research — Balico's "Dog Emotion Image Classification Dataset" and Tanwar's "Pet's Facial Expression Image Dataset" (both on Kaggle) — will be used as an initial calibration and held-out test set. A small labeled sample from each is included in the prompt as few-shot reference examples; a separate held-out sample (roughly 40–60 images, not shown to the model during prompt design) is used purely to measure agreement between the model's output and the dataset's human-assigned label before the feature is considered "working."
- **A published, pre-registered accuracy bar.** Before build, the team will set a minimum agreement threshold (e.g. majority-category agreement on the held-out set) that the classifier must clear to ship in the MVP; if it doesn't clear the bar, the fallback is to narrow the output to fewer, coarser categories (e.g. just "relaxed" vs. "not relaxed — worth a look") rather than force a five-category system the model can't reliably support. This keeps the team from quietly shipping an unvalidated classifier just because a demo happened to look good.

This is deliberately a lightweight, course-scale validation method, not a clinical study — it is designed to catch the most likely failure mode (a model that sounds confident but is not actually distinguishing categories reliably) before the feature reaches a real dog owner.

---

## 3. Results and Analysis

This document is being submitted at the proposal stage, before the build phase. This section therefore lays out the evaluation plan, target artifacts, and comparative analysis that will anchor the Results section of the final report, rather than presenting finished output. Placeholders below (screenshots, sample charts, accuracy numbers) will be replaced with real evidence once the MVP is built.

### 3.1 Planned Evidence

- Screenshots of the capture flow, the emotion chart, and the clinic-finder map, captured from a working build.
- A short table of sample clips (owner-provided, with consent) alongside the model's emotion reading and a human judgment (owner or a volunteer with dog-training experience) of whether the reading looked reasonable — an informal accuracy check, not a clinical validation.
- A sample generated avatar and bark-reply clip, captioned with the prompt/photo used to produce them.

### 3.2 What Is Expected to Work Well, and What Will Likely Be Brittle

Based on the research reviewed in Sections 1.3–1.4, the vision-language approach should perform reasonably on clearly happy/relaxed versus alert/aroused distinctions, since these map to visible, well-documented cues (ear position, mouth tension, gaze). It is expected to be noticeably less reliable on the highest-stakes category — possible pain or illness — which published research explicitly flags as harder to read from a still or short clip, and which varies more by breed and individual dog. This will be treated as the category where the product's language must be most conservative (a nudge to consider a check-up, never a confident claim), and where the most informal testing is planned before trusting the feature.

### 3.3 Informal Testing Plan

Once an MVP exists, a small, informal round of testing is planned with 8–12 dogs from classmates' and friends' households, covering a mix of breeds and ear/face shapes given the breed-sensitivity noted in the literature. Owners will rate whether each emotion reading matched what they know about their dog on a simple scale, and cases where the app suggested a vet visit will be logged separately to see whether that felt appropriately calibrated — not alarmist, not dismissive.

### 3.4 Competitive Landscape

The closest comparable products fall into two categories: hardware-first health monitors and app-first wellness/symptom tools. None of the products found analyze facial expression from live or recorded video to infer mood — Tailtale's core differentiator.

| Product | Category | What it does | Gap vs. Tailtale |
|---|---|---|---|
| Furbo Dog Camera | Hardware camera | Remote video, treat-tossing, bark alerts, AI-flagged activity notifications. | Detects that barking happened, not what the dog is feeling; no expression analysis. |
| PetCube | Hardware ecosystem | Cameras, GPS trackers, and fountains with AI-driven activity alerts across a unified app. | Same activity-alert model as Furbo; no facial/emotion layer, no clinic-finder. |
| PetPace Smart Collar | Wearable vitals monitor | Continuous vital-sign tracking (temperature, pulse, respiration) with a vet-facing dashboard; strong clinical grounding. | Requires a paid collar (roughly USD 780 over 3 years per industry comparisons); measures physiology, not facial expression; no community/avatar layer. |
| FitBark / Invoxia | Wearable activity tracker | Activity and, for Invoxia, basic vitals plus GPS. | Activity-level data, not emotion; separate device required. |
| PerkyPet AI / PetNexa | Symptom-chat apps | Owner describes symptoms in text/chat; AI gives breed-aware guidance and a wellness score from logged data. | Relies on the owner noticing and typing a symptom first; no camera-based, passive read of expression. |
| **Tailtale (proposed)** | Browser app, camera-first | Live/recorded video, dog-specific facial emotion read, trend chart, clinic-finder map when concerning, plus community and bark-reply. | (own row, for reference) |

### 3.5 Economics

The dominant recurring cost for Tailtale is the per-call price of the vision-language model, since every analysis request sends image frames as input tokens. Using published 2026 API pricing as a planning baseline (rates vary by provider and change frequently, so these are order-of-magnitude estimates for the proposal, not a committed budget):

| Cost driver | Basis | Rough estimate |
|---|---|---|
| Vision-language emotion read (one clip, a few sampled frames) | Budget-tier multimodal model, image + short text prompt/response | Roughly USD 0.01–0.05 per analysis, depending on model tier and frame count |
| Avatar image generation | Per-image generation, standard resolution | Roughly USD 0.04–0.15 per avatar |
| Bark-reply audio generation | Short audio clip per request | Low single-digit cents per clip (provider-dependent; to be benchmarked) |
| Places / maps clinic lookup | Per-request places API call, only fired on concern readings | Low single-digit cents per lookup; usage capped by the concern-threshold gating in 2.3 |
| Hosting + database | Static frontend hosting + managed Postgres, low MVP traffic | Free-tier or low tens of USD per month at course-project scale |

At MVP/course-project scale (a few dozen active testers), total monthly API spend should stay in the tens of USD, comfortably inside typical free-tier or trial credits. If Tailtale were pursued beyond the course as a real product, a freemium model looks most realistic given the comps: a free tier covering basic emotion checks and the community feed, with a paid tier (roughly the price band of the symptom-chat apps reviewed, i.e. a few USD per month) unlocking trend history, multiple dog profiles, and priority clinic recommendations, similar in spirit to the subscription-vs-subscription-free split observed among hardware competitors.

---

## 4. Conclusion

Tailtale proposes a narrow, honest slice of a large and growing pet-care market: use generative, multimodal AI to give dog owners a same-day, camera-based read on their dog's mood and possible discomfort, and connect that read directly to real veterinary options nearby — something none of the closest competitors currently do, because they monitor either raw activity/vitals or owner-typed symptoms, not facial expression. The community and bark-reply features add a lighter, shareable layer that can help the app spread the way pet-owner communities already spread content about their animals, without being the core value proposition.

The main lesson from scoping this proposal is that the hardest part of the project is not the engineering — React/Vite, a vision-model API call, and a maps integration are all well-trodden — it is being disciplined about what the AI is allowed to claim. The published research is clear that dog facial-expression AI is promising but immature, and breed variation (such as ear shape) measurably affects accuracy. The product's credibility, and the safety of the dogs using it, depends on the app consistently under-claiming rather than over-claiming.

### Roadmap and Extensions (Next 12–24 Months)

- **Phase 1 (course MVP)**: upload/record, emotion chart with conservative, plain-language categories, and a clinic-finder map. No live-stream yet; no full 3D avatars.
- **Phase 2**: community feed and stylized avatar sharing; basic moderation for shared content.
- **Phase 3**: true live-video analysis, and the bark-reply feature, once the core emotion pipeline has been validated informally against a broader set of dogs.
- **12–24 month horizon**: as dog-specific vision-language benchmarks mature, swap in higher-accuracy, dog-fine-tuned models as they become available; explore an opt-in partnership with a veterinary clinic chain so a flagged reading can offer direct booking, not just a map pin; and, if pursued as more than a course project, commission a small validation study with a veterinary behaviorist before making any stronger claims about accuracy.

This roadmap ties back to the problem framed in Section 1.1: Thai dog owners increasingly treat their dogs as family, but dogs cannot say when something is wrong, and the tools available today either watch vitals without emotion or chat about symptoms without a camera. Tailtale's contribution is a modest, well-scoped bridge between those two, provided it stays disciplined about its own limitations.

---

## References

- Camicoo. (2026, April 17). *Best dog health monitor 2026: 6 collars compared*. https://camicoo.com/blog/en/dog-health-monitor-2026/
- Chiang Rai Times. (2026, March 8). *Thailand pet economy boom in 2026, luxury hotels, organic food, and new trends*. https://www.chiangraitimes.com/news/thailand-pet-economy-boom/
- Curlscape. (2026, July). *Google Gemini API pricing guide 2026: Flash, Pro, and Vertex AI*. https://curlscape.com/blog/google-gemini-api-pricing-guide-2026
- Analytics Insight. (2026, July 1). *Best pet tech gadgets of 2026 compared: AI feeders, GPS trackers, cameras and health monitors*. https://www.analyticsinsight.net/amp/story/gadgets/best-pet-tech-gadgets-of-2026-compared-ai-feeders-gps-trackers-cameras-health-monitors
- Anwar, A. (2023). *Pet's facial expression image dataset* [Data set]. Kaggle. https://www.kaggle.com/datasets/anshtanwar/pets-facial-expression-dataset
- Balico, D. S. (2023). *Dog emotion image classification dataset* [Data set]. Kaggle. https://www.kaggle.com/datasets/danielshanbalico/dog-emotion
- Google AI for Developers. (2026, July 30). *Gemini Developer API pricing*. https://ai.google.dev/gemini-api/docs/pricing
- Grand View Research. (2025, September 17). *Thailand pet services market size and outlook, 2023–2030*. https://www.grandviewresearch.com/horizon/outlook/pet-services-market/thailand
- Mao, Y., and Liu, Y. (2023). Pet dog facial expression recognition based on convolutional neural network and improved whale optimization algorithm. *Scientific Reports*, 13(1), 3314. https://doi.org/10.1038/s41598-023-30442-0
- Martvel, G., Abele, G., Bremhorst, A., Canori, C., Farhat, N., Pedretti, G., Shimshoni, I., and Zamansky, A. (2024). DogFLW: Dog facial landmarks in the wild dataset (Version 1) [Data set]. *arXiv*. https://doi.org/10.48550/ARXIV.2405.11501
- Martvel, G., Zamansky, A., Shimshoni, I., and Bremhorst, A. (2025). Investigating the capabilities of large vision language models in dog emotion recognition. *Scientific Reports*, 15. https://doi.org/10.1038/s41598-025-25199-7
- Mordor Intelligence. (2026, January 9). *Thailand pet food market size and share outlook to 2031*. https://www.mordorintelligence.com/industry-reports/thailand-pet-food-market
- PawTech Review. (2026). *Best pet health trackers 2026, ranked*. https://pawtechreview.com/pawtech-health
- PerkyPet AI. (2026, January 21). *Top 5 pet wellness tracking apps: 2026 guide*. https://perkypetai.com/tips/the-top-5-pet-wellness-tracking-apps
- PetNexa. (2026, March 8). *8 best pet health apps in 2026: A complete guide for pet parents*. https://www.petnexa.app/blog/best-pet-health-apps-guide-2026
- Modern Pet Tech. (2026, January 25). *Top 4 pet monitoring tools for behavior in 2026*. https://modernpettech.com/pet-monitoring-tools-for-behavior-4/
- Smart Home Explorer. (2026, April 27). *Best smart pet wellness ecosystems 2026: Health, feeding and activity*. https://www.smarthomeexplorer.com/guides/best-smart-pet-wellness-ecosystem-connected-2026
- SiiPet. (2026, March 18). *Smart pet products: Must-have tech for 2026 pet care*. https://siipet.com/blogs/knowledge/smart-pet-products-must-have-tech-for-2026-pet-care
- Unnamed authors. (2025, October 24). Automated facial landmark analysis vs. manual coding: Accuracy in dog emotional expression classification [Preprint]. *bioRxiv*. https://www.biorxiv.org/content/10.1101/2025.10.23.683931v1.full
- Vyansa Intelligence. (2026). *Thailand pet care market size, share and forecast 2026–2032*. https://www.vyansaintelligence.com/industry-report/thailand-pet-care-size
