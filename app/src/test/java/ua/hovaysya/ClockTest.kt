package ua.hovaysya

import java.time.LocalTime
import java.util.TimeZone
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * Kyiv time, whatever the machine underneath thinks.
 *
 * This is the one file where the phone's own zone is a hazard rather than a
 * preference, and it has already cost a scare: on an emulator out of the box the
 * feed read 06:28 while Kyiv said 09:28, which looks exactly like a watcher that
 * died three hours ago. So every test here first sets the default zone to
 * somewhere else on purpose, and none of them may notice.
 */
class ClockTest {

    @Before
    fun elsewhere() {
        // Los Angeles rather than UTC: an offset that is both negative and on
        // the other side of the date line from Kyiv, so a formatter reading the
        // default zone cannot accidentally agree.
        TimeZone.setDefault(TimeZone.getTimeZone("America/Los_Angeles"))
    }

    @Test
    fun `an iso stamp from the log is read as Kyiv time`() {
        // The watcher writes UTC. Kyiv is three hours ahead in September.
        assertEquals("21:41", clock("2026-09-04T18:41:25+00:00"))
        assertEquals("21:41", clock("2026-09-04T18:41:25Z"))
    }

    @Test
    fun `an offset already in the stamp is honoured, not assumed`() {
        // Same instant, written from Kyiv rather than from UTC.
        assertEquals("21:41", clock("2026-09-04T21:41:25+03:00"))
    }

    @Test
    fun `something that is not a stamp comes back unchanged`() {
        // Better a visibly odd string on screen than a crash or a plausible
        // wrong time.
        assertEquals("не час", clock("не час"))
        assertEquals("", clock(""))
    }

    @Test
    fun `epoch seconds are read as Kyiv time too`() {
        // 2026-09-04T18:41:25Z
        assertEquals("21:41", clock(1788547285L))
    }

    @Test
    fun `winter keeps its own offset`() {
        // Ukraine keeps summer time, so the offset is not a constant. In
        // January it is +02:00, and a hard-coded three would be an hour out.
        assertEquals("20:41", clock("2026-01-04T18:41:25Z"))
    }

    @Test
    fun `a duration is spelled the way a person would say it`() {
        assertEquals("1 год 20 хв", spell(4800))
        assertEquals("2 год", spell(7200))
        assertEquals("45 хв", spell(2700))
        assertEquals("40 с", spell(40))
        assertEquals("0 с", spell(0))
    }

    @Test
    fun `the quiet window is a union because it crosses midnight`() {
        // The obvious `from <= now && now < until` is false at every hour the
        // window is actually open, which is why the function is written out.
        assertTrue(inQuietHours(LocalTime.of(22, 0)))
        assertTrue(inQuietHours(LocalTime.of(23, 59)))
        assertTrue(inQuietHours(LocalTime.of(0, 0)))
        assertTrue(inQuietHours(LocalTime.of(7, 59)))
        assertFalse(inQuietHours(LocalTime.of(8, 0)))
        assertFalse(inQuietHours(LocalTime.of(12, 0)))
        assertFalse(inQuietHours(LocalTime.of(21, 59)))
    }

    @Test
    fun `the zone resolves to Kyiv and not to a fixed offset`() {
        // The fixed +03:00 is the last resort for a device whose tzdata
        // predates "Europe/Kyiv", and it is knowingly wrong for half the year.
        // On any machine that can run these tests it must not be what we got.
        assertTrue(KYIV.id, KYIV.id.startsWith("Europe/"))
    }
}
