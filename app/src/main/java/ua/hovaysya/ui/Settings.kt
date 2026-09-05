package ua.hovaysya.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import ua.hovaysya.Bell
import ua.hovaysya.BuildConfig
import ua.hovaysya.Gazetteer
import ua.hovaysya.Screen
import ua.hovaysya.Siren
import ua.hovaysya.Store
import ua.hovaysya.saidPlainly

/**
 * Settings, and one thing that is not a setting: whether the bell can actually
 * wake this phone.
 *
 * That belongs here because it is the only thing on any screen the person has to
 * act on themselves. Everything else is a preference; this one is the difference
 * between an app that works and an app that is decoration, and Android gives it
 * no runtime prompt -- so if it is not said plainly here, it is not said.
 */
@Composable
fun Settings(
    store: Store,
    bell: Bell,
    onBack: () -> Unit,
    forgotten: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var granted by remember { mutableStateOf(Bell.policyGranted(context)) }
    var wakes by remember { mutableStateOf(bell.canWake(context)) }
    var gazetteer by remember { mutableStateOf<Gazetteer?>(null) }
    var home by remember { mutableStateOf<String?>(null) }
    var radius by remember { mutableStateOf(6f) }
    var volume by remember { mutableStateOf(store.volume) }
    var quiet by remember { mutableStateOf(store.quietHours) }
    var saved by remember { mutableStateOf<String?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }

    // The grant is made in system settings, so the answer changes while this app
    // is in the background and there is no callback for it. Re-asking cheaply is
    // the honest way to notice.
    LaunchedEffect(Unit) {
        while (true) {
            granted = Bell.policyGranted(context)
            wakes = bell.canWake(context)
            delay(2_000)
        }
    }

    LaunchedEffect(Unit) {
        runCatching { store.api().config() }.onSuccess { cfg ->
            home = cfg["home"] as? String
            (cfg["radius_km"] as? Number)?.let { radius = it.toFloat() }
        }
        runCatching { store.api().gazetteer() }.onSuccess { gazetteer = it }
    }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
    ) {
        // Its own way out, since it is no longer a tab somebody can leave by
        // tapping another one.
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .clickable(onClick = onBack),
                contentAlignment = Alignment.Center,
            ) {
                Text("←", style = MaterialTheme.typography.titleLarge)
            }
            Spacer(Modifier.width(4.dp))
            Text("Налаштування", style = MaterialTheme.typography.titleLarge)
        }
        Spacer(Modifier.height(4.dp))
        Text(
            "Ти тут як «${store.name ?: "?"}» · версія ${BuildConfig.VERSION_NAME}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        // --- the one that matters ------------------------------------------
        Spacer(Modifier.height(24.dp))
        Card(bad = !wakes) {
            Text(
                if (wakes) "Дзвінок пробиває «не турбувати»"
                else "Дзвінок НЕ пробиває «не турбувати»",
                style = MaterialTheme.typography.bodyLarge,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                if (wakes) {
                    "Балістика о третій ночі буде почута."
                } else if (!granted) {
                    "Android не питає про це сам. Дай доступ до режиму " +
                        "«Не турбувати», інакше нічний режим просто зʼїсть тривогу."
                } else {
                    "Доступ є, але канал створився раніше за нього — а канал " +
                        "після створення незмінний. Треба створити наново."
                },
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(12.dp))
            Row {
                if (!granted) {
                    Button(onClick = {
                        context.startActivity(Bell.policyIntent())
                    }) { Text("Дати доступ") }
                } else if (!wakes) {
                    Button(onClick = {
                        bell.remake(context)
                        wakes = bell.canWake(context)
                    }) { Text("Створити канали наново") }
                }
            }
        }

        // --- the alphabet ---------------------------------------------------
        Spacer(Modifier.height(16.dp))
        Card {
            Text("Як це відчувається", style = MaterialTheme.typography.bodyLarge)
            Spacer(Modifier.height(6.dp))
            Text(
                "Чотири сигнали, які варто почути й відчути зараз — бо " +
                    "вночі розрізняти доведеться не дивлячись. Пʼятий не " +
                    "відчувається взагалі, і в цьому вся його робота.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(12.dp))
            // One row per bell, with the rhythm drawn beside it. The drawing is
            // not decoration: it is what lets somebody check they felt the one
            // they meant to press, which a row of identical buttons does not.
            Bells(
                "Тривога", "··· ▬▬▬ ···", "початок, як у Тривозі",
                onRing = {
                    bell.ring(context, bell.siren, "Повітряна тривога",
                        "Тривога. Реактивний шахед. Бровари.")
                },
            )
            // Not "або над домом", which promised something the policy does
            // not do. The home rule fires on ballistic alone -- his own ruling,
            // "коли летить балістика і Жуляни" -- so a drone over Жуляни
            // arrives as "Загроза сюди", and this row taught the alphabet wrong.
            Bells(
                "В укриття", "··· ···", "балістика",
                onRing = {
                    bell.ring(context, bell.shelter, "В укриття",
                        "Тривога. Балістика. Жуляни.")
                },
            )
            Bells(
                "Загроза сюди", "·· ··", "летить у бік кола",
                onRing = {
                    bell.ring(context, bell.near, "Загроза сюди",
                        "Загроза: реактивний шахед. Вишневе.")
                },
            )
            Bells(
                "Відбій", "▬", "один довгий, без ритму",
                onRing = {
                    bell.ring(context, bell.clear, "Відбій тривоги",
                        "Відбій тривоги.")
                },
            )
            Bells(
                "Тихо", "—", "не будить, не вібрує",
                // Still worth pressing: it puts the line in the shade, which is
                // where this class is meant to be found rather than felt.
                verb = "Показати",
                onRing = {
                    bell.ring(context, bell.quiet, "Тихо",
                        "Дорозвідка по балістиці.")
                },
            )
        }

        // --- how loud -------------------------------------------------------
        Spacer(Modifier.height(16.dp))
        Card {
            Text("Звук", style = MaterialTheme.typography.bodyLarge)
            Spacer(Modifier.height(6.dp))
            Text(
                "Сирена, коли оголошують тривогу. Та сама, але коротко, тим " +
                    "самим ритмом 2+2 — коли летить у твоє коло. Короткий " +
                    "пілік на відбій. Вібрація працює завжди, навіть на нулі.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Гучність", style = MaterialTheme.typography.bodyMedium)
                Slider(
                    value = volume,
                    onValueChange = { volume = it },
                    // Saved on release rather than on every pixel, and the pip
                    // plays then too: a volume you cannot hear while setting it
                    // is a number, not a setting. It plays at the slider's own
                    // value, not at `volumeNow()` -- previewing silence inside
                    // the quiet window would look like a broken slider.
                    onValueChangeFinished = {
                        store.volume = volume
                        Siren.clear(volume)
                    },
                    modifier = Modifier
                        .weight(1f)
                        .padding(horizontal = 12.dp),
                )
                Text(
                    "${(volume * 100).toInt()}%",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Тихі години", style = MaterialTheme.typography.bodyMedium)
                    Text(
                        "22:00–08:00 без звуку. Вібрація лишається, і в " +
                            "укриття все одно розбудить.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Switch(
                    checked = quiet,
                    onCheckedChange = { quiet = it; store.quietHours = it },
                )
            }
        }

        // --- where I live ---------------------------------------------------
        Spacer(Modifier.height(16.dp))
        Card {
            Text("Дім і коло", style = MaterialTheme.typography.bodyLarge)
            Spacer(Modifier.height(6.dp))
            Text(
                home ?: "не вибрано",
                style = MaterialTheme.typography.bodyLarge,
                color = colourFor(Screen.WATCHING),
            )
            Spacer(Modifier.height(10.dp))
            Text(
                "Ближнє коло: ${"%.0f".format(radius)} км",
                style = MaterialTheme.typography.bodyMedium,
            )
            Slider(
                value = radius,
                onValueChange = { radius = it },
                valueRange = 2f..15f,
                steps = 12,
            )
            gazetteer?.let { ready ->
                Text(
                    "${ready.homes().size} районів на вибір",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(10.dp))
            Button(onClick = {
                scope.launch {
                    saved = null
                    problem = null
                    runCatching {
                        store.api().saveConfig(
                            mapOf("radius_km" to radius.toDouble()))
                    }.onSuccess {
                        // The watcher notices within one poll -- nothing has to
                        // be restarted for a moved home to take effect.
                        saved = "збережено, застосується протягом хвилини"
                    }.onFailure { problem = saidPlainly(it) }
                }
            }) { Text("Зберегти коло") }
            saved?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            problem?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.error)
            }
        }

        // No server field here, and its absence is deliberate rather than tidy.
        // The token is issued by one server and means nothing on another, so
        // changing the address after registering could only ever break the app
        // -- silently, into a 401 that looks like the service being down.
        //
        // It is asked once at first run, before a token exists, which is the
        // only moment the question is coherent. "Забути цей пристрій" leads back
        // there, so the way to change it is to stop being registered first,
        // which is exactly what changing it means.
        Spacer(Modifier.height(16.dp))
        TextButton(onClick = {
            scope.launch {
                // Ask the server to drop the registration first, then forget it
                // here. In that order, because the token is what authorises the
                // removal and clearing it locally first would throw away the
                // only thing that could.
                //
                // A failure is not a reason to stay registered on this phone:
                // the person asked to be forgotten, and the row left behind is
                // a stale recipient rather than anything of theirs.
                runCatching { store.api().unregister() }
                store.forget()
                forgotten()
            }
        }) {
            Text("Забути цей пристрій", color = MaterialTheme.colorScheme.error)
        }
        Text(
            "Знімає реєстрацію і на сервері.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(24.dp))
    }
}

/** One bell: what it means, how it feels, and a way to feel it now. */
@Composable
private fun Bells(
    name: String,
    rhythm: String,
    meaning: String,
    // What the button honestly offers. His objection, and it was about the copy
    // rather than the code: "а на «Тихо» навіщо вібро? На те воно й тихо."
    // The channel has never vibrated -- `enableVibration(false)` -- but a button
    // saying "Відчути" beside it promised a sensation that cannot arrive, and a
    // quiet bell is defined by not being felt.
    verb: String = "Відчути",
    onRing: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(name, style = MaterialTheme.typography.bodyLarge)
            Text(
                rhythm,
                style = MaterialTheme.typography.bodyMedium,
                color = colourFor(Screen.WATCHING),
            )
            Text(
                meaning,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        OutlinedButton(onClick = onRing) { Text(verb) }
    }
}

@Composable
private fun Card(bad: Boolean = false, content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(
                // 10% of a red read as almost nothing over a near-black
                // ground -- a tint tuned as half of a light/dark pair. With one
                // dark theme it can be set for the ground it actually sits on,
                // and this card has to say "something is wrong" at a glance.
                if (bad) MaterialTheme.colorScheme.error.copy(alpha = 0.18f)
                else MaterialTheme.colorScheme.surfaceVariant
            )
            .padding(16.dp),
    ) {
        content()
    }
}
