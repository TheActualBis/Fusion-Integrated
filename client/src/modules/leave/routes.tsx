import { Navigate, type RouteObject } from "react-router-dom";
import LeavePage from "./pages/LeavePage";

export const routes: RouteObject[] = [
  { index: true, element: <Navigate to="mine" replace /> },
  { path: "mine", element: <LeavePage mode="mine" /> },
  { path: "tasks", element: <LeavePage mode="tasks" /> },
  { path: "requests", element: <LeavePage mode="requests" /> },
  { path: "settings", element: <LeavePage mode="settings" /> },
];
