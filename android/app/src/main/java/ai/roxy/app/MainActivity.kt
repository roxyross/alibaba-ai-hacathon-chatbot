package ai.roxy.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ContentResolver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONObject
import java.util.UUID

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private val channelId = "roxy_reminders_channel"

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val recordAudioGranted = permissions[Manifest.permission.RECORD_AUDIO] ?: false
        val notificationsGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions[Manifest.permission.POST_NOTIFICATIONS] ?: false
        } else {
            true
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setupNotificationChannel()
        requestPlatformPermissions()

        webView = WebView(this)
        setContentView(webView)

        configureWebView()

        handleDeepLink(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleDeepLink(intent)
    }

    private fun configureWebView() {
        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.cacheMode = WebSettings.LOAD_DEFAULT

        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: android.webkit.PermissionRequest?) {
                request?.grant(request.resources)
            }
        }

        webView.webViewClient = WebViewClient()

        // Expose Native Android bridge into Window JavaScript
        webView.addJavascriptInterface(RoxyMobileBridge(this), "RoxyAndroidBridge")

        // Load production web application
        val backendUrl = "https://roxy-personal-ai-backend.vercel.app"
        webView.loadUrl(backendUrl)
    }

    private fun handleDeepLink(intent: Intent?) {
        val data: Uri? = intent?.data
        if (data != null) {
            val deepLinkString = data.toString()
            webView.post {
                val script = "window.dispatchEvent(new CustomEvent('roxy:deepLink', { detail: '$deepLinkString' }));"
                webView.evaluateJavascript(script, null)
            }
        }
    }

    private fun setupNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val name = getString(R.string.notification_channel_name)
            val descriptionText = getString(R.string.notification_channel_description)
            val importance = NotificationManager.IMPORTANCE_HIGH

            val soundUri = Uri.parse(
                "${ContentResolver.SCHEME_ANDROID_RESOURCE}://${packageName}/raw/roxy_reminder"
            )

            val audioAttributes = AudioAttributes.Builder()
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .setUsage(AudioAttributes.USAGE_NOTIFICATION_EVENT)
                .build()

            val channel = NotificationChannel(channelId, name, importance).apply {
                description = descriptionText
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 250, 150, 250)
                setSound(soundUri, audioAttributes)
            }

            val notificationManager: NotificationManager =
                getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun requestPlatformPermissions() {
        val permissionsToRequest = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                permissionsToRequest.add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        requestPermissionLauncher.launch(permissionsToRequest.toTypedArray())
    }

    inner class RoxyMobileBridge(private val context: Context) {

        private val sharedPrefs by lazy {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()

            EncryptedSharedPreferences.create(
                context,
                "roxy_secure_prefs",
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        }

        @JavascriptInterface
        fun getDeviceId(): String {
            var deviceId = sharedPrefs.getString("device_id", null)
            if (deviceId == null) {
                deviceId = "android-${UUID.randomUUID()}"
                sharedPrefs.edit().putString("device_id", deviceId).apply()
            }
            return deviceId
        }

        @JavascriptInterface
        fun getSecureToken(key: String): String? {
            return sharedPrefs.getString(key, null)
        }

        @JavascriptInterface
        fun setSecureToken(key: String, value: String): Boolean {
            sharedPrefs.edit().putString(key, value).apply()
            return true
        }

        @JavascriptInterface
        fun deleteSecureToken(key: String): Boolean {
            sharedPrefs.edit().remove(key).apply()
            return true
        }

        @JavascriptInterface
        fun getPlatformInfo(): String {
            val json = JSONObject()
            json.put("platform", "android")
            json.put("os_version", Build.VERSION.RELEASE)
            json.put("sdk_int", Build.VERSION.SDK_INT)
            json.put("device_model", Build.MODEL)
            json.put("manufacturer", Build.MANUFACTURER)
            return json.toString()
        }
    }
}
