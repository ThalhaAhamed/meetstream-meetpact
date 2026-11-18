# Integrations

All integrations are optional and switched on by setting their environment variables.

## Calendar auto-join

Connect a calendar under **Schedules → Calendar auto-join** (admin only) with an OAuth client ID,
secret and refresh token for Google (Calendar API) or Microsoft (Graph, `Calendars.Read`). The
credentials are passed to MeetStream, which keeps the calendar in sync; this app does not store them.
MeetStream's [labs](https://github.com/meetstream-ai/labs) repo has helpers that produce the refresh
token (`google-calendar-integration`, `outlook-calendar-integration`).

With auto-join on, the app reads upcoming events every two minutes and books the bot for each
meeting that has a link and passes the title filters, through the same path as scheduled meetings,
so consent notices, analysis and progress tracking all apply.

## Report delivery (email and Slack)

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` for email and/or
`SLACK_WEBHOOK_URL` (a Slack incoming webhook), then turn delivery on under Admin → Bot & settings.
Each person allowed to see the full report gets it by email, with individual updates filtered by the
employee-update sharing setting. Slack gets a short summary and a link, and only for reports shared
with participants or managers. A report is sent once; "Send report" on the meeting page resends it.

## Task tools

Set the variables for any tool in `.env` (see `.env.example`) and restart. Work items then get a
"Create in …" button, and **Admin → Bot & settings → Create tasks automatically** can push every new
action item. Status sync runs every `INTEGRATION_SYNC_MINUTES` minutes, or on demand:

| Tool | Creates | Reads back |
|---|---|---|
| ClickUp | task in `CLICKUP_LIST_ID` | status type (done/closed) |
| Jira Cloud | issue in `JIRA_PROJECT_KEY` | status category (new / in progress / done) |
| Asana | task in `ASANA_PROJECT_GID` | `completed` |
| Trello | card in `TRELLO_LIST_ID` | `dueComplete`, or moved to `TRELLO_DONE_LIST_ID` |
| monday.com | item on `MONDAY_BOARD_ID` | text of `MONDAY_STATUS_COLUMN_ID` |
