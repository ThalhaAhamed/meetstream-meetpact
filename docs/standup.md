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
5. **Leave.** With a public address (`PUBLIC_URL`, or the automatic tunnel when `cloudflared` is
   installed), the host calls an `end_meeting` tool and the app removes the bot a
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
the host gets a `list_participants_now` tool (the automatic tunnel provides this too): it checks who
joined or left before the round and again before the open floor, so it skips people who left and asks
late joiners for their update. MeetStream sends no join event for people who were already in the call
when the bot arrived, so the host still calls on the expected team by name. It can also
look up a late joiner's history through the `/mcp` endpoint (`get_person_context`).

## Voice providers

There is no default voice. An admin picks the host's voice under **Admin → Bot & settings → Stand-up voice** (or in the setup guide), and stand-ups can't be booked until one is picked. Setting `MIA_MODEL_PROVIDER` in `.env` also counts as a choice.

| Voice | MeetStream mode | Needs |
|---|---|---|
| **Gemini Live** | realtime, provider `google`, voices Puck, Charon, Kore… | your Google (Gemini) key in MeetStream |
| **OpenAI** | realtime, provider `openai`, `gpt-realtime-mini`, voices coral, alloy, nova… | your OpenAI key in MeetStream |
| **Grok** | realtime, provider `xai` (MeetStream picks the model), voices Ara, Eve, Leo, Rex, Sal | your xAI key in MeetStream |
| **Claude** | pipeline: Deepgram → Claude (`claude-haiku-4-5`) → ElevenLabs voice | your Anthropic, Deepgram and ElevenLabs keys in MeetStream. Anthropic has no speech-to-speech model, so answers take a little longer |

MeetStream runs these with the provider keys saved in its dashboard (**app.meetstream.ai → Configure →
Integrations → Models / Voice / Transcription**); there is no documented API to add them, so MeetPact
links there. Every voice needs at least one key: MeetStream's own inbuilt keys only cover pipeline
agents built on Deepgram and OpenAI, and realtime (speech-to-speech) agents always run on your key.
The host costs MeetStream's agent fee per hour on top of the bot; your provider bills you for the model. **Check with MeetStream** creates a throwaway agent config and deletes it, which tells you
straight away whether your account can use the voice ("API key not configured for … OpenAI" means
add the key in the dashboard).

The notes are written by the AI picked under *AI notes* (Gemini, Claude, OpenAI or Grok), independent
of the voice. Without a choice in the app, the `MIA_*` variables decide, as before
([configuration.md](configuration.md#ai-stand-up-host)).

## Limits

- When voices overlap, transcription can attach a sentence of the host's speech to a person. The
  analysis is told to treat questions, greetings and recaps as the host's.
- Speech-to-text can mishear names and product names.
- Turn-taking quality depends on the MeetStream voice agent and the meeting platform's audio.
