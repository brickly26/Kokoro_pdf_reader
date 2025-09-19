import { app, BrowserWindow, ipcMain, dialog } from "electron";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const isDev =
  process.env.VITE_DEV_SERVER_URL || process.env.NODE_ENV === "development";

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    titleBarStyle: "hiddenInset",
    backgroundColor: "#0b0b0c",
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  // Expose dialog API directly to the renderer
  mainWindow.webContents.once("dom-ready", () => {
    mainWindow.webContents
      .executeJavaScript(
        `
      window.electronAPI = {
        openPDF: async () => {
          try {
            const { ipcRenderer } = require('electron');
            const result = await ipcRenderer.invoke('dialog:openPDF');
            return result;
          } catch (error) {
            console.error('Failed to open PDF dialog:', error);
            return null;
          }
        }
      };
    `
      )
      .catch((err) => {
        console.error("Failed to inject electronAPI:", err);
      });
  });

  if (isDev && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/dist/index.html"));
  }
}

app.whenReady().then(() => {
  ipcMain.handle("dialog:openPDF", async () => {
    try {
      const result = await dialog.showOpenDialog(mainWindow, {
        properties: ["openFile"],
        filters: [{ name: "PDF", extensions: ["pdf"] }],
      });

      if (
        result.canceled ||
        !result.filePaths ||
        result.filePaths.length === 0
      ) {
        return null;
      }

      return result.filePaths[0];
    } catch (error) {
      console.error("Error in dialog:openPDF handler:", error);
      return null;
    }
  });

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
