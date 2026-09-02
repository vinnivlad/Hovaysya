# Ховайся, the phone half

Four screens over the API in `tools/serve/api.py`. Kotlin and Jetpack Compose,
one module, and no dependency that is not AndroidX.

## Why native, and not React Native or a web page

The screens are the easy part. The product is **a bell at three in the morning
that "не турбувати" does not swallow**, and that is native API surface:

    NotificationChannel   IMPORTANCE_HIGH · setVibrationPattern · setBypassDnd
    VibrationEffect       three patterns that differ through a mattress
    FCM high priority     waking the process out of Doze

React Native reaches all of it through native modules -- meaning the Kotlin gets
written anyway, with a JavaScript layer over it. A web page cannot reach it at
all: the `vibrate` option on a web notification is ignored on Android and there
is no bypass for night mode. So the thing that makes this app worth having is
the thing only the native path can do.

## Opening it

The Android SDK and an emulator come with the IDE; nothing else is needed.

1. Open **this directory** (`app/`) as a project -- not the repository root.
   The Gradle build lives here, and `deploy/lean.sh` keeps this whole directory
   off the servers.
2. There is no `gradle-wrapper.jar`. It is a binary and this repository has
   never carried one; the distribution is pinned in
   `gradle/wrapper/gradle-wrapper.properties` and the IDE fetches it on first
   sync. For a working `./gradlew` on the command line, one `gradle wrapper`
   from any Gradle writes the jar.
3. JDK 17 or 21. Both are already in `~/.jdks`; the IDE also ships one.
4. `local.properties` with `sdk.dir=...` is written by the IDE and is
   gitignored, because that path differs on every machine.

## Pointing it somewhere

The default is `https://hovaysya.duckdns.org`. On first launch there is an
**Інший сервер** field, and the same field is in Settings afterwards.

From the emulator, the machine it runs on is `10.0.2.2`, so a local API is
`http://10.0.2.2:8080`. Cleartext to a plain-HTTP address is blocked by default
on Android 9 and up, so a local run needs either an `https` front or a debug
network-security config -- which is deliberately not committed, because a
release build must never carry one.

Registration is open and creates a real recipient on whatever server it is
pointed at. `python -m tools.serve.token --list` shows who exists and `--revoke`
removes a test one.

## What is here

    Api.kt        the four endpoints. `HttpURLConnection` and `org.json`, both
                  in the platform, so there is no HTTP or JSON dependency at all
    Store.kt      the secret this phone made for itself, and where the server is
    Bell.kt       the three channels and the vibration alphabet
    ui/Now.kt     screen one: the worst thing in the air, what is only scouted
    ui/Feed.kt    screens two and three: what Ховайся said, and every channel
    ui/Setup.kt   the first run -- a name, a district, a radius
    ui/Settings.kt and the one thing that is not a preference, below

## The trap worth knowing about

A notification channel is **immutable once created**. Importance, vibration
pattern and `setBypassDnd` are read at creation and every later
`createNotificationChannel` with the same id is ignored -- by design, because
those settings belong to the person.

Which means the obvious sequence is wrong. The app has to create channels on
launch to be able to notify at all, but `setBypassDnd(true)` is refused unless
"Доступ до режиму «Не турбувати»" is already granted -- and that grant has no
runtime prompt, so on a first launch it never is. The shelter channel is then
permanently one that cannot bypass night mode: no error, no warning, and the
failure surfaces at three in the morning on the one night it counts.

So the channel ids carry a generation number kept in `Store`, granting the
access offers a rebuild, and `Bell.canWake` reports what the channel *actually*
got by reading it back from the system rather than assuming we were obeyed.
Settings says so in as many words, because it is the only thing on any screen
that the person has to go and do themselves.

## Not here yet

**Push.** Everything above is a screen being looked at; nothing wakes the phone.
That needs FCM, which needs a Google account and a Firebase project -- no Play
Developer account, no payment method -- and a `google-services.json` that must
not be committed. Until then `Bell` can be exercised from Settings, which is the
only way to check the alphabet at all: three patterns are distinguishable only
if somebody has felt all three.

**A moving home.** "Можливо навіть автоматично, при переміщенні містом" needs
location permission and a rule for when a move is real rather than a walk to the
shop. The watcher already picks up a changed `home` within one poll, so the
server side of it is done.
