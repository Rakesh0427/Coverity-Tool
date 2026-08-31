# Publish Instructions - Coverity Tool Confluence Page

Target parent page:
https://confluence.honaero.com/spaces/CNSDLK/pages/1561644079/Datalink+Quality+Dashboard

## What was prepared

This folder contains a ready-to-publish Confluence page kit:

- `Coverity_Tool_Confluence_Page.md` - readable Markdown copy for normal Confluence editing.
- `Coverity_Tool_Confluence_Storage.xhtml` - Confluence storage-format content for source/API import.
- `attachments/images/` - 11 annotated tool screenshots.
- `attachments/docs/` - final Word user manual.
- `attachments/Coverity-Tool-Final-20260831.zip` - final packaged tool.

## Recommended manual publish flow

1. Open the parent page in browser:
   `https://confluence.honaero.com/spaces/CNSDLK/pages/1561644079/Datalink+Quality+Dashboard`
2. Log in using Honeywell AERO SSO.
3. Create a child page under the parent page.
4. Page title suggestion:
   `Coverity Disposition Tool - User Guide`
5. Attach all files from:
   - `attachments/images/`
   - `attachments/docs/`
   - `attachments/Coverity-Tool-Final-20260831.zip`
6. Copy content from `Coverity_Tool_Confluence_Page.md` into the Confluence editor.
7. If images do not render automatically, insert each attached image in the same section where it is referenced.
8. Publish the page.

## Storage-format publish flow

Use `Coverity_Tool_Confluence_Storage.xhtml` only if your Confluence editor/admin tooling supports storage-format import or REST API page creation.

Important:
- Upload attachments to the Confluence page before using the storage-format image macros.
- The storage file references image attachments by filename.
- The prepared image filenames must not be changed unless the storage file is updated too.

## Attachment checklist

Images:
- `01_setup_live.png`
- `02_commit_live.png`
- `03a_pull_top_live.png`
- `03b_pull_bottom_live.png`
- `04_analysis_live.png`
- `05_results_live.png`
- `06_detail_live.png`
- `07a_push_csv_top_live.png`
- `07b_push_csv_bottom_live.png`
- `08a_direct_push_top_live.png`
- `08b_direct_push_bottom_live.png`

Documents/package:
- `Coverity_Tool_User_Manual.docx`
- `Coverity-Tool-Final-20260831.zip`

## Access note

The Confluence page redirects to Honeywell AERO SSO from this environment, so automated publishing cannot be completed here without a logged-in user session or an approved Confluence API token. Do not paste passwords or tokens into chat. If API publishing is needed, use a local secure terminal/session with an approved token stored outside source control.
