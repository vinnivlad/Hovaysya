package ua.hovaysya

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * What the phone remembers about itself, and what forgetting has to reach.
 *
 * The defaults here are decisions rather than conveniences -- one of them is a
 * window that can silence an air-raid alarm -- so they are worth a test that
 * says so out loud.
 */
@RunWith(RobolectricTestRunner::class)
class StoreTest {

    private lateinit var store: Store

    @Before
    fun fresh() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        context.getSharedPreferences("hovaysya", Context.MODE_PRIVATE)
            .edit().clear().commit()
        store = Store(context)
    }

    @Test
    fun `a fresh phone is not registered and knows where the service is`() {
        assertFalse(store.registered)
        assertNull(store.secret)
        assertNull(store.name)
        assertEquals(Store.DEFAULT_BASE, store.base)
    }

    @Test
    fun `the quiet window is off until somebody chooses it`() {
        // "a window that silences an air-raid alarm is a thing somebody has to
        // choose, never a thing they discover."
        assertFalse(store.quietHours)
        assertEquals(0.8f, store.volume, 0.001f)
        assertEquals(store.volume, store.volumeNow(), 0.001f)
    }

    @Test
    fun `the quiet window is consulted before the volume is used`() {
        store.quietHours = true
        // Whether the window is open right now depends on the clock, and the
        // point is only that the setting is read at all -- a `volumeNow` that
        // ignored it would fail this at some hour of the day and pass at
        // others, which is worse than failing.
        val expected = if (inQuietHours()) 0f else store.volume
        assertEquals(expected, store.volumeNow(), 0.001f)
    }

    @Test
    fun `the volume cannot be set outside its range`() {
        store.volume = 4f
        assertEquals(1f, store.volume, 0.001f)
        store.volume = -1f
        assertEquals(0f, store.volume, 0.001f)
    }

    @Test
    fun `a pasted address loses its trailing slash and its spaces`() {
        // Every path in `Api` starts with one, so a stored slash makes
        // "//state" -- and a copied address is where the spaces come from.
        store.base = "  http://10.0.2.2:8080/  "
        assertEquals("http://10.0.2.2:8080", store.base)
    }

    @Test
    fun `an empty secret is not a registration`() {
        store.secret = ""
        assertFalse(store.registered)
        store.secret = "тк"
        assertTrue(store.registered)
    }

    @Test
    fun `the channel generation starts at one so the ids can move`() {
        assertEquals(1, store.channelGeneration)
        store.channelGeneration = 2
        assertEquals(2, store.channelGeneration)
    }

    @Test
    fun `forgetting the device leaves nothing of the person behind`() {
        store.secret = "тк"
        store.name = "Володимир"
        store.lastSaid = "2026-09-04T18:41:25+00:00"
        Held.problem = "немає мережі"

        store.forget()

        assertNull(store.secret)
        assertNull(store.name)
        // The ring memory goes too: kept, the next registration on this phone
        // would inherit a stamp from somebody else's night and stay silent
        // until the clock caught up with it.
        assertNull(store.lastSaid)
        // And whatever was on the screens, decided from a home that is not
        // theirs.
        assertNull(Held.problem)
    }

    @Test
    fun `forgetting the device keeps the address it was talking to`() {
        // Deliberate: the server does not change when the person does, and
        // somebody testing against a local API would otherwise have to type it
        // again every time they re-registered.
        store.base = "http://10.0.2.2:8080"
        store.secret = "тк"

        store.forget()

        assertEquals("http://10.0.2.2:8080", store.base)
    }

    @Test
    fun `the volume and the quiet window survive forgetting`() {
        // They belong to the phone rather than to the registration -- how loud
        // this handset is allowed to be is not a fact about who is holding it.
        store.volume = 0.3f
        store.quietHours = true

        store.forget()

        assertEquals(0.3f, store.volume, 0.001f)
        assertTrue(store.quietHours)
    }
}
