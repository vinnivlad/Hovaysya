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

## Only the backend on a server

Once the Android client lives in this repository, a server should carry what it
runs and nothing else -- his requirement: "щоб тільки бекенд качався і деплоївся
на серверах". The app source, and one day its signing config, have no business on
a box reachable from the internet.

**One repository, and the split is in the checkout.** `deploy/lean.sh` sets a
cone-mode sparse checkout to `tools deploy docs labels`; both installers run it,
as the checkout owner rather than as root, because git would otherwise write the
sparse config root-owned and the update timer could not read it. `git pull` is
unchanged and needs no flags -- sparse configuration lives in the repository and
every later pull respects it.

Two repositories were the alternative and lose on the thing this project is
arranged around: every decision, every measurement and the reason it was taken sit
in one `git log`, and the API contract the app depends on is documented beside
the code that implements it. Split them and those drift.

Renaming `tools/` to `backend/` was considered and skipped. It touches 325
imports, 7 places in the deploy and 13 in the documentation, and buys nothing the
sparse checkout does not already give -- it selects `tools/` exactly as it would
select `backend/`. On a system that deploys itself every ten minutes, a
mechanical rename of that size is a poor trade for a tidier name.

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
says what the watcher was configured to do -- and the deploy note repeats it to
the phone whenever it moved since the last one:

    🔁 Перезапуск.
    версія: b5c4914 — One file, because there is one server
    налаштування:
    · ring: 10 назв → 11 назв
    · ring_all_clear: за замовчуванням → ні
    стан: тихо · 5 канал(и)

A commit subject says what a settings change was *meant* to do; only the process
that came up can say what took effect, so that is where it belongs. It also
overrides the half-hour restart cooldown, because a settings-only change is a
restart on the same commit -- exactly what the cooldown would otherwise swallow.
Unchanged settings say nothing.

## The API, and the two machines

`tools/serve/api.py` is what the app talks to: the merged raw feed, the
decisions, and one person's settings. It exists because config editing needs it
-- "користувачі мають мати можливість змінювати свій конфіг" -- which makes the
inbound door both compulsory and writable.

    GET  /messages?since=<cursor>     the raw feed, cursor-paged
    GET  /messages?back=30m           ...or the last half hour, for a cold screen
    GET  /decisions?since=<cursor>    what Ховайся decided, for this recipient
    GET  /config · PUT /config        their settings
    GET  /health                      no token needed, and see below

**The API runs on A and the certificate lives on B.** The app talks TLS to B,
Caddy proxies over the private VCN address to A, and A answers out of the
database the watcher wrote a second ago.

That is the second design. The first replicated the corpus from A to B, and he
killed it in one sentence: "якщо треба чекати поки щось запушиться, а потім поки
застосунок опитає - то сенс застосунку губиться." He was right, and the
arithmetic agrees -- a push on a timer plus an app poll is minutes of lag on a
screen whose whole job is to be current during an attack, and no interval fixes
that, it only makes it smaller. Proxying is zero.

| | A | B |
| --- | --- | --- |
| runs | the watcher, the API | Caddy, and nothing else |
| inbound | SSH, and 8080 from B's private address | 80 and 443 from anywhere |
| holds | everything | a certificate |

**What this costs, stated rather than argued away.** A now accepts inbound
connections. Only from the private network, not the internet -- but if B were
compromised the attacker could reach A's API: the corpus, which is public, and
the recipient configs, which are not. Not the bot token, not SSH. Compare the
alternative we refused, where B pulled over SSH and holding B meant holding A.

The bot token is on A now, so the argument that used to keep it away from the
service -- it lives on the other box -- is gone. `ReadOnlyPaths` grants *read*
access, so the unit names each secret and denies it with `InaccessiblePaths`.

**The bell never goes through any of this.** A decides and calls FCM directly:
detection is a measured 6 s and the push about one. The proxy path carries only
the screens, which are read by somebody the bell has already woken.

### /health is the point, not a detail

His question settled the shape: "реально, якщо А не працює, то який взагалі
сенс?" A service that answers `{"ok": true}` while the watcher is dead is worse
than one that does not answer at all -- the app would show a calm sky and the
phone would stay silent, which is exactly what a quiet night looks like.

    {"ok": true, "corpus": true, "poll_age_s": 3, "message_age_s": 585}

**`poll_age_s` is the one to act on.** The watcher rewrites its decision log
after every poll cycle whether or not anything arrived, so this is the age of the
poll loop itself: seconds while it runs, unbounded when it stops. Nothing has to
be shared or agreed -- it is read off the file the watcher writes.

**`message_age_s` is information, not health**, and the corpus is what says so.
Over two weeks of seven channels the median gap between messages is 23 s, but
silences longer than ten minutes happen 307 times -- about twenty-two a day -- and
the longest was six hours. An app treating minutes here as a fault would cry wolf
daily. This paragraph said the opposite until the first live `/health` answered
`585` and the data was checked.

Numbers rather than a verdict, because the threshold is the app's business and
the app is the only part that knows whether anyone is looking. Caddy also probes
`/health` every 30 s, so a dead A becomes a fast 502 instead of a hang.

### Two ways into the feed

A cursor the app has never held means the beginning of the corpus -- January 2024,
and 27 000 messages to walk before reaching tonight. So opening a screen cold
needed its own way in, which is his: "коли я відкриваю скрін, я хочу бачити
останні повідомлення за 30хв".

    ?since=<cursor>   everything after what it already has. The ordinary poll.
    ?back=30m         the last half hour. Also 1800, 2h, 45s -- clamped to
                      between a minute and a day, and ignored if unparseable.

 returns the **newest** messages in the window, not the oldest, and hands
them over oldest-first so the app can append. A screen is not an archive: half an
hour during an attack is three hundred messages and the last two hundred are the
ones worth showing.

**An empty window still hands over a cursor.** Ten minutes of silence happens
about twenty-two times a day, so an app opening during one is ordinary -- and
without a cursor it would have no way forward except replaying from January 2024.
His words, which are plainer than mine: "якщо за минулі 30хв нічого не було, то
курсора нема."

That is also why there is no third way in. `?since=head` existed to fetch a bare
cursor and he asked what it was for; once `back` carries a cursor of its own,
nothing was left for it to do.

### Setting it up

On **A**:

    cd ~/hovaysya && git pull
    sudo ./deploy/install-api.sh                  # finds its own 10.x address
    python3 -m tools.serve.token --name <who>      # printed once

On **B**:

    sudo ./deploy/install-proxy.sh hovaysya.duckdns.org <A's 10.x address>

A hostname is not optional: **Let's Encrypt will not issue for a bare IP.** A
free DuckDNS name is enough, `deploy/duckdns.sh` keeps it current on a timer, and
Caddy handles the certificate and its renewal -- so nothing in this repository
touches a private key.

Three things the scripts cannot do, all of them clicks in the dashboard:

- **80 and 443 for B**, in an NSG on B rather than the subnet's security list --
  both instances share `public subnet-hovaysya-vcn`, so opening it there would
  open the watcher too.
- **8080 for A, from B's private address only.** The script opens the host
  firewall for the whole subnet; the NSG is what narrows it to one machine.
- **Reserve B's public IP.** An ephemeral one changes on stop, and the DuckDNS
  updater would follow it only after a pause.

Then `curl https://<host>/health` should answer with the ages above.

### What protects it

- **A token on every path but `/health`**, compared with `hmac.compare_digest`.
- **The config loader is the trust boundary.** It was written so a typo could not
  take the watch down at 3 a.m.; the same code now stands between a hostile body
  and the decision, which is why `MAX_RING` and `MAX_NAME` exist -- a ring of
  50 000 names was once accepted and moved one decision from 0.03 ms to 0.3 ms,
  which at a hundred recipients is a denial of service written in JSON. What lands
  on disk is what the loader accepted, never the body as sent.
- **A read-only database handle**, said in the connection URI rather than left to
  the code.
- **A systemd jacket** tighter than the watcher's: its own unprivileged user,
  `ProtectSystem=strict`, an empty capability set, `ReadWritePaths` covering only
  where settings live, and `InaccessiblePaths` over each secret by name.

There is no rate limit, and that was a correction rather than a choice: the
Caddyfile had one until I checked, and `rate_limit` is a third-party module the
packaged Caddy cannot parse -- the directive fails the config at startup. Adding
it means building Caddy with xcaddy, a second toolchain for a service whose only
unauthenticated path returns four numbers. The token is 32 bytes from
`secrets.token_urlsafe` and is not guessable at any rate; fail2ban is the answer
if the log ever suggests otherwise.

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
