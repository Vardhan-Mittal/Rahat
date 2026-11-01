# RAHAT राहत

**From alert to "I'm safe".** RAHAT turns live flood, heat and cyclone data into a plan for one person: where to go, which road is safe, in their own language, by voice. Then it checks that people in the danger zone actually heard the alert, and sends help to those who didn't make it out.

Built for the **Forge Gen AI Buildathon** · Theme 2: Climate, Resource Infrastructure & Global Supply Resilience · *Autonomous Emergency Response & Logistics Swarm*

**Team Clauder** · Vardhan Mittal, Shubham Bhatt · National Institute of Technology Delhi

**Try it live:** [rahat-pi.vercel.app](https://rahat-pi.vercel.app) (command centre) · [t.me/rahatsevabot](https://t.me/rahatsevabot) (Telegram bot) · [rahat-t2az.onrender.com/api/health](https://rahat-t2az.onrender.com/api/health) (API)

![RAHAT command centre: live satellite map of India with rain radar, official NDMA alert areas and a cyclone, a watchlist ranked by IMD colour level, and the reasons behind Chennai's orange level](docs/images/command-centre.jpg)

---

## The problem

India doesn't lack forecasts. It lacks the last mile. Official warnings (IMD, NDMA SACHET) cover whole districts, are mostly text, and are fire-and-forget: SACHET has sent billions of location-based SMS alerts, but nobody can see who heard one or who is still stuck. Research on flood early warning in India finds alerts often miss the people most at risk, because of literacy, weak networks and trust. Relief coordination still runs on phone calls and WhatsApp groups.

## What RAHAT does

| For | What they get |
|---|---|
| **Citizens** (Telegram, any language, voice or text) | Send an SOS, a voice note or a location. Get back the hazard level with its source, the nearest safe shelter on higher ground, a walking route that avoids the danger zone, a map pin and a spoken alert. |
| **Officials** (web command centre) | A live map of India with rain radar, official alert areas and cyclone tracks; a watchlist ranked by IMD colour level; the agent's reasoning streamed step by step; one-tap approval to alert everyone in a zone; and a live **heard → safe** count. |
| **People in a zone after an alert** | Buttons: ✅ Got it · 🟢 I'm safe · 🔴 Need help. Silence triggers re-sends; "need help" immediately runs a new rescue plan. |

## See it working

A Hindi SOS from central Chennai ("पानी घर में घुस गया है, 4 लोग फँसे हैं", *water has entered the house, 4 people are trapped*), run on the live system during an official IMD rain alert. RAHAT picks a school outside the danger zone on higher ground and draws a walking route that never re-enters the zone:

![Response plan on the live map: a blue walking route from the SOS point to a school shelter outside the dashed danger zone, with nearby hospitals marked](docs/images/response-plan.jpg)

<table>
<tr>
<td width="50%" valign="top">

**The agents, step by step.** Each step shows what it found, which sources it used and how long it took. Yellow chips are automatic fallbacks: here Open-Meteo was rate-limited, so the forecast came from MET Norway, and a busy OpenStreetMap server was swapped for Nominatim.

<img src="docs/images/agent-trace.jpg" alt="Agent trace: Intake, Sentinel, Impact, Logistics, Verifier and Comms, each with its result, sources and timing" width="400">

</td>
<td width="50%" valign="top">

**What the citizen sees.** The alert in IMD's colour, three steps in Hindi, a button to hear it aloud, and one tap to say "I'm safe" or "I need help". On Telegram it also arrives as a voice note with the shelter as a map pin.

<img src="docs/images/citizen-view.jpg" alt="Citizen phone view: orange warning in Hindi with the nearest shelter, a Listen button, and I'm safe / Need help buttons" width="348">

</td>
</tr>
</table>

## Architecture

```mermaid
flowchart LR
  subgraph People
    TG[Telegram bot<br/>text · voice · location]
    CC[Command centre<br/>Next.js]
  end

  subgraph API[FastAPI + LangGraph]
    IN[Intake]
    SE[Sentinel]
    IM[Impact]
    LO[Logistics]
    VE[Verifier]
    CO[Comms]
    LOOP[Heard → safe loop]
  end

  subgraph Live data
    OM[Open-Meteo<br/>forecast · GloFAS · elevation · archive]
    SA[NDMA SACHET]
    GD[GDACS]
    OSM[OSM Overpass / Nominatim]
    RT[OSM foot router / OSRM]
    SV[Sarvam AI<br/>speech in/out]
    CL[Claude<br/>SOS intake · translation]
  end

  DB[(SQLite<br/>opt-ins · SOS · alerts · replies)]

  TG --> IN --> SE --> IM --> LO --> VE
  VE -- route re-enters zone --> LO
  VE --> CO --> TG
  CC -- SSE trace --> API
  CC -- approve zone alert --> LOOP --> TG
  TG -- buttons --> LOOP
  SE --- OM & SA & GD
  IM --- OSM & OM
  LO --- RT
  IN --- CL & SV
  CO --- SV
  API --- DB
```

### The agent pipeline

| Step | What it does | Self-correction |
|---|---|---|
| **Intake** | Reads the SOS in any language (Claude, structured output), extracts the need and the place; geocodes a spoken place name | Falls back to script detection and keyword rules without an LLM; asks for location when it can't find one; refuses points outside India |
| **Sentinel** | Scores the hazard with fixed rules: IMD rainfall thresholds, IMD heatwave criteria against the 1991-2020 normal, GloFAS river discharge vs. seasonal median, plus official SACHET and GDACS alerts | Switches to MET Norway when Open-Meteo is rate-limited; missing forecast data makes the level **unknown**, never safe; an official alert can only raise a level |
| **Impact** | Finds hospitals, schools and colleges; flags those inside the hazard zone; gets elevations | Races two Overpass mirrors, falls back to Nominatim |
| **Logistics** | Picks the nearest school outside the zone on higher ground; routes on foot | Falls back from the foot router to OSRM driving, then to direction-only with a warning |
| **Verifier** | Checks the route geometry leaves the zone and never re-enters; checks every number in the alert comes from a tool | Rejects the shelter and loops back to Logistics (max 2 retries), then flags for a human |
| **Comms** | Fills the alert from verified values only, in Hindi and English; Claude translates to other languages | A translation is rejected if any number changes |

**The LLM never sets a hazard level, picks a shelter or draws a route.** Those come from deterministic code with cited sources, which is how RAHAT avoids hallucinated safety advice.

### Live data sources (no mock data)

Open-Meteo forecast, flood (GloFAS), elevation and historical archive, with MET Norway (forecast) and OpenTopoData (elevation) as automatic fallbacks · NDMA SACHET CAP alerts · GDACS · OpenStreetMap via Overpass and Nominatim · OSM foot router (routing.openstreetmap.de) and OSRM · RainViewer radar · Esri World Imagery · Sarvam AI speech · Claude. People, SOS requests and alert replies are stored only when real users act.

## Repository

```
apps/web/          Next.js command centre (MapLibre, Motion)
services/api/      FastAPI + LangGraph backend and Telegram bot
  rahat/graph/     agent nodes and graph
  rahat/sources/   one module per live data source
  rahat/hazards.py deterministic hazard rules
  rahat/bot.py     Telegram channel and heard → safe loop
  tests/           hazard rule and store tests
design/            original design prototype
```

## Run it locally

Requirements: Python 3.12, Node 20+.

**API**

```bash
cd services/api
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env                             # add keys (all optional)
.venv/Scripts/python -m uvicorn main:app --host 127.0.0.1 --port 8787
```

**Web**

```bash
cd apps/web
npm install
echo NEXT_PUBLIC_API_URL=http://127.0.0.1:8787 > .env.local
npm run dev
```

Open http://localhost:3000.

**Keys** (in `services/api/.env`; the app runs without any of them, with fallbacks):

| Variable | Turns on |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the Telegram bot (create one with @BotFather) |
| `SARVAM_API_KEY` | voice notes in, spoken alerts out |
| `ANTHROPIC_API_KEY` | free-text SOS understanding and alert translation |

**Tests**

```bash
cd services/api && .venv/Scripts/python -m pytest -q
```

## Deploy

- **API:** `services/api/Dockerfile` (runs as a non-root user on port 8000). Run exactly **one** always-on instance, because the bot uses long polling. Our live instance runs on Hugging Face Spaces (Docker); any container host works. Mount a persistent volume at `/data` to keep the SQLite database across restarts. Set the keys above plus `RAHAT_CORS_ORIGINS=https://<your-web-domain>`.
- **Web:** deploy `apps/web` as its own project (we use Vercel) with `NEXT_PUBLIC_API_URL=https://<your-api-domain>`. Serverless platforms can't host the API: the bot and the re-send loop need a process that stays running.

## Credits

Map imagery and labels © Esri, Maxar, Earthstar Geographics · Radar © RainViewer · Map data © OpenStreetMap contributors (ODbL) · Weather and flood data © Open-Meteo (CC BY 4.0), GloFAS / Copernicus · Alerts © NDMA SACHET, GDACS. RAHAT supports, and never replaces, official instructions. In an emergency, call **112**.
