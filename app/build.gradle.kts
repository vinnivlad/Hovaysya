// The whole build. Compose and AndroidX, and nothing else -- no HTTP client, no
// JSON library, no dependency injection.
//
// That is the same choice the backend made and for the same reason: this has to
// still build in a year, on a machine nobody has prepared, at a moment when
// something is wrong. `HttpURLConnection` and `org.json` are in the platform.
// Four endpoints returning small objects do not repay a dependency that can
// break a build the night it is needed.

plugins {
    id("com.android.application") version "8.7.3"
    id("org.jetbrains.kotlin.android") version "2.1.0"
    // Kotlin 2.x moved the Compose compiler into its own plugin.
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"
}

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

    buildTypes {
        release {
            isMinifyEnabled = false
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
