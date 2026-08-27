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
python - <<'PY'
import json, pathlib
rows = [json.loads(l) for p in sorted(pathlib.Path("data/live").glob("*.jsonl"))
        for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
live = [r for r in rows if not r.get("warm")]
woke = [r for r in live if r["level"] == "alert"]
print(f"{len(live)} messages, {len(woke)} would have woken you")
for r in woke:
    print(f"  {r['at'][11:19]}  {r['said']}   <- {r['text'][:50]}")
PY
```

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
