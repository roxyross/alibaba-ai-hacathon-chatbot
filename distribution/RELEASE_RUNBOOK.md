# ROXY-AI Multi-Platform Release & Distribution Runbook

## 1. Overview
This Runbook outlines the end-to-end production packaging, code signing, validation, and distribution workflow for Roxy-AI across:
1. **Windows Desktop** (NSIS installer `.exe` & portable)
2. **macOS Desktop** (Universal `.dmg` & hardened `.zip`)
3. **Linux Desktop** (Standalone `.AppImage` & `.deb`)
4. **Android** (Sideloadable `.apk` & Google Play `.aab`)
5. **iOS** (Apple TestFlight & App Store `.ipa` / `.xcarchive`)

---

## 2. Pre-Flight Verification Checklist
Before triggering any distribution build:
- [ ] Backend tests passing (`python -m pytest backend/tests`)
- [ ] Frontend typecheck passing (`npm run typecheck` in `frontend/`)
- [ ] Desktop TypeScript compiling (`npx tsc -p desktop/tsconfig.json`)
- [ ] Backend deployed and verified on Vercel: `https://roxy-personal-ai-backend.vercel.app`
- [ ] Device distribution endpoints responding:
  - `GET /api/v1/devices/updates?platform=windows`
  - `GET /api/v1/devices/updates?platform=macos`
  - `GET /api/v1/devices/updates?platform=android`
  - `GET /api/v1/devices/updates?platform=ios`

---

## 3. Desktop Packaging Workflow

### A. Windows Desktop
```bash
# 1. Build frontend bundle
cd frontend && npm run build && cd ..

# 2. Package Windows installer
cd desktop
npm run build:ts
npx electron-builder --win --x64 --arm64
```
**Output:** `desktop/release/Roxy-AI-Setup-2.0.0.exe`  
**Signing:** In CI/CD, provide `WIN_CSC_LINK` (base64 encoded `.pfx`) and `WIN_CSC_KEY_PASSWORD`.

### B. macOS Desktop
```bash
# Build universal binary on macOS runner
cd desktop
npm run build:ts
npx electron-builder --mac --universal
```
**Output:** `desktop/release/Roxy-AI-2.0.0-universal.dmg`  
**Notarization:** Handled in GitHub Actions via `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, and `APPLE_TEAM_ID`.

### C. Linux Desktop
```bash
cd desktop
npm run build:ts
npx electron-builder --linux AppImage deb
```
**Output:** `desktop/release/Roxy-AI-2.0.0.AppImage`

---

## 4. Android Mobile Packaging Workflow

### A. Generate Release APK & AAB
```bash
# 1. Copy web assets to Android assets folder
mkdir -p android/app/src/main/assets/public
cp -r frontend/dist/* android/app/src/main/assets/public/

# 2. Build release artifacts
cd android
./gradlew assembleRelease bundleRelease
```
**Outputs:**
- Controlled Distribution APK: `android/app/build/outputs/apk/release/app-release.apk`
- Google Play AAB: `android/app/build/outputs/bundle/release/app-release.aab`

### B. Play Console Upload
1. Sign in to Google Play Console.
2. Select **Roxy AI** (`ai.roxy.app`).
3. Under **Production** > **Create new release**, upload `app-release.aab`.
4. Enter release notes from `distribution/store-metadata/google_play_metadata.md`.
5. Complete rollout review.

---

## 5. iOS Mobile Packaging Workflow

### A. Xcode Archive Generation
```bash
# 1. Copy web assets to iOS public bundle
mkdir -p ios/App/App/public
cp -r frontend/dist/* ios/App/App/public/

# 2. Archive using xcodebuild
cd ios/App
xcodebuild clean archive \
  -project App.xcodeproj \
  -scheme App \
  -configuration Release \
  -archivePath build/RoxyAI.xcarchive
```
**Output:** `ios/App/build/RoxyAI.xcarchive`

### B. TestFlight & App Store Submission
```bash
xcodebuild -exportArchive \
  -archivePath build/RoxyAI.xcarchive \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath build/ipa
```
Upload `RoxyAI.ipa` to App Store Connect via Transporter or `xcrun altool`.

---

## 6. Update Manifest & Rollback Strategy
When a new version is released:
1. Update `backend/src/app/device/service.py` in `get_update_manifest()` with the new version string, download URL, and sha256 checksum.
2. If a critical regression is discovered in a release:
   - Set `"mandatory": false` in the update manifest.
   - Point the download URL back to the previous stable release version.
   - Electron desktop and mobile clients gracefully notify users without crashing or force-installing corrupt binaries.

---

## 7. Security Best Practices
- Never commit private `.p12`, `.jks`, `.keystore`, or `.pfx` files to git.
- All signing credentials must be stored as encrypted GitHub repository secrets (`ROXY_KEYSTORE_BASE64`, `WIN_CSC_LINK`, `BUILD_CERTIFICATE_BASE64`).
- No hardcoded API keys exist in client sources — all calls authenticate dynamically using short-lived tokens stored in OS-native secure keychains.
