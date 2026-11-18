# AI stand-up host

Pick **AI stand-up** when sending a bot or creating a schedule. Instead of only listening, the bot runs
the meeting out loud, from start to finish.

## How a stand-up runs

1. **Opening.** The host greets everyone, says it is the AI facilitator and how the meeting will go,
   and starts with the first person. The written recording notice is posted in the meeting chat when
   the bot is admitted. To have the host also ask out loud whether recording is OK, turn on
   *AI stand-up asks out loud for recording consent* in Admin → Bot & settings.
2. **Round.** It calls on each person by name and asks what they completed, what they're working on
   today, what they expect to finish and by when, and whether anything is blocking them. It uses each
   person's carried-over work to follow up specifically ("last time you said the export was nearly
   done - did it land?") and asks one follow-up when an answer is vague. People who don't answer are
   skipped; anyone not on the list who speaks up is included.
3. **Open floor.** "Is there anything else anyone wants to raise before we wrap up?"
4. **Close.** A short recap of who committed to what (with deadlines) and any blockers, then
   "That's everything for today. Thanks everyone - I'll leave the meeting now."
5. **Leave.** With `PUBLIC_URL` set, the host calls an `end_meeting` tool and the app removes the bot a
   few seconds after the goodbye. Without a public URL, the bot leaves 60 seconds after everyone else
   has left the call, with a 3-minute silence timeout as a safety net
   (`STANDUP_SILENCE_LEAVE_SECONDS`). Keep that timeout generous: MeetStream measures silence from the
   participants only, so the agent's own speech does not count, and a short value removes the bot
   mid-meeting.

The call is transcribed like any other meeting and goes through the same analysis, so the updates,
work items and blockers land in everyone's records.

## What the host knows

Before joining, MeetPact creates a MeetStream MIA agent for that meeting. Its instructions contain the
roster - the meeting's team, or everyone if no team is set (up to 15 people) - and for each person
their open work, deadlines, how often items were carried over, open blockers and last update. The
agent is deleted after the meeting.

**Who is in the call.** MeetStream exposes the participant list only after the meeting, so by
default the host does not see who joined: it calls on the team, skips people who don't answer and
includes anyone who speaks up. With `PUBLIC_URL` set, MeetStream sends live join/leave events, and
the host gets a `list_participants_now` tool: it checks who is present before the round and again
before the open floor, so it skips absent people and asks late joiners for their update. It can also
look up a late joiner's history through the `/mcp` endpoint (`get_person_context`). Late joiners
also see the recording notice: by name with `PUBLIC_URL`, otherwise via a reminder every 10 minutes.

## Voice providers

The default is **Gemini Live** (`MIA_MODE=realtime`, `MIA_MODEL_PROVIDER=google`, voice `Puck`), which
a MeetStream account can use without adding its own provider key. Pipeline agents (a transcriber, an
LLM and a voice, for example Claude + ElevenLabs + Deepgram, or OpenAI) work too, but MeetStream
rejects them with "API key not configured" until that provider's key has been added to your MeetStream
account. See [configuration.md](configuration.md#ai-stand-up-host).

## Limits

- When voices overlap, transcription can attach a sentence of the host's speech to a person. The
  analysis is told to treat questions, greetings and recaps as the host's.
- Speech-to-text can mishear names and product names.
- Turn-taking quality depends on the MeetStream voice agent and the meeting platform's audio.
