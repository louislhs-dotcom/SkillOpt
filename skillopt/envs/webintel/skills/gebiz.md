# GeBIZ (Government e-Procurement) — Site Configuration

**Site:** GeBIZ Singapore (www.gebiz.gov.sg)  
**Type:** Government e-procurement portal — tenders, quotations, awards  
**Auth:** Public browse OK for some sections; login required for submissions, document downloads, supplier registration

---

## Base URLs
- **Root:** `https://www.gebiz.gov.sg/`
- **Tender Search:** `https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml`
- **Award Search:** `https://www.gebiz.gov.sg/ptn/opportunity/AwardListing.xhtml`
- **Supplier Portal:** `https://www.gebiz.gov.sg/ptn/supplier/`

---

## JSF ViewState Handling

### Critical Patterns
- **ViewState parameter:** `javax.faces.ViewState` — must be extracted from each page and submitted with forms
- **Form submission:** All forms use POST with ViewState; GET requests fail for actions
- **Partial page updates:** Uses JSF `<f:ajax>` / PrimeFaces `p:ajax` — wait for `data-updated="true"` or specific element updates
- **Component IDs:** Follow JSF naming convention: `formId:componentId` (e.g., `searchForm:keywordInput`)

### Key Form Fields
| Field | Pattern | Purpose |
|-------|---------|---------|
| `javax.faces.ViewState` | Hidden input | Required for all POST submissions |
| `searchForm:keywordInput` | Text input | Tender keyword search |
| `searchForm:categorySelect` | Dropdown | Category filter |
| `searchForm:statusSelect` | Dropdown | Tender status filter |
| `searchForm:dateFrom` / `dateTo` | Date pickers | Date range filter |
| `searchForm:searchBtn` | Command button | Triggers search |

---

## Endpoints

### Tender Search Flow
1. GET `/ptn/opportunity/BOListing.xhtml` — loads page with initial ViewState
2. POST to same URL with form data + ViewState — returns results table
3. Pagination: POST with `searchForm:resultsTable_pagination` or similar PrimeFaces paginator

### Document Download
- Links require authenticated session
- Direct download URLs: `/ptn/opportunity/DownloadDocument.xhtml?docId=<id>&tenderId=<id>`
- Must maintain JSF session + ViewState chain

### Award Listing
- GET `/ptn/opportunity/AwardListing.xhtml`
- Similar JSF form patterns for filtering

---

## Selectors (for ego-browser / Moli extraction)

### Tender List Page
- **Results table:** `#searchForm\\:resultsTable` or `table[id$="resultsTable"]`
- **Row data:** `tbody tr[data-ri]` (PrimeFaces dataTable rows)
- **Tender ID:** `td[data-col="tenderId"]` or first column
- **Title:** `td[data-col="title"] a` or `.tender-title`
- **Agency:** `td[data-col="agency"]`
- **Category:** `td[data-col="category"]`
- **Closing date:** `td[data-col="closingDate"]`
- **Status:** `td[data-col="status"]`
- **View details link:** `a[id$="viewBtn"]` or `.view-details`

### Pagination
- **Paginator:** `.ui-paginator` or `#searchForm\\:resultsTable_paginator`
- **Next page:** `.ui-paginator-next a` or `a[aria-label="Next Page"]`
- **Page links:** `.ui-paginator-page a`

### Tender Detail Page
- **Title:** `h1` or `#detailForm\\:tenderTitle`
- **Description:** `#detailForm\\:description` or `.tender-description`
- **Documents table:** `#detailForm\\:documentsTable`
- **Download links:** `a[id$="downloadLink"]`

### Login / Auth
- **Login form:** `#loginForm` or `form[id$="loginForm"]`
- **Username:** `input[id$="username"]` or `#loginForm\\:username`
- **Password:** `input[id$="password"]` or `#loginForm\\:password`
- **Login button:** `button[id$="loginBtn"]`
- **CorpPass / SingPass integration:** External redirect handlers

---

## Tool Routing for GeBIZ

| Task | Tool | Rationale |
|------|------|-----------|
| Browse tender listings (public) | **Moli** | Public pages, but JSF requires ViewState handling |
| Search tenders with filters | **ego-browser** | JSF form submission + ViewState chain required |
| Download tender documents | **ego-browser** | Login-walled, JSF download links |
| Submit quotation/bid | **ego-browser** | Complex JSF wizard, login required |
| Monitor award listings | **Moli** (scheduled) | Public pages, fast extraction |
| Supplier registration | **ego-browser** | Multi-step JSF forms, CorpPass login |
| 50+ tenders batch extraction | **ego-browser** (parallel spaces) | JSF session management, login state |

---

## Anti-patterns to Avoid
- Don't use simple GET for search/filter actions (must POST with ViewState)
- Don't ignore `javax.faces.ViewState` — every form submit needs current value
- Don't use `networkidle` for JSF partial updates (use `waitForSelector` on updated element)
- Don't assume component IDs are stable across sessions (extract dynamically)
- Don't use Agent Reach (no GeBIZ tap installed)
- Don't try to scrape without handling CorpPass/SingPass login flow

---

## Trust & Safety Notes
- Government procurement portal — official Singapore government site
- All data is public sector procurement information
- Supplier data governed by PDPA and government data policies
- Audit trail on all actions (login, search, download, submit)