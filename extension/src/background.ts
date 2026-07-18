import { registerBackgroundListener } from "./background-listener";

void chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
registerBackgroundListener();
