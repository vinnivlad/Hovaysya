package ua.hovaysya

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * The all-clear's waveform, which nothing else can check.
 *
 * A sound is judged by ear and these are the two things an ear will not catch
 * until it is too late: silent clipping, and a level that has quietly drifted
 * back down. Both were real -- he reported the all-clear as quiet against the
 * other sounds, and it was 5.8 dB under the wail.
 *
 * Robolectric only because `Siren` holds a `Handler` on the main looper, which
 * a plain JVM test has no answer for. Nothing here touches audio.
 */
@RunWith(RobolectricTestRunner::class)
class SirenTest {

    private val samples = Siren.dings()

    @Test
    fun `the three dings never clip`() {
        // The soft limiter exists so the sum can be loud without wrapping
        // round, and a sample at the rail means it stopped doing its job.
        val loudest = samples.maxOf { abs(it.toInt()) }
        assertTrue("peaked at $loudest", loudest <= Short.MAX_VALUE.toInt())
        assertTrue("suspiciously quiet: $loudest", loudest > Short.MAX_VALUE * 0.9)
    }

    @Test
    fun `it is louder than dividing by the sum's own peak would leave it`() {
        // What the code did before: scale the whole phrase down until its
        // loudest instant fit. That cost 4.0 dB, and this is the guard against
        // it coming back -- an rms this far up cannot be reached that way.
        val rms = sqrt(samples.sumOf { it.toDouble() * it.toDouble() } / samples.size)
        val ratio = rms / Short.MAX_VALUE
        assertTrue("rms is only ${"%.3f".format(ratio)} of full scale", ratio > 0.45)
    }

    // --- the wail ----------------------------------------------------------

    private val wail = Siren.wail()

    /** Loudness of one slice, as a fraction of full scale. */
    private fun rms(from: Double, to: Double): Double {
        val a = (from * 22_050).toInt()
        val b = (to * 22_050).toInt().coerceAtMost(wail.size)
        var acc = 0.0
        for (i in a until b) acc += wail[i].toDouble() * wail[i]
        return sqrt(acc / (b - a)) / Short.MAX_VALUE
    }

    /** Sign changes per second over two: a pitch, without an FFT. */
    private fun pitch(samples: ShortArray): Double {
        var crossings = 0
        for (i in 1 until samples.size) {
            if ((samples[i - 1] < 0) != (samples[i] < 0)) crossings++
        }
        return crossings * 22_050.0 / samples.size / 2
    }

    @Test
    fun `the wail runs for thirty seconds`() {
        // His: "збільш довжину всієї сирени до 20с" and then "підніми довжину
        // сирена до 30с також". Ten seconds was already long on purpose -- long
        // enough to be crossed a room for -- and the rise now eats the first
        // five of them, so the part that is actually at full volume has to be
        // paid for somewhere.
        assertEquals(30.0, wail.size / 22_050.0, 0.05)
    }

    @Test
    fun `it rises out of nothing`() {
        // "Спочатку звук наростає з нуля ... на старті змінюй гучність з 0 до
        // заданої десь за 5 секунд." Squared rather than straight, so it climbs
        // the way a motor spins up: slow off the mark, then gathering. A linear
        // ramp is already half-loud at 2.5 s, which is not a rise, it is a fade.
        assertTrue("it starts audible: ${rms(0.0, 0.2)}", rms(0.0, 0.2) < 0.02)
        assertTrue("no climb by 2 s", rms(1.8, 2.0) > rms(0.0, 0.2))
        assertTrue("still climbing at 4 s", rms(4.8, 5.0) > rms(1.8, 2.0) * 2)
    }

    @Test
    fun `the swell falls but never to silence`() {
        // His correction, and the one that makes it a siren rather than a beep:
        // "низ амплітуди не тиша". The amplitude follows the sweep -- quiet at
        // the bottom, full at the top -- which is what makes the top read as
        // loud. If the bottom went to nothing it would read as two sounds.
        val windows = (6..29).map { rms(it.toDouble(), it + 0.5) }
        val loudest = windows.max()
        val quietest = windows.min()
        assertTrue("the bottom is silence: $quietest", quietest > loudest * 0.35)
        assertTrue("no swell at all: $quietest vs $loudest", quietest < loudest * 0.85)
    }

    @Test
    fun `the wail never clips`() {
        val loudest = wail.maxOf { abs(it.toInt()) }
        assertTrue("peaked at $loudest", loudest <= Short.MAX_VALUE.toInt())
        assertTrue("suspiciously quiet: $loudest", loudest > Short.MAX_VALUE * 0.9)
    }

    @Test
    fun `the short pulses keep their own, higher band`() {
        // The guard, and it is the reason the two sounds no longer share a pair
        // of constants. The wail went down to 140-330 Hz because he asked for
        // it; the rhythm pulses did not, and must not follow.
        //
        // Measured: a 180 ms pulse in the wail's band comes back 2.9 dB quieter
        // through a phone speaker, because a small driver gives almost nothing
        // under 200 Hz and a short pulse has no time to make up for it. Those
        // pulses are the sounds that say "this one is about you, now". His
        // ruling when shown the number: "імпульси залиш незмінними".
        val pulse = Siren.pulses(longArrayOf(0, 180))
        assertTrue("the wail is not low: ${pitch(wail)}", pitch(wail) < 300)
        assertTrue("the pulse followed it down: ${pitch(pulse)}",
                   pitch(pulse) > 300)
    }

    @Test
    fun `it is about a second long`() {
        // Three dings 0.24 s apart, the last running out to 0.62 s. Long enough
        // to be a phrase, short enough not to be an alarm.
        val seconds = samples.size / 22_050.0
        assertEquals(1.10, seconds, 0.05)
    }
}
