// This file is yours: edit it freely (it is never overwritten by `pyxpo build`).
// App id, version, ABIs and signing come from [tool.pyxpo] through pyxpo-gen/pyxpo.properties.
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val px = Properties().apply {
    val f = rootProject.file("pyxpo-gen/pyxpo.properties")
    if (!f.exists()) throw GradleException("pyxpo-gen/pyxpo.properties is missing: run `pyxpo build android` (or `pyxpo prebuild android`) first")
    f.inputStream().use { load(it) }
}

android {
    namespace = "dev.pyxpo.runtime"
    compileSdk = 35
    ndkVersion = "27.3.13750724"
    defaultConfig {
        applicationId = px.getProperty("applicationId")
        minSdk = 24
        targetSdk = 35
        versionCode = px.getProperty("versionCode").toInt()
        versionName = px.getProperty("versionName")
        ndk { abiFilters += px.getProperty("abis").split(",") }
        manifestPlaceholders["pyxpoName"] = px.getProperty("name")
        manifestPlaceholders["pyxpoScheme"] = px.getProperty("scheme")
        externalNativeBuild {
            cmake { arguments("-DPYXPO_DIST=" + px.getProperty("dist"), "-DPYXPO_NATIVE_COMMON=" + px.getProperty("common")) }
        }
    }
    externalNativeBuild { cmake { path = file("../pyxpo-gen/cpp/CMakeLists.txt") } }
    sourceSets["main"].java.srcDir("../pyxpo-gen/runtime/java")
    sourceSets["main"].assets.srcDir("../pyxpo-gen/assets")
    sourceSets["main"].jniLibs.srcDir("../pyxpo-gen/jniLibs")
    signingConfigs {
        if (px.containsKey("keystore")) {
            create("pyxpo") {
                storeFile = file(px.getProperty("keystore"))
                storePassword = System.getenv("PYXPO_KEYSTORE_PASSWORD")
                keyAlias = px.getProperty("keyAlias")
                keyPassword = System.getenv("PYXPO_KEY_PASSWORD") ?: System.getenv("PYXPO_KEYSTORE_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            // Without a keystore in [tool.pyxpo.android] the release APK is signed with the debug key (as in
            // React Native) so it installs on a phone. Set a keystore before uploading to Google Play.
            signingConfig = signingConfigs.getByName(if (px.containsKey("keystore")) "pyxpo" else "debug")
        }
    }
    packaging {
        // CPython loads extension modules from the extracted dir via dlopen; keep libs uncompressed + extracted
        jniLibs { useLegacyPackaging = true }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

// Native modules listed in [tool.pyxpo] modules are linked by pyxpo (regenerated on every build).
apply(from = "../pyxpo-gen/modules.app.gradle.kts")

// `./gradlew assembleDebug|assembleRelease` and Android Studio stage the Python app first, like `pyxpo build android`.
// The interpreter is the one that ran `pyxpo prebuild`; set PYXPO_PYTHON to use another. `pyxpo build` stages
// before calling Gradle and sets PYXPO_STAGED, so the task skips itself there.
for (variant in listOf("Debug", "Release")) {
    val stage = tasks.register<Exec>("pyxpoStage$variant") {
        onlyIf { System.getenv("PYXPO_STAGED") == null }
        workingDir = rootProject.projectDir.parentFile
        val python = System.getenv("PYXPO_PYTHON") ?: px.getProperty("python") ?: "python3"
        commandLine(listOf(python, "-m", "pyxpo", "stage", "android") + if (variant == "Release") listOf("--release") else emptyList())
    }
    tasks.matching { it.name == "pre${variant}Build" }.configureEach { dependsOn(stage) }
}
