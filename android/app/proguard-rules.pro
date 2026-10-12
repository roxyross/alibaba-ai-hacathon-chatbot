# Roxy AI Production Proguard Rules
-keepattributes *Annotation*
-keepattributes JavascriptInterface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class ai.roxy.app.** { *; }
