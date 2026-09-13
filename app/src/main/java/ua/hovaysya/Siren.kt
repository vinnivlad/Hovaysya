package ua.hovaysya

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Handler
import android.os.Looper
import kotlin.math.abs
import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.sin
import kotlin.math.tanh

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

    private val handler = Handler(Looper.getMainLooper())

    // What is sounding, so it can be cut short. Guarded because the siren is
    // started from the service's coroutine and stopped from a notification's
    // delete intent on the main thread, and an `AudioTrack` released twice
    // throws.
    private var playing: AudioTrack? = null
    private var release: Runnable? = null

    /**
     * The **pulses'** range, and it is deliberately low: "можна тон сирени
     * нижче? Не схоже на те як в застосунку Тривога". A mechanical siren is a
     * big slow thing and it sounds like one; 440 to 880 was a smoke detector.
     *
     * It is no longer the wail's range, and the split is measured rather than
     * merely cautious. The wail went lower still on his ask; these did not
     * follow, because a 180 ms pulse in the wail's band comes back **2.9 dB
     * quieter** through a phone speaker -- a small driver gives almost nothing
     * under 200 Hz, and a pulse that short has no time to make up for it in
     * duration. These are the sounds that say "this one is about you, now", so
     * the trade the wail can afford is the one they cannot. Shown the number,
     * his ruling was "імпульси залиш незмінними ... відокрем, якщо потрібно".
     */
    private const val PULSE_LOW = 250.0
    private const val PULSE_HIGH = 500.0

    /**
     * How hard the sine is driven into saturation, and how close to full scale
     * it lands. Both exist because he asked for more volume than there was:
     * "максимальну гучність треба збільшити".
     *
     * A pure sine is the quietest waveform there is for a given peak -- all of
     * its energy sits at one frequency, and the peak is what runs out of
     * headroom first. Saturating it flattens the tops, which raises the average
     * power a long way without raising the peak at all, and the harmonics it
     * grows land at 750, 1250, 1750 Hz -- exactly where a phone speaker is
     * efficient and where a 250 Hz fundamental is not. So the same change that
     * makes it lower is what keeps it from getting quieter.
     *
     * Which is also the honest waveform. A siren is chopped airflow, not a tuning
     * fork; the grit is the instrument rather than distortion of it.
     */
    private const val PULSE_DRIVE = 2.6
    private const val PEAK = 0.95

    /**
     * The wail, and every number in it is his.
     *
     * "Зараз вона надто різка. Треба емулювати більше як звучить стандартна
     * сирена. Спочатку звук наростає з нуля, частота значно менша, [н]а одну
     * амплітуду секунд 10 ... низ амплітуди не тиша, мабуть починай сирену з
     * низу і на старті змінюй гучність з 0 до заданої десь за 5 секунд."
     *
     * Which is a real siren described from the outside, and it is four changes
     * at once:
     *
     *     140-330 Hz    an octave and a bit below where it was
     *     10 s          one climb and fall, against the old two-second flutter
     *     5 s           rising from silence, because a motor takes that long
     *     0.60          the swell's floor: the bottom is quiet, never silent
     *
     * The swell is the part that was missing and the part that makes it read as
     * a siren. Amplitude follows the sweep, so the top is loud *by contrast*
     * rather than by level -- there is no headroom left to be louder by level,
     * the peak already sits at [PEAK].
     *
     * The drive follows the sweep too, and that is the only one of these that
     * adds real loudness rather than the impression of it. At the bottom it is
     * nearly a pure sine; at the top it saturates, and the harmonics saturation
     * grows land where a phone speaker is efficient and a 140 Hz fundamental is
     * not. Measured against the flat version he started from, it puts 0.8 dB
     * back at the peak.
     *
     * Chosen by ear from seven, after seven more: "давай зупинимось поки на d".
     */
    private const val WAIL_LOW = 140.0
    private const val WAIL_HIGH = 330.0
    private const val WAIL_SECONDS = 30.0
    private const val WAIL_PERIOD = 10.0
    private const val WAIL_RISE = 5.0
    private const val WAIL_FLOOR = 0.60
    private const val WAIL_DRIVE_LOW = 1.0
    private const val WAIL_DRIVE_HIGH = 2.2

    /**
     * The wail: three climbs and falls over thirty seconds. A raid has begun.
     *
     * Long on purpose, and his, twice over -- "хочу додати сценарій, що
     * звук початку тривоги довший, нехай 10с", then "підніми довжину
     * сирена до 30с також". Four seconds was a notification chime -- it can
     * end while somebody is still working out what woke them. And the rise now
     * spends the first five on its own, so the part at full volume has to be
     * paid for out of a longer whole.
     *
     * Long enough to need a way out, too, which is why `stop` exists and why
     * dismissing the permanent notification calls it.
     */
    fun alert(volume: Float) = play(wail(), volume)

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
     * Three sine dings, E4 - C4 - F4. It is over.
     *
     * It was a till pip before, on his description of the official app's
     * all-clear -- "схожий на звук старого касового апарату" -- and he asked for
     * something else twice. First a bell, which came out sounding like a church
     * one; then this, and he brought the sound he meant: three files from
     * floraphonic's "short punchy sine wave ding" pack, in that order.
     *
     * Measured off those files rather than guessed from their names. They are
     * `1-c`, `5-e` and `6-f`, and the pitches are exactly C4, E4 and F4 -- 261.5,
     * 329.7 and 349.3 Hz, within a cent. The harmonics sit 42-52 dB down, so
     * "sine wave" is meant literally and a single sine reproduces them.
     *
     * The envelope is where the punch is, and it is not a decay:
     *
     *     0-20 ms     attack to peak
     *     20-230 ms   holds, drifting only -2 dB
     *     230-580 ms  falls away, steepening
     *
     * The note stands before it drops. An `exp(-t)` from the first sample --
     * which is what [pip] did -- is softer and rounder, and loses the whole
     * character.
     *
     * Still right for what it means, for the reason the pip was: every other
     * sound here is sustained because the thing it announces is still going on.
     * This one ends by itself.
     *
     * It is also now the only sound in the set with a *pitch*, which is what
     * keeps it from being mistaken for a warning at the moment of waking -- the
     * count no longer does that on its own, since `NEAR` is two pulses and this
     * is three.
     */
    fun clear(volume: Float) = play(dings(), volume)

    // --- the samples ---------------------------------------------------------

    /** Exposed for a test: the waveform, with no Android in the way. */
    internal fun wail(): ShortArray {
        val total = (RATE * WAIL_SECONDS).toInt()
        val out = ShortArray(total)
        // Phase is accumulated rather than computed from `sin(2π f t)`, because
        // the frequency changes: evaluating the closed form at a moving `f`
        // makes the waveform jump every sample and the result is a rasp instead
        // of a wail.
        var phase = 0.0
        val period = RATE * WAIL_PERIOD
        for (i in 0 until total) {
            val within = (i % period) / period
            // Up for the first half of a cycle, down for the second, so it
            // starts at the bottom: "починай сирену з низу".
            val sweep = if (within < 0.5) within * 2 else (1 - within) * 2
            phase += 2 * PI * (WAIL_LOW + (WAIL_HIGH - WAIL_LOW) * sweep) / RATE
            val drive = WAIL_DRIVE_LOW + (WAIL_DRIVE_HIGH - WAIL_DRIVE_LOW) * sweep
            val swell = WAIL_FLOOR + (1.0 - WAIL_FLOOR) * sweep
            // Squared, so it climbs the way a motor spins up rather than the
            // way a fader moves: a straight ramp is already half-loud at 2.5 s,
            // which reads as the sound having been turned down, not as a siren
            // starting.
            val rise = minOf(1.0, i / RATE.toDouble() / WAIL_RISE)
            out[i] = voice(phase, drive, swell * rise * rise)
        }
        return fade(out)
    }

    /** Exposed for a test: a rhythm rendered as sound. */
    internal fun pulses(pattern: LongArray): ShortArray = chop(pattern)

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
     * The same voice as the long wail, so four of these read as the siren being
     * interrupted rather than as a different instrument -- but no longer the
     * same span. See [PULSE_LOW] for why they stayed up where they were.
     */
    private fun burst(millis: Long): ShortArray {
        val out = ShortArray((RATE * millis / 1000).toInt())
        var phase = 0.0
        for (i in out.indices) {
            val through = i.toDouble() / out.size
            phase += 2 * PI * (PULSE_LOW + (PULSE_HIGH - PULSE_LOW) * through) / RATE
            out[i] = voice(phase, PULSE_DRIVE)
        }
        return fade(out)
    }

    /**
     * One sample of the siren, saturated. `tanh` is divided by its own value at
     * the peak so the result still reaches full scale rather than being both
     * driven and quieter.
     */
    private fun voice(phase: Double, drive: Double, gain: Double = 1.0): Short =
        (tanh(sin(phase) * drive) / tanh(drive) * gain * Short.MAX_VALUE * PEAK)
            .toInt().toShort()

    // E4, C4, F4 -- his order, and the pack's own numbering says which is which:
    // `ding-5-e`, then `ding-1-c`, then `ding-6-f`.
    private val DINGS = doubleArrayOf(329.63, 261.63, 349.23)

    // 0.24 s, his choice out of four spacings between 0.16 and 0.45. They
    // overlap, which is why the sum below is scaled rather than trusted.
    private const val DING_GAP = 0.24
    private const val DING_LEN = 0.62
    private const val DING_ATTACK = 0.015
    private const val DING_HOLD = 0.21
    // Per second, fitted to the measured fall: -3.4 dB at 240 ms, -42 at 580.
    private const val DING_RELEASE = 12.0

    // Where the soft limiter starts bending, as a fraction of full scale. High
    // on purpose: below it nothing is touched at all, so a single ding and the
    // whole tail of the phrase pass through exactly as written.
    private const val LIMIT_KNEE = 0.90

    private fun dingEnvelope(t: Double): Double = when {
        t < DING_ATTACK -> t / DING_ATTACK
        // The slight droop the originals have while they hold.
        t < DING_ATTACK + DING_HOLD ->
            1.0 - 0.10 * (t - DING_ATTACK) / DING_HOLD
        else -> 0.90 * exp(-(t - DING_ATTACK - DING_HOLD) * DING_RELEASE)
    }

    /** Exposed for a test: the waveform, with no Android in the way. */
    internal fun dings(): ShortArray {
        val total = (RATE * (DING_GAP * (DINGS.size - 1) + DING_LEN)).toInt()
        val mixed = DoubleArray(total)
        for ((k, freq) in DINGS.withIndex()) {
            val start = (RATE * DING_GAP * k).toInt()
            val length = (RATE * DING_LEN).toInt()
            for (i in 0 until length) {
                val at = start + i
                if (at >= total) break
                val t = i.toDouble() / RATE
                mixed[at] += sin(2 * PI * freq * t) * dingEnvelope(t)
            }
        }
        // Each ding at full scale, and the overlap softened rather than the
        // whole thing turned down.
        //
        // His report: the all-clear is quiet against the other sounds. Measured,
        // it was 5.8 dB under the wail, and most of that was self-inflicted --
        // the three dings overlap, their sum peaks at 1.59 times one of them,
        // and dividing by that peak put every ding 4.0 dB below where it could
        // have been. A quiet passage was being scaled down to protect one
        // instant of constructive alignment.
        //
        // So the sum is soft-limited at the knee instead. It recovers 3.7 dB and
        // touches 7.6% of the samples, at a total harmonic distortion of
        // -35.7 dB -- about 1.6%, which on three sine tones is inaudible.
        //
        // It does not reach the +6 dB he asked for, and that is deliberate: the
        // last two decibels cost -24.5 dB THD at gain 1.3 and -18.6 dB at 1.6,
        // and 12% distortion on a pure sine is a buzz. The sound he chose is a
        // sine; making it louder by making it dirty would be answering a
        // different request.
        val out = ShortArray(total)
        for (i in 0 until total) {
            val x = mixed[i] * PEAK
            val shaped = if (abs(x) > LIMIT_KNEE) {
                val over = (abs(x) - LIMIT_KNEE) / (1.0 - LIMIT_KNEE)
                val sign = if (x < 0) -1.0 else 1.0
                sign * (LIMIT_KNEE + (1.0 - LIMIT_KNEE) * tanh(over))
            } else {
                x
            }
            out[i] = (shaped * Short.MAX_VALUE).toInt().toShort()
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

    /**
     * Cut whatever is sounding, now.
     *
     * The way out of a ten-second siren. Safe to call when nothing is playing,
     * because that is how it is usually called: dismissing the notification
     * means "I have seen it" whether or not there is a noise to stop.
     */
    fun stop() {
        synchronized(this) {
            release?.let(handler::removeCallbacks)
            release = null
            playing?.let { track ->
                runCatching {
                    track.pause()
                    track.flush()
                    track.stop()
                    track.release()
                }
            }
            playing = null
        }
    }

    private fun play(samples: ShortArray, volume: Float) {
        if (volume <= 0f || samples.isEmpty()) {
            return
        }
        // One siren at a time. Two overlapping wails are not twice as clear,
        // and the second one would leave the first's track unreachable by
        // `stop`.
        stop()
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
        synchronized(this) {
            playing = track
            val done = Runnable {
                synchronized(this) {
                    if (playing === track) {
                        runCatching {
                            track.stop()
                            track.release()
                        }
                        playing = null
                        release = null
                    }
                }
            }
            release = done
            handler.postDelayed(done, millis)
        }
    }
}
