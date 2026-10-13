export interface CapacitorConfig {
  appId: string;
  appName: string;
  webDir: string;
  server?: {
    androidScheme?: string;
    iosScheme?: string;
    allowNavigation?: string[];
    [key: string]: any;
  };
  plugins?: {
    PushNotifications?: {
      presentationOptions?: string[];
    };
    LocalNotifications?: {
      smallIcon?: string;
      iconColor?: string;
      sound?: string;
    };
    [key: string]: any;
  };
  [key: string]: any;
}

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
