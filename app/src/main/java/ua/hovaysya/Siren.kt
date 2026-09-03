package ua.hovaysya

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Handler
import android.os.Looper
import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.sin

/**
 * The sounds, generated rather than shipped.
 *
 * He asked whether the official Тривога app's sounds could be pulled out of it.
 * They could, and this is better than that on every axis rather than as a
 * compromise: no question about somebody else's asset, no binary in a repository
 * that has never carried one, and complete control over pitch, length and
 * volume -- which is the whole reason the volume can be a setting at all.
 *
 * A siren is physics before it is anybody's recording: the wail is a tone
 * sweeping up and down because a mechanical siren spins up and down. Everyone
 * here recognises it without being taught, and it belongs to nobody.
 *
 * `USAGE_ALARM` on purpose. It plays on the alarm stream, which is louder than
 * notifications and is not silenced by the ringer being down -- and a phone on
 * silent is the ordinary state of a phone at three in the morning.
 */
object Siren {

    private const val RATE = 22_050

    /** The wail: 440 up to 880 and back, twice. A raid has begun. */
    fun alert(volume: Float) = play(wail(cycles = 2, seconds = 2.0), volume)

    /**
     * The siren's voice, chopped to a vibration pattern. A threat, right here.
     *
     * Two corrections of his, and together they decided the shape. First, this
     * sound is not about one place: "будь-яка загроза що видає звук -- балістика,
     * крилаті на підльоті тп", "звук там де його видає Ховайся, коли балістика
     * падає, ракети в колі". So it is one sound for every loud moment, and the
     * vibration is what says which -- the ear says "something", the hand says
     * "what". Second, it should be the siren rather than a beep, but short:
     * "можна сирену, але за тим коротким патерном, 2 короткі + 2 короткі".
     *
     * Which is why it takes the pattern instead of holding its own copy of the
     * rhythm. `Bell` owns the alphabet; this renders it. A drawn rhythm that
     * disagreed with the buzzing one has already cost us once -- he caught the
     * near pattern by feel while the settings screen drew something else -- and
     * a *heard* rhythm that disagrees with the felt one would be the same bug
     * with no way to see it. Now there is one array, and three senses read it.
     */
    fun rhythm(pattern: LongArray, volume: Float) =
        play(chop(pattern), volume)

    /**
     * A single struck note that dies away. It is over.
     *
     * His description of the official app's, and it is a better sound than the
     * steady tone I wrote first: "відбій там як одинарний пілік, схожий на звук
     * старого касового апарату". A till's ding is a bell being hit -- an attack
     * and a decay -- not a note being held.
     *
     * Which also makes it right for what it means. Every other sound here is
     * sustained because the thing it announces is still going on; this one is
     * over the moment it starts, and a sound that stops by itself says that
     * without a word.
     */
    fun clear(volume: Float) = play(pip(), volume)

    // --- the samples ---------------------------------------------------------

    private fun wail(cycles: Int, seconds: Double): ShortArray {
        val total = (RATE * seconds * cycles).toInt()
        val out = ShortArray(total)
        // Phase is accumulated rather than computed from `sin(2π f t)`, because
        // the frequency changes: evaluating the closed form at a moving `f`
        // makes the waveform jump every sample and the result is a rasp instead
        // of a wail.
        var phase = 0.0
        val period = RATE * seconds
        for (i in 0 until total) {
            val within = (i % period) / period
            // Up for the first half of a cycle, down for the second.
            val sweep = if (within < 0.5) within * 2 else (1 - within) * 2
            val frequency = 440.0 + 440.0 * sweep
            phase += 2 * PI * frequency / RATE
            out[i] = (sin(phase) * Short.MAX_VALUE * 0.6).toInt().toShort()
        }
        return fade(out)
    }

    /**
     * A vibration pattern read as sound: index 0 is the wait before the first
     * pulse, then on, off, on, off. The same convention Android's vibrator uses,
     * because it is the same array.
     */
    private fun chop(pattern: LongArray): ShortArray {
        var out = ShortArray(0)
        for ((i, millis) in pattern.withIndex()) {
            out += if (i % 2 == 1) burst(millis) else silence(millis / 1000.0)
        }
        return out
    }

    /**
     * One short pulse of the siren winding up: 440 to 880 across the pulse,
     * however long the pulse happens to be.
     *
     * The same voice and the same span as the long wail, so four of these read
     * as the siren being interrupted rather than as a different instrument.
     */
    private fun burst(millis: Long): ShortArray {
        val out = ShortArray((RATE * millis / 1000).toInt())
        var phase = 0.0
        for (i in out.indices) {
            val through = i.toDouble() / out.size
            phase += 2 * PI * (440.0 + 440.0 * through) / RATE
            out[i] = (sin(phase) * Short.MAX_VALUE * 0.6).toInt().toShort()
        }
        return fade(out)
    }

    private fun pip(): ShortArray {
        val out = ShortArray((RATE * 0.35).toInt())
        for (i in out.indices) {
            val t = i.toDouble() / RATE
            // A struck bell rather than a held note: mostly gone in 70 ms.
            val envelope = exp(-t * 14)
            val wave = sin(2 * PI * 988.0 * t) + 0.35 * sin(2 * PI * 1976.0 * t)
            out[i] = (wave * envelope * Short.MAX_VALUE * 0.45).toInt().toShort()
        }
        return fade(out)
    }

    private fun silence(seconds: Double) = ShortArray((RATE * seconds).toInt())

    /**
     * Five milliseconds of ramp at each end.
     *
     * Without it every one of these starts and stops on a non-zero sample, and
     * that discontinuity is an audible click -- which on the sound that says
     * "take cover" reads as a fault in the app rather than as part of the alarm.
     */
    private fun fade(samples: ShortArray): ShortArray {
        val ramp = minOf(RATE / 200, samples.size / 2)
        for (i in 0 until ramp) {
            val gain = i.toDouble() / ramp
            samples[i] = (samples[i] * gain).toInt().toShort()
            val last = samples.size - 1 - i
            samples[last] = (samples[last] * gain).toInt().toShort()
        }
        return samples
    }

    private operator fun ShortArray.plus(other: ShortArray): ShortArray {
        val out = ShortArray(size + other.size)
        copyInto(out)
        other.copyInto(out, size)
        return out
    }

    // --- playing it ----------------------------------------------------------

    private fun play(samples: ShortArray, volume: Float) {
        if (volume <= 0f || samples.isEmpty()) {
            return
        }
        val track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build())
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build())
            .setBufferSizeInBytes(samples.size * 2)
            .setTransferMode(AudioTrack.MODE_STATIC)
            .build()
        track.write(samples, 0, samples.size)
        track.setVolume(volume.coerceIn(0f, 1f))
        track.play()
        // Released on a timer rather than left to the garbage collector: an
        // AudioTrack holds a hardware buffer, and a leaked one is a phone that
        // stops being able to play the next alarm.
        val millis = (samples.size * 1000L / RATE) + 300
        Handler(Looper.getMainLooper()).postDelayed({
            runCatching {
                track.stop()
                track.release()
            }
        }, millis)
    }
}
