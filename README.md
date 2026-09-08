# PDF Anonymizer

A local, single-user web app for reversibly redacting areas of a PDF (client
names, addresses, etc. in invoices/contracts).

Everything runs on your machine only — no accounts, no external calls.

## How it works

1. **Upload** a PDF and drag rectangles over the areas to anonymize.
2. On **Anonymize**, for each selected area the app:
   - Takes a high-resolution snapshot of that exact area and encrypts it
     (AES via Fernet) with a key stored locally at `data/secret.key`.
   - Saves the encrypted snapshot in a local SQLite database
     (`data/redactions.db`) under a short random ID.
   - **Permanently strips** the underlying text/graphics in that area from
     the PDF (not just paints over it — a plain box would leave the real
     text copy-pasteable underneath).
   - Stamps the redaction ID and a small QR code in its place.
3. You **download** the anonymized PDF and share/store it as needed.
4. Later, on the **Restore** tab, upload that anonymized PDF back in. The
   app finds the redaction IDs, decrypts the matching snapshots from its
   local database, and pastes them back at the exact original position —
   producing a visually restored PDF.

Restoring only works on the same machine/installation, since the decryption
key and the ID→content mapping both live in the local `data/` folder.
Back up `data/secret.key` and `data/redactions.db` together if you need
restore capability to survive reinstalling or moving the app.

## Setup (already done once)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Running

```powershell
.\run.ps1
```

Then open **http://127.0.0.1:8756** in your browser.

## Notes / limitations

- Keep selection boxes tight around just the text you want to redact, with
  a little vertical padding. PDF text redaction removes whole lines of text
  that intersect the box — if a box edge slightly overlaps a neighboring
  line, that line gets swept in too.
- Restored content is a pasted image of the original area (pixel-perfect
  visually), not reflowed vector text — this is what makes restoring robust
  regardless of what was in the box (text, logo, signature, etc.).
- This is a single-user local tool: no authentication, no multi-tenant
  isolation. Anyone with access to this machine and its `data/` folder can
  restore anonymized documents produced here.
