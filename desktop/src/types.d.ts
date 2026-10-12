// Ambient type definitions for Electron desktop environment

declare namespace NodeJS {
  interface Process {
    platform: string;
    defaultApp?: boolean;
    argv: string[];
    execPath: string;
    env: Record<string, string | undefined>;
  }
}

declare const process: NodeJS.Process;
declare const __dirname: string;

declare class Buffer {
  static from(data: string, encoding?: string): Buffer;
  toString(encoding?: string): string;
}

declare module 'path' {
  export function join(...paths: string[]): string;
  export function resolve(...paths: string[]): string;
}

declare module 'fs' {
  export function existsSync(path: string): boolean;
  export function mkdirSync(path: string, options?: { recursive?: boolean }): void;
  export function readFileSync(path: string, encoding?: string): any;
  export function writeFileSync(path: string, data: any): void;
}

declare module 'os' {
  export function hostname(): string;
  export function platform(): string;
  export function arch(): string;
  export function cpus(): Array<{ model: string }>;
}

declare module 'crypto' {
  export interface Hash {
    update(data: string): Hash;
    digest(encoding: 'hex'): string;
  }
  export function createHash(algorithm: string): Hash;
}

declare module 'https' {
  export interface IncomingMessage {
    statusCode?: number;
    on(event: 'data', listener: (chunk: any) => void): this;
    on(event: 'end', listener: () => void): this;
  }
  export interface ClientRequest {
    on(event: 'error', listener: (err: any) => void): this;
  }
  export function get(url: string, callback: (res: IncomingMessage) => void): ClientRequest;
}

declare module 'electron' {
  export interface IpcRendererEvent {}

  export const app: {
    requestSingleInstanceLock(): boolean;
    quit(): void;
    on(event: string, listener: (...args: any[]) => void): void;
    setAsDefaultProtocolClient(protocol: string, path?: string, args?: string[]): boolean;
    getPath(name: string): string;
    whenReady(): Promise<void>;
  };

  export interface WebContents {
    send(channel: string, ...args: any[]): void;
    on(event: string, listener: (...args: any[]) => void): void;
  }

  export class BrowserWindow {
    constructor(options?: any);
    webContents: WebContents;
    show(): void;
    hide(): void;
    focus(): void;
    isMinimized(): boolean;
    restore(): void;
    loadURL(url: string): Promise<void>;
    loadFile(filePath: string): Promise<void>;
    reload(): void;
    on(event: string, listener: (...args: any[]) => void): void;
    once(event: string, listener: (...args: any[]) => void): void;
    static getAllWindows(): BrowserWindow[];
  }

  export const ipcMain: {
    handle(channel: string, listener: (event: any, ...args: any[]) => any): void;
  };

  export const ipcRenderer: {
    invoke(channel: string, ...args: any[]): Promise<any>;
    on(channel: string, listener: (event: any, ...args: any[]) => void): void;
    removeListener(channel: string, listener: (...args: any[]) => void): void;
  };

  export const safeStorage: {
    isEncryptionAvailable(): boolean;
    encryptString(plainText: string): any;
    decryptString(encrypted: any): string;
  };

  export class Notification {
    constructor(options?: any);
    static isSupported(): boolean;
    show(): void;
  }

  export class Tray {
    constructor(image: any);
    setToolTip(toolTip: string): void;
    setContextMenu(menu: any): void;
    on(event: string, listener: (...args: any[]) => void): void;
  }

  export const Menu: {
    buildFromTemplate(template: any[]): any;
  };

  export const shell: {
    openExternal(url: string): Promise<void>;
  };

  export const nativeImage: {
    createFromPath(path: string): any;
  };

  export const contextBridge: {
    exposeInMainWorld(apiKey: string, api: any): void;
  };

  export const dialog: {
    showMessageBox(browserWindow: any, options: any): Promise<{ response: number }>;
  };
}

declare module 'electron-updater' {
  export const autoUpdater: {
    autoDownload: boolean;
    autoInstallOnAppQuit: boolean;
    on(event: string, listener: (...args: any[]) => void): void;
    downloadUpdate(): Promise<any>;
    quitAndInstall(): void;
  };
}
