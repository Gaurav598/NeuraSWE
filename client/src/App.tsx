import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { DashboardHome } from "./pages/DashboardHome";
import { RunsList } from "./pages/RunsList";
import { RunDetail } from "./pages/RunDetail";
import { Repositories } from "./pages/Repositories";
import { Analytics } from "./pages/Analytics";
import { Issues } from "./pages/Issues";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardHome />} />
        <Route path="/runs" element={<RunsList />} />
        <Route path="/runs/:id" element={<RunDetail />} />
        <Route path="/issues" element={<Issues />} />
        <Route path="/repositories" element={<Repositories />} />
        <Route path="/analytics" element={<Analytics />} />
      </Routes>
    </Layout>
  );
}
