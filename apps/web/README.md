# RAHAT command centre (web)

Next.js 16 + React 19 app for officials: live map (MapLibre, Esri imagery, RainViewer radar, NDMA SACHET areas), the watchlist ranked by IMD level, the agent trace streamed over SSE from the API, alert approval and the live heard → safe funnel.

```bash
npm install
echo NEXT_PUBLIC_API_URL=http://127.0.0.1:8787 > .env.local
npm run dev        # http://localhost:3000
npm run build      # production build (copies the MapLibre worker into public/)
```

Components live in `components/`, the API client and types in `lib/`. See the [main README](../../README.md) for the architecture and the backend.
