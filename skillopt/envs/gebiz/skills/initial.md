# GeBIZ Procurement Search Skill

You are an agent that searches Singapore's GeBIZ e-procurement portal (https://www.gebiz.gov.sg).

## Critical: GeBIZ is a JSF app
- GeBIZ is a JavaServer Faces (JSF) application. A plain `curl` GET returns an empty shell showing "No opportunity found" because results load only after a full form POST with a valid `javax.faces.ViewState`.
- Do NOT use a naive GET to search. You must POST the search form.

## Working endpoint
- Advanced search: `https://www.gebiz.gov.sg/ptn/opportunity/BOAdvancedSearch.xhtml`
- Opportunity listing: `https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml?origin=opportunities`
- Direct document: `https://www.gebiz.gov.sg/ptn/opportunity/directlink.xhtml?docCode=XXXX`

## Search flow (JSF postback)
1. GET the advanced-search page to obtain a session cookie and the `javax.faces.ViewState` value.
2. POST the form with the search keyword in the "All these words" field (`contentForm:j_idt148_inputText`) and the Search button (`contentForm:buttonSearch`).
3. Parse the returned HTML for opportunity records.

## Result structure
- Records render in `formSectionHeader6` blocks with serial number, type (Tender/Quotation), document number, status (OPEN/CLOSED), title, agency, published date, and closing date.
- Title links carry the document code via `/ptn/opportunity/directlink.xhtml?docCode=XXXX`.

## Key rules
- Always confirm you are on the correct portal: GeBIZ is for procurement/tenders, NOT planning applications (use URA CID for planning).
- Use a proper User-Agent header.
- Preserve the session cookie between the GET and POST.
