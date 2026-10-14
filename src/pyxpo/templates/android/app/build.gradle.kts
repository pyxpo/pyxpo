plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "dev.pyxpo.runtime"
    compileSdk = 35
    ndkVersion = "27.3.13750724"
    defaultConfig {
        applicationId = "{{app_id}}"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        ndk { abiFilters += listOf({{abis}}) }
        externalNativeBuild {
            cmake { arguments("-DPYXPO_DIST={{dist}}", "-DPYXPO_NATIVE_COMMON={{common}}") }
        }
    }
    externalNativeBuild { cmake { path = file("src/main/cpp/CMakeLists.txt") } }
    sourceSets["main"].jniLibs.srcDir("{{dist_jnilibs}}")
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
