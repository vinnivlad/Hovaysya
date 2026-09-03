package ua.hovaysya

import android.content.Context

/**
 * The three things this phone remembers: where the service is, the secret it
 * made for itself, and the name that secret is filed under.
 *
 * Plain `SharedPreferences`, in app-private storage. Deliberately not encrypted,
 * and the reasoning is worth writing down rather than defaulting either way: the
 * token opens a feed that restates public Telegram channels, plus one home
 * district that the person chose on this screen. `EncryptedSharedPreferences`
 * would add a dependency and a keystore failure mode to protect a value that is
 * already unreadable to every other app on an unrooted device.
 *
 * There is no recovery. Reinstall and the secret is gone, so the phone registers
 * again and picks a district again -- thirty seconds. The alternative is
 * collecting a mail address or a phone number, which would mean holding more
 * about somebody than this whole system otherwise knows.
 */
class Store(context: Context) {

    private val prefs = context.getSharedPreferences("hovaysya", Context.MODE_PRIVATE)

    var base: String
        get() = prefs.getString(KEY_BASE, DEFAULT_BASE) ?: DEFAULT_BASE
        set(value) = prefs.edit().putString(KEY_BASE, value.trim().trimEnd('/')).apply()

    /** Null until this device has registered. */
    var secret: String?
        get() = prefs.getString(KEY_SECRET, null)
        set(value) = prefs.edit().putString(KEY_SECRET, value).apply()

    /** The name the server filed the secret under -- it may carry a suffix. */
    var name: String?
        get() = prefs.getString(KEY_NAME, null)
        set(value) = prefs.edit().putString(KEY_NAME, value).apply()

    val registered: Boolean get() = !secret.isNullOrEmpty()

    /**
     * The stamp of the newest line this phone has already rung for.
     *
     * Persisted, and that is the point: the state file still holds the lines of
     * a finished raid, so a service restarting after a reboot would ring for an
     * alert that ended two hours ago. Waking somebody at three for something
     * that is over is how an app stops being believed.
     */
    var lastSaid: String?
        get() = prefs.getString(KEY_LAST_SAID, null)
        set(value) = prefs.edit().putString(KEY_LAST_SAID, value).apply()

    /**
     * Which set of notification channels this phone is on. A channel cannot be
     * changed once created, so the only way to give the shelter bell the right
     * to bypass night mode -- after the person grants it -- is a new id. See
     * [Bell] for why that grant can never be in place on a first launch.
     */
    var channelGeneration: Int
        get() = prefs.getInt(KEY_CHANNELS, 1)
        set(value) = prefs.edit().putInt(KEY_CHANNELS, value).apply()

    /**
     * How loud the alarm is, 0 to 1. Silent is a legitimate choice: the
     * vibration alphabet works on its own, and somebody who wants only that
     * should not have to leave the phone on mute to get it.
     */
    var volume: Float
        get() = prefs.getFloat(KEY_VOLUME, 0.8f)
        set(value) = prefs.edit().putFloat(KEY_VOLUME, value.coerceIn(0f, 1f))
            .apply()

    /**
     * Withhold sound between 22:00 and 08:00 Kyiv time. **Off by default**, and
     * that default is the safe one: a window that silences an air-raid alarm is
     * a thing somebody has to choose, never a thing they discover.
     *
     * Vibration is not affected -- "коли звук не видається" is about sound, and
     * the shelter channel still bypasses night mode. So the quiet window makes
     * the phone buzz instead of wail; it does not make it ignore a raid.
     */
    var quietHours: Boolean
        get() = prefs.getBoolean(KEY_QUIET_HOURS, false)
        set(value) = prefs.edit().putBoolean(KEY_QUIET_HOURS, value).apply()

    /** The volume to use right now, which the quiet window can zero. */
    fun volumeNow(): Float =
        if (quietHours && inQuietHours()) 0f else volume

    fun api(): Api = Api(base, secret)

    /** Forget this device's registration, without touching the server. */
    fun forget() {
        prefs.edit().remove(KEY_SECRET).remove(KEY_NAME)
            // The ring memory goes too. Kept, the next registration on this
            // phone would inherit a stamp from somebody else's night and stay
            // silent until the clock caught up with it.
            .remove(KEY_LAST_SAID).apply()
    }

    companion object {
        // The emulator reaches the machine it runs on at 10.0.2.2, so a local
        // `python -m tools.serve.api` is http://10.0.2.2:8080 -- which is why
        // this is a setting rather than a constant.
        const val DEFAULT_BASE = "https://hovaysya.duckdns.org"

        private const val KEY_BASE = "base"
        private const val KEY_SECRET = "secret"
        private const val KEY_NAME = "name"
        private const val KEY_CHANNELS = "channels"
        private const val KEY_LAST_SAID = "lastSaid"
        private const val KEY_VOLUME = "volume"
        private const val KEY_QUIET_HOURS = "quietHours"
    }
}
