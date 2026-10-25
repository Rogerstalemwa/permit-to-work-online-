import type { CapacitorConfig } from '@capacitor/cli';

/*
 * DEMO SETUP:
 * 1. Start the Django server on your laptop using the root run.bat file.
 * 2. Find the laptop's IPv4 address on the same Wi-Fi network (ipconfig).
 * 3. Replace 192.168.1.100 below with that address.
 * 4. Keep the :8000 port. Both phone and laptop must be on the same Wi-Fi.
 *
 * This URL is for local demonstration only. Do not use plain HTTP for production.
 */
const config: CapacitorConfig = {
  appId: 'ug.co.demo.digitalworkpermit',
  appName: 'Digital Work Permit',
  webDir: 'www',
  server: {
    url: 'http://192.168.1.100:8000',
    cleartext: true,
    androidScheme: 'http'
  },
  android: {
    allowMixedContent: false
  }
};

export default config;
