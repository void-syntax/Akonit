"use client";

import { useEffect, useState } from "react";

export function StatusBar() {
  const [timeStr, setTimeStr] = useState<string>("");

  useEffect(() => {
    function update() {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    }
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <footer className="statusbar" aria-label="Status bar">
      <div className="statusbar-live">
        <span className="statusbar-dot" />
        LIVE FEED ACTIVE
      </div>
      <div className="statusbar-version">
        INTELLIGENCE TERMINAL v2.4 // LAYA AI ENGINE
      </div>
      {timeStr && <div className="statusbar-time">{timeStr} UTC</div>}
    </footer>
  );
}
