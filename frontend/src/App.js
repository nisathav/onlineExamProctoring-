import { useEffect } from "react";
import { Link, Redirect, Route, Switch, useLocation } from "wouter";
import ExamList from "./components/ExamList";
import ExamSitting from "./components/ExamSitting";
import Login from "./components/Login";
import IncidentReview from "./components/proctor/IncidentReview";
import ProctorDashboard from "./components/proctor/ProctorDashboard";
import { getUser, logout, setUnauthorizedHandler } from "./services/api";

function Guard({ role, children }) {
  const user = getUser();
  if (!user) return <Redirect to="/login" />;
  if (role && user.role !== role) return <Redirect to={user.role === "staff" ? "/proctor" : "/exams"} />;
  return children;
}

function Header() {
  const [, navigate] = useLocation();
  const user = getUser();
  if (!user) return null;
  return (
    <header className="topbar">
      <span>Online Proctoring</span>
      <span>
        {user.username} ({user.role}){" "}
        <button className="link" onClick={() => { logout(); navigate("/login"); }}>Log out</button>
      </span>
    </header>
  );
}

export default function App() {
  const [, navigate] = useLocation();
  useEffect(() => setUnauthorizedHandler(() => navigate("/login")), [navigate]);

  return (
    <>
      <Header />
      <Switch>
        <Route path="/login" component={Login} />
        <Route path="/exams">
          <Guard role="student"><ExamList /></Guard>
        </Route>
        <Route path="/exam/:id">
          {(params) => <Guard role="student"><ExamSitting id={params.id} /></Guard>}
        </Route>
        <Route path="/proctor">
          <Guard role="staff"><ProctorDashboard /></Guard>
        </Route>
        <Route path="/proctor/exams/:examId/students/:studentId">
          {(params) => (
            <Guard role="staff"><IncidentReview examId={params.examId} studentId={params.studentId} /></Guard>
          )}
        </Route>
        <Route>
          <main className="card narrow">
            <p>Page not found.</p>
            <Link href="/login">Go to sign in</Link>
          </main>
        </Route>
      </Switch>
    </>
  );
}
