# Android APK wrapper (demo setup)

This folder is the starting point for packaging the existing Django-served interface as an Android app. It reuses the existing backend and database; it is not a second permit system.

## Requirements on the Windows build computer

- Node.js and npm
- Android Studio with Android SDK installed
- A compatible JDK (use the version required by the installed Android Gradle plugin)
- The Django project dependencies installed from the root `requirements.txt`

## Build the APK

1. Start the Django app from the project root with `run.bat`.
2. Run `ipconfig` and note the laptop's Wi-Fi IPv4 address.
3. Edit `capacitor.config.ts` and replace `192.168.1.100` with the laptop's IPv4 address. Keep port `8000`.
4. Connect the phone and laptop to the same Wi-Fi. On the phone's browser, test `http://LAPTOP-IP:8000` first. If it cannot open, check Windows Firewall and the network.
5. Open a terminal in this folder and run:
   - `npm install`
   - `npx cap add android` (first time only)
   - `npx cap sync android`
   - `npx cap open android`
6. In Android Studio, allow Gradle sync to finish, then choose **Build > Build Bundle(s) / APK(s) > Build APK(s)**.
7. Install the debug APK on the phone and keep the Django server running during the demonstration.

The generated APK is normally at `android/app/build/outputs/apk/debug/app-debug.apk`.

## Demo limitations and safety

- This configuration uses plain HTTP on a trusted local Wi-Fi network for a demonstration only. Do not expose this setup directly to the public internet or use real confidential permit data.
- The phone is a client. The Django server and its database remain on the laptop.
- If the laptop IP changes, update the URL and rebuild/sync the app.
- The APK has not been built in the current environment; Android Studio/SDK and dependency installation are required to complete that step.
