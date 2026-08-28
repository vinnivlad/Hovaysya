# Leaving it running overnight (Windows)

`python -m tools.live.run` only watches while the machine is awake, and Windows
will put it to sleep by default. Four settings, and the first two are the ones
that actually matter.

## 1. Never sleep on mains power

**Settings → System → Power & battery → Screen and sleep**

Set **"When plugged in, put my device to sleep after"** to **Never**. The screen
turning off is fine and does not stop the process — only sleep does.

Or in one command, from an **elevated** terminal:

```
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 10
```

The last line lets the screen go dark after 10 minutes, which is what you want
at night.

`hibernate-timeout-ac 0` is not optional wherever hibernation is available:
Windows will hibernate on its own schedule even with sleep disabled, and a
hibernated machine is a stopped watch.

## 2. Check which sleep states the machine even has

```
powercfg /a
```

- **"Standby (S3)"** and no S0 — classic suspend. Step 1 is the whole of it,
  nothing further to do. This is what the dev machine here reports.
- **"Standby (S0 Low Power Idle)"** — modern standby, and it will sleep despite
  step 1. Then also run:

```
powercfg /setacvalueindex SCHEME_CURRENT SUB_NONE CONSOLELOCK 0
powercfg /setactive SCHEME_CURRENT
```

**If it does sleep anyway, the watcher survives it.** On S3 the process is
suspended and resumes mid-loop, so the missed stretch arrives all at once. That
is detected — a poll returning more than two minutes late is read as a suspend,
not as a slow poll — and the batch is treated as catch-up: it goes through the
tracker, prints a note instead of a fake live feed, and stays out of the lag
statistics, where one forty-minute delay would destroy the only measurement this
stage produces.

## 3. Do not require a password on wake, if you want to see the screen

**Settings → Accounts → Sign-in options → If you've been away, when should
Windows require you to sign in again → Never**

This is a real reduction in security on a machine that leaves the house. On a
desktop that stays home it is reasonable; on a laptop, prefer leaving the lock on
and just reading the log in the morning.

## 4. Closing the lid, on a laptop

**Control Panel → Hardware and Sound → Power Options → Choose what closing the
lid does → When plugged in: Do nothing**

```
powercfg /setacvalueindex SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936 0
powercfg /setactive SCHEME_CURRENT
```

## Verify it stayed awake

The watcher prints a heartbeat line every 15 minutes. In the morning, gaps in
those lines are gaps in the watch:

```
python -m tools.live.run 2>&1 | tee data/live/console.txt
```

And to see what actually happened, without scrolling:

```
python -m tools.live.report            # the newest run
python -m tools.live.report --all      # every run in data/live
```

Read the newest log by default, not all of them: an older run's log can hold
messages this one caught up on, and mixing them turns the lag figure into
nonsense — the first attempt reported a median of two and a half hours that way.

## Undoing it

**Read the current values out before changing anything**, because the defaults
differ per machine and per scheme, and "30 minutes" is a guess:

```
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
powercfg /query SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE
powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE
```

The number to keep is the hex one on the "AC power setting index" line, in
seconds — `0x00000a8c` is 2700, i.e. 45 minutes. Only the `-ac` values need
restoring if only those were changed.

`data/live/power-restore.cmd` holds the ones captured on this machine, written
before the first overnight watch. That file is gitignored on purpose: it is a
fact about one machine, not about the project.

## What this does not solve

The machine still has to be on, and a power cut ends the watch. That is what the
Oracle Cloud stage is for — see [oracle-cloud-setup.md](oracle-cloud-setup.md) —
and it is worth doing only once a night of this proves the decisions are worth
delivering.

## Getting it onto the phone

Two steps, both his, and the watcher runs identically without them.

1. In Telegram, write to **@BotFather**: `/newbot`, pick a name, and it hands
   back a token. Put that token in `data/telegram-bot.token`, one line. That
   directory is gitignored — the token must not go into the repo or into a chat.
2. Find the new bot by the username BotFather gave, and send it the word
   **hovaysya**. A bot may not open a conversation, so he has to write first —
   and the word is a handshake, not decoration: the bot's username is public,
   and without it whoever wrote to the bot first would become the recipient of
   his alerts. The watcher picks the chat up on its next poll and caches it in
   `data/telegram-chat.id`.

### A bot cannot be made private

There is no such setting. Its username is public and anyone who knows it can
write to it — they simply receive nothing, because sending goes only to the ids
in the file.

**For himself and a few close people, a private channel is the better shape.**
Create a channel, add the bot as an administrator, and put the channel's id in
`data/telegram-chat.id`. Then:

- people he invites see everything; nobody else can find the channel at all
- they need no bot, no code word, and no setup — just the invite link
- it is also the distribution he wanted from the start: himself plus a few
  others, no app store

The file takes one id per line, so a channel and direct chats can be mixed. A
recipient that fails does not stop the others.

**Finding the channel's id** without opening an API URL with the token in it:

```
python -m tools.live.whoami                     # lists every chat it can see
python -m tools.live.whoami --save -1001234567890
```

Add the bot to the channel as an administrator **first**, then post anything
there, then run it — a channel produces no updates at all until the bot is an
admin, which is the usual reason for an empty list. Telegram hands each update
over once and then forgets it, so if the list is empty, post again and re-run.

Two hardening steps in BotFather, both one command: `/setjoingroups` → *Disable*
stops anyone adding the bot to a group, and `/setdescription` can be left empty
so the bot says nothing about itself.

Then the two levels arrive as two kinds of notification:

    Тривога.                    a normal message — beeps
    Загроза: балістика.         silent — appears without a sound

Per-chat sound and volume are Telegram's own settings, so a custom tone for this
bot is set the same way as for any chat.

**What this is not.** There is no persistent status line and no sound that
overrides silent mode; both of those need the Android client. What it is for is
the comparison: this bot and the official "Тривога" app on one screen, both
beeping, and afterwards it is plain which one was worth waking up for.
