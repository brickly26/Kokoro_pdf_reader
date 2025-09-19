import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./screens/Home";
import Reader from "./screens/Reader";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/reader/:id" element={<Reader />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
