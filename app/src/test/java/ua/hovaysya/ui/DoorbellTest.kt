package ua.hovaysya.ui

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import ua.hovaysya.Held
import ua.hovaysya.Loopback
import ua.hovaysya.Store

/**
 * The feed asks again when the doorbell rings, instead of waiting out its timer.
 *
 * His report of 2026-09-21: "в мене враження що сервер оновлюється швидше ніж в
 * додатку", and he had taken to flicking between tabs to force a refresh. He was
 * right, and it was structural. `AlertService` holds one long poll open against
 * `/state?wait=30` and learns of a new decision within a second -- that is what
 * rings the bell and draws the shade -- while the feeds sat on private timers of
 * fifteen and twenty seconds and never heard about it.
 *
 * So the service now says "something changed" and the feeds listen. The timer
 * stays as the floor: if the service is dead or the long poll is failing, a feed
 * must not go quiet, and nothing here may be slower than the version it replaces.
 *
 * `every` is enormous in these tests on purpose. It leaves exactly one thing that
 * can cause a second request, so a pass cannot be the timer firing early under a
 * clock the test does not own.
 */
@RunWith(RobolectricTestRunner::class)
@Config(qualifiers = "w400dp-h800dp")
class DoorbellTest {

    @get:Rule
    val rule = createComposeRule()

    private lateinit var server: Loopback

    private val never = 24L * 60 * 60 * 1000

    // Real milliseconds, not the virtual clock: a request over a loopback
    // socket under Robolectric takes longer than the one second `waitUntil`
    // allows by default, and that timeout is what failed here first.
    private val WAIT_MS = 15_000L

    @Before
    fun start() {
        server = Loopback()
        Held.clear()
    }

    @After
    fun stop() {
        server.close()
        Held.clear()
    }

    private fun store(): Store {
        val store = Store(ApplicationProvider.getApplicationContext())
        store.base = server.base
        store.secret = "token"
        return store
    }

    private fun decisions(said: String) = """
        {"decisions": [
          {"cursor": "1", "at": "2026-09-20T18:15:29+00:00", "anchor": "a",
           "level": "alert", "alarm": "ballistic", "said": "$said",
           "reason": "threat level rose", "text": "текст"}
        ], "next": "1"}
    """.trimIndent()

    @Test
    fun `a ring makes the said feed ask again`() {
        server.respond(payload = decisions("Загроза: балістика."))
        rule.setContent {
            HovaysyaTheme { HovaysyaFeed(store(), onSettings = {}, every = never) }
        }
        rule.waitUntil(WAIT_MS) { server.asked.isNotEmpty() }
        val first = server.asked.size

        rule.runOnIdle { Held.ring() }

        rule.waitUntil(WAIT_MS) { server.asked.size > first }
    }

    @Test
    fun `a ring makes the channel feed ask again`() {
        server.respond(payload = """{"messages": []}""")
        rule.setContent {
            HovaysyaTheme { ChannelFeed(store(), onSettings = {}, every = never) }
        }
        rule.waitUntil(WAIT_MS) { server.asked.isNotEmpty() }
        val first = server.asked.size

        rule.runOnIdle { Held.ring() }

        rule.waitUntil(WAIT_MS) { server.asked.size > first }
    }

    @Test
    fun `nobody ringing leaves the feed asking exactly once`() {
        """The floor, stated as a test: without a ring the feed waits out its
        interval and does not spin. A doorbell that also fired on every
        recomposition would look like a working feed and cost a request a
        frame."""
        server.respond(payload = decisions("Тривога."))
        rule.setContent {
            HovaysyaTheme { HovaysyaFeed(store(), onSettings = {}, every = never) }
        }
        rule.waitUntil(WAIT_MS) { server.asked.isNotEmpty() }
        rule.waitForIdle()

        assert(server.asked.size == 1) { "asked ${server.asked.size} times: ${server.asked}" }
    }
}
