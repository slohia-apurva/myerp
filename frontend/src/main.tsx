import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { followLinksHere } from "./Master";
import { labelTablesOnPhones } from "./PhoneTables";

followLinksHere();
labelTablesOnPhones();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
