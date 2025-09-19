import { ipcRenderer } from "electron";

// With contextIsolation=false, directly assign to window
window.api = {
  openPDF: async () => await ipcRenderer.invoke("dialog:openPDF"),
};
