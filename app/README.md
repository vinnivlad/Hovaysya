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

Registration is open and creates a real recipient on whatever server it is
pointed at. `python -m tools.serve.token --list` shows who exists and `--revoke`
removes a test one.

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

    початок тривоги   ··· --- ···       SOS, as Тривога rings it
    балістика         ▪▪▪▪▪▪▪▪▪▪▪▪      a dense stutter: the roof is not enough
    летить сюди       ·· ··             two knocks
    відбій            ▬▬▬▬▬             one long note, no rhythm at all
    тихо              (nothing)

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

## Not here yet

**Push.** Everything above is a screen being looked at; nothing wakes the phone.
That needs FCM, which needs a Google account and a Firebase project -- no Play
Developer account, no payment method -- and a `google-services.json` that must
not be committed. Until then `Bell` can be exercised from Settings, one row
per bell with its rhythm drawn beside it -- which is the only way to check the
alphabet at all: patterns are distinguishable only if somebody has felt every
one of them.

**A moving home.** "Можливо навіть автоматично, при переміщенні містом" needs
location permission and a rule for when a move is real rather than a walk to the
shop. The watcher already picks up a changed `home` within one poll, so the
server side of it is done.
