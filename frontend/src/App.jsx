/**
 * App.jsx — Root application component.
 *
 * FIXES APPLIED:
 *  1. Added BrowserRouter wrapper (previously missing → entire app was blank)
 *  2. Added Routes + Route definitions for all 5 pages
 *  3. Layout uses <Outlet /> from react-router-dom, so all pages now render
 */

import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout     from "@/components/layout/Layout";
import Dashboard  from "@/pages/Dashboard";
import Reports    from "@/pages/Reports";
import Analytics  from "@/pages/Analytics";
import AuditLogs  from "@/pages/AuditLogs";
import Settings   from "@/pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Layout wraps every page — Sidebar + Topbar + <Outlet /> */}
        <Route element={<Layout />}>
          <Route index          element={<Dashboard />} />
          <Route path="/reports"   element={<Reports />}   />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/logs"      element={<AuditLogs />} />
          <Route path="/settings"  element={<Settings />}  />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
