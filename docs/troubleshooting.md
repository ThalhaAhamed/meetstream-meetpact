# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The bot never appears in the meeting | It is in the waiting room. Google Meet often needs the host to admit an anonymous bot. | Admit it. It waits `WAITING_ROOM_TIMEOUT` seconds, then the meeting shows *Not admitted*. To have it join without the host, use a [signed-in Google Meet bot](configuration.md#signed-in-google-meet-bot) or set the meeting's access to *Open*. |
| The bot leaves an empty meeting before the host arrives | Nobody else joined within `NO_ONE_JOINED_TIMEOUT` seconds. | Raise `NO_ONE_JOINED_TIMEOUT` (up to 1800). |
| A signed-in Google Meet bot shows *Failed: the bot could not sign in to its Google account* | MeetStream could not sign in to the bot account (`google_sign_in_failed`): the domain or account isn't registered, or that account is busy with `GOOGLE_BOT_STRICT_EMAIL=true`. | Check the registration with MeetStream, or set `GOOGLE_BOT_STRICT_EMAIL=false`. |
| Meeting shows *Denied* | A host refused the bot. | Not retried on purpose. Send it again if that was a mistake. |
| "MEETSTREAM_API_KEY is not set" | No key in `.env`. | Add it and restart the backend. |
| Stand-up fails with "API key not configured for: model.provider=openai" | The voice agent uses a provider whose key isn't on your MeetStream account. | Add that provider's key in MeetStream (app.meetstream.ai → Configure → Integrations), or pick a voice whose key is already there. **Check with MeetStream** under the stand-up voice tells you straight away. |
| The stand-up host stays in the call after saying goodbye | No public address, so it can't call its leave tool; it leaves 60 s after everyone else does. | Install `cloudflared` (MeetPact then opens a tunnel itself) or set `PUBLIC_URL`. Admin → Server setup shows whether the tunnel is up. |
| The stand-up host leaves in the middle of the meeting | The silence timeout is too short: MeetStream only counts participants' voices. | Keep `STANDUP_SILENCE_LEAVE_SECONDS` at 180 or more. |
| Report stays at *Waiting for transcript* | MeetStream is still transcribing (usually 1-2 minutes after the call; longer for long calls). | Wait. It gives up after 6 hours; *Re-analyse* tries again. |
| *Processing failed: MeetStream could not transcribe this meeting* | The transcription provider's key is missing on your MeetStream account. | Use `TRANSCRIPT_PROVIDER=meetstream`, or add the provider key in MeetStream. |
| *No Anthropic credentials found* / *Gemini rejected the API key* | Analysis key missing or wrong. | Set `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`, restart, then *Re-analyse*. |
| A speaker isn't linked to anyone | Their meeting name doesn't match an employee name or alias. | Pick the person under the meeting's *Participants* tab (remembered as an alias), then *Re-analyse*. |
| Lines from the AI host are attributed to a person | Overlapping voices in the transcript. | The analysis ignores host-style lines; correct anything left over from the person's profile. |
| Webhooks never arrive | `PUBLIC_URL` isn't reachable from the internet. | Check `https://<PUBLIC_URL>/api/health` from outside. Polling keeps working without them. |
