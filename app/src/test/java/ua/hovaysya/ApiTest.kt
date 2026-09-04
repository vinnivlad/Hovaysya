package ua.hovaysya

import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The contract with the server, exercised over real HTTP.
 *
 * A loopback server from the JDK rather than a mocking library: the parsers are
 * lambdas inside the suspend functions, so the only way to reach them is to let
 * one make a request, and `com.sun.net.httpserver` is already on the class path
 * of any JVM. Robolectric is here for `org.json`, which on a plain JVM is the
 * stub out of `android.jar` and throws on every call.
 *
 * What this is for: the app and the watcher are versioned together but deploy
 * separately -- the server updates itself on a timer, the phone when he installs
 * it -- so a field renamed on one side is a screen that silently says nothing on
 * the other. That has happened once already, when the feed asked for the newest
 * sixty rows and filtered them itself.
 */
@RunWith(RobolectricTestRunner::class)
class ApiTest {

    private lateinit var server: Loopback

    @Before
    fun start() {
        server = Loopback()
    }

    @After
    fun stop() {
        server.close()
    }

    private val seen: List<String> get() = server.asked
    private val auth: String? get() = server.authorization

    /** What the server will answer, whatever is asked of it. */
    private fun serve(path: String, code: Int = 200, payload: String) {
        server.respond(code, payload)
    }

    private fun api(token: String? = "тк") = Api(server.base, token)

    @Test
    fun `health reads the two ages apart`() {
        serve("/health", payload = """
            {"ok": true, "corpus": true, "poll_age_s": 0, "message_age_s": 90}
        """.trimIndent())

        val health = runBlocking { api().health() }

        assertTrue(health.ok)
        assertTrue(health.corpus)
        assertEquals(0L, health.pollAgeS)
        assertEquals(90L, health.messageAgeS)
    }

    @Test
    fun `an age the server did not send is absent rather than zero`() {
        // Zero means "just polled" and is the best possible news. A missing
        // field must not be able to say it.
        serve("/health", payload = """{"ok": false, "corpus": false}""")

        val health = runBlocking { api().health() }

        assertNull(health.pollAgeS)
        assertNull(health.messageAgeS)
    }

    @Test
    fun `the feed asks the server to filter, and reads what it sends back`() {
        serve("/decisions", payload = """
            {"decisions": [
              {"cursor": "1", "at": "2026-09-04T18:41:25+00:00", "anchor": "a",
               "level": "info", "alarm": "none", "said": "Очікується тривога.",
               "reason": "a siren is expected", "text": "можлива тривога"},
              {"cursor": "2", "at": "2026-09-04T18:42:00+00:00", "anchor": "b",
               "level": "alert", "alarm": "drone-jet", "said": "Загроза сюди.",
               "reason": "new target near me"}
            ], "next": "2"}
        """.trimIndent())

        val rows = runBlocking { api().verdicts(limit = 60) }

        // `said=1` belongs in the query and not in the app: one row in seven
        // carries an utterance and silent runs reach seventy-two, so filtering
        // after a limit is not filtering.
        assertTrue(seen.toString(), seen.single().contains("said=1"))
        assertTrue(seen.single().contains("limit=60"))
        assertEquals(2, rows.size)
        assertEquals("Очікується тривога.", rows[0].said)
        assertEquals("a siren is expected", rows[0].reason)
        // Absent, not empty: the second row carries no channel message.
        assertNull(rows[1].text)
    }

    @Test
    fun `the channel feed asks for a window and keeps the order it is given`() {
        serve("/messages", payload = """
            {"messages": [
              {"channel": "nebo_raketa", "id": 10, "ts": 1788547285,
               "text": "перше", "reply": null},
              {"channel": "kievinform_ua1", "id": 11, "ts": 1788547300,
               "text": "друге", "reply": "цитата"}
            ], "next": "1788547300:kievinform_ua1:11"}
        """.trimIndent())

        val posts = runBlocking { api().posts(minutes = 30) }

        assertTrue(seen.single(), seen.single().contains("back=30m"))
        // Oldest first, as the server sends them -- the feed depends on it, and
        // so does the cursor, which is the last row of the answer.
        assertEquals(listOf("перше", "друге"), posts.map { it.text })
        assertNull(posts[0].reply)
        assertEquals("цитата", posts[1].reply)
    }

    @Test
    fun `a state with no state is read as unknown and not as calm`() {
        serve("/state", payload = """{"at": 1788547285, "v": "7"}""")

        val screen = runBlocking { api().screen() }

        assertNull(screen.state)
        assertEquals(false, screen.known)
        assertEquals("7", screen.version)
        assertEquals(0, screen.peak)
        assertEquals(emptyList<Line>(), screen.said)
    }

    @Test
    fun `a full state comes through with its classes and its last lines`() {
        serve("/state", payload = """
            {"state": "alert", "at": 1788547285, "peak": 2,
             "top": {"class": "drone-jet", "word": "реактивний шахед"},
             "threat": {"class": "drone-rocket", "word": "дрон-ракета"},
             "recon": [{"class": "ballistic", "word": "балістика"}],
             "cleared": [{"class": "ballistic", "word": "балістиці"}],
             "said": [{"at": "2026-09-04T18:41:25+00:00", "level": "alert",
                       "alarm": "clear", "text": "Відбій тривоги."}],
             "ended": {"at": 1788547000, "lasted_s": 1800},
             "note": "нотатка", "v": "8"}
        """.trimIndent())

        val screen = runBlocking { api().screen(wait = 25, version = "7") }

        assertTrue(seen.single(), seen.single().contains("wait=25"))
        assertTrue(seen.single().contains("v=7"))
        assertEquals(Screen.ALERT, screen.state)
        assertEquals("дрон-ракета", screen.threat?.word)
        assertEquals("drone-rocket", screen.threat?.cls)
        assertEquals(listOf("балістика"), screen.recon.map { it.word })
        assertEquals(1800L, screen.ended?.lastedS)
        assertTrue(screen.said.single().isClear)
    }

    @Test
    fun `the token travels as a bearer and only when there is one`() {
        serve("/health", payload = """{"ok": true}""")
        runBlocking { api(token = "секрет").health() }
        assertEquals("Bearer секрет", auth)

        // No token, no header -- rather than an empty one, which the server
        // would answer with 401 and the phone would read as "register again".
        runBlocking { api(token = null).health() }
        assertNull(auth)
    }

    @Test
    fun `a proxy's html error page becomes a status code and nothing else`() {
        // Caddy answers with HTML while the upstream is restarting, and there
        // is no JSON in it to read a message out of.
        serve("/health", code = 502,
              payload = "<html><body>502 Bad Gateway</body></html>")

        val thrown = runCatching { runBlocking { api().health() } }
            .exceptionOrNull()

        assertTrue(thrown.toString(), thrown is ApiError)
        assertEquals(502, (thrown as ApiError).code)
        // ...and what a person is shown never contains the number.
        assertEquals("сервіс не відповідає", saidPlainly(thrown))
    }

    @Test
    fun `the server's own explanation survives the trip`() {
        serve("/config", code = 429,
              payload = """{"error": "занадто часто, спробуй за хвилину"}""")

        val thrown = runCatching { runBlocking { api().config() } }
            .exceptionOrNull()

        assertEquals("занадто часто, спробуй за хвилину", thrown?.message)
        assertEquals("занадто часто, спробуй за хвилину", saidPlainly(thrown!!))
    }

    @Test
    fun `a config value that is null stays a key with no value`() {
        // The difference between "not set" and "set to nothing" is what the
        // settings screen edits, so it must survive the parse.
        serve("/config", payload = """
            {"config": {"home": "Жуляни", "radius_km": 6.0, "note": null}}
        """.trimIndent())

        val config = runBlocking { api().config() }

        assertEquals(setOf("home", "radius_km", "note"), config.keys)
        assertEquals("Жуляни", config["home"])
        assertNull(config["note"])
    }

    @Test
    fun `the gazetteer offers only names somebody can live in`() {
        serve("/places", payload = """
            {"tiers": ["my-area", "my-district", "city", "oblast", "elsewhere"],
             "places": [
               {"name": "Жуляни", "tier": "my-area", "lat": 50.4, "lon": 30.45,
                "home": true, "landmark": false},
               {"name": "ТЕЦ-5", "tier": "my-area", "home": true,
                "landmark": true},
               {"name": "Суми", "tier": "elsewhere", "home": true,
                "landmark": false},
               {"name": "Кільцева", "tier": "city", "home": false,
                "landmark": false}
             ]}
        """.trimIndent())

        val places = runBlocking { api().gazetteer() }

        assertEquals(5, places.tiers.size)
        assertEquals("my-area", places.tiers.first())
        // No coordinate, no home; and nowhere anybody would call home either.
        assertEquals(listOf("Жуляни", "ТЕЦ-5"), places.homes().map { it.name })
        assertNull(places.places.first { it.name == "ТЕЦ-5" }.lat)
    }
}
