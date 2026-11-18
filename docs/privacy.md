# Privacy and consent

* **Notice:** posted in the meeting chat as soon as the bot is admitted (editable under Admin → Bot &
  settings). In a live Google Meet test it went out about 15 seconds after the host admitted the bot.
* **Late joiners:** MeetStream only exposes the participant list after the call (`get_participants`
  answers 404 while the bot is in the meeting). With `PUBLIC_URL` set, `participant_events.join`
  webhooks arrive live and each late joiner gets a notice by name. Without it, the bot re-posts a
  short reminder every 10 minutes while recording (`consent_reminder_minutes`, 0 turns it off).
* **Stand-up mode** also asks out loud whether everyone is OK with recording before it starts.
* **Opt-out:** a participant types "opt out" (phrases are configurable) in the chat. The chat is read
  after the call; that person's speech is replaced with a placeholder before the transcript reaches
  Claude, and no update is recorded for them.
* **Pause:** the organizer, managers and admins can pause, resume or remove the bot from the meeting
  page. Typing "pause recording" in the chat does **not** work live: MeetStream returns the chat only
  after the call (`get_chats` answers 202 during it). Use the dashboard controls.
* **Transcripts:** silence can come back as filler ("Thank you." every ~30 seconds). Short phrases
  that repeat three or more times are dropped before analysis.
* **Platform limits apply:** hosts can deny the bot (recorded as *Denied*, never retried), waiting
  rooms need someone to admit it, and Zoom may ask the host for recording permission
  (`recording_permission_denied_timeout` is set). The bot cannot hear a verbal objection in notetaker
  mode: there is no live transcript, so it cannot act on one.
* **Access:** admins see everything. Managers see all employee records. Team leads see their team.
  Employees see their own records. Meeting reports follow the organizer's sharing choice. Transcripts
  are part of the full report.
