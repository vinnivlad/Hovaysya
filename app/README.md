# Ховайся, the phone half

Four screens over the API in `tools/serve/api.py`. Kotlin and Jetpack Compose,
one module, and no dependency that is not AndroidX.

## Why native, and not React Native or a web page

The screens are the easy part. The product is **a bell at three in the morning
that "не турбувати" does not swallow**, and that is native API surface:

    NotificationChannel   IMPORTANCE_HIGH · setVibrationPattern · setBypassDnd
    VibrationEffect       patterns that differ through a mattress
    FCM high priority     waking the process out of Doze

React Native reaches all of it through native modules -- meaning the Kotlin gets
written anyway, with a JavaScript layer over it. A web page cannot reach it at
all: the `vibrate` option on a web notification is ignored on Android and there
is no bypass for night mode. So the thing that makes this app worth having is
the thing only the native path can do.

## Opening it

The Android SDK and an emulator come with the IDE; nothing else is needed.

1. Open **the repository root** as the project. The Gradle build lives there --
   `settings.gradle.kts` includes `:app` -- so opening `app/` on its own finds
   nothing to build. `deploy/lean.sh` still keeps this whole directory off the
   servers.
2. **JDK 17 or 21, not 25.** Gradle 8.9 runs on 17 through 22 and IntelliJ picks
   its own default, which here was `openjdk-25` -- so the sync fails on the JVM
   before it reaches any of this. Both usable versions are already in `~/.jdks`;
   set it under Settings → Build Tools → Gradle → Gradle JVM.
3. There is no `gradle-wrapper.jar`. It is a binary and this repository has
   never carried one; the distribution is pinned in
   `gradle/wrapper/gradle-wrapper.properties` and the IDE fetches it on first
   sync. For a working `./gradlew` on the command line, one `gradle wrapper`
   from any Gradle writes the jar.
4. `local.properties` with `sdk.dir=...` is written by the IDE and is
   gitignored, because that path differs on every machine.

## Pointing it somewhere

The default is `https://hovaysya.duckdns.org`. On first launch there is an
**Інший сервер** field, and the same field is in Settings afterwards.

From the emulator, the machine it runs on is `10.0.2.2`, so a local API is
`http://10.0.2.2:8080`. Android 9 and up refuse plain HTTP by default, so there
is a network-security config permitting cleartext to that one address -- and it
lives under `src/debug/`, which means a release build cannot carry it even by
accident: the file is not in that variant's sources at all.

**Test against the real server, under a test user.** His workflow, and the right
way round: real data, real state, real timing, so the emulator sees exactly what
a phone will. Register from the emulator under a name like `тест` and the watcher
takes it on within one poll -- warmed from the corpus, so its first screen is
true even if a raid is already running.

Nothing needs preparing for that. Registration is open, the test user gets no
Telegram (only `telegram_channel` does), and **Забути цей пристрій** removes the
registration from the server as well as the phone -- which is what keeps a
reinstall from leaving a recipient behind every time.

`python -m tools.serve.token --list` still shows who exists and `--revoke`
removes one from the server side, for the cases where the phone is gone.

A local API is the other option -- `python -m tools.serve.api`, reached from the
emulator at `http://10.0.2.2:8080` -- but it answers less than it looks like it
does: `/state` and `/decisions` come from files the watcher writes, so without a
watcher running locally the first screen reads "НЕ ЗНАЮ" and both feeds are
empty. `/places`, `/config` and registration work fully.

## What is here

    Api.kt        the four endpoints. `HttpURLConnection` and `org.json`, both
                  in the platform, so there is no HTTP or JSON dependency at all
    Store.kt      the secret this phone made for itself, and where the server is
    Bell.kt       the five channels and the vibration alphabet
    ui/Now.kt     screen one: the worst thing in the air, what is only scouted
    ui/Feed.kt    screens two and three: what Ховайся said, and every channel
    ui/Setup.kt   the first run -- a name, a district, a radius
    ui/Settings.kt and the one thing that is not a preference, below

## One theme, dark

His call, and the right one for this app rather than a preference: "зроби його в
темних тонах, наче він в dark-mode. Це буде одна і єдина тема в ньому."

The screen that matters is opened in a dark room, at arm's length, in the first
seconds after being woken. A light theme there is not a different taste -- it is
a flash of white in the face of somebody who has just been told a missile is
coming, and it costs them the seconds their eyes need to read the one word on
the screen.

So there is no `values-night`, and the dark values live in plain `values/`: a
phone set to light mode has to get this theme too. The ground colour is written
twice on purpose -- once in `ui/Theme.kt` and once in `res/values/colors.xml`,
because the window manager paints it before any Kotlin runs, and getting that
one wrong means launching flashes the wrong colour on the way to the right one.

Being the only theme is also why the palette can be tuned rather than
compromised. The ground is not pure black -- on OLED that makes type edges bloom
-- the text is a warm off-white so a 46sp headline does not glare, and saturation
is spent in exactly one place: the state.

## The alphabet

    початок тривоги   ··· ▬▬▬ ···       SOS, as Тривога rings it
    балістика         ············      a dense stutter: the roof is not enough
    летить сюди       ·· ··             knock-knock, knock-knock
    відбій            ▬                 one long note, no rhythm at all
    тихо              (nothing)

One glyph per pulse, `·` short and `▬` long, and that convention exists so a
test can compare what Settings draws against what the arrays do. It could not,
and the cost was `NEAR`: drawn as two pairs since the day it was written, buzzing
as one. He caught it by feel.

The start is his: "3 коротких, 3 довгих, 3 коротких, так само як і в застосунку
Тривога". The point is not the code -- it is that everyone here already knows
that rhythm without being taught, so it is the one pattern this app must not
invent for itself.

The end being different is his too, and it exposed a real defect. The server
marks an all-clear as `level="alert"` with `alarm="clear"`, because announcing it
*is* an audible event -- so a mapping keyed on the level rang the raid pattern
for the end of the raid. 72 of those in the live log. Being woken by what feels
exactly like an alert, to be told the alert is over, is the worst thing in this
list. `channelFor` now tests the all-clear before the level, and that order is
the whole correction.

Four things to tell apart half asleep, so each differs in *rhythm* rather than
in length: nine structured pulses, twelve rapid ones, two quick ones, one note.
The all-clear is a single pulse on purpose -- nothing else in the set is, so it
cannot read as a warning at the moment of waking.

Two calls in there that are worth disagreeing with if they are wrong. A raid that
opens with ballistic rings the shelter pattern rather than SOS, because at that
point the more urgent thing to say is not "a raid started". And the all-clear
does **not** bypass night mode: somebody who slept through a raid does not need
waking to hear it ended, and somebody awake and waiting gets it anyway. Both are
one line to change.

Every channel the server can ring with `level="alert"` bypasses night mode and
none of the others do, and that division is not this app's to make twice: the
server has already decided whether this person should be woken, and all that is
left here is what it feels like.

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

## Debug or release

Debug is the fast path and needs nothing: the IDE signs it with the throwaway
keystore in `~/.android`, and `adb install` is the whole ceremony. Two things
differ, and only one of them is cosmetic.

    підпис        debug: ~/.android/debug.keystore, password "android"
                  release: your own, or the APK is unsigned and will not install
    відкритий HTTP debug: permitted to 10.0.2.2 only, from `src/debug/`
                  release: refused -- that file is not in the variant
    debuggable    debug: yes, so anything with adb reads app-private storage
                  release: no
    ui-tooling    debug only

**The signing key is app identity**, which makes it the one to decide early.
Debug and release are signed differently, so one cannot replace the other:
installing a release over a debug build requires an uninstall, and uninstalling
wipes the secret this phone registered with. Home and radius get chosen again,
and a stale recipient is left on the server. Deciding that on the day you start
relying on the app is deciding it at the worst moment.

So make the keystore before that day:

    keytool -genkeypair -v -keystore data/hovaysya.keystore         -alias hovaysya -keyalg RSA -keysize 4096 -validity 10000

Then copy `keystore.properties.example` to `keystore.properties` and fill in the
two passwords. Both files stay out of git -- the repository is public -- and the
keystore lives under `data/` with every other secret here, which also means
`python -m tools.backup` copies it. **Losing it loses the ability to update the
app on any phone that has it.** Back it up somewhere that is not this machine.

Without `keystore.properties` the build still configures and debug still works;
only `assembleRelease` produces an unsigned APK, and Gradle says so on every
build rather than leaving it to be discovered at install time.

`versionCode` counts itself, from the year and the number of commits in it --
his scheme, and his reason for wanting one: "я сам буду забувати".

    versionCode  20260222      year * 10000 + commits this year
    versionName  2026.222

Monotonic across a year boundary, which a bare commit count is not: 2026 with its
five-thousandth commit is 20265000 and the first of 2027 is 20270001. Counted
rather than typed, because a number somebody has to remember to raise is one that
stays wrong -- and Android refuses to install an older code over a newer one, so
a forgotten bump means a phone silently keeping the build it has, which is the
same outcome as not shipping.

Settings shows `versionName`, which is the other half of having a version: a
number nobody can read from the device answers no question. It is the commit,
so `git log` finds exactly what a phone is running.

Without git the number would be lower than the last real one, so such a build
simply will not install over anything, and Gradle says so. That is deliberate --
a loud failure rather than a build quietly claiming to be older than it is.

## Not here yet

**Nothing, on the push side.** There is no Firebase here and there is not going
to be. He asked whether it was really compulsory, and it is not: it is compulsory
only to use *Google's* channel. `AlertService` keeps one request open against
`/state?wait=30` and rings the moment the answer changes -- no account, no
`google-services.json`, no service key on the server, and nothing between that
machine and this phone on the one night it matters.

Android's price is a notification that cannot be dismissed, and that turned out
to be the thing he already wanted: a status line saying what is happening rather
than a feed of what happened. The cost is the feature.

Two constraints in there worth knowing. The service type is `specialUse` and not
`dataSync`, because since Android 15 a `dataSync` service is capped at six hours
in any twenty-four and a thing that watches for air raids cannot be off for
eighteen of them; Play asks for a justification for `specialUse`, and not being
in Play is the one place where having no store makes something simpler. And the
stamp of the last line rung for is persisted, because the state file still holds
a finished raid's lines -- a service restarting after a reboot would otherwise
ring for an alert that ended two hours ago.

`Bell` can still be exercised from Settings, one row per bell with its rhythm
beside it, which is the only way to check the alphabet at all: patterns are
distinguishable only if somebody has felt every one of them.

**A moving home.** "Можливо навіть автоматично, при переміщенні містом" needs
location permission and a rule for when a move is real rather than a walk to the
shop. The watcher already picks up a changed `home` within one poll, so the
server side of it is done.
