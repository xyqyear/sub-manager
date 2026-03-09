import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ErrorBoundary } from "react-error-boundary";
import { getAdminToken } from "@/utils/api";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { SiteHeader } from "@/components/site-header";
import LoginPage from "@/pages/Login";
import SubscriptionsPage from "@/pages/Subscriptions";
import RulesPage from "@/pages/Rules";
import RouteTemplatesPage from "@/pages/RouteTemplates";
import MainConfigsPage from "@/pages/MainConfigs";

function isLoggedIn(): boolean {
  return getAdminToken().trim().length > 0;
}

const routeTitles: Record<string, string> = {
  "/subscriptions": "Subscriptions",
  "/rules": "Rules",
  "/routes": "Route Templates",
  "/configs": "Configs",
};

function ErrorFallback() {
  return (
    <div className="flex items-center justify-center h-screen text-destructive">
      Application error. Please refresh the page.
    </div>
  );
}

function ProtectedAppLayout() {
  const location = useLocation();

  if (!isLoggedIn()) {
    return <Navigate to="/login" replace />;
  }

  const title = routeTitles[location.pathname] || "Sub Manager";

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <SiteHeader title={title} />
        <div className="flex-1 p-3 md:p-6">
          <Routes>
            <Route path="/subscriptions" element={<SubscriptionsPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/routes" element={<RouteTemplatesPage />} />
            <Route path="/configs" element={<MainConfigsPage />} />
            <Route path="*" element={<Navigate to="/subscriptions" replace />} />
          </Routes>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

export default function App() {
  return (
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <Routes>
        <Route
          path="/login"
          element={isLoggedIn() ? <Navigate to="/subscriptions" replace /> : <LoginPage />}
        />
        <Route path="/*" element={<ProtectedAppLayout />} />
      </Routes>
    </ErrorBoundary>
  );
}
