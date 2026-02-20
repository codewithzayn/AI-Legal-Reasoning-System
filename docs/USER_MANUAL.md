# LexAI User Manual

LexAI is a Finnish legal reasoning assistant powered by AI. It helps you search Finnish case law (KKO, KHO), statutes, and legal definitions, and can ingest your own documents from local files or cloud drives.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Chat Interface](#2-chat-interface)
3. [Search Filters](#3-search-filters)
4. [Document Ingestion](#4-document-ingestion)
5. [Cloud Drive Integration](#5-cloud-drive-integration)
6. [Conversations](#6-conversations)
7. [PDF Export](#7-pdf-export)
8. [Appearance & Language](#8-appearance--language)
9. [Keyboard Shortcuts](#9-keyboard-shortcuts)

---

## 1. Getting Started

Open the app at `http://localhost:8501` (or your deployed URL). You will see:

- A **welcome screen** with a brief introduction
- **Quick-start template buttons** with example questions
- A **chat input** at the bottom of the page
- A **sidebar** with templates, ingestion, filters, conversations, and settings

Type a question in the chat input and press Enter. The AI will search Finnish legal databases and respond with citations.

### Supported Languages

The interface is available in **English**, **Finnish** (default), and **Swedish**. Change the language using the dropdown in the top-right corner or in the sidebar.

---

## 2. Chat Interface

### Asking Questions

Type your question in the chat input at the bottom of the screen and press Enter. Questions can be in Finnish or English.

**Examples:**
- "What is the penalty for theft under Finnish law?"
- "Etsi tapauksia petoksesta" (Find cases about fraud)
- "Summarize KKO:2024:76"

### Quick-Start Templates

When the chat is empty, pre-written example questions appear as clickable buttons. Click one to load it into an editable text area where you can modify it before sending.

Templates are also available in the sidebar under "Example questions".

### AI Responses

Responses stream in real-time with a typing indicator. Each response includes:

- **Answer text** based on retrieved legal documents
- **Sources section** (collapsible) showing cited cases with links to Finlex
- **Copy button** to copy the response to your clipboard
- **Feedback buttons** (thumbs up / thumbs down) to rate the response
- **Related questions** (up to 3 follow-up suggestions) below the last response

### Year Clarification

If your question is about court decisions but doesn't specify a time range, the AI may ask: "Which years' court decisions would you like to search?" You can respond with:
- A range like "2010-2020"
- "all" or "kaikki" for no year filter

---

## 3. Search Filters

Enable filters using the toggle in the sidebar. Three filter controls appear:

### Year Range

A slider from 1926 to 2026. Drag to narrow results to a specific time period.

### Court Type

Multi-select dropdown:
- **KKO** -- Supreme Court (Korkein oikeus)
- **KHO** -- Supreme Administrative Court (Korkein hallinto-oikeus)

Select one or both to filter results.

### Legal Domain

Multi-select dropdown with categories:
- Rikosasia (Criminal law)
- Siviiliasia (Civil law)
- Hallintoasia (Administrative law)
- Tyorikos (Labor crime)
- Seksuaalirikos (Sexual crime)
- Huumausainerikos (Drug crime)
- Vahingonkorvaus (Compensation)
- Sopimus (Contracts)
- Konkurssi (Bankruptcy)

Filters apply to all subsequent queries. Disable the toggle to clear all filters.

---

## 4. Document Ingestion

The Document Ingestion section in the sidebar allows you to upload your own documents for the AI to search alongside the built-in case law database.

> **Note:** Document ingestion requires a tenant ID. This is configured by your administrator via the `LEXAI_TENANT_ID` environment variable.

### File Upload

1. Click the **Upload** tab
2. Click the file uploader and select a file (PDF, DOCX, or TXT)
3. Click **Ingest**
4. Watch the progress bar through stages:
   - Checking for duplicates
   - Extracting text
   - Chunking document
   - Generating embeddings
   - Storing in database
5. A success message shows how many chunks were created

### Ingested Documents

Below the upload tabs, an expandable section shows all previously ingested documents with their status:
- Checkmark: Completed
- Cross: Failed
- Hourglass: Processing

---

## 5. Cloud Drive Integration

Connect Google Drive or OneDrive to browse and ingest files directly from the cloud.

### Connecting a Drive

1. Click the **Google Drive** or **OneDrive** tab
2. Click **Connect Google Drive** / **Connect OneDrive**
3. Click the authorization link that appears
4. Sign in to your Google/Microsoft account and grant permissions
5. You will be redirected back to LexAI with a "Connected" confirmation

Your connection persists across page refreshes -- tokens are saved to the database.

### Browsing Folders

Once connected, a folder browser appears:

- **Current folder** is shown as a breadcrumb path (e.g., "Root / Projects / Legal")
- **Subfolders** are listed in a dropdown -- select one and click **Open** to navigate into it
- Click **Back** to return to the parent folder
- Click **Use this folder** to set the current folder as your ingestion root

The selected folder is saved and remembered on future visits.

### Ingesting Files from a Drive

Below the folder browser, files in the selected folder are listed in a dropdown with file name and size. Select a file and click **Ingest** to download and process it.

### Disconnecting

Click **Disconnect** next to the "Connected" status. This removes the saved tokens from the database and clears the folder selection.

---

## 6. Conversations

### Auto-Save

Every conversation is automatically saved after each exchange. You don't need to do anything -- it happens in the background.

### Viewing Past Conversations

In the sidebar under "Previous conversations", up to 10 recent conversations are listed. Click a conversation title to reload it.

### Managing Conversations

- **Load**: Click a conversation title to restore it
- **Delete**: Click the trash icon next to a conversation to permanently remove it
- **New conversation**: Click the "New conversation" button to start fresh (the previous conversation remains saved)
- **Clear chat**: Clears the current messages from view (does not delete the saved conversation)

---

## 7. PDF Export

When you have an active conversation, a **Download as PDF** button appears in the sidebar.

Click it to download a formatted PDF containing:
- A header with "LexAI Chat Export" and timestamp
- All messages in chronological order
- User and assistant messages labeled and color-coded

The PDF supports Finnish characters (using DejaVuSans font when available).

---

## 8. Appearance & Language

### Dark Mode

Toggle dark mode using the switch in the sidebar. The entire interface switches to a dark color scheme.

### Language

Switch between:
- **English** (en)
- **Suomi / Finnish** (fi) -- default
- **Svenska / Swedish** (sv)

The language selector is available in both the top-right corner of the main area and in the sidebar. Changing the language updates all UI labels, templates, and AI response language.

---

## 9. Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+L** | Clear chat |
| **Ctrl+K** | Focus the chat input field |

These shortcuts are also documented in the sidebar under the "Keyboard shortcuts" expander.
