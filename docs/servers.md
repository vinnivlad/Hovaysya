# The two servers

Operating Ховайся: what runs where, how a change reaches it, and how to rebuild
from nothing. Oracle Always Free, region Marseille, Ubuntu 24.04 Minimal on
aarch64.

**Addresses, keys and account details are not here.** They live in
`data/runbook.md`, which is gitignored — this repository is public, and that is
what lets an instance `git pull` with no credentials at all. Everything in this
file is procedure, which is the part that has to be versioned: the runbook spent
two days describing B as the API after the API had moved to A, and the only
reason nobody saw it is that a file outside git has no diff.

---

## What runs where

Two machines, and the split has one purpose: **the box reachable from the
internet is not the box holding the bot token.** The reasoning is in
`deploy/README.md`.

| | A | B |
| --- | --- | --- |
| Role | the watcher **and** the API | TLS only |
| Private IP | `10.0.0.75` | `10.0.0.109` |
| Services | `hovaysya.service`, `hovaysya-api.service` on the private address | `caddy.service`, proxying to `10.0.0.75:8080` |
| Inbound | **SSH only** | 80 and 443 |
| Timers | `hovaysya-update.timer` | `hovaysya-duckdns.timer`, `hovaysya-proxy-update.timer` |
| Holds | the corpus, the decision logs, the bot token, the recipients directory | nothing of its own |
| Shape | `VM.Standard.A1.Flex`, 1 OCPU / 1 GB | the same |

The API is on **A**, beside the watcher, and that was the third arrangement
rather than the first. It was going to live on B with the database replicated to
it, and the constraint that killed that is his: "якщо треба чекати поки щось
запушиться, а потім поки застосунок опитає — то сенс застосунку губиться". So
the API reads the database the watcher has just written, and B is a proxy with a
certificate and nothing else.

**B's ports are on a Network Security Group, not the subnet's security list.**
Both instances sit in the same public subnet, and a security list applies to the
whole subnet — opening 80/443 there would have opened them on the watcher too,
which is the one thing this split exists to prevent. The NSG is attached at
Instance → Networking → Primary VNIC → Network security groups.

**There must be no watcher on B.** `systemctl is-active hovaysya` should fail
there, and its `data/` should hold no `telegram-bot.token`: two watchers on one
channel means every notification twice. See "When two watchers run at once".

---

## Day to day

    systemctl status hovaysya            # running, and since when
    journalctl -u hovaysya -f            # the live feed
    journalctl -u hovaysya -n 100        # what it just did
    sudo systemctl restart hovaysya      # a plain restart
    systemctl list-timers 'hovaysya*'

A restart is cheap: the watcher rebuilds its episode state from the last ninety
minutes of the database, so restarting mid-alert does not make it start blind.

On B:

    systemctl is-active caddy hovaysya-proxy-update.timer
    grep -c '@waiting' /etc/caddy/Caddyfile        # 1 once the proxy split is applied
    curl -s https://<the name>/health              # {"ok":true,...}

## Deploying a change

Push to `main`. Each machine pulls on its own timer and acts only if something
actually changed.

    sudo systemctl start hovaysya-update           # on A, to not wait
    sudo systemctl start hovaysya-proxy-update     # on B

On A a **silent** Telegram message arrives once the watcher is back on the air —
`🔧 Оновлено і перезапущено` with the commit and what came with it. It is sent at
the end of start-up rather than by the deploy script on purpose: that git pulled
says nothing about whether the process came up and reached the live feed. A
restart on the same commit says `🔁 Перезапуск`, rate-limited to once every half
hour, so a crash loop cannot become the thing that wakes anybody.

On B the Caddy config is **re-templated and compared** rather than restarted:
almost nothing committed here touches the proxy, so `update-proxy.sh` renders the
Caddyfile with the hostname and A's address, does nothing if the result is
identical, and validates before installing if it is not.

B had no update timer at all until 2026-09-03, and the cost of that is the reason
it is written down: its checkout moved only when somebody typed `git pull`, so
the day that started asking for a password, B silently stopped receiving
anything. A proxy fix sat on its disk, pulled and unapplied, and the only symptom
was the app reading `HTTP 504` — which points at everything except the machine
that had stopped updating.

## Rolling back

    cd ~/hovaysya
    git log --oneline -10
    git checkout <sha>
    sudo systemctl restart hovaysya

The timer will pull `main` back over it, so for anything longer than a look,
revert on `main` instead.

---

## From nothing

### 1. The instance

Compute → Instances → **Create instance**. Set the **shape first** — the image
list and the memory fields both depend on it.

| Field | Value |
| --- | --- |
| Shape | Change shape → Ampere → `VM.Standard.A1.Flex` → **1 OCPU, 1 GB** |
| Image | `Canonical Ubuntu 24.04 Minimal aarch64` — without the `aarch64` suffix it is an x86 build and will not boot here |
| Capacity type | On-demand |
| Primary network | the existing VCN |
| Subnet | the one whose name says **Public** |
| Public IPv4 | on |
| IPv6 | off — the watcher is outbound-only |
| SSH keys | paste the public key |
| Boot volume | leave the custom-size toggle **off** |

Two rules that cost money if broken:

- **Never click "Upgrade to Pay As You Go."** Without it the account has no
  billing relationship at all: an attempt to exceed Always Free fails with an
  error instead of quietly costing something.
- **If the "Always Free eligible" badge is missing from a field, stop.** That
  badge is the only indicator that a resource is free.

The cost estimator in the create dialog shows the boot volume at list price
because it does not apply the Always Free allowance. Compute shows nothing, which
is the tell. The two boot volumes together are under half of the 200 GB allowed.

**1 GB of memory is deliberate, and it is the smallest shape rather than the
largest.** Oracle reclaims an idle Always Free instance when CPU, network **and**
memory all sit below 20% for seven days — ANDed, so clearing any one is enough.
The threshold scales with what was provisioned, so asking for less makes the
instance safer: 20% of 1 GB is 200 MB, and the service holds a stated 260 MB
ballast (`--memory-floor-mb 260` in the unit). On 6 GB the threshold would be
1.2 GB, the watcher uses tens of megabytes, and the machine would be taken.
Growing later is a resize rather than a rebuild — Always Free allows 4 OCPU and
24 GB.

If it says **"Out of host capacity"**: normal for A1, not a mistake. Try another
availability domain, or retry in an hour or two. Do not switch to a paid shape to
get past it.

### 2. The network, if it has to be rebuilt too

Networking → Virtual cloud networks → **Create VCN** → *VCN with Internet
Connectivity*, defaults for everything else. That wizard makes the VCN, a public
and a private subnet, an internet gateway and the routes, all Always Free.

The instance form loads its VCN list once, when the page opens. Create the
network first, or reload the page afterwards — otherwise the dropdown stays grey
and looks broken.

### 3. Install

On **A**, the watcher and the API:

    sudo apt update && sudo apt install -y git python3
    git clone https://github.com/vinnivlad/Hovaysya.git ~/hovaysya
    mkdir -p ~/hovaysya/data
    cd ~/hovaysya && sudo ./deploy/install.sh
    sudo ./deploy/install-api.sh                    # finds its own private address

On **B**, TLS only:

    sudo apt update && sudo apt install -y git curl
    git clone https://github.com/vinnivlad/Hovaysya.git ~/hovaysya
    nano ~/hovaysya/data/duckdns.token && chmod 600 ~/hovaysya/data/duckdns.token
    cd ~/hovaysya && sudo ./deploy/install-proxy.sh <the name> 10.0.0.75

**Clone with the plain URL, exactly as written.** A `username@` in front of
`github.com` obliges git to ask for that user's password on every fetch, even
though the repository is public and no authentication is wanted — and a timer,
having no terminal, does not fail on that but waits, holding the repository lock,
until somebody notices days later. That cost two days on B.

The watcher needs **no third-party packages** — Python's standard library and
nothing else. `deploy/lean.sh`, which both installers run, leaves only
`tools deploy docs labels` in the checkout: the app's source has no business on a
box reachable from the internet.

### 4. Secrets

Never retyped, always copied. The paths and the exact command are in
`data/runbook.md`; what has to arrive is:

| On | File | What it is |
| --- | --- | --- |
| A | `data/telegram-bot.token` | the bot |
| A | `data/telegram-chat.id` | where it writes |
| B | `data/duckdns.token` | keeps the name pointing at B |

A recipient's token is minted rather than copied, and only if somebody needs one
without the app:

    python3 -m tools.serve.token --name <who>       # shown once, never again

The app registers itself and needs none of this.

### 5. History, then start

    cd ~/hovaysya && python3 -m tools.export.export --since 2026-07-01
    sudo systemctl start hovaysya
    journalctl -u hovaysya -f

**The export is not optional.** A channel with no history starts blind: the
watcher takes the newest message id and begins there, so everything before the
first start is invisible to it — including an alert already running.

A silent `▶️ Спостерігач запущено` in Telegram is the confirmation that the whole
chain works: the process came up, found its token, warmed its tracker from the
database and started polling.

---

## The account, once

- Billing & Cost Management → **Payment Method**: Free Tier, no Pay As You Go
  subscription, no card. With nothing to charge, exceeding the allowance fails
  rather than bills.
- **Cost Analysis** should read zero.
- Governance → **Limits, Quotas and Usage**: nothing unexpected provisioned.

**A promo account's trial credits expire about thirty days after sign-up.**
Resources created *on the credits* are reclaimed then; Always Free ones are not.
If an instance vanishes near that date, something was on the wrong quota after
all — rebuild from "From nothing" above.

## When two watchers run at once

Both send to the same chat, so every alert arrives twice. That is the expected
state only while a server is being proved out; afterwards stop the local one:

    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
      Where-Object { $_.CommandLine -like '*tools.live.run*' } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

## Bringing the night logs home

A scheduled task on the Windows machine, `Hovaysya - pull night logs`, runs daily
at 13:00 and copies `~/hovaysya/data/live/` into a local directory. Missed runs —
the machine was off — start as soon as it is on again. The host and target are in
`data/runbook.md`.

    python -m tools.pull --host <A> --to <local directory>

    schtasks /run   /tn "Hovaysya - pull night logs"     # now, not tomorrow
    schtasks /query /tn "Hovaysya - pull night logs" /v  # when it last ran
    schtasks /delete /tn "Hovaysya - pull night logs"    # remove it

A healthy run says nothing — it runs every day, and a daily message is one you
learn to ignore. It sends a silent Telegram message in three cases: the copy
failed; the copy worked and found no logs at all; or the newest log is more than
six hours old, which means the watcher has stopped writing.

That third one is why this checks more than scp's exit code. **A watcher that
dies at 3 a.m. is otherwise invisible**: the phone simply stops beeping, and that
is exactly what a quiet night looks like.

## What cannot be recreated

`data/live/*.jsonl` — one file per night, every decision and the reason for it.
These are the training set and they exist nowhere else. `python -m tools.backup`
copies them, and the database through SQLite rather than as a file, because WAL
mode makes a plain copy look fine and be corrupt.

`data/hovaysya.keystore` — the app's signing key. Losing it means every phone
must uninstall and re-register, because Android identifies an app by its
signature and a build signed with a different key cannot replace an installed
one. It is the one file here worth a copy on another machine.
