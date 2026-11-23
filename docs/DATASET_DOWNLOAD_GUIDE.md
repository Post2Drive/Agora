# Dataset Download Guide — Owner Steps

**Purpose:** help the owner obtain the exact public benchmark files named in `VALIDATION_PROTOCOL.md`. This guide is for manual downloads only. It does not approve a source substitution, import data into AGORA, freeze the protocol, or authorize a simulation/validation run.

## Before downloading

1. Use the official publisher page first. Do not use a third-party mirror unless the owner separately approves its exact repository, commit, path, version and licence in writing.
2. Read the licence/competition terms before clicking Download. If the terms do not clearly permit the intended private evaluation and handoff, stop.
3. Keep the original filenames and source archive. Do not edit, re-save, rename or commit raw data to Git.
4. Record for every file: package, publisher, exact URL, licence/version, release/version, access date, original filename, exact size in bytes and SHA-256.
5. On Windows, right-click the downloaded file in File Explorer → **Properties** and record the exact **Size** in bytes. Sizes vary by release; do not accept a guessed size as a checksum.
6. In PowerShell, calculate the file hash (replace the filename with the exact downloaded name):

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\\filename.csv"
```

7. Compare the file list, headers and date coverage with the checklist and frozen protocol. If a required file is missing, the release is different, or the headers/date range do not match, stop; do not substitute another file.
8. Before attaching any file to this ChatGPT conversation, inspect its headers and a small local sample for names, emails, phone numbers, addresses, account IDs, respondent/customer/driver records or sensitive attributes. If any are present, do not upload the file; ask for an approved safe alternative. Never send passwords, API keys, cookies or account credentials.

## Package E — FiveThirtyEight polls + MEDSL election returns

### E1. FiveThirtyEight polling files

**Official index:** https://github.com/fivethirtyeight/data/tree/master/polls

The pinned repository README at commit `4c1ff5e3aef1816ae04af63218015066e186c147` lists these direct CSV URLs:

- Current presidential polls: https://projects.fivethirtyeight.com/polls-page/data/president_polls.csv
- Historical presidential polls: https://projects.fivethirtyeight.com/polls-page/data/president_polls_historical.csv
- 2020 presidential general-election averages: https://projects.fivethirtyeight.com/2020-general-data/presidential_poll_averages_2020.csv
- Corrected presidential general-election averages URL listed in that README: https://projects.fivethirtyeight.com/polls/data/presidential_general_averages.csv

**Steps**

1. Open the official polls index and read its README before downloading.
2. For each required CSV, open the exact direct URL above. Use the browser's download/save control; keep the publisher filename.
3. The `president_polls.csv` and `president_polls_historical.csv` endpoints are current/historical feeds and can change over time. The corrected 2024 averages endpoint is also a live URL, not a pinned immutable release. Confirm the downloaded file actually contains the protocol's required 2020/2024 pre-election records and cutoffs. Record the retrieval date and SHA-256. If it does not, stop and request a versioned source/protocol decision.
4. Do **not** use `presidential_general_averages_2024-09-12_uncorrected.csv` as a substitute; the repository marks it as the preserved uncorrected file. The GitHub `pres_pollaverages_1968-2016.csv` file ends in 2016 and does not supply 2020/2024 averages.
5. FiveThirtyEight repository data is stated as **CC BY 4.0** unless a dataset is otherwise noted. Retain the attribution and exact source commit/release with the files.

### E2. MEDSL county presidential returns

**Official dataset page:** https://doi.org/10.7910/DVN/VOQCHQ

1. Open the DOI page and select **Version 20.0** (released 25 February 2026, as recorded in the current checklist).
2. Open the version's **Files** tab/list. Download the County Presidential Election Returns 2000–2024 CSV and its codebook, using the exact filenames shown by Dataverse. The expected CSV name in the reviewed mirror is `countypres_2000-2024.csv`; verify the official file name rather than renaming it.
3. Record the Dataverse citation, V20.0, **CC0 1.0**, access date, exact bytes and SHA-256. Keep the poll and returns files separate.
4. If Dataverse cannot be accessed, do not silently use the reviewed GitHub mirror. The candidate `mathis-group/cas-201-data-project` at commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7` is a third-party snapshot; its README claims the V20.0 CSV is 10,222,208 bytes and MD5 `bd6661282936006b4ef4f5ee71418f3e`, with CC0 1.0 data terms. It is **not approved by this guide**. Use it only after the owner approves that exact repository/commit/path and its checksum/licence evidence is reconciled to Dataverse.

## Package R — M5 Walmart retail sales

**Official Kaggle page:** https://www.kaggle.com/c/m5-forecasting-accuracy/data

1. The owner must sign in to Kaggle personally, review the M5 competition rules and confirm that the intended evaluation/handoff is permitted. This is owner-only; do not share the password or session with ChatGPT or AGORA.
2. On the **Data** tab, use **Download All** after the terms step. Save the original archive, then extract it locally without renaming files.
3. Check for these original files:
   - `calendar.csv`
   - `sales_train_validation.csv`
   - `sell_prices.csv`
   - `sales_train_evaluation.csv` — required if retaining the protocol's reserved `d_1914`–`d_1941` window.
4. Record the exact archive and per-file byte sizes, SHA-256 values, Kaggle source page, access date and the competition-rules version/acceptance record. File sizes vary by archive/version; the current protocol does not set a fixed byte-size acceptance threshold.
5. Do not upload or redistribute any M5 file if the competition terms prohibit the intended handoff. If terms are unclear, stop and ask the owner to approve a revised source/protocol; Rossmann is not an automatic replacement.

## Package A — Ember Monthly EV Sales

**Official data and methodology page:** https://ember-energy.org/data/monthly-ev-sales-data/

1. Open the page and choose the **monthly CSV** download for Monthly EV Sales Data (not a quarterly export or a chart image).
2. Preserve the exact filename shown by the current official download. The reviewed third-party snapshot uses `monthly_ev_sales.csv`, but verify the official file name and release before accepting it.
3. Download the methodology/notes if offered. Keep country/economy monthly rows separate from regional aggregates and quarterly observations; do not interpolate.
4. Record the release/publication date, methodology version, underlying-source notes, **CC BY 4.0** attribution, exact bytes and SHA-256.
5. The reviewed GitHub candidate `Awes0mer/fuel-cars-pollution` at commit `2c21f1edced7aae884314ebc28c89ab212f30563` records a 16 November 2026 snapshot of 7,695,642 bytes with SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`. The checklist notes Ember's official page had a newer 18 November update. This candidate is **not the latest official release and is not approved**; do not use it unless the owner approves that exact snapshot.

## Hand off through a separate private GitHub repository

**Do not attach raw benchmark files to this ChatGPT conversation, Notion, or the AGORA source repository.** Claude's agreed handoff is a separate owner-controlled **private** GitHub repository, kept separate from AGORA. Suggested repository name: `agora-validation-data`. The owner creates it and controls who can access it.

### 1. Create the private repository

1. Sign in to GitHub in your own browser.
2. Select **+** (top-right) → **New repository**.
3. Repository name: `agora-validation-data` (or another name you choose).
4. Set **Visibility** to **Private**. Do not select Public.
5. For the simplest first push, leave **Add a README**, **.gitignore** and **license** unchecked so the repository is empty.
6. Select **Create repository**.
7. Give Claude's GitHub integration access using GitHub's own authorization/invitation controls, if it is not already authorized. Do not send passwords, personal access tokens, cookies or recovery codes in chat. If access cannot be granted safely, stop and ask for another owner-approved handoff.

### 2. Prepare the folders on your Windows laptop

Keep the downloaded originals in a local folder outside your AGORA checkout. Use one folder per package, for example:

```text
agora-validation-data/
  E_fivethirtyeight/
  E_medsl/
  R_m5/
  A_ember/
  register/
```

Put each publisher's original files in the matching folder. Keep the original filenames. Put the source/version/licence/size/hash register in `register/` as a small CSV or Markdown file. Do not add unrelated files, personal data, credentials, or AGORA project files.

**Expected filenames to look for (verify against the publisher page; do not rename to force a match):**

- FiveThirtyEight: `president_polls.csv`, `president_polls_historical.csv`, and the exact 2020/2024 average CSVs listed in the publisher README/direct links above. The required 2024 corrected averages file is a live external URL; verify coverage and retrieval date.
- MEDSL: the Dataverse Version 20.0 County Presidential Election Returns 2000–2024 CSV and its codebook. `countypres_2000-2024.csv` is the candidate mirror's filename, not a guarantee of the official Dataverse filename.
- M5: `calendar.csv`, `sales_train_validation.csv`, `sell_prices.csv`, and `sales_train_evaluation.csv` if retaining the reserved `d_1914`–`d_1941` window.
- Ember: the current official monthly CSV; the reviewed snapshot calls it `monthly_ev_sales.csv`. Verify the filename and release on Ember's download page.

There is no approved fixed byte-size threshold for the live FiveThirtyEight or Ember downloads, or for the current official MEDSL download. Record the actual byte size of every downloaded file; do not reject or accept a file solely because it differs from an unapproved mirror's size. The MEDSL mirror's claimed 10,222,208 bytes and Ember mirror's 7,695,642 bytes are candidate-snapshot details only, not official acceptance targets. Claude's handoff note estimates M5 `sales_train_evaluation.csv` at about 120 MB; verify your actual file size.

### 3. Check files before pushing

1. In PowerShell, change to the folder containing the dataset folders.
2. Record file sizes and SHA-256 values. Example:

```powershell
Get-ChildItem -File -Recurse | Select-Object FullName, Length
Get-ChildItem -File -Recurse | ForEach-Object {
  Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
}
```

3. Open each small CSV locally and confirm its header and expected date coverage. Do not upload or push respondent-level, personal, customer, driver, account, or sensitive data.
4. GitHub's browser upload limit is 25 MB per file; for Git pushes, do not push a file larger than 100 MB. For a file over 100 MB, create a ZIP copy locally (keep the original separately):

```powershell
Compress-Archive -LiteralPath ".\large-file.csv" -DestinationPath ".\large-file.csv.zip"
Get-Item ".\large-file.csv.zip" | Select-Object FullName, Length
```

5. The ZIP must itself be below 100 MB for an ordinary Git push. If it is still 100 MB or larger, **stop**; do not split it, use Git LFS, or switch to a public link without a separately approved handoff method. Record both the original file's size/hash and the ZIP's size/hash. Claude must be told which archive to retrieve and how it maps to the original filename.
6. **M5 gate:** do not push any Kaggle M5 file to the private repository until you have personally reviewed the competition terms and confirmed that this private collaborator handoff is permitted. A private repository does not override Kaggle terms. If unclear or prohibited, leave M5 local and stop for an owner-approved alternative.

### 4. Push to the private repository (PowerShell)

Install Git for Windows if needed, then open PowerShell. Replace the placeholders with your own GitHub username and private repository name. Do not use the AGORA repository URL.

```powershell
cd "$HOME\Downloads"
git clone https://github.com/<YOUR_GITHUB_USERNAME>/agora-validation-data.git
cd .\agora-validation-data
```

Copy the prepared package folders and register into this newly cloned folder. Then check exactly what will be committed:

```powershell
git status --short
git add .\E_fivethirtyeight .\E_medsl .\A_ember .\register
# Add .\R_m5 only if the Kaggle terms explicitly permit this handoff.
git status --short
```

If the staged list contains anything unexpected, stop and unstage it before continuing. Once the staged list is correct:

```powershell
git commit -m "Add owner-approved validation benchmark files"
git push origin main
```

If GitHub asks you to authenticate, use the normal Git Credential Manager/browser sign-in on your own computer. Never paste a token or password into ChatGPT, Notion, a commit, or a log. Confirm the repository page still shows **Private** after the push.

### 5. Tell Claude what is ready

Send Claude the private repository name/URL and the package folder names, plus the register. Do not send credentials. Claude should pull only the owner-approved files, verify the original filenames, versions, sizes and SHA-256 values, and update the dataset register. A successful push is not approval to import the data into AGORA.

## Stop conditions

- No source substitution or mirror use without exact owner approval.
- No download/use under unclear licence or competition terms.
- No upload of personal, sensitive, customer, respondent or credential data.
- No AGORA network connector, credential, write-back or external source fetch.
- Dataset availability does not authorize import, simulation, calibration, backtest or validation. The validation protocol still needs explicit owner approval and a merged freeze commit; the production policy/identity gate must also be resolved.
- Keep `VALIDATED_PREDICTION_ENABLED=False`. No validation result is claimed by this guide.
