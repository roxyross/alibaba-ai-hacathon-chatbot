import UIKit
import WebKit
import UserNotifications
import AVFoundation
import Security

@main
class AppDelegate: UIResponder, UIApplicationDelegate, UNUserNotificationCenterDelegate, WKScriptMessageHandler {

    var window: UIWindow?
    var webView: WKWebView?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {

        // Setup Audio Session for Voice Agent
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetooth])
            try session.setActive(true)
        } catch {
            print("Audio session configuration error: \(error)")
        }

        // Setup Push Notifications
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, _ in
            if granted {
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }

        // Initialize Native Web View
        let config = WKWebViewConfiguration()
        let contentController = WKUserContentController()
        contentController.add(self, name: "roxyIOS")
        config.userContentController = contentController

        window = UIWindow(frame: UIScreen.main.bounds)
        let rootVC = UIViewController()
        rootVC.view.backgroundColor = UIColor(red: 10/255, green: 10/255, blue: 15/255, alpha: 1)

        let wv = WKWebView(frame: rootVC.view.bounds, configuration: config)
        wv.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        wv.backgroundColor = .clear
        wv.isOpaque = false

        rootVC.view.addSubview(wv)
        self.webView = wv

        window?.rootViewController = rootVC
        window?.makeKeyAndVisible()

        // Load production URL
        if let url = URL(string: "https://roxy-personal-ai-backend.vercel.app") {
            wv.load(URLRequest(url: url))
        }

        return true
    }

    // -------------------------------------------------------------------------
    // Push Notifications
    // -------------------------------------------------------------------------

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let tokenParts = deviceToken.map { String(format: "%02.2hhx", $0) }
        let token = tokenParts.joined()
        print("APNs Token: \(token)")

        DispatchQueue.main.async {
            let script = "window.dispatchEvent(new CustomEvent('roxy:pushToken', { detail: '\(token)' }));"
            self.webView?.evaluateJavaScript(script, completionHandler: nil)
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge])
    }

    // -------------------------------------------------------------------------
    // Deep Linking: Custom Schemes (roxy://) and Universal Links (https://app.roxy.ai)
    // -------------------------------------------------------------------------

    func application(
        _ app: UIApplication,
        open url: URL,
        options: [UIApplication.OpenURLOptionsKey: Any] = [:]
    ) -> Bool {
        dispatchDeepLink(url.absoluteString)
        return true
    }

    func application(
        _ application: UIApplication,
        continue userActivity: NSUserActivity,
        restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
    ) -> Bool {
        if userActivity.activityType == NSUserActivityTypeBrowsingWeb,
           let webpageURL = userActivity.webpageURL {
            dispatchDeepLink(webpageURL.absoluteString)
            return true
        }
        return false
    }

    private func dispatchDeepLink(_ urlString: String) {
        DispatchQueue.main.async {
            let script = "window.dispatchEvent(new CustomEvent('roxy:deepLink', { detail: '\(urlString)' }));"
            self.webView?.evaluateJavaScript(script, completionHandler: nil)
        }
    }

    // -------------------------------------------------------------------------
    // JavaScript Message Handler (Keychain and Hardware Identity)
    // -------------------------------------------------------------------------

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }

        switch action {
        case "getDeviceId":
            let devId = getOrCreateDeviceId()
            respondToJS(callbackId: body["callbackId"] as? String, result: devId)

        case "getSecureToken":
            let key = body["key"] as? String ?? ""
            let val = readKeychain(key: key)
            respondToJS(callbackId: body["callbackId"] as? String, result: val as Any)

        case "setSecureToken":
            let key = body["key"] as? String ?? ""
            let val = body["value"] as? String ?? ""
            let success = saveKeychain(key: key, value: val)
            respondToJS(callbackId: body["callbackId"] as? String, result: success)

        case "deleteSecureToken":
            let key = body["key"] as? String ?? ""
            let success = deleteKeychain(key: key)
            respondToJS(callbackId: body["callbackId"] as? String, result: success)

        default:
            break
        }
    }

    private func respondToJS(callbackId: String?, result: Any) {
        guard let callbackId = callbackId else { return }
        let jsonStr: String
        if let str = result as? String {
            jsonStr = "\"\(str)\""
        } else if let boolVal = result as? Bool {
            jsonStr = boolVal ? "true" : "false"
        } else {
            jsonStr = "null"
        }
        let script = "window['roxy_callback_\(callbackId)'] && window['roxy_callback_\(callbackId)'](\(jsonStr));"
        DispatchQueue.main.async {
            self.webView?.evaluateJavaScript(script, completionHandler: nil)
        }
    }

    private func getOrCreateDeviceId() -> String {
        if let id = readKeychain(key: "roxy_device_id") {
            return id
        }
        let newId = "ios-\(UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString)"
        _ = saveKeychain(key: "roxy_device_id", value: newId)
        return newId
    }

    // -------------------------------------------------------------------------
    // Keychain Helpers
    // -------------------------------------------------------------------------

    private func saveKeychain(key: String, value: String) -> Bool {
        guard let data = value.data(using: .utf8) else { return false }
        _ = deleteKeychain(key: key)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]
        let status = SecItemAdd(query as CFDictionary, nil)
        return status == errSecSuccess
    }

    private func readKeychain(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func deleteKeychain(key: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key
        ]
        let status = SecItemDelete(query as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }
}
