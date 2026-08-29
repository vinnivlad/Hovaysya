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
