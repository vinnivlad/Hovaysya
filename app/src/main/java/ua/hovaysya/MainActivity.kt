package ua.hovaysya

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import ua.hovaysya.ui.App
import ua.hovaysya.ui.HovaysyaTheme

class MainActivity : ComponentActivity() {

    private val askNotifications =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val store = Store(this)
        val bell = Bell(store)

        // Before anything is drawn, because a channel has to exist before it can
        // ever be rung -- and see `Bell` on why the shelter one will not be able
        // to bypass night mode on this first pass, and what puts that right.
        bell.create(this)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        // Watching starts here rather than in `App`, because a service may be
        // started from an activity that is in the foreground and this is the
        // only moment that is certainly true. `BootReceiver` covers the other
        // way in.
        if (store.registered) {
            AlertService.start(this)
        }

        setContent {
            HovaysyaTheme {
                App(store, bell)
            }
        }
    }
}
