package ua.hovaysya

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * What the server says, and nothing more.
 *
 * `HttpURLConnection` and `org.json` are in the platform, so this app has no
 * networking or serialisation dependency at all -- the same choice the backend
 * made, for the same reason: it has to still build in a year, on a machine
 * nobody prepared, at a moment when something is wrong.
 *
 * The shapes here are the ones `tools/serve/api.py` actually returns, read off
 * the running service rather than from its docstring.
 */

/** A threat class and the word the announcer uses for it. */
data class Named(val cls: String, val word: String)

/** One line Ховайся said. */
data class Line(val at: String, val level: String?, val text: String)

/**
 * The first screen. `state` is null when the watcher has never written for this
 * recipient, which is what a phone sees in the seconds after it registers -- and
 * is why this is nullable rather than defaulted to [QUIET]. Telling somebody
 * there are no threats when nobody has looked would be the worst available lie.
 */
data class Screen(
    val state: String?,
    val at: Long?,
    val top: Named?,
    val threat: Named?,
    val recon: List<Named>,
    val cleared: List<Named>,
    val peak: Int,
    val said: List<Line>,
    val note: String?,
) {
    val known: Boolean get() = state != null

    companion object {
        const val QUIET = "quiet"
        const val WATCHING = "watching"
        const val ALERT = "alert"
    }
}

/** A name from the gazetteer. [home] is false for the ones with no point. */
data class Place(
    val name: String,
    val tier: String,
    val lat: Double?,
    val lon: Double?,
    val home: Boolean,
    val landmark: Boolean,
)

/**
 * Every name the policy knows, grouped the way it ranks them. The picker takes
 * its order from here rather than inventing one that disagrees with the rules.
 */
data class Gazetteer(val places: List<Place>, val tiers: List<String>) {
    /** The ones somebody can actually live in: a home needs a coordinate. */
    fun homes(): List<Place> =
        places.filter { it.home && it.tier != "elsewhere" }
}

/** One post, as it arrived from a channel. */
data class Post(
    val channel: String,
    val id: Long,
    val ts: Long,
    val text: String,
    val reply: String?,
)

/** One decision, from the watcher's own log. */
data class Verdict(
    val cursor: String,
    val at: String,
    val anchor: String,
    val level: String?,
    val alarm: String?,
    val said: String?,
    val reason: String?,
    val text: String?,
)

/**
 * `pollAgeS` is the one to act on: the watcher rewrites its decision log after
 * every poll whether or not anything arrived. `messageAgeS` is information --
 * over two weeks of seven channels, ten-minute silences happened 307 times.
 */
data class Health(
    val ok: Boolean,
    val corpus: Boolean,
    val pollAgeS: Long?,
    val messageAgeS: Long?,
)

class ApiError(message: String, val code: Int = 0) : IOException(message)

class Api(private val base: String, private val token: String?) {

    suspend fun health(): Health = get("/health") { o ->
        Health(
            ok = o.optBoolean("ok"),
            corpus = o.optBoolean("corpus"),
            pollAgeS = o.longOrNull("poll_age_s"),
            messageAgeS = o.longOrNull("message_age_s"),
        )
    }

    suspend fun screen(): Screen = get("/state") { o ->
        Screen(
            state = o.stringOrNull("state"),
            at = o.longOrNull("at"),
            top = o.namedOrNull("top"),
            threat = o.namedOrNull("threat"),
            recon = o.namedList("recon"),
            cleared = o.namedList("cleared"),
            peak = o.optInt("peak", 0),
            said = o.list("said") { row ->
                Line(
                    at = row.optString("at"),
                    level = row.stringOrNull("level"),
                    text = row.optString("text"),
                )
            },
            note = o.stringOrNull("note"),
        )
    }

    /** The gazetteer, with the tier order the policy ranks names in. */
    suspend fun gazetteer(): Gazetteer = get("/places") { o ->
        val tiers = o.optJSONArray("tiers")
        val places = o.list("places") { row ->
            Place(
                name = row.optString("name"),
                tier = row.optString("tier"),
                lat = row.doubleOrNull("lat"),
                lon = row.doubleOrNull("lon"),
                home = row.optBoolean("home"),
                landmark = row.optBoolean("landmark"),
            )
        }
        Gazetteer(
            places = places,
            tiers = (0 until (tiers?.length() ?: 0)).map { tiers!!.optString(it) },
        )
    }

    /** The last [minutes] of the merged feed, newest first. */
    suspend fun posts(minutes: Int = 30): List<Post> =
        get("/messages?back=${minutes}m") { o ->
            o.list("messages") { row ->
                Post(
                    channel = row.optString("channel"),
                    id = row.optLong("id"),
                    ts = row.optLong("ts"),
                    text = row.optString("text"),
                    reply = row.stringOrNull("reply"),
                )
            }
        }

    suspend fun verdicts(limit: Int = 60): List<Verdict> =
        get("/decisions?limit=$limit") { o ->
            o.list("decisions") { row ->
                Verdict(
                    cursor = row.optString("cursor"),
                    at = row.optString("at"),
                    anchor = row.optString("anchor"),
                    level = row.stringOrNull("level"),
                    alarm = row.stringOrNull("alarm"),
                    said = row.stringOrNull("said"),
                    reason = row.stringOrNull("reason"),
                    text = row.stringOrNull("text"),
                )
            }
        }

    suspend fun config(): Map<String, Any?> = get("/config") { o ->
        val cfg = o.optJSONObject("config") ?: JSONObject()
        cfg.keys().asSequence().associateWith { key ->
            if (cfg.isNull(key)) null else cfg.get(key)
        }
    }

    /** Change settings. Only the keys that differ from the shipped ones are kept. */
    suspend fun saveConfig(changes: Map<String, Any?>): Map<String, Any?> {
        val body = JSONObject()
        changes.forEach { (key, value) -> body.put(key, value ?: JSONObject.NULL) }
        return send("PUT", "/config", body) { o ->
            val cfg = o.optJSONObject("config") ?: JSONObject()
            cfg.keys().asSequence().associateWith { key ->
                if (cfg.isNull(key)) null else cfg.get(key)
            }
        }
    }

    /**
     * Take this device in. Sends only the hash: the secret never leaves the
     * phone, so the server holds nothing that could impersonate it. Returns the
     * stored name, which may carry a suffix if the chosen one was taken.
     */
    suspend fun register(hash: String, name: String): String {
        val body = JSONObject().put("hash", hash).put("name", name)
        return send("POST", "/register", body) { o -> o.optString("name") }
    }

    // --- the plumbing -------------------------------------------------------

    private suspend fun <T> get(path: String, read: (JSONObject) -> T): T =
        send("GET", path, null, read)

    private suspend fun <T> send(
        method: String,
        path: String,
        body: JSONObject?,
        read: (JSONObject) -> T,
    ): T = withContext(Dispatchers.IO) {
        val connection = URL(base.trimEnd('/') + path).openConnection()
                as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 8_000
            connection.readTimeout = 8_000
            connection.setRequestProperty("Accept", "application/json")
            token?.let {
                connection.setRequestProperty("Authorization", "Bearer $it")
            }
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty(
                    "Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) {
                connection.inputStream
            } else {
                connection.errorStream
            }
            val payload = stream?.bufferedReader()?.use { it.readText() } ?: ""
            if (code !in 200..299) {
                // The server explains itself in Ukrainian, and its wording is
                // better than anything this side could invent for a 507 or a 429.
                val said = runCatching { JSONObject(payload).optString("error") }
                    .getOrNull()
                throw ApiError(said?.takeIf { it.isNotBlank() } ?: "HTTP $code", code)
            }
            read(JSONObject(payload))
        } finally {
            connection.disconnect()
        }
    }
}

// --- org.json, made to admit that a field can be absent ---------------------

private fun JSONObject.stringOrNull(key: String): String? =
    if (isNull(key)) null else optString(key).takeIf { it.isNotEmpty() }

private fun JSONObject.longOrNull(key: String): Long? =
    if (isNull(key)) null else optLong(key)

private fun JSONObject.doubleOrNull(key: String): Double? =
    if (isNull(key)) null else optDouble(key).takeIf { !it.isNaN() }

private fun JSONObject.namedOrNull(key: String): Named? {
    val o = optJSONObject(key) ?: return null
    return Named(cls = o.optString("class"), word = o.optString("word"))
}

private fun JSONObject.namedList(key: String): List<Named> =
    list(key) { Named(cls = it.optString("class"), word = it.optString("word")) }

private fun <T> JSONObject.list(key: String, read: (JSONObject) -> T): List<T> {
    val array = optJSONArray(key) ?: return emptyList()
    return (0 until array.length()).mapNotNull { i ->
        array.optJSONObject(i)?.let(read)
    }
}

/**
 * A secret this phone makes for itself, and the hash it sends instead.
 *
 * The same shape the server's own `token.py` mints -- 32 random bytes,
 * url-safe -- because `name_for` hashes the UTF-8 of the token string, so the
 * two have to agree on the exact characters.
 */
object Secret {
    fun make(): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        return Base64.encodeToString(
            bytes, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
    }

    fun hash(secret: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(secret.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }
}
