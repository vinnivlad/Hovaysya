package ua.hovaysya

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * What stands in for a push, and why there is no Firebase in this app.
 *
 * The phone keeps one request open against `/state?wait=30`, and the answer
 * arrives the moment the watcher writes a different one. That is the whole
 * mechanism: no Google account, no `google-services.json`, no service key on the
 * server, and nothing between that machine and this phone on the one night it
 * matters. Every other part of this project is arranged to avoid depending on
 * somebody else's decision, and push was the last place that would have.
 *
 * Android's price for it is a notification that cannot be dismissed, and that
 * turned out to be the thing he already wanted -- a status line showing what is
 * happening rather than a feed of what happened. So the cost is the feature.
 *
 * # What it rings for, and what it refuses to ring twice
 *
 * The server has already decided. Each line in `said` carries the level and the
 * alarm this recipient's own rules produced, so this only has to notice a line
 * it has not seen and choose the bell. The mark of "seen" is persisted, because
 * without it a reboot would replay a finished raid: the state file still holds
 * the lines, and a phone waking up to ring for an alert that ended two hours ago
 * is exactly the kind of thing that gets an app uninstalled.
 *
 * # When it cannot reach the server
 *
 * It says so, in the notification. A silent alerting app that has quietly lost
 * its connection is worse than no app at all, because it is trusted.
 */
class AlertService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var worker: Job? = null

    private lateinit var store: Store
    private lateinit var bell: Bell

    override fun onCreate() {
        super.onCreate()
        store = Store(this)
        bell = Bell(store)
        bell.create(this)
        startForeground(NOTIFICATION_ID, status(null, null))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_HUSH) {
            // He swiped the permanent notification away, and that gesture now
            // means "I have seen it": the siren stops and the line comes
            // straight back. His design, and it is the right one -- the shade
            // is where a hand already is at three in the morning, and swiping
            // is the one gesture nobody has to find a button for.
            //
            // It also fixes something that read as a fault. Dismissing it used
            // to leave the shade empty for up to thirty seconds, because the
            // line is only redrawn when `/state` answers and that request is
            // held open for `wait=30`. So the app's one permanently visible
            // part could be missing for half a minute at a time, which looks
            // exactly like a watcher that has died.
            Siren.stop()
            show(status(latest, latestProblem))
            return START_STICKY
        }
        if (worker == null) {
            worker = scope.launch { watch() }
        }
        // Restarted by the system if it is ever killed, which is the point of a
        // service that exists to be there at three in the morning.
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // The last thing shown, so the line can be put back exactly as it was when
    // it is dismissed. Redrawing it from nothing would replace a real state
    // with "стежу" -- a downgrade dressed as a refresh.
    private var latest: Screen? = null
    private var latestProblem: String? = null

    /** One request open at a time, forever. */
    private suspend fun watch() {
        var version: String? = null
        var failures = 0
        // When it stopped working, not how many times it has failed. A deploy
        // restarts the API and Caddy answers 502 for ten seconds; a real outage
        // answers the same way for an hour. One number tells those apart and a
        // count does not, so the notification can stop being alarming about the
        // first without going quiet about the second.
        var failingSince: Long? = null
        while (true) {
            if (!store.registered) {
                // Nothing to watch for a phone that has not registered. Stop
                // rather than spin: the app starts this again when it does.
                stopSelf()
                return
            }
            val result = runCatching { store.api().screen(wait = WAIT_S, version = version) }
            result.onSuccess { screen ->
                failures = 0
                failingSince = null
                version = screen.version
                latest = screen
                latestProblem = null
                ringFor(screen)
                show(status(screen, null))
            }.onFailure { problem ->
                failures += 1
                val began = failingSince ?: System.currentTimeMillis()
                failingSince = began
                latest = null
                latestProblem = trouble(problem, began)
                show(status(null, latestProblem))
                // Backing off, but never past a minute. A phone that has been
                // offline for an hour still has to notice the moment it is not.
                delay(minOf(60_000L, 2_000L * failures))
            }
        }
    }

    /**
     * Ring for every line this phone has not seen, and remember the newest.
     *
     * The stamps are ISO in UTC, so comparing them as strings orders them --
     * which is worth saying out loud because it is only true while they are all
     * written by the same watcher in the same format.
     */
    private fun ringFor(screen: Screen) {
        val seen = store.lastSaid
        val fresh = screen.said.filter { seen == null || it.at > seen }
        for (line in fresh) {
            if (line.level == "alert") {
                bell.ring(this, bell.channelFor(line.level, line.alarm),
                    title(screen), line.text)
            }
        }
        screen.said.maxByOrNull { it.at }?.let { store.lastSaid = it.at }
    }

    /**
     * The failure, and how long it has been one.
     *
     * Silent about the duration for the first minute, because that is what a
     * deploy looks like and there is nothing to act on: the API restarts, Caddy
     * says 502, and it is over before anybody has read the line. Past that it
     * counts, because a service that has been unreachable for half an hour is a
     * different fact and the only place this app can state it is here.
     */
    private fun trouble(error: Throwable, since: Long): String {
        val said = saidPlainly(error)
        val minutes = (System.currentTimeMillis() - since) / 60_000
        return if (minutes < 1) said else "$said · $minutes хв"
    }

    private fun show(notification: Notification) {
        getSystemService(NotificationManager::class.java)
            ?.notify(NOTIFICATION_ID, notification)
    }

    private fun title(screen: Screen?): String = when {
        screen == null -> "Ховайся"
        !screen.known -> "Ховайся: не знаю"
        screen.state == Screen.ALERT -> "ТРИВОГА"
        else -> "Без тривог"
    }

    /**
     * The line in the shade. It is the only permanently visible part of this
     * app, so it says the two things worth knowing at a glance: whether an alert
     * is on, and whether this is still working.
     */
    private fun status(screen: Screen?, problem: String?): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        // Fired when the line is swiped away. A different request code from
        // `open`, or the two would be the same PendingIntent and tapping the
        // notification would silence the siren instead of opening the app.
        val hush = PendingIntent.getService(
            this, 1, Intent(this, AlertService::class.java).setAction(ACTION_HUSH),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

        val body = when {
            problem != null -> problem
            screen == null -> "стежу"
            !screen.known -> "спостерігач ще не писав"
            screen.state == Screen.ALERT ->
                screen.top?.word?.replaceFirstChar { it.uppercase() } ?: "тривога"
            else -> screen.said.lastOrNull()?.text ?: "тихо"
        }

        val accent = getColor(colourOf(screen, problem))
        return Notification.Builder(this, bell.status)
            .setSmallIcon(R.drawable.ic_bell)
            .setContentTitle(title(screen))
            .setContentText(body)
            .setContentIntent(open)
            .setDeleteIntent(hush)
            .setOngoing(true)
            .setShowWhen(false)
            .setOnlyAlertOnce(true)
            // `setColorized` paints the whole notification and is honoured for
            // foreground services, which this is. There was a coloured disc on
            // the right as well, as insurance against shells that ignore it --
            // his phone is not one, and he was right that it earned nothing
            // there: "дзвоник справа прибирай, він там нічого не дає". A second
            // signal that adds no information is just something else to read.
            .setColor(accent)
            .setColorized(true)
            .build()
    }

    /** Red for an alert, green for none, muted for not knowing. */
    private fun colourOf(screen: Screen?, problem: String?): Int = when {
        problem != null -> R.color.muted
        screen == null || !screen.known -> R.color.muted
        screen.state == Screen.ALERT -> R.color.danger
        else -> R.color.calm
    }


    companion object {
        private const val NOTIFICATION_ID = 1
        private const val WAIT_S = 30

        /** Swiping the permanent line away: stop the siren, put the line back. */
        const val ACTION_HUSH = "ua.hovaysya.HUSH"

        /** Start it, from anywhere that is allowed to. */
        fun start(context: Context) {
            val intent = Intent(context, AlertService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, AlertService::class.java))
        }
    }
}
