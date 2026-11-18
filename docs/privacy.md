# Privacy

MeetPact keeps this simple: the organizer adds the bot, so the organizer is responsible for telling
people the meeting is recorded. The bot helps with one short note.

* **Recording notice:** posted once in the meeting chat as soon as the bot is admitted (a message sent
  from the waiting room would be lost). Edit or turn it off under Admin → Bot and reports; an empty
  notice posts nothing. In a live Google Meet test it went out about 15 seconds after admission.
* **AI stand-up:** the host greets everyone and starts. It does not ask about recording.
* **Pause and remove:** the organizer, managers and admins can pause, resume or remove the bot from
  the meeting page. Each action is listed on the meeting's *Activity* tab.
* **Transcripts:** silence can come back as filler ("Thank you." every ~30 seconds). Short phrases
  that repeat three or more times are dropped before analysis.
* **Platform limits apply:** hosts can deny the bot (recorded as *Denied*, never retried), waiting
  rooms need someone to admit it, and Zoom may ask the host for recording permission
  (`recording_permission_denied_timeout` is set).
* **Access:** admins see everything. Managers see all employee records. Team leads see their team.
  Employees see their own records. Meeting reports follow the organizer's sharing choice. Transcripts
  are part of the full report.
* **Retention:** transcripts and recordings can be deleted automatically after a number of days
  (Admin), and an admin can erase everything about one person from their profile. Recordings are
  deleted at MeetStream too.
