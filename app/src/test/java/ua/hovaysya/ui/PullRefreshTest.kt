package ua.hovaysya.ui

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeUp
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
 * Pulling the feed up past its newest line asks the server now.
 *
 * His ask: "примусового оновлення чату змахуванням по чату вгору, щоб воно
 * примусово питало сервер про нові повідомлення. Для чату ховайся і фіду". Up,
 * not down, because the newest line is at the bottom -- the pull continues the
 * direction he was already reading in.
 *
 * `every` is enormous for the same reason as in `DoorbellTest`: nothing but the
 * gesture can cause a second request.
 */
@RunWith(RobolectricTestRunner::class)
@Config(qualifiers = "w400dp-h800dp")
class PullRefreshTest {

    @get:Rule
    val rule = createComposeRule()

    private lateinit var server: Loopback

    private val never = 24L * 60 * 60 * 1000
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

    private val decisions = """
        {"decisions": [
          {"cursor": "1", "at": "2026-09-20T18:15:29+00:00", "anchor": "a",
           "level": "alert", "alarm": "ballistic", "said": "Загроза: балістика.",
           "reason": "threat level rose", "text": "текст"}
        ], "next": "1"}
    """.trimIndent()

    @Test
    fun `pulling the said feed up asks again`() {
        server.respond(payload = decisions)
        rule.setContent {
            HovaysyaTheme { HovaysyaFeed(store(), onSettings = {}, every = never) }
        }
        rule.waitUntil(WAIT_MS) { server.asked.isNotEmpty() && Held.said.isNotEmpty() }
        val first = server.asked.size

        rule.onRoot().performTouchInput { swipeUp() }

        rule.waitUntil(WAIT_MS) { server.asked.size > first }
    }

    @Test
    fun `pulling the channel feed up asks again`() {
        server.respond(payload = """{"messages": [
            {"channel": "kievinform_ua1", "id": 1, "ts": 1790000000, "text": "Чисто."}
        ]}""")
        rule.setContent {
            HovaysyaTheme { ChannelFeed(store(), onSettings = {}, every = never) }
        }
        rule.waitUntil(WAIT_MS) { server.asked.isNotEmpty() && Held.posts.isNotEmpty() }
        val first = server.asked.size

        rule.onRoot().performTouchInput { swipeUp() }

        rule.waitUntil(WAIT_MS) { server.asked.size > first }
    }

    @Test
    fun `a nudge short of the threshold does not`() {
        server.respond(payload = decisions)
        rule.setContent {
            HovaysyaTheme { HovaysyaFeed(store(), onSettings = {}, every = never) }
        }
        rule.waitUntil(WAIT_MS) { server.asked.isNotEmpty() && Held.said.isNotEmpty() }

        rule.onRoot().performTouchInput {
            swipeUp(startY = centerY + 10f, endY = centerY - 10f)
        }
        rule.waitForIdle()

        assert(server.asked.size == 1) { "asked ${server.asked.size} times" }
    }
}
