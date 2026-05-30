# GDPR Frontend Prototype

This folder contains the hackathon frontend prototype for the GDPR data discovery workflow.

## What it shows

- Admin dashboard with scan KPIs
- Findings workbench with filters
- Employee review view with human-in-the-loop actions
- Mock scan results loaded from `data/gdpr_training_dataset.json`

## Run locally

From the repository root:

```bash
node frontend/server.mjs
```

Then open:

```text
http://localhost:4173/frontend/index.html
```

## Backend integration

The frontend currently reads static JSON from:

```js
./data/gdpr_training_dataset.json
```

When the backend is ready, replace `DATA_URL` in `app.js` with the API endpoint that returns the same field structure.

## Deploy online

This repository includes a GitHub Actions workflow at:

```text
.github/workflows/deploy-frontend.yml
```

After the changes are pushed to GitHub, enable GitHub Pages with **GitHub Actions** as the source:

```text
Repository Settings -> Pages -> Build and deployment -> Source: GitHub Actions
```

The workflow deploys the `frontend` folder as a static website.
