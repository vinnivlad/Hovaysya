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

    @Test
    fun `it is about a second long`() {
        // Three dings 0.24 s apart, the last running out to 0.62 s. Long enough
        // to be a phrase, short enough not to be an alarm.
        val seconds = samples.size / 22_050.0
        assertEquals(1.10, seconds, 0.05)
    }
}
