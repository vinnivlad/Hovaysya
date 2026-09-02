package ua.hovaysya.ui

import androidx.compose.foundation.background
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
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
import ua.hovaysya.Gazetteer
import ua.hovaysya.Screen
import ua.hovaysya.Store

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
fun Settings(store: Store, bell: Bell, forgotten: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var granted by remember { mutableStateOf(Bell.policyGranted(context)) }
    var wakes by remember { mutableStateOf(bell.canWake(context)) }
    var gazetteer by remember { mutableStateOf<Gazetteer?>(null) }
    var home by remember { mutableStateOf<String?>(null) }
    var radius by remember { mutableStateOf(6f) }
    var saved by remember { mutableStateOf<String?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }
    var base by remember { mutableStateOf(store.base) }

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
        Text("Налаштування", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(4.dp))
        Text(
            "Ти тут як «${store.name ?: "?"}»",
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
                "Пʼять сигналів. Їх варто відчути зараз, бо вночі " +
                    "розрізняти доведеться не дивлячись.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(12.dp))
            // One row per bell, with the rhythm drawn beside it. The drawing is
            // not decoration: it is what lets somebody check they felt the one
            // they meant to press, which a row of identical buttons does not.
            Bells(
                "Тривога", "··· --- ···", "початок, як у Тривозі",
                onRing = {
                    bell.ring(context, bell.siren, "Повітряна тривога",
                        "Тривога. Реактивний шахед. Бровари.")
                },
            )
            Bells(
                "В укриття", "▪▪▪▪▪▪▪▪▪▪▪▪", "балістика, або над домом",
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
                "Відбій", "▬▬▬▬▬", "один довгий, без ритму",
                onRing = {
                    bell.ring(context, bell.clear, "Відбій тривоги",
                        "Відбій тривоги.")
                },
            )
            Bells(
                "Тихо", "—", "не будить",
                onRing = {
                    bell.ring(context, bell.quiet, "Тихо",
                        "Дорозвідка по балістиці.")
                },
            )
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
                    }.onFailure { problem = it.message ?: "не вийшло" }
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

        // --- the plumbing ---------------------------------------------------
        Spacer(Modifier.height(16.dp))
        Card {
            Text("Сервер", style = MaterialTheme.typography.bodyLarge)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = base,
                onValueChange = { base = it },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = { store.base = base }) { Text("Запамʼятати") }
        }

        Spacer(Modifier.height(16.dp))
        TextButton(onClick = {
            // Only on this phone. The server keeps the settings, because a lost
            // phone is the usual reason and throwing away where somebody lives
            // would be a poor answer to that.
            store.forget()
            forgotten()
        }) {
            Text("Забути цей пристрій", color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(24.dp))
    }
}

/** One bell: what it means, how it feels, and a way to feel it now. */
@Composable
private fun Bells(
    name: String,
    rhythm: String,
    meaning: String,
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
        OutlinedButton(onClick = onRing) { Text("Відчути") }
    }
}

@Composable
private fun Card(bad: Boolean = false, content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(
                if (bad) MaterialTheme.colorScheme.error.copy(alpha = 0.10f)
                else MaterialTheme.colorScheme.surfaceVariant
            )
            .padding(16.dp),
    ) {
        content()
    }
}
