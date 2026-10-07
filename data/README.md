# Data Folder Usage Guide

This folder contains synthetic/demo-only files for local testing.

## UI Claim Upload Dummy Files

Use these files when creating a draft claim in the UI and uploading attachments:

- `claim-upload-photos/`
  - `car-front-damage.jpg`
  - `car-side-view.png`
  - `car-rear-view.jpg`
- `claim-upload-documents/`
  - `repair-estimate-demo.pdf`
  - `incident-report-demo.pdf`
  - `vehicle-damage-photo-reference.png`

## How to use in the UI

1. Start API and UI from the project root.
2. Open the claim creation form.
3. Upload photos from `data/claim-upload-photos/` in **Pictures of the car**.
4. Upload files from `data/claim-upload-documents/` in **Supporting documents**.
5. Submit the draft claim for adjudication.

## Upload limits (must match UI/API validation)

- Photos: up to **3** files, **JPEG/PNG/WebP**, max **5 MB** each.
- Supporting documents: up to **10** files, **PDF/JPEG/PNG/WebP**, max **10 MB** each.

## Notes

- These are dummy files for demo/test use only.
- Do not upload real customer or sensitive documents.
- Policy and seeded claim fixtures remain in `policies.json`, `demo_claims.json`, and `policies-pdf/`.
- Seeded scenarios include `fast-track-collision-complete`. In `scripts/seed_demo.py`, this scenario is auto-settled by a synthetic reviewer step after adjudication so the demo database contains paid/fast-tracked examples.
