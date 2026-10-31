import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import GrowMateApp from "./growmate/GrowMateApp";
import DesktopPet from "./components/DesktopPet/DesktopPet";

// Keep the existing MeetingBro UI available for its original backend.
const legacy = Boolean(window.meetingbro) || new URLSearchParams(window.location.search).has("legacy");
const transcriptOnly = new URLSearchParams(window.location.search).has("transcript");
if (legacy) { void import("./App.css"); document.title = "MeetingBro"; }
else if (transcriptOnly) { document.title = "课堂系统声音转文字"; }

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {legacy ? <App /> : transcriptOnly ? <GrowMateApp transcriptOnly /> : <><GrowMateApp /><DesktopPet /></>}
  </React.StrictMode>,
);
