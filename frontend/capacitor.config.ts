import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'ai.roxy.app',
  appName: 'Roxy AI',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    iosScheme: 'roxy',
    allowNavigation: ['roxy-personal-ai-backend.vercel.app', 'api.roxy.ai'],
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
    LocalNotifications: {
      smallIcon: 'ic_launcher',
      iconColor: '#6366f1',
      sound: 'roxy_reminder.wav',
    },
  },
};

export default config;
