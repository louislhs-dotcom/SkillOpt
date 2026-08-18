# Site: GeBIZ — Government e-Procurement (gebiz.gov.sg)
**Type:** Singapore gov procurement portal — tenders, quotations, awards (JSF/PrimeFaces)
**Auth:** Public browse OK; login required for submissions, document download, supplier registration
**Bot protection:** Moderate — JSF stateful app requires ViewState handling; Moli works for static content but ego-browser needed for form interactions

---

## Base URLs
- **Root:** `https://www.gebiz.gov.sg/`
- **Tender Listings:** `https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml`
- **Advanced Search:** `https://www.gebiz.gov.sg/ptn/opportunity/BOAdvancedSearch.xhtml`
- **Supplier Directory:** `https://www.gebiz.gov.sg/ptn/supplierdirectory/SupplierSearch.xhtml`
- **Tender Detail:** `https://www.gebiz.gov.sg/ptn/opportunity/BODetail.xhtml?tenderId=<id>`
- **Document Download:** `https://www.gebiz.gov.sg/ptn/opportunity/DownloadDocument.xhtml?docId=<id>&tenderId=<id>`
- **Login/Register:** `https://www.gebiz.gov.sg/ptn/login.xhtml` (CorpPass/SingPass)

---

## The Key Fact: It's a JSF App, Not a Normal Page
- **Tender listings do NOT render on static load** — Moli AND plain ego-browser load get only the page shell (header/nav/footer, body ~700-900 chars, stuck at "LOADING/SEARCHING"). The tender table hydrates only via JSF AJAX partial updates.
- **ViewState is mandatory:** Every page has a hidden `javax.faces.ViewState` (e.g., `-2457674906927854573:6221920039114427688`). Extract it and submit it with every form POST. GET requests fail for form actions.
- **Component IDs use JSF colon naming:** `formId:componentId` (e.g., `contentForm:buttonContinue`, `searchForm:keywordInput`).
- **AJAX partial updates:** After clicking a command button, wait for the updated element (`waitForSelector` on a specific id, or `data-updated="true"`) — do NOT use `networkidle` (JSF partial updates never fully idle).

---

## Verified Flow (ego-browser)

1. Open `https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml`
2. Read the hidden `javax.faces.ViewState` from the form
3. Click a command button (e.g., `contentForm:buttonContinue`) via its JSF id
4. Wait for the results `table` to hydrate (`#searchForm:resultsTable` / `table[id$="resultsTable"]`), PrimeFaces `tbody tr[data-ri]` rows
5. For filtered search: POST form data + the fresh ViewState to the same URL

---

## Selectors (ego-browser)

### Tender List Page
- **Search Form:** `form#searchForm` or `form[id$="searchForm"]`
- **Keyword Input:** `input[id*="keywordInput"]` or `#searchForm\\:keywordInput`
- **Search Button:** `input[name*="buttonGo"]` or `button[id*="buttonGo"]`
- **Advanced Search Link:** `a[id*="advancedSearch"]`
- **Results Table:** `table[id$="resultsTable"]` or `#searchForm\\:resultsTable`
- **Table Rows:** `tbody tr[data-ri]` (PrimeFaces data table rows)
- **Tender Title Link:** `a[id*="tenderTitle"]` or `.tender-title a`
- **Tender ID:** `span[id*="tenderId"]` or data attribute
- **Closing Date:** `span[id*="closingDate"]`
- **Category:** `span[id*="category"]`
- **Agency:** `span[id*="agency"]`

### Pagination
- **Next Page:** `.ui-paginator-next a` or `.pagination-next`
- **Page Numbers:** `.ui-paginator-pages a`
- **Page Input:** `input.ui-paginator-current`
- **Page Dropdown:** `select.ui-paginator-rpp-options`

### ViewState Handling
- **Hidden Input:** `input[name="javax.faces.ViewState"]`
- **Extract:** `await js('document.querySelector("input[name=\\"javax.faces.ViewState\\"]').value')`
- **Include in every POST**

### Tender Detail Page
- **Title:** `h1[id*="tenderTitle"]` or `.tender-title`
- **Tender ID:** `span[id*="tenderId"]`
- **Reference No:** `span[id*="referenceNo"]`
- **Category:** `span[id*="category"]`
- **Description:** `div[id*="description"]` or `.tender-description`
- **Closing Date/Time:** `span[id*="closingDate"]`
- **Estimated Value:** `span[id*="estimatedValue"]`
- **Contact Person:** `span[id*="contactPerson"]`
- **Document Links:** `a[id*="downloadDoc"]` or `.document-link`

### Document Download
- **Download Link:** `a[id*="downloadDocument"]` or `a[href*="DownloadDocument.xhtml"]`
- **URL Pattern:** `/ptn/opportunity/DownloadDocument.xhtml?docId=<id>&tenderId=<id>`

### Search Form Fields (Advanced)
- **Tender Reference:** `input[id*="referenceNo"]`
- **Category Dropdown:** `select[id*="category"]`
- **Agency Dropdown:** `select[id*="agency"]`
- **From Date:** `input[id*="fromDate"]`
- **To Date:** `input[id*="toDate"]`
- **Status Dropdown:** `select[id*="status"]`

### Auth-Required Elements
- **Login Button:** `a[id*="login"]`, `a[href*="login.xhtml"]`
- **Sign Up:** `a[id*="signup"]`, `a[href*="register.xhtml"]`
- **Submit Quotation:** Requires CorpPass/SingPass login flow
- **Document Download (restricted):** Requires login

---

## Tool Routing for GeBIZ

| Task | Tool | Rationale |
|------|------|-----------|
| Browse/filter/search tenders | **ego-browser** | JSF session + ViewState chain; Moli gets only the shell |
| Document download | **ego-browser** | Login-walled, JSF download links |
| Submit quotation/bid | **ego-browser** | CorpPass/SingPass login flow |
| Supplier registration | **ego-browser** | CorpPass/SingPass login flow |
| View tender details (public) | **ego-browser** | JSF partial updates require real browser |

**Moli is NOT usable for GeBIZ tender data** — static fetch gets only the shell.

---

## Anti-patterns to Avoid
- Don't use simple GET for search/filter (must POST with ViewState)
- Don't ignore `javax.faces.ViewState` (every submit needs the current value)
- Don't use `networkidle` for JSF partial updates (use `waitForSelector`)
- Don't assume JSF component IDs are stable across sessions (extract dynamically)
- Don't use `networkidle` wait for listing pages (JSF partial updates never idle)
- Don't try to scrape with Moli/curl — gets only the loading shell