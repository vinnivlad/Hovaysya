# Running it on a server

The watcher needs **no third-party packages** — Python's standard library and
nothing else. `requirements.txt` exists for the tests and for the deferred
MTProto path, and neither runs in production.

## The shape of a deploy

**The instance pulls; nobody pushes to it.** A new version is a commit on
`main`; the instance fetches it on a timer and restarts itself if anything
changed.

That is a deliberate choice and not merely convenient:

- no server credentials have to be shared with anyone, including me
- rollback is `git checkout <sha>` on the instance, or a revert commit
- what is running is always a named commit, and `systemctl status` says which

The cost is that a deploy is not instant — the timer decides. That is the right
trade for a service whose whole job is to be running at 3 a.m.

## Once, on a fresh instance

    sudo apt update && sudo apt install -y git python3
    git clone https://github.com/vinnivlad/Hovaysya.git ~/hovaysya
    cd ~/hovaysya && sudo ./deploy/install.sh

Then place the secrets, which are gitignored and never travel through the repo:

    mkdir -p ~/hovaysya/data
    nano ~/hovaysya/data/telegram-bot.token     # from @BotFather
    nano ~/hovaysya/data/telegram-chat.id       # the channel id, one per line

Then fill the database, because **a channel with no history starts blind** — the
watcher takes the newest message id and begins there, so everything before the
first start is invisible:

    python3 -m tools.export.export --since 2026-07-01

Finally:

    sudo systemctl start hovaysya
    journalctl -u hovaysya -f

## Watching it

    systemctl status hovaysya            # running, and on which commit
    journalctl -u hovaysya -n 50         # the live feed
    systemctl list-timers hovaysya-update

## The idle-reclamation problem, which is real here

Oracle reclaims an Always Free instance when CPU, network **and** memory all sit
below 20% for seven days. The conditions are ANDed, so clearing any one is
enough — and `docs/oracle-cloud-setup.md` originally argued that memory would be
cleared by a loaded classifier.

That classifier does not exist yet, and the watcher uses a few tens of
megabytes. On the 6 GB shape that guide recommends it would sit at roughly 1% of
the memory threshold and the instance would be taken.

Two answers, and the service uses both:

- **Provision 1 OCPU / 1 GB, not 6 GB.** The threshold scales with what you
  asked for, so asking for less makes the instance safer. 20% of 1 GB is 200 MB.
- **`--memory-floor-mb 260`**, which holds a real allocation for exactly this
  reason. It is stated plainly rather than disguised as a cache, because a cache
  that exists to fool a monitor is a lie in the code.

When the model arrives it will clear the threshold honestly and the floor can go.

## Deploying a change

Commit and push to `main`. Within the timer's period the instance pulls, and
restarts only if the working tree actually changed. To force it:

    sudo systemctl start hovaysya-update

## Settings

`hovaysya.json` at the repo root, **in git** on his reasoning: a change to a
setting is then a commit with a message saying why, it deploys by the same pull
as the code, and the restart that deploy performs is what applies it -- so there
is nothing to re-read and no reload machinery to get wrong.

One file, because there is one server. A second layer in `data/` was written and
then removed on his reading of it -- "у нас же один сервер" -- and an experiment
does not need one either, since `--config` points the watcher at any path.

A missing file means the defaults, which are the behaviour as shipped. A broken file, an unknown
key or a number out of range prints a line and changes nothing else -- a typo
must never be the reason the watch is not running at 3 a.m.

An empty object is the same as no file at all -- every setting below is shown
with the value it already has, so this example changes nothing:

    {
      "home": "Жуляни",
      "ring_all_clear": true,
      "ring_memory_s": 600,
      "quiet_hours": false
    }

What can be set, and the full list is in `tools/policy/config.py`:

- **whose place** -- `home` and `ring` as lists of names. The gazetteer stays the
  recognition layer, with every inflection and piece of slang; only the tier
  becomes personal, which is what makes a different ring cheap.
- **what makes a sound** -- the start of an alert, the all-clear, a partial
  all-clear, each rung of the cruise ladder, a ballistic launch after a recheck,
  and whether a drone needs the home name or the whole ring will do.
- **what appears without one** -- the ballistic detail during a wave, rechecks,
  ballistic destinations, a repeat over home, a drone in the ring.
- **how long something counts as already said** -- and the measured ones are
  marked as measured in the file's comments, so whoever changes one knows what
  they are overriding.
- **quiet hours** -- a window in which only ballistic and above keep their sound.

The startup line prints only what differs from the defaults, so a night's log
says what the watcher was configured to do.

## How you find out it worked

The watcher sends a **silent** message to the same chat as it reaches the live
feed:

    🔧 Оновлено і перезапущено.
    версія: af814ab — Leave an orientation for whoever picks this up
    · Keep what is not in git
    стан: тихо · 5 канал(и)

`update.sh` could send that itself and it would be cheaper, but it would be
answering the wrong question: that git pulled says nothing about whether the
process came up, found its token, warmed its tracker and started polling. Sent
from `tools/live/version.py` at the end of startup, the message exists only if
all of that actually happened — which is also what makes it the answer to "чи
запрацював спостерігач на ораклі", on a machine that has never run it before:

    ▶️ Спостерігач запущено.

A restart on the **same** commit says `🔁 Перезапуск.` and is rate-limited to
once every half hour. `Restart=always` with `RestartSec=10` means a watcher that
cannot start would otherwise send six messages a minute forever, and the deploy
note would become the thing waking him up.

The last announcement is recorded in `data/live-version.json`, which is
gitignored along with the rest of `data/`. Deleting it makes the next start
announce itself as a first start.
