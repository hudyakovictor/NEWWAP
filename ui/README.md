# DEEPUTIN Forensic SCAP v2.0

A forensic photo comparison application for 3D facial analysis and identity verification.

## Features

- **Dashboard**: Overview of forensic analysis metrics and system status
- **Gallery**: Browse and search photo archives with persona clustering
- **Timeline**: Chronological analysis of biometric constants over time
- **Compare**: Side-by-side photo comparison with Bayesian evidence analysis
- **3D Mesh Viewer**: Interactive 3D mesh visualization with heatmap overlay
- **Matrix Analysis**: N×N similarity matrix for batch photo comparison
- **Calibration**: Manage calibration dataset and override recommendations
- **Settings**: Job management for batch feature extraction

## Tech Stack

- **Frontend**: React 18, TypeScript, Vite
- **3D Rendering**: Three.js, React Three Fiber, React Three Drei
- **UI Components**: Lucide Icons, Framer Motion
- **Charts**: Recharts
- **Styling**: Tailwind CSS

## Development

### Install Dependencies

```bash
npm install
```

### Run Development Server

```bash
npm run dev
```

### Build for Production

```bash
npm run build
```

### Type Checking

```bash
npx tsc --noEmit
```

## Project Structure

```
ui/
├── src/
│   ├── components/       # Reusable UI components
│   │   ├── compare/      # Photo comparison components
│   │   ├── 3d/           # 3D mesh viewer
│   │   ├── gallery/      # Gallery components
│   │   └── NotificationSystem.tsx
│   ├── hooks/            # Custom React hooks
│   │   └── useJobPolling.ts
│   ├── pages/            # Page components
│   │   ├── Dashboard.tsx
│   │   ├── Gallery.tsx
│   │   ├── Timeline.tsx
│   │   ├── Compare.tsx
│   │   ├── Calibration.tsx
│   │   └── Settings.tsx
│   ├── types/            # TypeScript type definitions
│   │   └── api.ts
│   ├── utils/            # Utility functions
│   │   ├── heatmap.ts
│   │   └── clusterColors.ts
│   ├── App.tsx
│   └── main.tsx
├── public/               # Static assets
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## API Integration

The frontend communicates with the backend via REST API endpoints:

- `/api/photos/main` - List main dataset photos
- `/api/photos/calibration` - List calibration photos
- `/api/evidence/compare` - Compare two photos
- `/api/evidence/matrix` - Build similarity matrix
- `/api/persona-clusters` - Get persona clusters
- `/api/timeline-summary` - Get timeline data
- `/api/calibration/summary` - Get calibration status
- `/api/recommendations` - Get calibration recommendations
- `/api/jobs/extract` - Start batch extraction job
- `/api/jobs/{job_id}` - Get job status
- `/api/mesh/{dataset}/{photoId}` - Get 3D mesh data

## License

Proprietary - Forensic Use Only
