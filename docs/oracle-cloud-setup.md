# Oracle Cloud Free Tier setup — a zero-charge guide

Goal: run the Hovaysya ingest server 24/7 outside Ukraine at **no cost, with no
possibility of being billed** — a hard stop, not a budget alert.

Verified against Oracle documentation on 2026-08-27. Oracle changes these terms;
re-check the linked pages before signing up.

---

## The one rule that guarantees you are never charged

**Never click "Upgrade to Pay As You Go."**

That is the entire safety model, and unlike a budget it is a genuine hard limit:

- A Free Tier account has **no billing relationship**. Oracle authorizes your
  card at signup to verify identity, then releases the hold. Per Oracle, the
  card is not charged unless you upgrade.
- Without an upgrade, the account **cannot provision paid resources at all**. An
  attempt to exceed Always Free limits fails with an error instead of silently
  generating cost. This is exactly the behavior we want.
- Always Free resources are available for unlimited time and are never reclaimed
  for billing reasons.

Contrast with AWS, where a free-tier overrun becomes an invoice and "budgets"
only email you after the fact. An Oracle Free Tier account is structurally
incapable of billing you. The budget alert in Step 3 is a tripwire, not the cap.

## Two different things are called "free"

Signup gives you **both**, and conflating them is how people get surprised:

|  | Free Trial credits | Always Free |
| --- | --- | --- |
| What | US$300 of credits | A fixed set of resources |
| Duration | 30 days from signup | Unlimited, for the life of the account |
| Can provision paid shapes | **Yes** | No |
| Risk | Resources created here are **reclaimed** when the trial ends unless you upgrade | None |

**Therefore: during the 30-day trial, provision only resources the console marks
"Always Free eligible."** Then nothing is reclaimed when the trial expires,
nothing is owed, and the account simply continues as Always Free.

When the trial expires without an upgrade you get a 30-day grace period; paid
resources you created are reclaimed at the end of it, and Always Free resources
continue untouched. If you followed the rule above, this transition is a
non-event.

---

## Step 1 — Sign up

1. Go to <https://www.oracle.com/cloud/free/> and choose **Start for free**.
2. Fill in country, name, email. Verify the email.
3. **Home region — choose carefully. It cannot be changed later.**
   - Pick a region reasonably close to Ukraine: Frankfurt, Amsterdam,
     Stockholm, or Marseille.
   - Trade-off: popular EU regions frequently report "Out of host capacity" for
     Ampere A1 instances. A less busy region (Stockholm, Marseille, Zurich) is
     often easier to provision into. A 10-30 ms latency difference is irrelevant
     for this workload, so optimize for capacity, not latency.
4. Phone verification by SMS.
5. Card verification. Expect a temporary authorization hold (typically ~US$1,
   released by the issuing bank within a few days).

### Card safety

- The safest practical option is a **virtual card with a low limit** (Monobank,
  Revolut, Wise), so even a hypothetical charge cannot exceed that limit.
- Caveat: Oracle's fraud checks sometimes reject virtual or prepaid cards. If
  verification fails, a normal debit card usually works; the hold is still only
  a hold.
- Do **not** keep a stored payment method beyond verification, and do not add a
  second card later. There is no reason to.

### If signup fails

Accounts from some countries land in manual review, which can take hours to
days, and are occasionally rejected with no stated reason. Do not fight it.
Fallbacks, in order of preference:

1. **Hetzner Cloud CX22** — about EUR 4/month, 2 vCPU / 4 GB, EU. Not free, but
   prepayable, so it is equally incapable of surprising you. This is the
   pragmatic answer if Oracle turns into a fight.
2. **Google Cloud e2-micro Always Free** — 1 GB RAM, US regions only. Enough for
   ingest, too tight for local model inference.

---

## Step 2 — Provision the instance

Create a Compute instance with:

- **Shape:** `VM.Standard.A1.Flex` (Ampere ARM), marked *Always Free eligible*
- **OCPUs:** 1 — **Memory: 1 GB** (deliberately the *smallest* shape, not the
  largest — see "the idle-reclamation trap" below, which is the whole reason)
- **Boot volume:** 50 GB (minimum 47 GB; Always Free allows 200 GB total)
- **Image:** Ubuntu 24.04 LTS (ARM build) or Oracle Linux 9
- **Networking:** assign a public IPv4. No inbound ports beyond SSH are needed —
  Hovaysya is outbound-only (Telegram MTProto, the alert APIs, and FCM are all
  outbound connections), so dynamic addressing and NAT are non-issues.

Every cost-affecting field in the console carries an "Always Free eligible"
badge. If a badge is missing, you are about to create a paid resource — stop.

### The idle-reclamation trap, and why we ask for 6 GB

Oracle reclaims idle **Always Free** compute instances. Per Oracle's docs, an
instance counts as idle when **all** of the following hold over a 7-day window:

- CPU utilization, 95th percentile, below 20%
- Network utilization below 20%
- Memory utilization below 20% *(A1 shapes only)*

Because the conditions are ANDed, **staying above any single threshold is
enough**. Memory is the cheapest one to clear, and the threshold scales with
what you provisioned — which is why asking for *less* memory makes the instance
*safer*:

| Provisioned | 20% threshold | Realistic usage of our service |
| --- | --- | --- |
| 12 GB | 2.4 GB | ~0.6 GB for ingest alone → **at risk** |
| 6 GB | 1.2 GB | ingest + loaded classifier → **clears it** |

A Python service holding a loaded `xlm-roberta-base`, the toponym gazetteer, and
a SQLite page cache sits comfortably above 1.2 GB.

**That model does not exist yet, and this advice was written as though it did.**
Measured: the watcher needs no third-party packages at all and uses a few tens of
megabytes, which is about 1% of the 6 GB threshold. On the shape this guide
recommends, the instance would be reclaimed.

So until the classifier arrives, provision **1 OCPU / 1 GB** — the threshold
scales with what you ask for, so asking for less makes the instance safer, and
20% of 1 GB is 200 MB. The service holds a stated ballast above that; see
`deploy/README.md`. Always Free allows up to 4 OCPU and 24 GB, so growing later
is a resize rather than a rebuild.

Oracle's docs do not promise advance notice before reclamation. Treat the
instance as replaceable: the server must be reproducible from this repo plus a
config file, and the message database must be backed up off-instance.

---

## Step 3 — Set the budget tripwire (advisory only)

This caps nothing. It exists so that if you ever do upgrade, or Oracle changes
its model, you find out immediately.

1. Console → **Billing & Cost Management** → **Budgets** → *Create Budget*
2. Target the root compartment. Monthly amount: **US$1**.
3. Alert rule: **at 1% of budget**, emailed to an address you actually read.

A US$1 budget alerting at 1% means the first cent of real spend emails you.

## Step 4 — Verify you are safe

Check all four before considering setup done:

- [ ] **Billing & Cost Management → Payment Method** shows the account as Free
      Tier / trial, with **no active Pay As You Go subscription**.
- [ ] **Cost Analysis** shows US$0.00 actual spend.
- [ ] Every provisioned resource (compute, boot volume, VCN) is Always Free
      eligible. Check **Governance → Limits, Quotas and Usage** for anything
      unexpected.
- [ ] The US$1 budget alert exists and emails a live address.

After that, for as long as you never upgrade, the worst case is a refused
resource request — never money moving.

---

## Sources

- [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/)
- [Always Free resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm)
- [Always Free resources and idle reclamation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [What happens when the promotion expires](https://docs.oracle.com/iaas/Content/GSG/Tasks/signingup_topic-What_Happens_When_the_Promotion_Expires.htm)
- [Free Tier FAQ](https://www.oracle.com/cloud/free/faq/)
