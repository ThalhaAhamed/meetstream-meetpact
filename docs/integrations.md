# Integrations

All integrations are optional and switched on by setting their environment variables.

## Calendar auto-join

**Google Calendar, one click.** Create an OAuth client once, put it in `.env`, and connect from the app:

1. In the [Google Cloud Console](https://console.cloud.google.com/), pick or create a project and
   enable the **Google Calendar API** (APIs & Services → Library).
2. **OAuth consent screen:** External, any app name, your email. Add yourself under *Test users*.
   The scopes MeetPact asks for are read-only: `calendar.readonly`, `calendar.events.readonly`,
   `userinfo.email`, `userinfo.profile`.
3. **Credentials → Create credentials → OAuth client ID → Web application.** Add this
   *Authorized redirect URI* exactly: `http://localhost:8000/api/calendar/google/callback`
   (another host or port: set `GOOGLE_REDIRECT_URI` to match).
4. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, restart,
   and click **Schedules → Calendar auto-join → Connect Google Calendar** (admin). Sign in with the
   Google account whose calendar the bot should follow.

MeetPact exchanges the sign-in for a refresh token and passes the client and token to MeetStream
(`POST /calendar/create_calendar`), which keeps the calendar in sync. The token is not stored here.

**Outlook, or a token you already have:** use *connect with a refresh token instead* and paste an
OAuth client ID, secret and refresh token (Microsoft Graph needs `Calendars.Read`). MeetStream's
[labs](https://github.com/meetstream-ai/labs) repo has helpers that produce one
(`google-calendar-integration`, `outlook-calendar-integration`).

With auto-join on, the app reads upcoming events every two minutes and books the bot for each
meeting that has a link and passes the title filters, through the same path as scheduled meetings,
so consent notices, analysis and progress tracking all apply.

## Report delivery (email and Slack)

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` for email and/or
`SLACK_WEBHOOK_URL` (a Slack incoming webhook), restart, then turn delivery on under **Admin → Bot
and reports**. *Send test email* / *Send test to Slack* there check the setup straight away (the test
email goes to your own account's address).

* **Gmail:** `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER` and `SMTP_FROM` = your address,
  `SMTP_PASSWORD` = an [app password](https://myaccount.google.com/apppasswords) (needs 2-step
  verification; your normal password is rejected). Port 465 also works.
* **Slack:** create an app at [api.slack.com/apps](https://api.slack.com/apps) → *Incoming Webhooks*
  → on → *Add New Webhook to Workspace* → pick a channel, and copy the `https://hooks.slack.com/...` URL.
Each person allowed to see the full report gets it by email, with individual updates filtered by the
employee-update sharing setting. Slack gets a short summary and a link, and only for reports shared
with participants or managers. A report is sent once; "Send report" on the meeting page resends it.

## Trello as a team's task board

Each team keeps its tasks either on MeetPact's own board or on a Trello board.

1. **Connect Trello** under **Admin → Bot & settings → Trello** (or the setup guide): create a Power-Up
   at [trello.com/power-ups/admin](https://trello.com/power-ups/admin), paste its API key, click
   *Allow MeetPact on Trello* and paste the token Trello shows. `TRELLO_API_KEY` / `TRELLO_TOKEN` in
   `.env` work too and take priority.
2. **Admin → Teams → edit a team → Task board → Trello board:** pick the board. MeetPact guesses what each
   list means from its name (To do, Doing, Blocked, Done, or not tracked) and matches Trello members to
   people by name; correct either there.

Then, for that team:

* **Work board** shows the live Trello board (pick the team at the top): lists in Trello's order, who is
  on each card, due dates, links to the cards. Dragging a card moves it in Trello.
* Every open card is also a work item, so dashboards, reports, Ask and the person pages include them.
  The board syncs every `INTEGRATION_SYNC_MINUTES`, when it is opened, before a meeting is analysed
  and before a stand-up starts.
* New work from that team's meetings becomes cards in the first *To do* list (assigned to the person when
  they're matched); work reported as done or in progress moves its card to the matching list.
* The AI stand-up host gets the open cards and who owns them: it asks people about their own cards and
  raises overdue or unassigned ones before wrapping up.

## Task tools

Set the variables for any tool in `.env` (see `.env.example`) and restart. **Admin → Task tools →
Check** confirms the credentials and the target list or project without creating anything. Work items then get a
"Create in …" button, and **Admin → Bot & settings → Create tasks automatically** can push every new
action item. Status sync runs every `INTEGRATION_SYNC_MINUTES` minutes, or on demand:

| Tool | Creates | Reads back |
|---|---|---|
| ClickUp | task in `CLICKUP_LIST_ID` | status type (done/closed) |
| Jira Cloud | issue in `JIRA_PROJECT_KEY` | status category (new / in progress / done) |
| Asana | task in `ASANA_PROJECT_GID` | `completed` |
| Trello | card in `TRELLO_LIST_ID` | `dueComplete`, or moved to `TRELLO_DONE_LIST_ID` |
| monday.com | item on `MONDAY_BOARD_ID` | text of `MONDAY_STATUS_COLUMN_ID` |

Where to find the values:

* **Jira Cloud:** `JIRA_BASE_URL` is `https://<site>.atlassian.net`; an API token from
  [id.atlassian.com → Security → API tokens](https://id.atlassian.com/manage-profile/security/api-tokens);
  `JIRA_EMAIL` is your Atlassian login; `JIRA_PROJECT_KEY` is the prefix of issue keys (`ABC` in `ABC-12`).
  If the project has no "Task" type, Check lists the ones it has for `JIRA_ISSUE_TYPE`.
* **Trello:** API key and token from [trello.com/power-ups/admin](https://trello.com/power-ups/admin)
  (create a Power-Up, then *API key* → *Token*). For a list id, open a card on the board, add
  `.json` to its URL and look for `idList`.
* **Asana:** a personal access token from the [developer console](https://app.asana.com/0/my-apps);
  the project gid is the long number in the project's URL.
