# Feeding the revision helper from Claude

An MCP server, so an assistant can load a term of papers, hand in work done on
paper, put work on a child's plan and read back how they are doing — without
going through the browser one file at a time.

It runs on your Mac, reads the files you point it at from your disk, and talks
to the deployed app as you.

```
You, in Claude: "upload every PDF in ~/Downloads/summer-papers for maths"
        │
        ▼
MCP server (this folder, on your Mac) ──── reads those files
        │
        │  Authorization: Bearer <your token>
        ▼
The app on Railway ──── parses each paper, hides the answer key
```

## What it can do

| Tool | What it is for |
|------|----------------|
| `check_connection` | Confirm the app is reachable and the token is accepted. Start here. |
| `list_children` | Who is set up in the app |
| `list_papers` | What is already in the library, so nothing is added twice |
| `upload_papers` | Add papers in bulk, from files, folders or patterns |
| `hand_in_work` | Record work that was never assigned, and mark it |
| `assign_work` | Put a paper or a task on a child's plan |
| `get_progress` | Work done, average score, time, weak topics |
| `record_results` | Record a whole batch of already-marked work in one call |
| `correct_marks` | Put several marks right in one call |
| `work_needing_marks` | Everything across all children waiting to be scored |
| `list_work` | What is on a child's record, with the ids needed to change it |
| `update_work` | Correct one mark, title, subject, date, time or note |
| `delete_work` | Take one wrong entry off the record |
| `restore_work` | Put back something removed by mistake |
| `move_work` | Move work logged against the wrong child |
| `rename_child` | Change a name, year group, emoji or colour |

## Setting it up

### 1. Make a token

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep the output — it is a password to your children's data, and it does not
expire. Anything shorter than 32 characters is refused by the server.

### 2. Find your Auth0 user id

Sign in to the app in your browser, then open:

```
https://web-production-35acf.up.railway.app/api/user/me
```

Copy the `user_id`. It looks like `auth0|68a1f...`. This is the account the
token will act as, which is what makes files fed in this way show up in the app
next to everything else.

### 3. Set both on Railway

In the Railway service variables:

```
API_TOKEN=<the token from step 1>
API_TOKEN_USER_ID=<the user_id from step 2>
```

The service restarts and the token starts working. Leave either one unset and
the whole mechanism stays off, which is the safe default.

### 4. Install the server

It gets its own virtualenv on purpose: the MCP SDK needs a newer `starlette`
than the app's FastAPI accepts, so sharing one environment breaks the app.

```bash
cd mcp_server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 5. Point Claude Desktop at it

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "revision-helper": {
      "command": "/Users/stacygorelik/projects/my_revision_helper/mcp_server/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "PYTHONPATH": "/Users/stacygorelik/projects/my_revision_helper",
        "REVISION_HELPER_URL": "https://web-production-35acf.up.railway.app",
        "REVISION_HELPER_TOKEN": "<the token from step 1>"
      }
    }
  }
}
```

`PYTHONPATH` rather than `cwd`, because a working directory is not honoured
everywhere the config is read, and without one of the two the module cannot be
found.

Restart Claude Desktop — fully quit it, rather than closing the window. For
Cursor the same block goes in `.cursor/mcp.json`.

### Cowork

The same local server shows up in Cowork sessions. Anthropic's own
documentation says local servers configured this way are not available there,
but in practice they are, and installing the same server as a `.mcpb` bundle
instead is what has the [first-turn
race](https://github.com/anthropics/claude-code/issues/55903). Either way, a
full restart of Claude Desktop after any change is what settles it.

If a Cowork session genuinely cannot see the tools, the documented route is a
custom connector, which is fetched from Anthropic's cloud rather than from this
machine. That needs the server behind a public HTTPS address — a tunnel back to
here, since the whole point is reading files off this disk — and the bearer
token set as a request header in the connector's advanced settings.

### 6. Check it

Ask Claude to run `check_connection`. It should name your children back at you.

## Using it

Things worth saying out loud:

- "Upload every PDF in ~/Downloads/summer-papers as maths papers for week 3"
- "Here's Savva's fractions worksheet at ~/Desktop/scan.pdf — he did it on
  paper yesterday, mark it"
- "Yuri got 18 out of 25 on the calculator paper on Monday, took him an hour"
- "Assign the Level 2 calculator paper to both of them for next Tuesday"
- "How is Savva doing in chemistry?"
- "The comprehension paper was marked 42%, it should be 41 out of 50"
- "Delete Yuri's mis-marked fractions worksheet"
- "The English scan I put on Savva was actually Yuri's — move it"
- "What's waiting for a mark?"

Leave the subject out of an upload and it is guessed per file from the
filename, which works when they are named like `Maths_Week1_Workbook.docx`.

### Keeping the record up to date

Most updating is faster in batches. Say the week out loud and let it go in as
one call:

> "Catch the app up on this week. Yuri: calculator paper 41/50 on Monday, an
> hour; comprehension 18/20 Tuesday, 40 minutes. Savva: chemistry quiz 14/20
> Wednesday, half an hour; read two chapters Thursday, 45 minutes."

That is one `record_results` call covering both children. Rows can each name
their own child, and a row that is wrong is reported and skipped rather than
taking the good ones down with it.

Corrections work the same way:

> "What's waiting for a mark?" → `work_needing_marks`
> "Score the comprehension 33 out of 40 and the physics 22 out of 30"
> → one `correct_marks` call

`record_results` takes scores as given and does not scan or mark anything, so
it is quick. Use `hand_in_work` when you want the app to read a scan and mark
it, and `upload_papers` for blank papers going into the library.

## Things to know

**It is slow, and that is the app working.** Every paper is parsed by a model
as it lands, and marking a scan means reading each page. A 15 page paper takes
several minutes. Twelve files is the most one call will take; ask again for the
rest.

**A scan of completed work does not need the original paper.** As long as the
questions are visible next to the answers, it can be marked from the scan
alone, and the blank worksheet is kept in the library for your other child with
the answers stripped out.

**Files never go through the model.** The server reads them from disk and posts
them straight to the app. Claude only ever sees the paths and the summary that
comes back.

**Work the app cannot mark is not scored nought.** A scan it could not read is
recorded as done and left without a percentage, out of the average, until
someone supplies one. `list_work` with `needs_review_only` shows what is
waiting; `update_work` scores it.

**Nothing is really deleted.** `delete_work` takes an entry off the averages and
the charts but keeps it, so `restore_work` can put it back.

## When something is wrong

| What you see | What it usually is |
|--------------|--------------------|
| "No REVISION_HELPER_TOKEN is set" | The `env` block in the Claude config is missing or misspelt |
| "the token was not accepted" | `API_TOKEN` on Railway does not match, or `API_TOKEN_USER_ID` is unset |
| Connected, but "Children: nobody yet" | `API_TOKEN_USER_ID` is not the id from `/api/user/me`, so it is a different account |
| "did not answer within 600s" | Too many files at once; try three or four |
| A file silently missing | Look at the "Left out" list — unsupported type, empty, or over 25MB |

## Tests

```bash
cd ..
mcp_server/.venv/bin/python -m pytest mcp_server/test_mcp_server.py
```

They stub the API, so they need no network, no token and no running app.
