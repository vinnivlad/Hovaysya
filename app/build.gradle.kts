// The whole build. Compose and AndroidX, and nothing else -- no HTTP client, no
// JSON library, no dependency injection.
//
// That is the same choice the backend made and for the same reason: this has to
// still build in a year, on a machine nobody has prepared, at a moment when
// something is wrong. `HttpURLConnection` and `org.json` are in the platform.
// Four endpoints returning small objects do not repay a dependency that can
// break a build the night it is needed.

import java.util.Properties

plugins {
    id("com.android.application") version "8.7.3"
    id("org.jetbrains.kotlin.android") version "2.1.0"
    // Kotlin 2.x moved the Compose compiler into its own plugin.
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"
}

// Where the release key lives, read from a file that is not in git.
//
// The passwords are the reason this is a file and not a constant: this
// repository is public. `keystore.properties` sits beside `local.properties` in
// the root, is gitignored the same way, and points at a keystore under `data/`
// -- which is where every other secret in this project already lives and which
// no server ever receives, because `deploy/lean.sh` carries only tracked
// directories and `data/` is not one.
//
// Absent, the build still configures and `assembleDebug` still works. Only the
// release APK comes out unsigned, which Android refuses to install -- so the
// failure is loud rather than a silently unsigned build handed to somebody.
val signingProperties = Properties().apply {
    val file = rootProject.file("keystore.properties")
    if (file.exists()) {
        file.inputStream().use { load(it) }
    }
}
// Complete, not merely present. A half-filled file would make this true and
// then fail the build on a wrong password, which says nothing about the cause --
// where an absent one says exactly what to do.
val signable = listOf("storeFile", "storePassword", "keyAlias", "keyPassword")
    .all { !signingProperties.getProperty(it).isNullOrBlank() }

android {
    namespace = "ua.hovaysya"
    compileSdk = 35

    defaultConfig {
        applicationId = "ua.hovaysya"
        // 26 is where notification channels and `setBypassDnd` begin, and those
        // are the app: a bell at three in the morning that "не турбувати" does
        // not swallow. Below that there is nothing worth shipping.
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
    }

    if (signable) {
        signingConfigs {
            create("release") {
                storeFile = rootProject.file(
                    signingProperties.getProperty("storeFile"))
                storePassword = signingProperties.getProperty("storePassword")
                keyAlias = signingProperties.getProperty("keyAlias")
                keyPassword = signingProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Null rather than the debug key, deliberately. Signing a release
            // with the debug key would install and would tie the app's identity
            // to a keystore that lives in everybody's home directory -- and the
            // identity is the whole point of signing: it is what lets one build
            // replace another instead of demanding an uninstall.
            signingConfig = if (signable) {
                signingConfigs.getByName("release")
            } else {
                null
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }
}

if (!signable) {
    logger.lifecycle(
        "  Ховайся: keystore.properties немає — release-APK буде без підпису " +
        "і не встановиться. Для debug це не потрібно; див. app/README.md.")
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    val compose = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(compose)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
