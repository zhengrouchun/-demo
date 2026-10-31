import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import GrowMateApp from "./growmate/GrowMateApp";
import DesktopPet from "./components/DesktopPet/DesktopPet";

// Keep the existing MeetingBro UI available for its original backend.
const legacy = Boolean(window.meetingbro) || new URLSearchParams(window.location.search).has("legacy");
if (legacy) { void import("./App.css"); document.title = "MeetingBro"; }

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {legacy ? <App /> : <><GrowMateApp /><DesktopPet /></>}
  </React.StrictMode>,
);
